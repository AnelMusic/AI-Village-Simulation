from __future__ import annotations

from sim.agent import build_observation
from sim.engine import SimulationEngine


def test_seasons_advance_every_four_days(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        assert engine.world.season == "spring"

        def roll_day(day_before_rollover: int) -> None:
            engine.world.day = day_before_rollover
            engine.world.time_of_day = 1.0 - (engine.config.tick_interval_seconds / engine.config.day_length_seconds) / 2
            engine._advance_time()

        roll_day(4)
        assert engine.world.day == 5
        assert engine.world.season == "summer"
        roll_day(8)
        assert engine.world.season == "autumn"
        roll_day(12)
        assert engine.world.season == "winter"
        roll_day(16)
        assert engine.world.season == "spring"
    finally:
        engine.shutdown()


def test_winter_slows_regeneration(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        grove = next(tile for row in engine.world.grid for tile in row if tile.kind == "berry_grove")
        grove.berries = 0

        engine.world.season = "summer"
        summer_interval = max(5, int(round(20 * 0.9)))
        regenerated_summer = False
        for tick in range(1, summer_interval * 3):
            engine.world.tick_count = tick
            engine._grow_crops_and_regenerate_forest()
            if grove.berries > 0:
                regenerated_summer = True
                break
        assert regenerated_summer, "summer regen should be quick"

        grove.berries = 0
        engine.world.season = "winter"
        winter_interval = max(5, int(round(20 * 2.0)))
        # Winter regen must be strictly slower than summer regen.
        assert winter_interval > summer_interval
        for tick in range(1, summer_interval + 1):
            engine.world.tick_count = tick
            engine._grow_crops_and_regenerate_forest()
        assert grove.berries == 0, "berries should not regenerate within the summer window during winter"
    finally:
        engine.shutdown()


def test_observation_shows_stockpile_price_hints(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira = engine.world.agents["Mira"]
        # Make wood scarce across all inventories.
        for agent in engine.world.agents.values():
            agent.inventory.pop("wood", None)
        observation = build_observation(app_config, engine.world, mira, engine.memory_store, engine.relationships)
        assert "Village stockpiles" in observation
        assert "wood: 0 held by villagers - SCARCE, trades high" in observation
        assert "season: spring" in observation
    finally:
        engine.shutdown()


def test_winter_chills_agents(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira = engine.world.agents["Mira"]
        mira.position = (4, 12)  # away from hearth/home
        engine.world.time_of_day = 0.5  # day
        mira.warmth = 0.5

        engine.world.season = "spring"
        spring_warmth = mira.warmth = 0.5
        engine._update_agent_needs(mira)
        spring_change = mira.warmth - spring_warmth

        mira.warmth = spring_warmth
        engine.world.season = "winter"
        engine._update_agent_needs(mira)
        winter_change = mira.warmth - spring_warmth
        assert winter_change < spring_change, "winter days should feel colder than spring days"
    finally:
        engine.shutdown()
