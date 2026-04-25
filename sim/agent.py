from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass, field
import json
import re
from typing import Any, Protocol

from openai import OpenAI

from .config import AppConfig
from .memory import MemoryStore
from .relationships import RelationshipGraph
from .tools import TOOLS
from .world import AgentState, TradeOffer, WorldState, WorldEvent


@dataclass
class UsageStats:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Decision:
    tool_name: str
    arguments: dict[str, Any]
    thought: str
    raw_text: str = ""
    usage: UsageStats = field(default_factory=UsageStats)


@dataclass
class DecisionRequest:
    agent_name: str
    observation: str
    system_prompt: str
    tools: list[dict]


class DecisionPolicy(Protocol):
    def decide(self, request: DecisionRequest) -> Decision:
        ...


def build_system_prompt(agent: AgentState, personality: str) -> str:
    return (
        f"You are {agent.name}, a villager in a small simulated community.\n"
        f"{personality}\n\n"
        "You must choose exactly one tool call each turn.\n"
        "Use your thought field to explain your intention briefly.\n"
        "Prefer concrete, local actions that fit your energy, inventory, memories, relationships, and village conditions.\n"
        "Avoid repeating the same action over and over when it is no longer improving your situation.\n"
        "Stay grounded in the observation. Only farm on listed farm tiles, only fish on pond water, only gather flowers in the flower garden, and only chop on forest tiles.\n"
        "If the observation gives immediate valid actions from your current position, prefer those over invented targets.\n"
        "Trade and conversation require being adjacent to other villagers, so travel to shared places when you want interaction.\n"
        "You can also visit someone at their house, give gifts, broadcast to everyone nearby, and propose alliances when trust feels strong enough.\n"
        "You can move to named landmarks like village_plaza, well, community_hearth, notice_board, communal_farm, berry_grove, village_pond, flower_garden, west_forest, east_forest, north_forest, my_house, another villager's name, another villager's house name like Mira_house, or any walkable x,y coordinate.\n"
        "The village has shared pressures: food, warmth, and morale. Public projects can improve those pressures for everyone.\n"
        "The granary helps preserve food and improves communal harvests. The wood_shed helps warmth and makes resting stronger.\n"
        "Market stalls can improve plaza life, and market hours at the plaza make trade and conversation more valuable.\n"
        "Berry groves provide quick food and energy through foraging. The village pond provides fish. The flower garden raises morale and creates gift-like trade items.\n"
        "The community hearth can turn raw food into better meals. The well makes short rests more effective.\n"
        "At your own house you can light a wood fire so nighttime recovery there becomes better for a while.\n"
        "The notice board reflects what the village seems to need most right now.\n"
        "Sleep is only for your own house. Rest is a lighter recovery action that works anywhere.\n"
        "Invalid actions will fail and waste your turn."
    )


def build_board_notice(world: WorldState) -> str:
    if world.village_food <= 4.5:
        return "Board notice: Food stores are thinning. Prioritize cooking, harvesting, fishing, foraging, and granary work."
    if world.village_warmth <= 4.5:
        return "Board notice: Warmth is slipping. Bring wood, finish the wood shed, and keep the village comfortable."
    if world.village_morale <= 4.8:
        return "Board notice: Spirits are low. Flowers, shared meals, and time in the village center would help."
    if not world.public_projects.get("bathhouse", None) or not world.public_projects["bathhouse"].completed:
        return "Board notice: The bathhouse would make the center more livable. Materials are still needed."
    if not world.public_projects.get("greenhouse", None) or not world.public_projects["greenhouse"].completed:
        return "Board notice: The greenhouse would keep the village productive and beautiful through lean stretches."
    if world.is_market_active():
        return "Board notice: Market hour is active. The plaza is the best place for trade, gossip, and coordination."
    return "Board notice: The village is stable for now. Shared meals, conversations, and steady project work keep it that way."


