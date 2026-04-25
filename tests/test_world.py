from __future__ import annotations

from pathlib import Path

from sim.engine import SimulationEngine
from sim.world import WorldState, generate_world


def test_world_generation_and_roundtrip(app_config, tmp_path: Path) -> None:
    world = generate_world(app_config)

    assert world.size == app_config.world_size
    for character in app_config.characters:
        tile = world.tile_at(character.house_position)
        assert tile.kind == "house"

    assert "village_plaza" in world.landmarks
    assert "well" in world.landmarks
    assert "community_hearth" in world.landmarks
    assert "notice_board" in world.landmarks
    assert "berry_grove" in world.landmarks
    assert "village_pond" in world.landmarks
    assert "flower_garden" in world.landmarks
    assert "communal_farm" in world.landmarks
    assert "granary" in world.public_projects
    assert "wood_shed" in world.public_projects
    assert "market_stalls" in world.public_projects
    assert "bathhouse" in world.public_projects
    assert "greenhouse" in world.public_projects
    assert any(tile.kind == "farm" for row in world.grid for tile in row)
    assert any(tile.kind == "berry_grove" for row in world.grid for tile in row)
    assert any(tile.kind == "flower_garden" for row in world.grid for tile in row)
    assert any(tile.kind == "water" and tile.fish > 0 for row in world.grid for tile in row)
    assert any(tile.kind == "hearth" for row in world.grid for tile in row)
    assert any(tile.kind == "notice_board" for row in world.grid for tile in row)
    assert any(tile.feature == "granary_site" for row in world.grid for tile in row)
    assert any(tile.feature == "wood_shed_site" for row in world.grid for tile in row)
    assert any(tile.feature == "market_site" for row in world.grid for tile in row)
    assert any(tile.feature == "bathhouse_site" for row in world.grid for tile in row)
    assert any(tile.feature == "greenhouse_site" for row in world.grid for tile in row)
    assert any(tile.feature == "dock" for row in world.grid for tile in row)
    for agent in world.agents.values():
        for item in ("wood", "wheat", "berries", "fish", "flowers", "meal"):
            assert agent.inventory.get(item, 0) >= 10

    forest_tiles = [
        (x, y)
        for y, row in enumerate(world.grid)
        for x, tile in enumerate(row)
        if tile.kind == "forest"
    ]
    assert forest_tiles

    engine = SimulationEngine(app_config, world=world)
    path = engine.find_path(app_config.characters[0].house_position, app_config.characters[1].house_position)
    assert path
    plaza_path = engine.find_path(app_config.characters[0].house_position, world.landmarks["village_plaza"])
    assert plaza_path

    save_path = tmp_path / "world_state.json"
    world.save(save_path)
    loaded = WorldState.load(save_path)
    assert loaded.to_dict() == world.to_dict()
    engine.shutdown()
