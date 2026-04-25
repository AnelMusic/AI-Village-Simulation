from __future__ import annotations

from sim.agent import Decision, build_observation
from sim.engine import SimulationEngine


def test_engine_reroutes_exhausted_agents_to_recovery(app_config) -> None:
    engine = SimulationEngine(app_config)
    mira = engine.world.agents["Mira"]
    well = engine.world.landmarks["well"]
    forest_tile = next(
        (x, y)
        for y, row in enumerate(engine.world.grid)
        for x, tile in enumerate(row)
        if tile.kind == "forest" and tile.wood > 0 and abs(x - well[0]) + abs(y - well[1]) > 4
    )
    mira.position = (forest_tile[0] - 1, forest_tile[1])
    mira.energy = 0.10

    engine._apply_decision(
        mira,
        Decision(
            "chop_wood",
            {"tile_position": f"{forest_tile[0]},{forest_tile[1]}", "thought": "I should keep chopping."},
            "I should keep chopping.",
        ),
    )

    assert mira.last_tool == "move"
    assert "recover" in mira.last_thought.lower()
    assert mira.pending_result is not None and "Moving toward" in mira.pending_result


def test_engine_corrects_invalid_farm_target_to_real_farm(app_config) -> None:
    engine = SimulationEngine(app_config)
    mira = engine.world.agents["Mira"]
    farm_tile, standing_tile = next(
        ((x, y), (x - 1, y))
        for y, row in enumerate(engine.world.grid)
        for x, tile in enumerate(row)
        if tile.kind == "farm" and x > 0 and engine.world.tile_at((x - 1, y)).kind != "farm"
    )
    wrong_target = standing_tile
    mira.position = standing_tile
    mira.energy = 0.65
    engine.world.tile_at(farm_tile).crop_stage = "ripe"
    engine.world.tile_at(farm_tile).crop_progress = 1.0

    engine._apply_decision(
        mira,
        Decision(
            "farm",
            {"action": "harvest", "tile_position": f"{wrong_target[0]},{wrong_target[1]}", "thought": "Harvest this crop."},
            "Harvest this crop.",
        ),
    )

    assert mira.inventory["wheat"] >= 3
    assert mira.pending_result is not None and "harvested" in mira.pending_result.lower()


def test_observation_lists_immediate_valid_actions(app_config) -> None:
    engine = SimulationEngine(app_config)
    mira = engine.world.agents["Mira"]
    berry_tile = next(
        (x, y)
        for y, row in enumerate(engine.world.grid)
        for x, tile in enumerate(row)
        if tile.kind == "berry_grove" and tile.berries > 0
    )
    mira.position = (berry_tile[0], berry_tile[1] - 1)
    observation = build_observation(app_config, engine.world, mira, engine.memory_store, engine.relationships)

    assert "Immediate valid actions from where you stand" in observation
    assert "forage" in observation
