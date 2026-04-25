from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import csv
import json
import threading
import time

from .actions import ActionResolver
from .agent import (
    CostTracker,
    Decision,
    DecisionPolicy,
    DecisionRequest,
    HeuristicDecisionPolicy,
    OpenAIDecisionPolicy,
    build_observation,
    build_system_prompt,
)
from .config import AppConfig
from .memory import MemoryStore
from .relationships import RelationshipGraph
from .tools import TOOLS
from .world import AgentState, WorldState, generate_world


@dataclass
class PendingDecision:
    agent_name: str
    future: Future[Decision]


def json_dumps_compact(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class SimulationEngine:
    def __init__(
        self,
        config: AppConfig,
        *,
        world: WorldState | None = None,
        relationships: RelationshipGraph | None = None,
        decision_policy: DecisionPolicy | None = None,
    ):
        self.config = config
        self.world = world or generate_world(config)
        self.memory_store = MemoryStore(Path(config.data_dir) / "memory", list(self.world.agents.keys()))
        self.relationships = relationships or self._load_or_create_relationships()
        self.decision_policy = decision_policy or self._build_default_policy()
        self.action_resolver = ActionResolver(self.world, self.memory_store, self.relationships)
        self.cost_tracker = CostTracker(
            input_per_million=config.pricing.input_per_million,
            output_per_million=config.pricing.output_per_million,
        )
        self.executor = ThreadPoolExecutor(max_workers=config.max_concurrent_model_calls)
        self.pending_decisions: dict[str, PendingDecision] = {}
        self.accumulator = 0.0
        self.last_autosave_monotonic = time.monotonic()
        self.last_tick_monotonic = time.monotonic()
        self._csv_lock = threading.Lock()
        self._ensure_storage()
        self._ensure_event_log()

    def _build_default_policy(self) -> DecisionPolicy:
        if self.config.openai_key:
            return OpenAIDecisionPolicy(self.config)
        return HeuristicDecisionPolicy()

    def _load_or_create_relationships(self) -> RelationshipGraph:
        path = Path(self.config.data_dir) / "relationships.json"
        if path.exists():
            return RelationshipGraph.load(path)
        return RelationshipGraph(list(self.world.agents.keys()))

    def _ensure_storage(self) -> None:
        Path(self.config.data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.logs_dir).mkdir(parents=True, exist_ok=True)

    def _ensure_event_log(self) -> None:
        path = Path(self.config.event_log_file)
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["tick", "day", "time_of_day", "kind", "actor", "target", "location", "summary", "thought"])

    @classmethod
    def load_or_create(cls, config: AppConfig, *, new_world: bool = False, decision_policy: DecisionPolicy | None = None) -> "SimulationEngine":
        save_path = Path(config.save_file)
        if save_path.exists() and not new_world:
            world = WorldState.load(save_path)
            if (
                world.schema_version < 7
                or world.size != config.world_size
                or not world.landmarks
                or not world.public_projects
            ):
                return cls(config, decision_policy=decision_policy)
            engine = cls(config, world=world, decision_policy=decision_policy)
            return engine
        return cls(config, decision_policy=decision_policy)

    def shutdown(self) -> None:
        self.save_all()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def save_all(self) -> None:
        self.world.save(self.config.save_file)
        self.memory_store.save_all()
        self.relationships.save(Path(self.config.data_dir) / "relationships.json")

    def update(self, dt_seconds: float) -> None:
        self._poll_futures()
        self._update_speech_bubbles(dt_seconds)
        self.accumulator += dt_seconds
        tick_interval = self.config.tick_interval_seconds
        while self.accumulator >= tick_interval:
            self.accumulator -= tick_interval
            self.tick()
        self.maybe_autosave()

    def tick(self) -> None:
        self.world.tick_count += 1
        self._advance_time()
        self._update_village_pressures()
        self._update_sleep_and_energy()
        self._advance_movement()
        self._grow_crops_and_regenerate_forest()
        self._expire_trades()
        self._expire_alliances()
        self._emit_shared_gathering_events()
        self._schedule_decisions()

    def maybe_autosave(self) -> None:
        now = time.monotonic()
        if now - self.last_autosave_monotonic >= self.config.autosave_interval_seconds:
            self.save_all()
            self.last_autosave_monotonic = now

    def wait_for_idle(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._poll_futures()
            if not self.pending_decisions:
                return
            time.sleep(0.01)

    def _advance_time(self) -> None:
        day_progress = self.config.tick_interval_seconds / self.config.day_length_seconds
        self.world.time_of_day += day_progress
        if self.world.time_of_day >= 1.0:
            self.world.time_of_day -= 1.0
            self.world.day += 1

    def _update_speech_bubbles(self, dt_seconds: float) -> None:
        for agent in self.world.agents.values():
            if agent.speech_bubble_ttl > 0:
                agent.speech_bubble_ttl = max(0.0, agent.speech_bubble_ttl - dt_seconds)
                if agent.speech_bubble_ttl <= 0:
                    agent.speech_bubble = None

    def _update_sleep_and_energy(self) -> None:
        wood_shed_complete = self.world.public_projects.get("wood_shed") is not None and self.world.public_projects["wood_shed"].completed
        for agent in self.world.agents.values():
            if agent.is_sleeping:
                sleep_gain = 0.10
                if agent.house_fire_ticks > 0 and self._is_night():
                    sleep_gain += 0.05
                if self.world.village_warmth <= 3.0:
                    sleep_gain -= 0.03
                elif self.world.village_warmth >= 7.0:
                    sleep_gain += 0.01
                if self.world.village_food <= 3.0:
                    sleep_gain -= 0.02
                if wood_shed_complete:
                    sleep_gain += 0.04
                agent.energy = min(1.0, agent.energy + sleep_gain)
                if agent.energy >= 0.98:
                    agent.is_sleeping = False
                    agent.current_action = "idle"
                    agent.pending_result = "You feel rested."
                    agent.next_think_tick = self.world.tick_count + 1
            else:
                drain = 0.01 if agent.comfort_ticks > 0 else 0.02
                if self.world.village_food <= 4.0:
                    drain += 0.01
                if self.world.village_warmth <= 4.0:
                    drain += 0.005
                if self.world.village_morale <= 3.0:
                    drain += 0.005
                agent.energy = max(0.0, agent.energy - drain)
            if agent.comfort_ticks > 0:
                agent.comfort_ticks -= 1
            if agent.house_fire_ticks > 0:
                agent.house_fire_ticks -= 1

    def _update_village_pressures(self) -> None:
        food_drain = 0.035
        warmth_drain = 0.025
        morale_drift = 0.0
        if self.world.public_projects.get("granary") and self.world.public_projects["granary"].completed:
            food_drain -= 0.012
        if self.world.public_projects.get("wood_shed") and self.world.public_projects["wood_shed"].completed:
            warmth_drain -= 0.010
        if self.world.public_projects.get("bathhouse") and self.world.public_projects["bathhouse"].completed:
            morale_drift += 0.01
        if self.world.public_projects.get("greenhouse") and self.world.public_projects["greenhouse"].completed:
            food_drain -= 0.008
            morale_drift += 0.008
        if self.world.is_market_active():
            morale_drift += 0.015
        if self.world.village_food <= 4.0:
            morale_drift -= 0.02
        if self.world.village_warmth <= 4.0:
            morale_drift -= 0.02

        active_social_agents = 0
        for agent in self.world.agents.values():
            if self.world.tick_count - agent.last_social_tick <= 8:
                active_social_agents += 1
        if active_social_agents >= max(2, len(self.world.agents) // 2):
            morale_drift += 0.015

        self.world.village_food = min(12.0, max(0.0, self.world.village_food - food_drain))
        self.world.village_warmth = min(12.0, max(0.0, self.world.village_warmth - warmth_drain))
        self.world.village_morale = min(12.0, max(0.0, self.world.village_morale + morale_drift))

    def _advance_movement(self) -> None:
        for agent in self.world.agents.values():
            if not agent.current_path:
                continue
            next_position = agent.current_path.pop(0)
            if self.world.is_passable(next_position):
                agent.position = next_position
                agent.current_action = "moving"
                if not agent.current_path:
                    agent.current_action = "idle"
                    agent.pending_result = f"Arrived at {agent.position}."
                    agent.next_think_tick = self.world.tick_count + 1
            else:
                agent.current_path.clear()
                agent.current_action = "idle"
                agent.pending_result = "Movement failed because the path was blocked."
                agent.next_think_tick = self.world.tick_count + 1

    def _grow_crops_and_regenerate_forest(self) -> None:
        greenhouse_complete = self.world.public_projects.get("greenhouse") is not None and self.world.public_projects["greenhouse"].completed
        for row in self.world.grid:
            for tile in row:
                if tile.kind == "farm" and tile.crop_stage == "growing":
                    tile.crop_progress += 0.11 if greenhouse_complete else 0.08
                    if tile.crop_progress >= 1.0:
                        tile.crop_stage = "ripe"
                        tile.crop_progress = 1.0
                if tile.kind == "forest" and tile.wood < 8 and self.world.tick_count % 16 == 0:
                    tile.wood += 1
                if tile.kind == "berry_grove" and tile.berries < 5 and self.world.tick_count % 20 == 0:
                    tile.berries += 1
                if tile.kind == "water" and tile.fish < 4 and self.world.tick_count % 18 == 0:
                    tile.fish += 1
                if tile.kind == "flower_garden" and tile.flowers < 5 and self.world.tick_count % (14 if greenhouse_complete else 22) == 0:
                    tile.flowers += 1

    def _expire_trades(self) -> None:
        for trade_id, trade in list(self.world.pending_trades.items()):
            if trade.status == "pending" and trade.expires_tick <= self.world.tick_count:
                trade.status = "expired"

    def _expire_alliances(self) -> None:
        for proposal_id, proposal in list(self.world.pending_alliances.items()):
            if proposal.status == "pending" and proposal.expires_tick <= self.world.tick_count:
                proposal.status = "expired"

    def _emit_shared_gathering_events(self) -> None:
        market_tick = max(6, int(round(20 * self.config.ticks_per_second)))
        if self.world.tick_count % market_tick == 0:
            plaza = self.world.landmarks.get("village_plaza")
            if plaza is not None:
                duration = max(4, int(round(6 * self.config.ticks_per_second)))
                if self.world.public_projects.get("market_stalls") and self.world.public_projects["market_stalls"].completed:
                    duration += max(2, int(round(3 * self.config.ticks_per_second)))
                self.world.market_active_until_tick = self.world.tick_count + duration
                summary = "Market hour has started at the village plaza. Trade and conversation there feel unusually productive."
                if self.world.public_projects.get("market_stalls") and self.world.public_projects["market_stalls"].completed:
                    summary = "Market hour has started at the improved plaza stalls. Trade, gossip, and regrouping there feel unusually productive."
                event = self.action_resolver._record_event(
                    kind="market_hour",
                    actor="system",
                    summary=summary,
                    location=plaza,
                    public=True,
                )
                self._append_event_row(event, "system")
        plaza = self.world.landmarks.get("village_plaza")
        if plaza is None:
            return
        nearby = [
            agent
            for agent in self.world.agents.values()
            if abs(agent.position[0] - plaza[0]) + abs(agent.position[1] - plaza[1]) <= 2
        ]
        if self.world.is_market_active() and len(nearby) >= 2 and self.world.tick_count % max(3, int(round(4 * self.config.ticks_per_second))) == 0:
            self.world.village_morale = min(12.0, self.world.village_morale + 0.12)
            for agent in nearby[:3]:
                agent.comfort_ticks = min(agent.comfort_ticks + 1, 16)
        hearth = self.world.landmarks.get("community_hearth")
        if hearth is not None:
            cooks_and_guests = [
                agent for agent in self.world.agents.values() if abs(agent.position[0] - hearth[0]) + abs(agent.position[1] - hearth[1]) <= 1
            ]
            if len(cooks_and_guests) >= 2 and self.world.tick_count % max(4, int(round(5 * self.config.ticks_per_second))) == 0:
                self.world.village_morale = min(12.0, self.world.village_morale + 0.08)
                for agent in cooks_and_guests[:3]:
                    agent.comfort_ticks = min(agent.comfort_ticks + 1, 16)

    def _schedule_decisions(self) -> None:
        for agent in self.world.agents.values():
            if agent.name in self.pending_decisions:
                continue
            if agent.is_sleeping or agent.current_path:
                continue
            if self.world.tick_count < agent.next_think_tick:
                continue
            self._submit_decision(agent)

    def _submit_decision(self, agent: AgentState) -> None:
        observation = build_observation(self.config, self.world, agent, self.memory_store, self.relationships)
        personality = next(character.personality for character in self.config.characters if character.name == agent.name)
        request = DecisionRequest(
            agent_name=agent.name,
            observation=observation,
            system_prompt=build_system_prompt(agent, personality),
            tools=TOOLS,
        )
        agent.last_observation = observation
        future = self.executor.submit(self.decision_policy.decide, request)
        self.pending_decisions[agent.name] = PendingDecision(agent_name=agent.name, future=future)

    def _poll_futures(self) -> None:
        finished: list[str] = []
        for agent_name, pending in self.pending_decisions.items():
            if not pending.future.done():
                continue
            finished.append(agent_name)
            agent = self.world.agents[agent_name]
            try:
                decision = pending.future.result()
            except Exception as exc:
                decision = Decision(tool_name="wait", arguments={"thought": f"Error: {exc}"}, thought=f"Error: {exc}")
            self._apply_decision(agent, decision)
        for agent_name in finished:
            self.pending_decisions.pop(agent_name, None)

    def _project_escape_decision(self, agent: AgentState) -> Decision | None:
        priorities = [
            ("wood_shed", "wood_shed_site", "wood"),
            ("granary", "granary_site", "wheat"),
            ("market_stalls", "market_stalls_site", "wood"),
            ("bathhouse", "bathhouse_site", "wood"),
            ("greenhouse", "greenhouse_site", "wood"),
        ]
        for project_name, site_name, preferred_item in priorities:
            project = self.world.public_projects.get(project_name)
            if project is None or project.completed:
                continue
            remaining = project.remaining()
            contribution = {
                "wood": 0,
                "wheat": 0,
            }
            for item in ("wood", "wheat"):
                contribution[item] = min(agent.inventory.get(item, 0), remaining.get(item, 0))
            if preferred_item in contribution and contribution[preferred_item] <= 0 and all(value <= 0 for value in contribution.values()):
                continue
            if all(value <= 0 for value in contribution.values()):
                continue
            if abs(agent.position[0] - project.site[0]) + abs(agent.position[1] - project.site[1]) <= 1:
                return Decision(
                    tool_name="contribute_project",
                    arguments={
                        "project_name": project_name,
                        "contribution": contribution,
                        "thought": f"I should stop looping and put my resources into the {project.title}.",
                    },
                    thought=f"I should stop looping and put my resources into the {project.title}.",
                )
            return Decision(
                tool_name="move",
                arguments={
                    "target": site_name,
                    "thought": f"I should stop looping here and head to the {project.title} site.",
                },
                thought=f"I should stop looping here and head to the {project.title} site.",
            )
        return None

    def _is_night(self) -> bool:
        return self.world.time_of_day <= 0.25 or self.world.time_of_day >= 0.8

    def _adjacent_matching_tiles(self, agent: AgentState, predicate) -> list[tuple[int, int]]:
        matches: list[tuple[int, int]] = []
        for position in self.world.neighbors(agent.position):
            if predicate(self.world.tile_at(position)):
                matches.append(position)
        return matches

    def _recovery_target_label(self, agent: AgentState) -> str:
        well = self.world.landmarks.get("well")
        if well is not None:
            return "well"
        return "my_house"

    def _reroute_low_energy_decision(self, agent: AgentState, decision: Decision) -> Decision:
        if agent.is_sleeping or decision.tool_name in {"sleep", "rest", "wait", "accept_trade", "reject_trade"}:
            return decision

        very_low_energy = agent.energy <= 0.12
        low_energy = agent.energy <= 0.22
        strenuous_tools = {
            "chop_wood",
            "farm",
            "forage",
            "fish",
            "gather_flowers",
            "cook_meal",
            "contribute_project",
        }
        recovery_target = self._recovery_target_label(agent)
        recovery_distance = None
        if recovery_target == "well":
            well = self.world.landmarks.get("well")
            if well is not None:
                recovery_distance = abs(agent.position[0] - well[0]) + abs(agent.position[1] - well[1])

        if very_low_energy and agent.position == agent.house_position and agent.energy <= 0.85:
            return Decision(
                tool_name="sleep",
                arguments={"thought": "My energy is almost gone. I should sleep now instead of forcing another task."},
                thought="My energy is almost gone. I should sleep now instead of forcing another task.",
                usage=decision.usage,
            )
        if very_low_energy and recovery_target == "well" and recovery_distance is not None and recovery_distance <= 1:
            return Decision(
                tool_name="rest",
                arguments={"thought": "My energy is almost gone. Resting by the well is safer than forcing another task."},
                thought="My energy is almost gone. Resting by the well is safer than forcing another task.",
                usage=decision.usage,
            )
        if low_energy and decision.tool_name in strenuous_tools:
            if agent.position == agent.house_position:
                return Decision(
                    tool_name="rest",
                    arguments={"thought": "I should recover at home before I push into another demanding task."},
                    thought="I should recover at home before I push into another demanding task.",
                    usage=decision.usage,
                )
            if recovery_target == "well" and recovery_distance is not None and recovery_distance <= 1:
                return Decision(
                    tool_name="rest",
                    arguments={"thought": "I am running low on energy. A short rest near the well is smarter than collapsing mid-task."},
                    thought="I am running low on energy. A short rest near the well is smarter than collapsing mid-task.",
                    usage=decision.usage,
                )
            return Decision(
                tool_name="move",
                arguments={"target": "my_house" if self._is_night() else recovery_target, "thought": "My energy is running low. I should recover before trying more work."},
                thought="My energy is running low. I should recover before trying more work.",
                usage=decision.usage,
            )
        if very_low_energy and decision.tool_name == "move":
            target = str(decision.arguments.get("target", "")).strip().lower()
            if target not in {"my_house", "well"}:
                return Decision(
                    tool_name="move",
                    arguments={"target": "my_house" if self._is_night() else recovery_target, "thought": "I am too exhausted for a long detour. Recovery comes first."},
                    thought="I am too exhausted for a long detour. Recovery comes first.",
                    usage=decision.usage,
                )
        return decision

    def _correct_action_target(self, agent: AgentState, decision: Decision) -> Decision:
        tile_tool_specs = {
            "chop_wood": {
                "resource_name": "forest",
                "fallback_target": "forest",
                "predicate": lambda tile: tile.kind == "forest" and tile.wood > 0,
            },
            "forage": {
                "resource_name": "berry grove",
                "fallback_target": "berry_grove",
                "predicate": lambda tile: tile.kind == "berry_grove" and tile.berries > 0,
            },
            "fish": {
                "resource_name": "pond water",
                "fallback_target": "village_pond",
                "predicate": lambda tile: tile.kind == "water" and tile.fish > 0,
            },
            "gather_flowers": {
                "resource_name": "flower garden",
                "fallback_target": "flower_garden",
                "predicate": lambda tile: tile.kind == "flower_garden" and tile.flowers > 0,
            },
        }
        if decision.tool_name in tile_tool_specs:
            spec = tile_tool_specs[decision.tool_name]
            raw_position = str(decision.arguments.get("tile_position", ""))
            position = self.action_resolver._parse_position(raw_position)
            if position is not None and self.world.in_bounds(position):
                tile = self.world.tile_at(position)
                if position == agent.position or self.world.is_adjacent(agent.position, position):
                    if spec["predicate"](tile):
                        return decision
                adjacent_match = self._adjacent_matching_tiles(agent, spec["predicate"])
                if adjacent_match:
                    corrected = adjacent_match[0]
                    corrected_arguments = dict(decision.arguments)
                    corrected_arguments["tile_position"] = f"{corrected[0]},{corrected[1]}"
                    corrected_arguments["thought"] = f"{decision.thought} I should use the actual nearby {spec['resource_name']} tile instead."
                    return Decision(decision.tool_name, corrected_arguments, corrected_arguments["thought"], decision.raw_text, decision.usage)
            nearest = self._nearest_matching_tile(agent.position, spec["predicate"])
            if nearest is not None:
                return Decision(
                    tool_name="move",
                    arguments={
                        "target": f"{nearest[0]},{nearest[1]}",
                        "thought": f"I cannot {decision.tool_name} here. I should move to real {spec['resource_name']} nearby first.",
                    },
                    thought=f"I cannot {decision.tool_name} here. I should move to real {spec['resource_name']} nearby first.",
                    usage=decision.usage,
                )
            return Decision(
                tool_name="move",
                arguments={
                    "target": spec["fallback_target"],
                    "thought": f"I need to head toward a real {spec['resource_name']} before trying this again.",
                },
                thought=f"I need to head toward a real {spec['resource_name']} before trying this again.",
                usage=decision.usage,
            )

        if decision.tool_name == "farm":
            action = str(decision.arguments.get("action", "harvest"))
            position = self.action_resolver._parse_position(str(decision.arguments.get("tile_position", "")))
            if action == "harvest":
                predicate = lambda tile: tile.kind == "farm" and tile.crop_stage == "ripe"
                target_name = "ripe farm tile"
            else:
                predicate = lambda tile: tile.kind == "farm" and tile.crop_stage == "empty"
                target_name = "empty farm tile"
            if position is not None and self.world.in_bounds(position):
                tile = self.world.tile_at(position)
                if (position == agent.position or self.world.is_adjacent(agent.position, position)) and predicate(tile):
                    return decision
            adjacent_match = self._adjacent_matching_tiles(agent, predicate)
            if adjacent_match:
                corrected = adjacent_match[0]
                corrected_arguments = dict(decision.arguments)
                corrected_arguments["tile_position"] = f"{corrected[0]},{corrected[1]}"
                corrected_arguments["thought"] = f"{decision.thought} I should use the real nearby {target_name} instead."
                return Decision(decision.tool_name, corrected_arguments, corrected_arguments["thought"], decision.raw_text, decision.usage)
            nearest = self._nearest_matching_tile(agent.position, predicate)
            if nearest is not None:
                return Decision(
                    tool_name="move",
                    arguments={
                        "target": f"{nearest[0]},{nearest[1]}",
                        "thought": f"I need to move to a {target_name} before trying to farm.",
                    },
                    thought=f"I need to move to a {target_name} before trying to farm.",
                    usage=decision.usage,
                )
            return Decision(
                tool_name="move",
                arguments={"target": "communal_farm", "thought": "I should head to the communal farm before trying to farm again."},
                thought="I should head to the communal farm before trying to farm again.",
                usage=decision.usage,
            )

        if decision.tool_name in {"speak", "offer_trade", "give_gift", "propose_alliance"}:
            target_name = str(decision.arguments.get("target") or decision.arguments.get("target_agent") or "").strip()
            if decision.tool_name == "speak" and target_name.lower() in {"everyone", "nearby", "all"}:
                return decision
            if target_name in self.world.agents:
                other = self.world.agents[target_name]
                if not self.world.is_adjacent(agent.position, other.position):
                    return Decision(
                        tool_name="move",
                        arguments={"target": target_name, "thought": f"I need to get adjacent to {target_name} before I can do that."},
                        thought=f"I need to get adjacent to {target_name} before I can do that.",
                        usage=decision.usage,
                    )
        return decision

    def _escape_repetitive_decision(self, agent: AgentState, decision: Decision) -> Decision:
        if agent.repeated_action_count < 4 and agent.repeated_tool_count < 5:
            return decision
        if decision.tool_name not in {"chop_wood", "farm", "forage", "fish", "gather_flowers"}:
            return decision

        project_escape = self._project_escape_decision(agent)
        if project_escape is not None:
            return project_escape

        if agent.energy < 0.4:
            well = self.world.landmarks.get("well")
            if well is not None and abs(agent.position[0] - well[0]) + abs(agent.position[1] - well[1]) <= 1:
                return Decision(
                    tool_name="rest",
                    arguments={"thought": "I have been looping on wood. A short recovery break near the well will help."},
                    thought="I have been looping on wood. A short recovery break near the well will help.",
                )
            return Decision(
                tool_name="move",
                arguments={"target": "well", "thought": "I have been looping on wood. I should break away and recover at the well."},
                thought="I have been looping on wood. I should break away and recover at the well.",
            )

        if self.world.is_market_active() or self.world.tick_count - agent.last_social_tick >= 6:
            return Decision(
                tool_name="move",
                arguments={"target": "village_plaza", "thought": "I have looped on wood too long. I should head to the plaza and reconnect with others."},
                thought="I have looped on wood too long. I should head to the plaza and reconnect with others.",
            )

        if self.world.village_food <= 5.0 and agent.inventory.get("berries", 0) <= 0:
            return Decision(
                tool_name="move",
                arguments={"target": "berry_grove", "thought": "I have looped on wood too long. Fresh food would be more useful right now."},
                thought="I have looped on wood too long. Fresh food would be more useful right now.",
            )

        return Decision(
            tool_name="move",
            arguments={"target": "communal_farm", "thought": "I have looped on wood too long. I should switch tasks and go where people and food are."},
            thought="I have looped on wood too long. I should switch tasks and go where people and food are.",
        )

    def _apply_decision(self, agent: AgentState, decision: Decision) -> None:
        previous_tool = agent.last_tool
        thought = decision.arguments.get("thought", decision.thought)
        agent.last_thought = str(thought)
        agent.last_tool = decision.tool_name
        action_signature = f"{decision.tool_name}:{json_dumps_compact(decision.arguments)}"
        if action_signature == agent.last_action_signature:
            agent.repeated_action_count += 1
        else:
            agent.last_action_signature = action_signature
            agent.repeated_action_count = 1
        if decision.tool_name == previous_tool:
            agent.repeated_tool_count += 1
        else:
            agent.repeated_tool_count = 1
        if self.config.log_thoughts:
            print(f"[{agent.name}] {decision.tool_name}: {thought}")
        self.cost_tracker.record(decision.usage)

        escaped_decision = self._escape_repetitive_decision(agent, decision)
        if escaped_decision is not decision:
            decision = escaped_decision
            agent.last_thought = escaped_decision.thought
            agent.last_tool = escaped_decision.tool_name
            if self.config.log_thoughts:
                print(f"[{agent.name}] reroute: repetitive {action_signature} -> {decision.tool_name}")

        corrected_decision = self._reroute_low_energy_decision(agent, decision)
        if corrected_decision is not decision:
            decision = corrected_decision
            agent.last_thought = corrected_decision.thought
            agent.last_tool = corrected_decision.tool_name
            if self.config.log_thoughts:
                print(f"[{agent.name}] reroute: low-energy -> {decision.tool_name}")

        corrected_decision = self._correct_action_target(agent, decision)
        if corrected_decision is not decision:
            decision = corrected_decision
            agent.last_thought = corrected_decision.thought
            agent.last_tool = corrected_decision.tool_name
            if self.config.log_thoughts:
                print(f"[{agent.name}] reroute: invalid-target -> {decision.tool_name}")

        if decision.tool_name == "sleep" and agent.position != agent.house_position:
            rerouted = Decision(
                tool_name="move",
                arguments={"target": "my_house", "thought": "I need to get home before I can sleep."},
                thought="I need to get home before I can sleep.",
                usage=decision.usage,
            )
            decision = rerouted
            agent.last_thought = rerouted.thought
            agent.last_tool = rerouted.tool_name
            if self.config.log_thoughts:
                print(f"[{agent.name}] reroute: sleep -> move(my_house)")

        if decision.tool_name == "sleep" and agent.energy > 0.85:
            decision = Decision(
                tool_name="wait",
                arguments={"thought": "I am not tired enough to sleep, so I should pause or reconsider."},
                thought="I am not tired enough to sleep, so I should pause or reconsider.",
                usage=decision.usage,
            )
            agent.last_thought = decision.thought
            agent.last_tool = decision.tool_name

        if decision.tool_name == "move":
            target = self.resolve_move_target(agent.name, str(decision.arguments["target"]))
            if target is None:
                agent.pending_result = f"Action failed: could not resolve target {decision.arguments['target']}."
                agent.current_action = "idle"
            else:
                path = self.find_path(agent.position, target)
                if not path:
                    agent.pending_result = f"Action failed: no path to {target}."
                    agent.current_action = "idle"
                else:
                    agent.current_path = path[1:]
                    result = self.action_resolver.apply(agent, "move", decision.arguments)
                    agent.pending_result = result.message
                    if result.public_event is not None:
                        self._append_event_row(result.public_event, agent.last_thought)
        else:
            result = self.action_resolver.apply(agent, decision.tool_name, decision.arguments)
            agent.pending_result = result.message if result.success else f"Action failed: {result.message}"
            if decision.tool_name == "speak" and result.success:
                agent.speech_bubble_ttl = self.config.speech_bubble_seconds
            if result.public_event is not None:
                self._append_event_row(result.public_event, agent.last_thought)

        if decision.tool_name != "move":
            agent.next_think_tick = self.world.tick_count + 1

    def _append_event_row(self, event, thought: str) -> None:
        with self._csv_lock:
            with Path(self.config.event_log_file).open("a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        event.tick,
                        event.day,
                        f"{event.time_of_day:.3f}",
                        event.kind,
                        event.actor,
                        event.target or "",
                        event.location or "",
                        event.summary,
                        thought,
                    ]
                )

    def resolve_move_target(self, agent_name: str, target: str) -> tuple[int, int] | None:
        if "," in target:
            left, right = target.split(",", 1)
            try:
                return int(left.strip()), int(right.strip())
            except ValueError:
                return None
        agent = self.world.agents[agent_name]
        target_key = target.strip().lower()
        if target_key == "my_house":
            return agent.house_position
        if target in self.world.agents:
            return self.world.agents[target].position
        for other_name, other_agent in self.world.agents.items():
            if other_name.lower() == target_key:
                return other_agent.position
        if target_key in self.world.landmarks:
            return self.world.landmarks[target_key]
        if target_key.endswith("_house"):
            owner = target_key[:-6]
            for other_name, other_agent in self.world.agents.items():
                if other_name.lower() == owner:
                    return other_agent.house_position
        if target_key in {"nearest_forest", "forest"}:
            return self._nearest_matching_tile(agent.position, lambda tile: tile.kind == "forest" and tile.wood > 0)
        if target_key in {"berry_grove", "nearest_berries", "berries"}:
            return self._nearest_matching_tile(agent.position, lambda tile: tile.kind == "berry_grove" and tile.berries > 0)
        if target_key in {"pond", "village_pond", "nearest_pond"}:
            return self._nearest_matching_tile(agent.position, lambda tile: tile.kind == "water" and tile.fish > 0)
        if target_key in {"flowers", "flower_garden", "nearest_flowers"}:
            return self._nearest_matching_tile(agent.position, lambda tile: tile.kind == "flower_garden" and tile.flowers > 0)
        if target_key in {"hearth", "community_hearth"}:
            return self.world.landmarks.get("community_hearth")
        if target_key in {"board", "notice_board"}:
            return self.world.landmarks.get("notice_board")
        if target_key == "well":
            return self.world.landmarks.get("well")
        if target_key in {"nearest_farm", "farm"}:
            return self._nearest_matching_tile(
                agent.position,
                lambda tile: tile.kind == "farm" and tile.crop_stage in {"ripe", "empty", "growing"},
            )
        if target_key in {"village_center", "center"}:
            return self.world.landmarks.get("village_plaza", (self.world.size // 2, self.world.size // 2))
        return None

    def _nearest_matching_tile(self, origin: tuple[int, int], predicate) -> tuple[int, int] | None:
        best_position = None
        best_distance = None
        for y, row in enumerate(self.world.grid):
            for x, tile in enumerate(row):
                if not predicate(tile):
                    continue
                distance = abs(x - origin[0]) + abs(y - origin[1])
                if best_distance is None or distance < best_distance:
                    best_position = (x, y)
                    best_distance = distance
        return best_position

    def find_path(self, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
        if start == goal:
            return [start]
        frontier = [start]
        came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        index = 0
        while index < len(frontier):
            current = frontier[index]
            index += 1
            if current == goal:
                break
            for neighbor in self.world.neighbors(current):
                if neighbor in came_from or not self.world.is_passable(neighbor):
                    continue
                came_from[neighbor] = current
                frontier.append(neighbor)
        if goal not in came_from:
            return []
        current = goal
        path = [current]
        while current != start:
            current = came_from[current]
            assert current is not None
            path.append(current)
        path.reverse()
        return path
