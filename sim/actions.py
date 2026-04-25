from __future__ import annotations

from dataclasses import dataclass
import uuid

from .memory import MemoryStore
from .relationships import RelationshipGraph
from .world import AgentState, AllianceOffer, ProjectState, TradeOffer, WorldEvent, WorldState


@dataclass
class ActionResult:
    success: bool
    message: str
    public_event: WorldEvent | None = None


class ActionResolver:
    def __init__(self, world: WorldState, memory_store: MemoryStore, relationships: RelationshipGraph):
        self.world = world
        self.memory_store = memory_store
        self.relationships = relationships

    def apply(self, agent: AgentState, tool_name: str, args: dict) -> ActionResult:
        handler = getattr(self, f"_handle_{tool_name}", None)
        if handler is None:
            return ActionResult(False, f"Unknown action: {tool_name}")
        return handler(agent, args)

    def _remember(self, agent_name: str, summary: str, salience: int = 1, tags: list[str] | None = None) -> None:
        self.memory_store.get(agent_name).remember(
            tick=self.world.tick_count,
            day=self.world.day,
            summary=summary,
            salience=salience,
            tags=tags,
        )

    def _record_event(
        self,
        *,
        kind: str,
        actor: str,
        summary: str,
        location: tuple[int, int] | None,
        target: str | None = None,
        public: bool = True,
        metadata: dict | None = None,
    ) -> WorldEvent:
        event = WorldEvent(
            tick=self.world.tick_count,
            day=self.world.day,
            time_of_day=self.world.time_of_day,
            kind=kind,
            actor=actor,
            summary=summary,
            location=location,
            target=target,
            public=public,
            metadata=metadata or {},
        )
        self.world.recent_events.append(event)
        self.world.recent_events = self.world.recent_events[-200:]
        return event

    def _parse_position(self, raw: str) -> tuple[int, int] | None:
        if "," not in raw:
            return None
        left, right = raw.split(",", 1)
        try:
            return int(left.strip()), int(right.strip())
        except ValueError:
            return None

    def _validate_adjacent_tile(self, agent: AgentState, position: tuple[int, int], kind: str) -> str | None:
        if not self.world.in_bounds(position):
            return "Tile is outside the world."
        if position != agent.position and not self.world.is_adjacent(agent.position, position):
            return "Tile is not at or adjacent to your position."
        if self.world.tile_at(position).kind != kind:
            return f"Tile is not a {kind} tile."
        return None

    def _inventory_has(self, inventory: dict[str, int], payload: dict[str, int]) -> bool:
        return all(inventory.get(item, 0) >= quantity for item, quantity in payload.items())

    def _transfer(self, source: dict[str, int], dest: dict[str, int], payload: dict[str, int]) -> None:
        for item, quantity in payload.items():
            source[item] = source.get(item, 0) - quantity
            dest[item] = dest.get(item, 0) + quantity

    def _nearby_helpers(self, agent: AgentState, radius: int = 2) -> list[AgentState]:
        helpers: list[AgentState] = []
        for other in self.world.agents.values():
            if other.name == agent.name or other.is_sleeping:
                continue
            distance = abs(other.position[0] - agent.position[0]) + abs(other.position[1] - agent.position[1])
            if distance <= radius:
                helpers.append(other)
        return helpers

    def _nearby_allies(self, agent: AgentState, radius: int = 2) -> list[AgentState]:
        return [
            other
            for other in self._nearby_helpers(agent, radius=radius)
            if self.relationships.are_allies(agent.name, other.name)
        ]

    def _at_or_adjacent(self, first: tuple[int, int], second: tuple[int, int]) -> bool:
        return first == second or self.world.is_adjacent(first, second)

    def _market_trade_bonus_active(self, location: tuple[int, int]) -> bool:
        plaza = self.world.landmarks.get("village_plaza")
        return self.world.is_market_active() and plaza is not None and self._at_or_adjacent(location, plaza)

    def _near_well(self, location: tuple[int, int]) -> bool:
        well = self.world.landmarks.get("well")
        return well is not None and self._at_or_adjacent(location, well)

    def _near_hearth(self, location: tuple[int, int]) -> bool:
        hearth = self.world.landmarks.get("community_hearth")
        return hearth is not None and self._at_or_adjacent(location, hearth)

    def _house_visit_bonus(self, giver: AgentState, receiver: AgentState) -> bool:
        return giver.position == receiver.house_position or receiver.position == receiver.house_position

    def _boost_village_morale(self, amount: float) -> None:
        self.world.village_morale = min(12.0, self.world.village_morale + amount)

    def _boost_village_food(self, amount: float) -> None:
        self.world.village_food = min(12.0, self.world.village_food + amount)

    def _boost_village_warmth(self, amount: float) -> None:
        self.world.village_warmth = min(12.0, self.world.village_warmth + amount)

    def _handle_wait(self, agent: AgentState, args: dict) -> ActionResult:
        agent.current_action = "waiting"
        event = self._record_event(
            kind="wait",
            actor=agent.name,
            summary=f"{agent.name} waits and observes.",
            location=agent.position,
            public=False,
        )
        self._remember(agent.name, "I paused to observe the village.", 1, ["wait"])
        return ActionResult(True, "You waited this tick.", event)

    def _handle_move(self, agent: AgentState, args: dict) -> ActionResult:
        target = args["target"]
        agent.current_action = "moving"
        agent.move_target_label = target
        event = self._record_event(
            kind="move",
            actor=agent.name,
            summary=f"{agent.name} started moving toward {target}.",
            location=agent.position,
            public=True,
        )
        self._remember(agent.name, f"I decided to move toward {target}.", 1, ["move"])
        return ActionResult(True, f"Moving toward {target}.", event)

    def _handle_speak(self, agent: AgentState, args: dict) -> ActionResult:
        message = args["message"].strip()[:90]
        target = args["target"].strip()
        heard_by: list[AgentState] = []
        if target.lower() in {"everyone", "nearby", "all"}:
            for other in self.world.agents.values():
                if other.name == agent.name:
                    continue
                distance = abs(other.position[0] - agent.position[0]) + abs(other.position[1] - agent.position[1])
                if distance <= 3:
                    heard_by.append(other)
        elif target in self.world.agents:
            if not self.world.is_adjacent(agent.position, self.world.agents[target].position):
                return ActionResult(False, f"{target} is not adjacent, so they cannot hear you clearly.")
            heard_by.append(self.world.agents[target])
        agent.current_action = "speaking"
        agent.speech_bubble = message
        agent.last_social_tick = self.world.tick_count
        if self._market_trade_bonus_active(agent.position):
            self._boost_village_morale(0.25)
        event = self._record_event(
            kind="speak",
            actor=agent.name,
            target=target,
            summary=f'{agent.name} says to {target}: "{message}"',
            location=agent.position,
            public=True,
        )
        self._remember(agent.name, f'I said "{message}" to {target}.', 2, ["speak"])
        for listener in heard_by:
            listener.last_social_tick = self.world.tick_count
            self.relationships.record(agent.name, listener.name, self.world.day, 0.05, f'Spoke: "{message}"')
            self._remember(listener.name, f'{agent.name} said "{message}" nearby.', 2, ["heard"])
        return ActionResult(True, f'You said "{message}".', event)

    def _handle_give_gift(self, agent: AgentState, args: dict) -> ActionResult:
        target_name = args["target_agent"]
        target = self.world.agents.get(target_name)
        if target is None:
            return ActionResult(False, f"Unknown target agent: {target_name}")
        if not self.world.is_adjacent(agent.position, target.position):
            return ActionResult(False, f"{target_name} is not adjacent.")
        item = args["item"]
        quantity = max(1, int(args["quantity"]))
        if agent.inventory.get(item, 0) < quantity:
            return ActionResult(False, f"You do not have enough {item}.")
        agent.inventory[item] -= quantity
        target.inventory[item] = target.inventory.get(item, 0) + quantity
        visit_bonus = self._house_visit_bonus(agent, target)
        trust_note = f"{agent.name} gave {target_name} {quantity} {item}"
        favor_delta = 0.6 + (0.25 if item in {"flowers", "meal"} else 0.0) + (0.25 if visit_bonus else 0.0)
        self.relationships.record_gift(agent.name, target_name, self.world.day, trust_note, favor_delta=favor_delta)
        if item == "meal":
            target.energy = min(1.0, target.energy + 0.08)
            target.comfort_ticks = min(target.comfort_ticks + 4, 16)
            self._boost_village_morale(0.08)
        elif item == "flowers":
            target.comfort_ticks = min(target.comfort_ticks + 3, 16)
            self._boost_village_morale(0.12)
        else:
            target.comfort_ticks = min(target.comfort_ticks + 2, 16)
        if visit_bonus:
            target.energy = min(1.0, target.energy + 0.04)
            agent.comfort_ticks = min(agent.comfort_ticks + 2, 16)
        agent.current_action = "gifting"
        target.last_social_tick = self.world.tick_count
        agent.last_social_tick = self.world.tick_count
        summary = f"{agent.name} brought {target_name} a gift of {quantity} {item}."
        if visit_bonus:
            summary = f"{agent.name} visited {target_name}'s home and brought a gift of {quantity} {item}."
        event = self._record_event(
            kind="give_gift",
            actor=agent.name,
            target=target_name,
            summary=summary,
            location=agent.position,
            public=True,
            metadata={"item": item, "quantity": quantity},
        )
        self._remember(agent.name, f"I gave {target_name} a gift of {quantity} {item}.", 4, ["gift", "social"])
        self._remember(target_name, f"{agent.name} gave me a gift of {quantity} {item}.", 4, ["gift", "social"])
        return ActionResult(True, f"You gave {target_name} a gift of {quantity} {item}.", event)

    def _handle_propose_alliance(self, agent: AgentState, args: dict) -> ActionResult:
        target_name = args["target_agent"]
        target = self.world.agents.get(target_name)
        if target is None:
            return ActionResult(False, f"Unknown target agent: {target_name}")
        if not self.world.is_adjacent(agent.position, target.position):
            return ActionResult(False, f"{target_name} is not adjacent.")
        if self.relationships.are_allies(agent.name, target_name):
            return ActionResult(False, f"You are already allied with {target_name}.")
        proposal = AllianceOffer(
            proposal_id=str(uuid.uuid4())[:8],
            from_agent=agent.name,
            to_agent=target_name,
            message=args["message"][:90],
            created_tick=self.world.tick_count,
            expires_tick=self.world.tick_count + 8,
        )
        self.world.pending_alliances[proposal.proposal_id] = proposal
        agent.current_action = "allying"
        agent.last_social_tick = self.world.tick_count
        target.last_social_tick = self.world.tick_count
        event = self._record_event(
            kind="alliance_offer",
            actor=agent.name,
            target=target_name,
            summary=f"{agent.name} proposed an alliance to {target_name}.",
            location=agent.position,
            public=True,
            metadata={"proposal_id": proposal.proposal_id},
        )
        self._remember(agent.name, f"I proposed an alliance to {target_name}.", 4, ["alliance", "social"])
        self._remember(target_name, f"{agent.name} proposed an alliance to me.", 4, ["alliance", "social"])
        return ActionResult(True, f"Alliance proposal {proposal.proposal_id} created.", event)

    def _handle_farm(self, agent: AgentState, args: dict) -> ActionResult:
        position = self._parse_position(args["tile_position"])
        if position is None:
            return ActionResult(False, "Invalid tile_position format.")
        error = self._validate_adjacent_tile(agent, position, "farm")
        if error:
            return ActionResult(False, error)
        tile = self.world.tile_at(position)
        action = args["action"]
        if action == "plant":
            if tile.crop_stage != "empty":
                return ActionResult(False, "That farm tile is already in use.")
            if agent.inventory.get("wheat", 0) <= 0:
                return ActionResult(False, "You need wheat to plant.")
            agent.inventory["wheat"] -= 1
            tile.crop_stage = "growing"
            tile.crop_progress = 0.0
            agent.current_action = "farming"
            event = self._record_event(
                kind="farm_plant",
                actor=agent.name,
                summary=f"{agent.name} planted wheat at {position}.",
                location=position,
            )
            if tile.crop_owner is None:
                self._boost_village_morale(0.05)
            self._remember(agent.name, f"I planted wheat at {position}.", 2, ["farm"])
            return ActionResult(True, "You planted wheat.", event)
        if action == "harvest":
            if tile.crop_stage != "ripe":
                return ActionResult(False, "That crop is not ready to harvest.")
            tile.crop_stage = "empty"
            tile.crop_progress = 0.0
            harvest_yield = 3
            if tile.crop_owner is None and self.world.public_projects.get("granary", ProjectState("", "", (0, 0), {}, {}, "", "")).completed:
                harvest_yield += 1
            helpers = self._nearby_helpers(agent)
            allies = self._nearby_allies(agent)
            if helpers:
                harvest_yield += 1
            if allies:
                harvest_yield += 1
                agent.comfort_ticks = min(agent.comfort_ticks + 2, 16)
            agent.inventory["wheat"] = agent.inventory.get("wheat", 0) + harvest_yield
            agent.current_action = "farming"
            event = self._record_event(
                kind="farm_harvest",
                actor=agent.name,
                summary=f"{agent.name} harvested wheat at {position}.",
                location=position,
            )
            if tile.crop_owner is None:
                self._boost_village_food(0.8)
                self._boost_village_morale(0.1)
            memory_text = f"I harvested wheat at {position}."
            if helpers:
                helper_names = ", ".join(other.name for other in helpers[:2])
                memory_text = f"I harvested wheat at {position}, and working near {helper_names} made it unusually productive."
            self._remember(agent.name, memory_text, 3, ["farm"])
            return ActionResult(True, f"You harvested {harvest_yield} wheat.", event)
        return ActionResult(False, f"Unsupported farm action: {action}")

    def _handle_chop_wood(self, agent: AgentState, args: dict) -> ActionResult:
        position = self._parse_position(args["tile_position"])
        if position is None:
            return ActionResult(False, "Invalid tile_position format.")
        error = self._validate_adjacent_tile(agent, position, "forest")
        if error:
            return ActionResult(False, error)
        tile = self.world.tile_at(position)
        if tile.wood <= 0:
            return ActionResult(False, "That forest tile has no wood left.")
        tile.wood -= 1
        wood_yield = 2
        helpers = self._nearby_helpers(agent)
        allies = self._nearby_allies(agent)
        if helpers:
            wood_yield += 1
            agent.comfort_ticks = min(agent.comfort_ticks + 2, 12)
            for helper in helpers[:2]:
                helper.energy = min(1.0, helper.energy + 0.02)
        if allies:
            wood_yield += 1
            agent.energy = min(1.0, agent.energy + 0.03)
        agent.inventory["wood"] = agent.inventory.get("wood", 0) + wood_yield
        agent.current_action = "chopping"
        event = self._record_event(
            kind="chop_wood",
            actor=agent.name,
            summary=f"{agent.name} chopped wood at {position}.",
            location=position,
        )
        memory_text = f"I chopped wood at {position}."
        message = f"You chopped {wood_yield} wood."
        if helpers:
            helper_names = ", ".join(other.name for other in helpers[:2])
            memory_text = f"I chopped wood at {position}, and working near {helper_names} made the job noticeably faster."
            message = f"You chopped {wood_yield} wood, and teamwork made it easier."
            self._boost_village_morale(0.08)
        self._remember(agent.name, memory_text, 3, ["wood"])
        return ActionResult(True, message, event)

    def _handle_forage(self, agent: AgentState, args: dict) -> ActionResult:
        position = self._parse_position(args["tile_position"])
        if position is None:
            return ActionResult(False, "Invalid tile_position format.")
        error = self._validate_adjacent_tile(agent, position, "berry_grove")
        if error:
            return ActionResult(False, error)
        tile = self.world.tile_at(position)
        if tile.berries <= 0:
            return ActionResult(False, "That berry grove has been picked clean for now.")
        tile.berries -= 1
        berry_yield = 2
        helpers = self._nearby_helpers(agent)
        allies = self._nearby_allies(agent)
        if helpers:
            berry_yield += 1
            self._boost_village_morale(0.05)
        if allies:
            berry_yield += 1
        agent.inventory["berries"] = agent.inventory.get("berries", 0) + berry_yield
        agent.energy = min(1.0, agent.energy + 0.08)
        self._boost_village_food(0.35)
        agent.current_action = "foraging"
        event = self._record_event(
            kind="forage",
            actor=agent.name,
            summary=f"{agent.name} foraged berries at {position}.",
            location=position,
        )
        memory_text = f"I foraged berries at {position} and got a quick lift from the fresh food."
        if helpers:
            helper_names = ", ".join(other.name for other in helpers[:2])
            memory_text = f"I foraged berries at {position} with {helper_names} nearby, and the shared outing was unusually fruitful."
        self._remember(agent.name, memory_text, 3, ["forage", "food"])
        return ActionResult(True, f"You gathered {berry_yield} berries and recovered a little energy.", event)

    def _handle_fish(self, agent: AgentState, args: dict) -> ActionResult:
        position = self._parse_position(args["tile_position"])
        if position is None:
            return ActionResult(False, "Invalid tile_position format.")
        error = self._validate_adjacent_tile(agent, position, "water")
        if error:
            return ActionResult(False, error)
        tile = self.world.tile_at(position)
        if tile.fish <= 0:
            return ActionResult(False, "The pond is quiet right now.")
        tile.fish -= 1
        catch = 1
        helpers = self._nearby_helpers(agent)
        allies = self._nearby_allies(agent)
        if helpers:
            catch += 1
            self._boost_village_morale(0.04)
        if allies:
            catch += 1
        agent.inventory["fish"] = agent.inventory.get("fish", 0) + catch
        agent.energy = min(1.0, agent.energy + 0.05)
        self._boost_village_food(0.45)
        agent.current_action = "fishing"
        event = self._record_event(
            kind="fish",
            actor=agent.name,
            summary=f"{agent.name} fished at the village pond.",
            location=position,
        )
        memory_text = f"I fished at the village pond and caught {catch} fish."
        if helpers:
            helper_names = ", ".join(other.name for other in helpers[:2])
            memory_text = f"I fished at the village pond with {helper_names} nearby, and the shared trip felt easy and productive."
        self._remember(agent.name, memory_text, 3, ["fish", "food"])
        return ActionResult(True, f"You caught {catch} fish.", event)

    def _handle_gather_flowers(self, agent: AgentState, args: dict) -> ActionResult:
        position = self._parse_position(args["tile_position"])
        if position is None:
            return ActionResult(False, "Invalid tile_position format.")
        error = self._validate_adjacent_tile(agent, position, "flower_garden")
        if error:
            return ActionResult(False, error)
        tile = self.world.tile_at(position)
        if tile.flowers <= 0:
            return ActionResult(False, "The flower beds need time to bloom again.")
        tile.flowers -= 1
        bouquet = 1
        helpers = self._nearby_helpers(agent)
        allies = self._nearby_allies(agent)
        if helpers:
            bouquet += 1
        if allies:
            bouquet += 1
        agent.inventory["flowers"] = agent.inventory.get("flowers", 0) + bouquet
        agent.energy = min(1.0, agent.energy + 0.03)
        self._boost_village_morale(0.18)
        if self.world.public_projects.get("market_stalls") and self.world.public_projects["market_stalls"].completed:
            self._boost_village_morale(0.05)
        agent.current_action = "gardening"
        event = self._record_event(
            kind="gather_flowers",
            actor=agent.name,
            summary=f"{agent.name} gathered flowers from the garden.",
            location=position,
        )
        memory_text = f"I gathered {bouquet} flowers from the garden, and the village felt a little brighter."
        if helpers:
            helper_names = ", ".join(other.name for other in helpers[:2])
            memory_text = f"I gathered flowers from the garden with {helper_names} nearby, and it felt like a shared village ritual."
        self._remember(agent.name, memory_text, 3, ["flowers", "morale"])
        return ActionResult(True, f"You gathered {bouquet} flowers and lifted village morale.", event)

    def _handle_cook_meal(self, agent: AgentState, args: dict) -> ActionResult:
        if not self._near_hearth(agent.position):
            return ActionResult(False, "You need to be at or adjacent to the community hearth to cook.")
        ingredient = args["ingredient"]
        quantity = max(1, int(args["quantity"]))
        if agent.inventory.get("wood", 0) < quantity:
            return ActionResult(False, "You need wood to cook.")
        if agent.inventory.get(ingredient, 0) < quantity:
            return ActionResult(False, f"You do not have enough {ingredient} to cook.")

        agent.inventory["wood"] -= quantity
        agent.inventory[ingredient] -= quantity
        meal_yield_lookup = {"berries": 2, "wheat": 3, "fish": 3}
        meal_yield = quantity * meal_yield_lookup[ingredient]
        helpers = self._nearby_helpers(agent)
        allies = self._nearby_allies(agent)
        if helpers:
            meal_yield += 1
        if allies:
            meal_yield += 1
        agent.inventory["meal"] = agent.inventory.get("meal", 0) + meal_yield
        energy_gain = 0.10 + (0.03 if helpers else 0.0)
        agent.energy = min(1.0, agent.energy + energy_gain)
        agent.current_action = "cooking"
        self._boost_village_food(0.55 * quantity)
        self._boost_village_morale(0.12 * quantity)
        if self.world.public_projects.get("bathhouse") and self.world.public_projects["bathhouse"].completed:
            self._boost_village_morale(0.08)
        for helper in helpers[:2]:
            helper.energy = min(1.0, helper.energy + 0.04)
            helper.comfort_ticks = min(helper.comfort_ticks + 2, 16)

        meal_kind = "stew" if ingredient == "berries" else ("bread" if ingredient == "wheat" else "fish supper")
        event = self._record_event(
            kind="cook_meal",
            actor=agent.name,
            summary=f"{agent.name} cooked {meal_kind} at the community hearth.",
            location=agent.position,
            public=True,
            metadata={"ingredient": ingredient, "quantity": quantity, "meal_yield": meal_yield},
        )
        memory_text = f"I cooked {meal_kind} at the community hearth and made {meal_yield} meals."
        if helpers:
            helper_names = ", ".join(other.name for other in helpers[:2])
            memory_text = f"I cooked {meal_kind} at the community hearth with {helper_names} nearby, and the shared meal lifted everyone's mood."
        self._remember(agent.name, memory_text, 4, ["cook", "food", "social"])
        return ActionResult(True, f"You cooked {meal_yield} meal portions at the hearth.", event)

    def _handle_light_fire(self, agent: AgentState, args: dict) -> ActionResult:
        if agent.position != agent.house_position:
            return ActionResult(False, "You need to be at your own house to light a fire.")
        if agent.inventory.get("wood", 0) < 1:
            return ActionResult(False, "You need wood to light a house fire.")
        agent.inventory["wood"] -= 1
        agent.house_fire_ticks = min(agent.house_fire_ticks + 10, 24)
        self._boost_village_warmth(0.10)
        agent.current_action = "house_fire"
        event = self._record_event(
            kind="light_fire",
            actor=agent.name,
            summary=f"{agent.name} lit a fire at home and smoke curled from the chimney.",
            location=agent.position,
            public=True,
        )
        self._remember(agent.name, "I lit a home fire to make the coming rest warmer and easier.", 3, ["fire", "home"])
        return ActionResult(True, "You lit a warm fire at home.", event)

    def _handle_rest(self, agent: AgentState, args: dict) -> ActionResult:
        base_restore = 0.08
        if agent.position == agent.house_position:
            base_restore += 0.05
        if self._near_well(agent.position):
            base_restore += 0.04
        if self.world.public_projects.get("bathhouse") and self.world.public_projects["bathhouse"].completed and self._near_well(agent.position):
            base_restore += 0.05
        if self.world.public_projects.get("wood_shed") and self.world.public_projects["wood_shed"].completed:
            base_restore += 0.04
        if self.world.public_projects.get("market_stalls") and self.world.public_projects["market_stalls"].completed:
            plaza = self.world.landmarks.get("village_plaza")
            if plaza is not None and self._at_or_adjacent(agent.position, plaza):
                base_restore += 0.02
        if agent.position == agent.house_position and agent.house_fire_ticks > 0:
            base_restore += 0.08
        if agent.inventory.get("meal", 0) > 0:
            agent.inventory["meal"] -= 1
            base_restore += 0.06
            self._boost_village_morale(0.05)
        if self.world.village_warmth >= 6 and self.world.village_food >= 6:
            base_restore += 0.03
        agent.energy = min(1.0, agent.energy + base_restore)
        agent.current_action = "resting"
        if self.world.public_projects.get("bathhouse") and self.world.public_projects["bathhouse"].completed and self._near_well(agent.position):
            for helper in self._nearby_helpers(agent)[:2]:
                helper.energy = min(1.0, helper.energy + 0.03)
                helper.comfort_ticks = min(helper.comfort_ticks + 1, 16)
            self._boost_village_morale(0.06)
        event = self._record_event(
            kind="rest",
            actor=agent.name,
            summary=f"{agent.name} took a short rest.",
            location=agent.position,
            public=False,
        )
        self._remember(agent.name, "I took a brief rest and recovered a little energy.", 2, ["rest"])
        return ActionResult(True, f"You rested and recovered {base_restore:.2f} energy.", event)

    def _handle_sleep(self, agent: AgentState, args: dict) -> ActionResult:
        if agent.position != agent.house_position:
            return ActionResult(False, "You must be at your own house to sleep.")
        if agent.energy > 0.85:
            return ActionResult(False, "You are not tired enough to sleep right now.")
        agent.is_sleeping = True
        agent.current_action = "sleeping"
        event = self._record_event(
            kind="sleep",
            actor=agent.name,
            summary=f"{agent.name} went to sleep.",
            location=agent.position,
            public=False,
        )
        self._remember(agent.name, "I went to sleep at home.", 2, ["sleep"])
        return ActionResult(True, "You went to sleep.", event)

    def _handle_offer_trade(self, agent: AgentState, args: dict) -> ActionResult:
        target_name = args["target_agent"]
        target = self.world.agents.get(target_name)
        if target is None:
            return ActionResult(False, f"Unknown target agent: {target_name}")
        if not self.world.is_adjacent(agent.position, target.position):
            return ActionResult(False, f"{target_name} is not adjacent.")
        offer = {item: quantity for item, quantity in args["offer"].items() if quantity > 0}
        request = {item: quantity for item, quantity in args["request"].items() if quantity > 0}
        if not offer or not request:
            return ActionResult(False, "Trades must offer and request at least one item.")
        if not self._inventory_has(agent.inventory, offer):
            return ActionResult(False, "You do not have enough items for that trade.")
        trade = TradeOffer(
            trade_id=str(uuid.uuid4())[:8],
            from_agent=agent.name,
            to_agent=target_name,
            offer=offer,
            request=request,
            message=args["message"][:90],
            created_tick=self.world.tick_count,
            expires_tick=self.world.tick_count + (7 if self._market_trade_bonus_active(agent.position) else 5),
        )
        self.world.pending_trades[trade.trade_id] = trade
        agent.current_action = "trading"
        agent.last_social_tick = self.world.tick_count
        target.last_social_tick = self.world.tick_count
        if self._market_trade_bonus_active(agent.position):
            self._boost_village_morale(0.15)
        event = self._record_event(
            kind="trade_offer",
            actor=agent.name,
            target=target_name,
            summary=f"{agent.name} offered {target_name} a trade.",
            location=agent.position,
            public=True,
            metadata={"trade_id": trade.trade_id},
        )
        self._remember(agent.name, f"I offered {target_name} a trade: give {offer} for {request}.", 3, ["trade"])
        self._remember(target_name, f"{agent.name} offered me a trade: give {offer} for {request}.", 3, ["trade"])
        return ActionResult(True, f"Trade offer {trade.trade_id} created.", event)

    def _handle_accept_trade(self, agent: AgentState, args: dict) -> ActionResult:
        trade = self.world.pending_trades.get(args["trade_id"])
        if trade is None or trade.status != "pending":
            return ActionResult(False, "That trade offer is no longer available.")
        if trade.to_agent != agent.name:
            return ActionResult(False, "That trade is not for you.")
        other = self.world.agents[trade.from_agent]
        if not self.world.is_adjacent(agent.position, other.position):
            return ActionResult(False, f"{trade.from_agent} is not adjacent anymore.")
        if not self._inventory_has(other.inventory, trade.offer):
            trade.status = "failed"
            return ActionResult(False, f"{trade.from_agent} no longer has the offered items.")
        if not self._inventory_has(agent.inventory, trade.request):
            return ActionResult(False, "You no longer have the requested items.")
        self._transfer(other.inventory, agent.inventory, trade.offer)
        self._transfer(agent.inventory, other.inventory, trade.request)
        trade.status = "accepted"
        agent.current_action = "trading"
        other.current_action = "trading"
        agent.last_social_tick = self.world.tick_count
        other.last_social_tick = self.world.tick_count
        bonus = 0.08
        if self._market_trade_bonus_active(agent.position):
            bonus += 0.04
            self._boost_village_morale(0.35)
        if self.relationships.are_allies(agent.name, trade.from_agent):
            bonus += 0.05
        if self.world.public_projects.get("market_stalls") and self.world.public_projects["market_stalls"].completed:
            plaza = self.world.landmarks.get("village_plaza")
            if plaza is not None and self._at_or_adjacent(agent.position, plaza):
                bonus += 0.03
                self._boost_village_morale(0.12)
        agent.energy = min(1.0, agent.energy + bonus)
        other.energy = min(1.0, other.energy + bonus)
        agent.comfort_ticks = min(agent.comfort_ticks + 8, 16)
        other.comfort_ticks = min(other.comfort_ticks + 8, 16)
        event = self._record_event(
            kind="trade_accept",
            actor=agent.name,
            target=trade.from_agent,
            summary=f"{agent.name} accepted a trade from {trade.from_agent}.",
            location=agent.position,
            public=True,
            metadata={"trade_id": trade.trade_id},
        )
        note = f"Completed trade {trade.trade_id}: {trade.offer} for {trade.request}"
        self.relationships.record_trade(agent.name, trade.from_agent, self.world.day, note)
        self._remember(agent.name, f"I accepted {trade.from_agent}'s trade. {note}. The smooth exchange left me feeling more settled.", 4, ["trade"])
        self._remember(trade.from_agent, f"{agent.name} accepted my trade. {note}. The smooth exchange left me feeling more settled.", 4, ["trade"])
        return ActionResult(True, "Trade completed, and the smooth exchange left both of you more settled.", event)

    def _handle_accept_alliance(self, agent: AgentState, args: dict) -> ActionResult:
        proposal = self.world.pending_alliances.get(args["proposal_id"])
        if proposal is None or proposal.status != "pending":
            return ActionResult(False, "That alliance proposal is no longer available.")
        if proposal.to_agent != agent.name:
            return ActionResult(False, "That alliance proposal is not for you.")
        other = self.world.agents[proposal.from_agent]
        if not self.world.is_adjacent(agent.position, other.position):
            return ActionResult(False, f"{proposal.from_agent} is not adjacent anymore.")
        proposal.status = "accepted"
        self.relationships.form_alliance(agent.name, proposal.from_agent, self.world.day, f"Alliance formed: {proposal.message}")
        agent.current_action = "allying"
        other.current_action = "allying"
        agent.comfort_ticks = min(agent.comfort_ticks + 10, 18)
        other.comfort_ticks = min(other.comfort_ticks + 10, 18)
        agent.energy = min(1.0, agent.energy + 0.06)
        other.energy = min(1.0, other.energy + 0.06)
        event = self._record_event(
            kind="alliance_accept",
            actor=agent.name,
            target=proposal.from_agent,
            summary=f"{agent.name} accepted an alliance with {proposal.from_agent}.",
            location=agent.position,
            public=True,
            metadata={"proposal_id": proposal.proposal_id},
        )
        self._remember(agent.name, f"I formed an alliance with {proposal.from_agent}.", 5, ["alliance"])
        self._remember(proposal.from_agent, f"{agent.name} accepted my alliance proposal.", 5, ["alliance"])
        return ActionResult(True, "Alliance formed.", event)

    def _handle_reject_alliance(self, agent: AgentState, args: dict) -> ActionResult:
        proposal = self.world.pending_alliances.get(args["proposal_id"])
        if proposal is None or proposal.status != "pending":
            return ActionResult(False, "That alliance proposal is no longer available.")
        if proposal.to_agent != agent.name:
            return ActionResult(False, "That alliance proposal is not for you.")
        proposal.status = "rejected"
        self.relationships.record(agent.name, proposal.from_agent, self.world.day, -0.03, f"Rejected alliance: {args['reason'][:60]}")
        event = self._record_event(
            kind="alliance_reject",
            actor=agent.name,
            target=proposal.from_agent,
            summary=f"{agent.name} rejected an alliance proposal from {proposal.from_agent}.",
            location=agent.position,
            public=True,
            metadata={"proposal_id": proposal.proposal_id},
        )
        self._remember(agent.name, f"I rejected {proposal.from_agent}'s alliance proposal.", 3, ["alliance"])
        self._remember(proposal.from_agent, f"{agent.name} rejected my alliance proposal.", 3, ["alliance"])
        return ActionResult(True, "Alliance proposal rejected.", event)

    def _handle_reject_trade(self, agent: AgentState, args: dict) -> ActionResult:
        trade = self.world.pending_trades.get(args["trade_id"])
        if trade is None or trade.status != "pending":
            return ActionResult(False, "That trade offer is no longer available.")
        if trade.to_agent != agent.name:
            return ActionResult(False, "That trade is not for you.")
        trade.status = "rejected"
        agent.last_social_tick = self.world.tick_count
        self.world.agents[trade.from_agent].last_social_tick = self.world.tick_count
        event = self._record_event(
            kind="trade_reject",
            actor=agent.name,
            target=trade.from_agent,
            summary=f"{agent.name} rejected a trade from {trade.from_agent}.",
            location=agent.position,
            public=True,
            metadata={"trade_id": trade.trade_id, "reason": args["reason"]},
        )
        self.relationships.record(agent.name, trade.from_agent, self.world.day, -0.03, f"Rejected trade: {args['reason']}")
        self._remember(agent.name, f"I rejected {trade.from_agent}'s trade because {args['reason']}.", 2, ["trade"])
        self._remember(trade.from_agent, f"{agent.name} rejected my trade because {args['reason']}.", 2, ["trade"])
        return ActionResult(True, "Trade rejected.", event)

    def _handle_contribute_project(self, agent: AgentState, args: dict) -> ActionResult:
        project_name = args["project_name"].strip().lower()
        project = self.world.public_projects.get(project_name)
        if project is None:
            return ActionResult(False, f"Unknown project: {project_name}")
        if project.completed:
            return ActionResult(False, f"{project.title} is already completed.")
        if not self._at_or_adjacent(agent.position, project.site):
            return ActionResult(False, f"You need to be at or adjacent to the {project.title} site.")
        payload = {item: quantity for item, quantity in args["contribution"].items() if quantity > 0}
        if not payload:
            return ActionResult(False, "You must contribute at least one resource.")
        allowed = {item: min(quantity, project.remaining().get(item, 0)) for item, quantity in payload.items()}
        allowed = {item: quantity for item, quantity in allowed.items() if quantity > 0}
        if not allowed:
            return ActionResult(False, f"{project.title} does not need those resources anymore.")
        if not self._inventory_has(agent.inventory, allowed):
            return ActionResult(False, "You do not have enough resources for that contribution.")
        for item, quantity in allowed.items():
            agent.inventory[item] -= quantity
            project.progress[item] = project.progress.get(item, 0) + quantity
        agent.current_action = "building"
        agent.last_social_tick = self.world.tick_count
        helpers = self._nearby_helpers(agent)
        self._boost_village_morale(0.12)
        if "wheat" in allowed:
            self._boost_village_food(0.2 * allowed["wheat"])
        if "wood" in allowed:
            self._boost_village_warmth(0.12 * allowed["wood"])
        if helpers:
            for helper in helpers[:2]:
                helper.comfort_ticks = min(helper.comfort_ticks + 2, 16)
            self._boost_village_morale(0.08)

        completed_now = all(project.progress.get(item, 0) >= required for item, required in project.required.items())
        if completed_now:
            project.completed = True
            if project.name == "granary":
                self._boost_village_food(2.0)
            elif project.name == "wood_shed":
                self._boost_village_warmth(2.0)
            elif project.name == "market_stalls":
                self._boost_village_morale(2.0)
            elif project.name == "bathhouse":
                self._boost_village_morale(1.5)
            elif project.name == "greenhouse":
                self._boost_village_food(1.2)
                self._boost_village_morale(0.8)
            event = self._record_event(
                kind="project_complete",
                actor=agent.name,
                summary=f"{agent.name} completed the {project.title}.",
                location=project.site,
                public=True,
                metadata={"project": project.name},
            )
            memory_text = f"I completed the {project.title} for the village."
            if helpers:
                helper_names = ", ".join(helper.name for helper in helpers[:2])
                memory_text = f"I completed the {project.title} for the village with help nearby from {helper_names}."
            self._remember(agent.name, memory_text, 5, ["project"])
            return ActionResult(True, f"You completed the {project.title}. {project.bonus_description}", event)

        event = self._record_event(
            kind="project_contribution",
            actor=agent.name,
            summary=f"{agent.name} contributed to the {project.title}.",
            location=project.site,
            public=True,
            metadata={"project": project.name, "contribution": allowed},
        )
        memory_text = f"I contributed {allowed} to the {project.title}."
        if helpers:
            helper_names = ", ".join(helper.name for helper in helpers[:2])
            memory_text = f"I contributed {allowed} to the {project.title} while working near {helper_names}."
        self._remember(agent.name, memory_text, 3, ["project"])
        remain = project.remaining()
        remain_text = ", ".join(f"{item}:{amount}" for item, amount in remain.items())
        return ActionResult(True, f"You contributed to the {project.title}. Remaining: {remain_text}.", event)