def build_observation(
    config: AppConfig,
    world: WorldState,
    agent: AgentState,
    memory_store: MemoryStore,
    relationships: RelationshipGraph,
) -> str:
    radius = config.observation_radius
    nearby_tiles: list[str] = []
    immediate_actions: list[str] = []
    ax, ay = agent.position
    for y in range(max(0, ay - radius), min(world.size, ay + radius + 1)):
        for x in range(max(0, ax - radius), min(world.size, ax + radius + 1)):
            distance = abs(x - ax) + abs(y - ay)
            if distance == 0 or distance > radius:
                continue
            tile = world.grid[y][x]
            if tile.kind == "forest" and tile.wood > 0:
                nearby_tiles.append(f"- Forest at ({x}, {y}) with {tile.wood} wood")
            elif tile.kind == "berry_grove" and tile.berries > 0:
                nearby_tiles.append(f"- Berry grove at ({x}, {y}) with {tile.berries} berries")
            elif tile.kind == "water" and tile.fish > 0:
                nearby_tiles.append(f"- Pond water at ({x}, {y}) with {tile.fish} fish")
            elif tile.kind == "flower_garden" and tile.flowers > 0:
                nearby_tiles.append(f"- Flower garden at ({x}, {y}) with {tile.flowers} blooms")
            elif tile.kind == "farm" and tile.crop_stage != "empty":
                nearby_tiles.append(f"- Farm at ({x}, {y}) stage={tile.crop_stage}")
            elif tile.kind == "well":
                nearby_tiles.append(f"- Village well at ({x}, {y})")
            elif tile.kind == "hearth":
                nearby_tiles.append(f"- Community hearth at ({x}, {y})")
            elif tile.kind == "notice_board":
                nearby_tiles.append(f"- Notice board at ({x}, {y})")
            elif tile.feature == "granary_site":
                nearby_tiles.append(f"- Granary construction site at ({x}, {y})")
            elif tile.feature == "wood_shed_site":
                nearby_tiles.append(f"- Wood shed construction site at ({x}, {y})")
            elif tile.feature == "market_site":
                nearby_tiles.append(f"- Market stalls site at ({x}, {y})")
            elif tile.feature == "bathhouse_site":
                nearby_tiles.append(f"- Bathhouse site at ({x}, {y})")
            elif tile.kind == "house" and tile.house_owner:
                nearby_tiles.append(f"- {tile.house_owner}'s house at ({x}, {y})")

    for neighbor in world.neighbors(agent.position):
        tile = world.tile_at(neighbor)
        if tile.kind == "forest" and tile.wood > 0:
            immediate_actions.append(f"- chop_wood at ({neighbor[0]}, {neighbor[1]})")
        if tile.kind == "berry_grove" and tile.berries > 0:
            immediate_actions.append(f"- forage at ({neighbor[0]}, {neighbor[1]})")
        if tile.kind == "water" and tile.fish > 0:
            immediate_actions.append(f"- fish at ({neighbor[0]}, {neighbor[1]})")
        if tile.kind == "flower_garden" and tile.flowers > 0:
            immediate_actions.append(f"- gather_flowers at ({neighbor[0]}, {neighbor[1]})")
        if tile.kind == "farm":
            if tile.crop_stage == "ripe":
                immediate_actions.append(f"- farm harvest at ({neighbor[0]}, {neighbor[1]})")
            elif tile.crop_stage == "empty" and agent.inventory.get("wheat", 0) > 0:
                immediate_actions.append(f"- farm plant at ({neighbor[0]}, {neighbor[1]})")
    if world.landmarks.get("community_hearth") is not None:
        hearth = world.landmarks["community_hearth"]
        if abs(hearth[0] - ax) + abs(hearth[1] - ay) <= 1 and agent.inventory.get("wood", 0) > 0:
            if agent.inventory.get("wheat", 0) > 0 or agent.inventory.get("berries", 0) > 0 or agent.inventory.get("fish", 0) > 0:
                immediate_actions.append("- cook_meal at the community_hearth")
    if world.landmarks.get("well") is not None:
        well = world.landmarks["well"]
        if abs(well[0] - ax) + abs(well[1] - ay) <= 1:
            immediate_actions.append("- rest near the well")
    if agent.position == agent.house_position and agent.energy <= 0.85:
        immediate_actions.append("- sleep at your house")
    if agent.position == agent.house_position and agent.inventory.get("wood", 0) > 0:
        immediate_actions.append("- light_fire at your house")

    visible_agents = []
    for other in world.agents.values():
        if other.name == agent.name:
            continue
        if abs(other.position[0] - ax) + abs(other.position[1] - ay) <= radius:
            speech = f' saying "{other.speech_bubble}"' if other.speech_bubble else ""
            visible_agents.append(
                f"- {other.name} at {other.position}, action={other.current_action}, energy={other.energy:.2f}{speech}"
            )

    relevant_events: list[str] = []
    for event in reversed(world.recent_events[-30:]):
        if event.actor == agent.name or event.target == agent.name:
            relevant_events.append(f"- {event.summary}")
        elif event.public and event.location is not None:
            if abs(event.location[0] - ax) + abs(event.location[1] - ay) <= radius + 2:
                relevant_events.append(f"- {event.summary}")
        if len(relevant_events) >= 5:
            break
    relevant_events.reverse()

    pending_trades = [
        trade
        for trade in world.pending_trades.values()
        if trade.to_agent == agent.name and trade.status == "pending"
    ]
    trade_lines = [
        f"- Offer {trade.trade_id}: {trade.from_agent} gives {trade.offer} for {trade.request}. Message: {trade.message}"
        for trade in pending_trades
    ]
    pending_alliances = [
        proposal
        for proposal in world.pending_alliances.values()
        if proposal.to_agent == agent.name and proposal.status == "pending"
    ]
    alliance_lines = [
        f"- Proposal {proposal.proposal_id}: {proposal.from_agent} wants an alliance. Message: {proposal.message}"
        for proposal in pending_alliances
    ]

    memory_lines = memory_store.get(agent.name).recall_lines(limit=5)
    relationship_lines = relationships.summary_for(agent.name)
    landmark_lines = [
        f"- {name} at {position}"
        for name, position in sorted(world.landmarks.items())
    ]
    project_lines = [
        f"- {project.title} at {project.site}: {project.description} Remaining {project.remaining()}"
        if not project.completed
        else f"- {project.title} at {project.site}: completed. Bonus active: {project.bonus_description}"
        for project in world.public_projects.values()
    ]
    social_gap = world.tick_count - agent.last_social_tick
    adjacent_agents = [
        other.name
        for other in world.agents.values()
        if other.name != agent.name and world.is_adjacent(agent.position, other.position)
    ]

    nearby_tiles_text = "\n".join(nearby_tiles[:10]) or "- Nothing notable"
    visible_agents_text = "\n".join(visible_agents) or "- No one nearby"
    events_text = "\n".join(relevant_events) or "- Nothing recent"
    trade_text = "\n".join(trade_lines) or "- No pending trade offers"
    alliance_text = "\n".join(alliance_lines) or "- No pending alliance proposals"
    memory_text = "\n".join(memory_lines) or "- No memories yet"
    relationship_text = "\n".join(relationship_lines) or "- No relationships yet"
    landmark_text = "\n".join(landmark_lines) or "- No landmarks"
    project_text = "\n".join(project_lines) or "- No public projects"
    board_notice = build_board_notice(world)

    night = world.time_of_day <= 0.25 or world.time_of_day >= 0.8
    needs = []
    village_status = (
        f"Village food {world.village_food:.1f}/12, warmth {world.village_warmth:.1f}/12, morale {world.village_morale:.1f}/12."
    )
    if agent.energy < 0.3:
        if agent.position == agent.house_position:
            needs.append("Your energy is low. Sleeping at home is wise.")
        else:
            needs.append("Your energy is low. Rest now or head home to sleep soon.")
    elif night and agent.energy > 0.8:
        needs.append("You are already well-rested, so sleeping again is probably wasteful.")
    if agent.inventory.get("wheat", 0) <= 1:
        needs.append("You are low on wheat. Farming or trading for food is useful.")
    if agent.inventory.get("fish", 0) <= 0 and world.village_food <= 5.2:
        needs.append("Fresh protein is scarce. The village_pond can provide fish for food or cooking.")
    if agent.inventory.get("berries", 0) <= 0 and world.village_food <= 5.0:
        needs.append("Fresh food is scarce. The berry_grove can provide quick food and a little energy.")
    if agent.inventory.get("wheat", 0) + agent.inventory.get("berries", 0) >= 2 and agent.inventory.get("wood", 0) >= 1:
        needs.append("You have enough ingredients to cook at the community_hearth if you want a stronger food payoff.")
    if agent.inventory.get("fish", 0) >= 1 and agent.inventory.get("wood", 0) >= 1:
        needs.append("You could turn fish into a stronger cooked meal at the community_hearth.")
    if agent.inventory.get("wood", 0) <= 1:
        needs.append("You are low on wood. Chopping wood or trading for it is useful.")
    if agent.inventory.get("flowers", 0) <= 0 and world.village_morale <= 5.2:
        needs.append("Village morale is wavering. The flower_garden can lift spirits and create something nice to trade or offer.")
    if agent.inventory.get("wood", 0) >= 8:
        needs.append("You already have a strong wood stockpile. Consider food, conversation, or trade instead.")
    wood_shed = world.public_projects.get("wood_shed")
    granary = world.public_projects.get("granary")
    if wood_shed is not None and not wood_shed.completed and agent.inventory.get("wood", 0) >= 3:
        needs.append("You have enough wood to make a meaningful contribution to the wood_shed project.")
    if granary is not None and not granary.completed and agent.inventory.get("wheat", 0) >= 3:
        needs.append("You have enough wheat to make a meaningful contribution to the granary.")
    if world.village_food <= 4.0:
        needs.append("Village food stores are slipping. Harvest, fish, forage berries, trade wheat, or contribute to the granary soon.")
    if world.village_warmth <= 4.0:
        needs.append("Village warmth is slipping. Wood contributions and shelter work matter right now.")
    if world.village_morale <= 4.0:
        needs.append("Village morale is low. Conversation, fair trades, and visible cooperation will help.")
    if pending_trades:
        needs.append("You have pending trade offers waiting for a response.")
    if pending_alliances:
        needs.append("You have pending alliance proposals waiting for a response.")
    if night:
        needs.append("It is nighttime, so sleeping at home and resting anywhere are both possible.")
    if agent.energy < 0.45 and world.landmarks.get("well") is not None:
        needs.append("If you are near the well, resting there is especially effective.")
    if agent.inventory.get("meal", 0) > 0:
        needs.append("You are carrying cooked meals. Resting will make better use of them than carrying them forever.")
    if agent.position == agent.house_position and night and agent.inventory.get("wood", 0) > 0 and agent.house_fire_ticks <= 0:
        needs.append("A home fire would make nighttime rest better if you want to spend wood on comfort.")
    if agent.house_fire_ticks > 0:
        needs.append(f"Your house fire is lit for about {agent.house_fire_ticks} more ticks.")
    if social_gap >= 12:
        needs.append("You have been isolated for a while. The village_plaza and communal_farm are good places to meet others.")
    if adjacent_agents:
        needs.append("People are adjacent right now, so gifts, trade, alliance proposals, or a group announcement are immediately possible.")
    if agent.repeated_action_count >= 3:
        needs.append(
            f"You have repeated a very similar action {agent.repeated_action_count} times recently without enough progress. Change tactics and seek a different place, person, or project."
        )
    elif agent.repeated_tool_count >= 4:
        needs.append(
            f"You have used {agent.last_tool} {agent.repeated_tool_count} turns in a row. Even if the exact target changes, you should switch priorities now."
        )
    if agent.repeated_action_count >= 4:
        needs.append("If you keep repeating the same local action, you should deliberately break the loop by moving, contributing, speaking, or resting.")
    if agent.comfort_ticks > 0:
        needs.append("Recent cooperation left you feeling more settled and efficient for a while.")
    if world.is_market_active():
        needs.append("Market hour is active at the plaza. Trades and conversation there are unusually effective.")

    project_prompts: list[str] = []
    for project in world.public_projects.values():
        if project.completed:
            continue
        distance = abs(project.site[0] - ax) + abs(project.site[1] - ay)
        if distance <= 2:
            can_help = []
            for item, amount in project.remaining().items():
                if amount > 0 and agent.inventory.get(item, 0) > 0:
                    can_help.append(f"{item}:{min(amount, agent.inventory.get(item, 0))}")
            if can_help:
                project_prompts.append(f"- You can help the {project.title} right now with {', '.join(can_help)}.")
            else:
                project_prompts.append(f"- The {project.title} is nearby, but you need resources before you can help.")

    needs_text = "\n".join(f"- {item}" for item in needs) or "- No urgent needs"
    adjacent_text = ", ".join(adjacent_agents) if adjacent_agents else "nobody"
    project_prompt_text = "\n".join(project_prompts) or "- No immediate project opportunities at your position."
    immediate_actions_text = "\n".join(immediate_actions[:8]) or "- No especially strong local action is available, so moving is reasonable."
    market_text = (
        f"Market hour is active until tick {world.market_active_until_tick}. The plaza is especially social and trade-friendly."
        if world.is_market_active()
        else "No market hour is active right now."
    )

    return (
        f"=== Observation: Day {world.day}, tick {world.tick_count} ===\n"
        f"You are at {agent.position}. House: {agent.house_position}. Energy: {agent.energy:.2f}.\n"
        f"Inventory: {json.dumps(agent.inventory, sort_keys=True)}.\n"
        f"Current action: {agent.current_action}. Last result: {agent.pending_result or 'none'}.\n"
        f"House fire: {'lit' if agent.house_fire_ticks > 0 else 'out'}.\n\n"
        f"Village state:\n- {village_status}\n- {market_text}\n- {board_notice}\n\n"
        f"Urgent needs:\n{needs_text}\n\n"
        f"Agents you can trade or speak with right now: {adjacent_text}.\n\n"
        f"Known landmarks across the whole map:\n{landmark_text}\n\n"
        f"Public projects:\n{project_text}\n\n"
        f"Project opportunities from where you are:\n{project_prompt_text}\n\n"
        f"Immediate valid actions from where you stand:\n{immediate_actions_text}\n\n"
        f"Nearby villagers:\n{visible_agents_text}\n\n"
        f"Nearby tiles:\n{nearby_tiles_text}\n\n"
        f"Pending trades:\n{trade_text}\n\n"
        f"Pending alliances:\n{alliance_text}\n\n"
        f"Relationship summary:\n{relationship_text}\n\n"
        f"Recent events:\n{events_text}\n\n"
        f"Memories:\n{memory_text}\n\n"
        "Choose one action now."
    )


