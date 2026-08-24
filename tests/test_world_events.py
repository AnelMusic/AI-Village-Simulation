from __future__ import annotations

from sim.agent import HeuristicDecisionPolicy, build_observation, DecisionRequest
from sim.engine import SimulationEngine


def test_storm_event_effects(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        engine._start_world_event("storm")
        assert engine.world.active_event is not None
        assert all(agent.interrupt_flag for agent in engine.world.agents.values())

        # Outside agents lose warmth faster than agents at home.
        mira = engine.world.agents["Mira"]
        fen = engine.world.agents["Fen"]
        mira.position = (4, 12)  # far from hearth and home
        fen.position = fen.house_position
        engine.world.time_of_day = 0.5  # day
        mira_warmth, fen_warmth = mira.warmth, fen.warmth
        engine._update_agent_needs(mira)
        engine._update_agent_needs(fen)
        assert mira.warmth < mira_warmth, "storm should chill agents outside"
        assert fen.warmth >= fen_warmth, "agent at home should not be storm-chilled during the day"

        # Village pressures worsen while the storm runs.
        warmth_before = engine.world.village_warmth
        food_before = engine.world.village_food
        engine._update_village_pressures()
        assert engine.world.village_warmth < warmth_before
        assert engine.world.village_food < food_before

        # The event expires and clears.
        engine.world.tick_count = engine.world.active_event["ends_tick"]
        engine._expire_world_event()
        assert engine.world.active_event is None
    finally:
        engine.shutdown()


def test_shortage_pauses_regeneration(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        grove = next(tile for row in engine.world.grid for tile in row if tile.kind == "berry_grove")
        grove.berries = 2
        engine._start_world_event("shortage")
        for _ in range(25):
            engine.world.tick_count += 1
            engine._grow_crops_and_regenerate_forest()
        assert grove.berries == 2, "regeneration should pause during a shortage"
    finally:
        engine.shutdown()


def test_festival_boosts_morale_and_social_recovery(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        morale_before = engine.world.village_morale
        engine._start_world_event("festival")
        assert engine.world.village_morale >= morale_before + 0.5

        mira = engine.world.agents["Mira"]
        plaza = engine.world.landmarks["village_plaza"]
        mira.position = plaza
        mira.social_need = 0.8
        engine.world.time_of_day = 0.5
        engine._update_agent_needs(mira)
        assert mira.social_need < 0.8

        observation = build_observation(app_config, engine.world, mira, engine.memory_store, engine.relationships)
        assert "festival" in observation.lower()
    finally:
        engine.shutdown()


def test_trader_event_rewards_completed_trades(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        engine._start_world_event("trader")
        mira = engine.world.agents["Mira"]
        fen = engine.world.agents["Fen"]
        mira.position, fen.position = (5, 5), (6, 5)
        mira.inventory["wood"] = 2
        fen.inventory["wheat"] = 2
        engine.action_resolver.apply(
            mira,
            "offer_trade",
            {
                "target_agent": "Fen",
                "offer": {"wood": 1, "wheat": 0, "berries": 0, "fish": 0, "flowers": 0, "meal": 0},
                "request": {"wood": 0, "wheat": 1, "berries": 0, "fish": 0, "flowers": 0, "meal": 0},
                "message": "Trade?",
                "thought": "Deal.",
            },
        )
        trade_id = next(iter(engine.world.pending_trades.keys()))
        food_before = engine.world.village_food
        result = engine.action_resolver.apply(fen, "accept_trade", {"trade_id": trade_id, "thought": "Yes."})
        assert result.success
        assert engine.world.village_food >= food_before + 0.2
    finally:
        engine.shutdown()


def test_heuristic_reacts_to_storm(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira = engine.world.agents["Mira"]
        engine._start_world_event("storm")
        mira.position = (10, 10)
        observation = build_observation(app_config, engine.world, mira, engine.memory_store, engine.relationships)
        policy = HeuristicDecisionPolicy()
        decision = policy.decide(
            DecisionRequest(agent_name="Mira", observation=observation, system_prompt="", tools=[])
        )
        assert decision.tool_name == "move"
        assert decision.arguments["target"] == "my_house"
    finally:
        engine.shutdown()


def test_random_event_scheduler_runs_within_a_day(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        engine.rng = __import__("random").Random(1)
        saw_event = False
        for _ in range(600):
            engine.tick()
            engine.wait_for_idle()
            if engine.world.active_event is not None or any(
                event.kind == "world_event" for event in engine.world.recent_events
            ):
                saw_event = True
                break
        assert saw_event, "scheduler should fire world events eventually"
    finally:
        engine.shutdown()