class OpenAIDecisionPolicy:
    def __init__(self, config: AppConfig):
        self.client = OpenAI(api_key=config.openai_key)
        self.model = config.model
        self.max_output_tokens = config.max_tokens_per_turn

    def decide(self, request: DecisionRequest) -> Decision:
        response = self.client.responses.create(
            model=self.model,
            instructions=request.system_prompt,
            input=request.observation,
            tools=request.tools,
            tool_choice="required",
            max_output_tokens=self.max_output_tokens,
        )

        usage = UsageStats(
            input_tokens=int(getattr(response.usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(response.usage, "output_tokens", 0) or 0),
        )

        for item in response.output:
            if getattr(item, "type", "") == "function_call":
                arguments = json.loads(item.arguments)
                thought = str(arguments.get("thought", ""))
                return Decision(
                    tool_name=item.name,
                    arguments=arguments,
                    thought=thought,
                    raw_text=json.dumps(arguments),
                    usage=usage,
                )

        return Decision(tool_name="wait", arguments={"thought": "No tool call returned."}, thought="No tool call returned.", usage=usage)


class HeuristicDecisionPolicy:
    """Deterministic fallback for offline use and tests."""

    def decide(self, request: DecisionRequest) -> Decision:
        observation = request.observation
        observation_lower = observation.lower()
        position = self._extract_position(observation)
        inventory = self._extract_inventory(observation)
        visible_agents = self._extract_visible_agents(observation)
        farm_tiles = self._extract_tiles(observation, "Farm at (")
        forest_tiles = self._extract_tiles(observation, "Forest at (")
        berry_tiles = self._extract_tiles(observation, "Berry grove at (")
        pond_tiles = self._extract_tiles(observation, "Pond water at (")
        flower_tiles = self._extract_tiles(observation, "Flower garden at (")
        hearth_tiles = self._extract_tiles(observation, "Community hearth at (")
        project_options = self._extract_project_opportunities(observation)
        village_stats = self._extract_village_stats(observation)

        if "pending trade offers" in observation_lower and "offer " in observation_lower:
            trade_id = self._extract_trade_id(request.observation)
            if trade_id and ("gives {'wood':" in request.observation or '"wood":' in request.observation):
                return Decision("accept_trade", {"trade_id": trade_id, "thought": "This trade helps me."}, "This trade helps me.")
            if trade_id:
                return Decision(
                    "reject_trade",
                    {"trade_id": trade_id, "reason": "Not worthwhile right now.", "thought": "I should decline."},
                    "I should decline.",
                )
        if "energy is low" in observation_lower and position == self._extract_house(request.observation):
            return Decision("sleep", {"thought": "I need to sleep."}, "I need to sleep.")
        if "energy is low" in observation_lower and "nighttime" not in observation_lower:
            return Decision("rest", {"thought": "I should rest briefly before I overextend."}, "I should rest briefly before I overextend.")
        adjacent_berries = self._find_adjacent_tile(position, berry_tiles)
        if village_stats.get("food", 7.0) <= 5.0 and adjacent_berries:
            tile = f"{adjacent_berries[0]},{adjacent_berries[1]}"
            return Decision("forage", {"tile_position": tile, "thought": "Fresh berries would help the village and give me a quick lift."}, "Fresh berries would help the village and give me a quick lift.")
        adjacent_pond = self._find_adjacent_tile(position, pond_tiles)
        if village_stats.get("food", 7.0) <= 5.3 and adjacent_pond:
            tile = f"{adjacent_pond[0]},{adjacent_pond[1]}"
            return Decision("fish", {"tile_position": tile, "thought": "The pond can give us food quickly and break up the routine."}, "The pond can give us food quickly and break up the routine.")
        adjacent_flowers = self._find_adjacent_tile(position, flower_tiles)
        if village_stats.get("morale", 6.0) <= 5.2 and adjacent_flowers:
            tile = f"{adjacent_flowers[0]},{adjacent_flowers[1]}"
            return Decision("gather_flowers", {"tile_position": tile, "thought": "Fresh flowers would lift spirits and make the village feel more cared for."}, "Fresh flowers would lift spirits and make the village feel more cared for.")
        adjacent_hearth = self._find_adjacent_tile(position, hearth_tiles)
        if adjacent_hearth and inventory.get("wood", 0) >= 1:
            if inventory.get("wheat", 0) >= 1 and village_stats.get("food", 7.0) <= 6.0:
                return Decision(
                    "cook_meal",
                    {"ingredient": "wheat", "quantity": 1, "thought": "Cooking at the hearth would turn supplies into better food and help the whole village."},
                    "Cooking at the hearth would turn supplies into better food and help the whole village.",
                )
            if inventory.get("berries", 0) >= 1 and agent_energy_low(observation_lower):
                return Decision(
                    "cook_meal",
                    {"ingredient": "berries", "quantity": 1, "thought": "A quick berry stew at the hearth would help me recover and feed the village."},
                    "A quick berry stew at the hearth would help me recover and feed the village.",
                )
            if inventory.get("fish", 0) >= 1:
                return Decision(
                    "cook_meal",
                    {"ingredient": "fish", "quantity": 1, "thought": "Cooking fish at the hearth turns a simple catch into a better shared meal."},
                    "Cooking fish at the hearth turns a simple catch into a better shared meal.",
                )
        if "energy is low" in observation_lower and "house:" in observation_lower:
            return Decision("move", {"target": "my_house", "thought": "I need to get home."}, "I need to get home.")
        if (
            "nighttime" in observation_lower
            and position == self._extract_house(request.observation)
            and "already well-rested" not in observation_lower
        ):
            return Decision("sleep", {"thought": "I should rest now."}, "I should rest now.")
        if project_options and (village_stats.get("food", 7.0) <= 5.5 or village_stats.get("warmth", 6.0) <= 5.5):
            project_name, contribution = project_options[0]
            return Decision(
                "contribute_project",
                {
                    "project_name": project_name,
                    "contribution": contribution,
                    "thought": "Helping the village project is the best use of what I have right now.",
                },
                "Helping the village project is the best use of what I have right now.",
            )
        if visible_agents and self._is_market_active(observation):
            other = visible_agents[0]
            if inventory.get("wood", 0) >= 2 and inventory.get("wheat", 0) <= 1:
                return Decision(
                    "offer_trade",
                    {
                        "target_agent": other,
                        "offer": {"wood": 1, "wheat": 0},
                        "request": {"wood": 0, "wheat": 1},
                        "message": "Market hour is on. Wood for wheat?",
                        "thought": "This is a good moment to trade while everyone is gathered.",
                    },
                    "This is a good moment to trade while everyone is gathered.",
                )
            return Decision(
                "speak",
                {"message": "Market hour is live. What do you need?", "target": other, "thought": "This is a good time to coordinate."},
                "This is a good time to coordinate.",
            )
        if "isolated for a while" in observation_lower:
            return Decision(
                "move",
                {"target": "village_plaza", "thought": "I should go where people gather."},
                "I should go where people gather.",
            )
        ripe_tile = self._find_adjacent_tile(position, farm_tiles, "ripe")
        if ripe_tile:
            tile = f"{ripe_tile[0]},{ripe_tile[1]}"
            return Decision("farm", {"action": "harvest", "tile_position": tile, "thought": "Food is ready."}, "Food is ready.")
        if adjacent_berries and inventory.get("berries", 0) <= 2:
            tile = f"{adjacent_berries[0]},{adjacent_berries[1]}"
            return Decision("forage", {"tile_position": tile, "thought": "Quick food from the berry grove would help."}, "Quick food from the berry grove would help.")
        if adjacent_pond and inventory.get("fish", 0) <= 1:
            tile = f"{adjacent_pond[0]},{adjacent_pond[1]}"
            return Decision("fish", {"tile_position": tile, "thought": "Fishing would add a different kind of food and make the village less one-note."}, "Fishing would add a different kind of food and make the village less one-note.")
        if adjacent_flowers and inventory.get("flowers", 0) <= 1 and village_stats.get("morale", 6.0) <= 6.0:
            tile = f"{adjacent_flowers[0]},{adjacent_flowers[1]}"
            return Decision("gather_flowers", {"tile_position": tile, "thought": "The flower garden can help morale and give me something pleasant to carry or trade."}, "The flower garden can help morale and give me something pleasant to carry or trade.")
        empty_tile = self._find_adjacent_tile(position, farm_tiles, "empty")
        if empty_tile and inventory.get("wheat", 0) > 0:
            tile = f"{empty_tile[0]},{empty_tile[1]}"
            return Decision("farm", {"action": "plant", "tile_position": tile, "thought": "I should plant more food."}, "I should plant more food.")
        if visible_agents:
            other = visible_agents[0]
            if inventory.get("wood", 0) >= 2 and inventory.get("wheat", 0) <= 1:
                return Decision(
                    "offer_trade",
                    {
                        "target_agent": other,
                        "offer": {"wood": 1, "wheat": 0},
                        "request": {"wood": 0, "wheat": 1},
                        "message": "Wood for wheat?",
                        "thought": "A trade would help me.",
                    },
                    "A trade would help me.",
                )
            if "trade or speak with right now:" in observation_lower:
                return Decision(
                    "speak",
                    {"message": "Want to work together for a bit?", "target": other, "thought": "Nearby company could help."},
                    "Nearby company could help.",
                )
            return Decision(
                "speak",
                {"message": "How is your day going?", "target": other, "thought": "I should stay social."},
                "I should stay social.",
            )
        if project_options:
            project_name, contribution = project_options[0]
            return Decision(
                "contribute_project",
                {
                    "project_name": project_name,
                    "contribution": contribution,
                    "thought": "A public project will help everyone and create better future options.",
                },
                "A public project will help everyone and create better future options.",
            )
        if any(stage == "ripe" for _, stage in farm_tiles):
            tile = self._extract_tile_after("Farm at (", request.observation, only_stage="ripe")
            if tile:
                return Decision("move", {"target": tile, "thought": "There is food ready to gather."}, "There is food ready to gather.")
        if village_stats.get("food", 7.0) <= 4.5:
            if inventory.get("wheat", 0) >= 1 and inventory.get("wood", 0) >= 1:
                return Decision(
                    "move",
                    {"target": "community_hearth", "thought": "Cooking is one of the fastest ways to stabilize the village's food situation."},
                    "Cooking is one of the fastest ways to stabilize the village's food situation.",
                )
            if pond_tiles:
                return Decision(
                    "move",
                    {"target": "village_pond", "thought": "Fishing adds another food source when the village is running lean."},
                    "Fishing adds another food source when the village is running lean.",
                )
            return Decision(
                "move",
                {"target": "communal_farm", "thought": "The village needs food, so I should get to the communal farm."},
                "The village needs food, so I should get to the communal farm.",
            )
        if village_stats.get("food", 7.0) <= 5.0 and berry_tiles:
            return Decision(
                "move",
                {"target": "berry_grove", "thought": "Fresh berries are another quick way to support the village's food supply."},
                "Fresh berries are another quick way to support the village's food supply.",
            )
        if village_stats.get("morale", 6.0) <= 5.0:
            return Decision(
                "move",
                {"target": "flower_garden", "thought": "The flower garden can brighten the village and give me a more social errand."},
                "The flower garden can brighten the village and give me a more social errand.",
            )
        if village_stats.get("warmth", 6.0) <= 4.5 and inventory.get("wood", 0) >= 2:
            return Decision(
                "move",
                {"target": "wood_shed_site", "thought": "Warmth is slipping. I should bring wood to the shared project."},
                "Warmth is slipping. I should bring wood to the shared project.",
            )
        if inventory.get("wheat", 0) <= 1:
            return Decision(
                "move",
                {"target": "communal_farm", "thought": "The communal farm should have food or people."},
                "The communal farm should have food or people.",
            )
        adjacent_forest = self._find_adjacent_tile(position, forest_tiles)
        if adjacent_forest and inventory.get("wood", 0) <= 5:
            tile = f"{adjacent_forest[0]},{adjacent_forest[1]}"
            return Decision("chop_wood", {"tile_position": tile, "thought": "I can gather wood here."}, "I can gather wood here.")
        if inventory.get("wood", 0) >= 8:
            return Decision(
                "move",
                {"target": "village_plaza", "thought": "I have enough wood and should look for company or trade."},
                "I have enough wood and should look for company or trade.",
            )
        if inventory.get("wheat", 0) >= 2 and inventory.get("wood", 0) >= 1:
            return Decision(
                "move",
                {"target": "community_hearth", "thought": "Turning raw supplies into cooked meals would make the village feel more stable and alive."},
                "Turning raw supplies into cooked meals would make the village feel more stable and alive.",
            )
        if forest_tiles:
            tile = self._extract_tile_after("Forest at (", request.observation)
            if tile:
                return Decision("move", {"target": tile, "thought": "Wood is nearby."}, "Wood is nearby.")
        return Decision("wait", {"thought": "I will observe for a moment."}, "I will observe for a moment.")


def agent_energy_low(observation_lower: str) -> bool:
    return "energy is low" in observation_lower or "rest now" in observation_lower

    @staticmethod
    def _extract_trade_id(text: str) -> str | None:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- Offer "):
                return line.split(":", 1)[0].replace("- Offer ", "").strip()
        return None

    @staticmethod
    def _extract_tile_after(prefix: str, text: str, only_stage: str | None = None) -> str | None:
        for line in text.splitlines():
            if prefix in line:
                if only_stage and f"stage={only_stage}" not in line:
                    continue
                start = line.index(prefix) + len(prefix)
                end = line.index(")", start)
                return line[start:end].replace(" ", "")
        return None

    @staticmethod
    def _extract_position(text: str) -> tuple[int, int]:
        match = re.search(r"You are at \((\d+), (\d+)\)", text)
        if not match:
            return (0, 0)
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def _extract_house(text: str) -> tuple[int, int]:
        match = re.search(r"House: \((\d+), (\d+)\)", text)
        if not match:
            return (0, 0)
        return int(match.group(1)), int(match.group(2))

    @staticmethod
    def _extract_inventory(text: str) -> dict[str, int]:
        match = re.search(r"Inventory: (\{.+\})", text)
        if not match:
            return {}
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _extract_visible_agents(text: str) -> list[str]:
        agents: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- ") and " action=" in line:
                agents.append(line[2:].split(" at ", 1)[0].strip())
        return agents

    @staticmethod
    def _extract_tiles(text: str, prefix: str) -> list[tuple[tuple[int, int], str]]:
        items: list[tuple[tuple[int, int], str]] = []
        for line in text.splitlines():
            if prefix not in line:
                continue
            start = line.index(prefix) + len(prefix)
            end = line.index(")", start)
            coords = line[start:end].replace(" ", "")
            if "," not in coords:
                continue
            left, right = coords.split(",", 1)
            stage = "unknown"
            if "stage=" in line:
                stage = line.split("stage=", 1)[1].strip()
            items.append(((int(left), int(right)), stage))
        return items

    @staticmethod
    def _find_adjacent_tile(
        position: tuple[int, int], tiles: list[tuple[tuple[int, int], str]], required_stage: str | None = None
    ) -> tuple[int, int] | None:
        for coords, stage in tiles:
            if required_stage and stage != required_stage:
                continue
            if abs(coords[0] - position[0]) + abs(coords[1] - position[1]) <= 1:
                return coords
        return None

    @staticmethod
    def _extract_village_stats(text: str) -> dict[str, float]:
        match = re.search(r"Village food ([0-9.]+)/12, warmth ([0-9.]+)/12, morale ([0-9.]+)/12", text)
        if not match:
            return {}
        return {
            "food": float(match.group(1)),
            "warmth": float(match.group(2)),
            "morale": float(match.group(3)),
        }

    @staticmethod
    def _is_market_active(text: str) -> bool:
        return "market hour is active until tick" in text.lower()

    @staticmethod
    def _extract_project_opportunities(text: str) -> list[tuple[str, dict[str, int]]]:
        opportunities: list[tuple[str, dict[str, int]]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("- You can help the "):
                continue
            name_match = re.match(r"- You can help the (.+?) right now with (.+)\.", line)
            if not name_match:
                continue
            title = name_match.group(1).strip().lower().replace(" ", "_")
            contribution: dict[str, int] = {"wood": 0, "wheat": 0}
            for part in name_match.group(2).split(","):
                if ":" not in part:
                    continue
                item, amount = part.strip().split(":", 1)
                try:
                    contribution[item.strip()] = max(0, int(amount.strip()))
                except ValueError:
                    continue
            opportunities.append((title, contribution))
        return opportunities


class CostTracker:
    def __init__(self, input_per_million: float, output_per_million: float):
        self.input_per_million = input_per_million
        self.output_per_million = output_per_million
        self.input_tokens = 0
        self.output_tokens = 0

    def record(self, usage: UsageStats) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens

    @property
    def estimated_cost(self) -> float:
        input_cost = (self.input_tokens / 1_000_000) * self.input_per_million
        output_cost = (self.output_tokens / 1_000_000) * self.output_per_million
        return input_cost + output_cost


def decision_future_done(future: Future[Decision] | None) -> bool:
    return future is not None and future.done()
