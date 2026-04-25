from __future__ import annotations

from sim.actions import ActionResolver
from sim.memory import MemoryStore
from sim.relationships import RelationshipGraph
from sim.world import generate_world


def test_action_resolver_validates_and_applies_actions(app_config) -> None:
    world = generate_world(app_config)
    memory = MemoryStore(app_config.resolve_path(app_config.data_dir) / "memory", list(world.agents.keys()))
    relationships = RelationshipGraph(list(world.agents.keys()))
    resolver = ActionResolver(world, memory, relationships)

    mira = world.agents["Mira"]
    fen = world.agents["Fen"]

    fen.position = (10, 10)
    result = resolver.apply(
        mira,
        "offer_trade",
        {
            "target_agent": "Fen",
            "offer": {"wood": 1},
            "request": {"wheat": 1},
            "message": "Trade?",
            "thought": "Try trading.",
        },
    )
    assert not result.success

    farm_tile = next(
        (x, y)
        for y, row in enumerate(world.grid)
        for x, tile in enumerate(row)
        if tile.kind == "farm"
    )
    mira.position = (farm_tile[0] - 1, farm_tile[1])
    world.tile_at(farm_tile).crop_stage = "empty"
    mira.inventory["wheat"] = 2
    plant = resolver.apply(
        mira,
        "farm",
        {"action": "plant", "tile_position": f"{farm_tile[0]},{farm_tile[1]}", "thought": "Plant wheat."},
    )
    assert plant.success
    assert world.tile_at(farm_tile).crop_stage == "growing"

    forest_tile = next(
        (x, y)
        for y, row in enumerate(world.grid)
        for x, tile in enumerate(row)
        if tile.kind == "forest" and tile.wood > 0
    )
    mira.position = (forest_tile[0] - 1, forest_tile[1])
    chop = resolver.apply(
        mira,
        "chop_wood",
        {"tile_position": f"{forest_tile[0]},{forest_tile[1]}", "thought": "Need wood."},
    )
    assert chop.success
    assert mira.inventory["wood"] >= 3

    fen.position = mira.position
    bonus_chop = resolver.apply(
        mira,
        "chop_wood",
        {"tile_position": f"{forest_tile[0]},{forest_tile[1]}", "thought": "Need more wood."},
    )
    assert bonus_chop.success
    assert "teamwork" in bonus_chop.message.lower()

    berry_tile = next(
        (x, y)
        for y, row in enumerate(world.grid)
        for x, tile in enumerate(row)
        if tile.kind == "berry_grove" and tile.berries > 0
    )
    mira.position = (berry_tile[0], berry_tile[1] - 1)
    mira.energy = 0.3
    forage = resolver.apply(
        mira,
        "forage",
        {"tile_position": f"{berry_tile[0]},{berry_tile[1]}", "thought": "Gather berries."},
    )
    assert forage.success
    assert mira.inventory["berries"] >= 2
    assert mira.energy > 0.3

    pond_tile = next(
        (x, y)
        for y, row in enumerate(world.grid)
        for x, tile in enumerate(row)
        if tile.kind == "water" and tile.fish > 0
    )
    mira.position = (pond_tile[0] - 1, pond_tile[1])
    fish = resolver.apply(
        mira,
        "fish",
        {"tile_position": f"{pond_tile[0]},{pond_tile[1]}", "thought": "Catch dinner."},
    )
    assert fish.success
    assert mira.inventory["fish"] >= 1

    flower_tile = next(
        (x, y)
        for y, row in enumerate(world.grid)
        for x, tile in enumerate(row)
        if tile.kind == "flower_garden" and tile.flowers > 0
    )
    starting_morale = world.village_morale
    mira.position = (flower_tile[0], flower_tile[1] - 1)
    flowers = resolver.apply(
        mira,
        "gather_flowers",
        {"tile_position": f"{flower_tile[0]},{flower_tile[1]}", "thought": "Pick a few flowers."},
    )
    assert flowers.success
    assert mira.inventory["flowers"] >= 1
    assert world.village_morale > starting_morale

    hearth = world.landmarks["community_hearth"]
    mira.position = hearth
    mira.inventory["wood"] = 2
    mira.inventory["wheat"] = 2
    mira.inventory["fish"] = 1
    cook = resolver.apply(
        mira,
        "cook_meal",
        {"ingredient": "fish", "quantity": 1, "thought": "Cook something warm."},
    )
    assert cook.success
    assert mira.inventory["meal"] >= 3
    assert world.village_food > 5.8

    mira.position = mira.house_position
    mira.energy = 0.95
    sleep = resolver.apply(mira, "sleep", {"thought": "Rest."})
    assert not sleep.success

    mira.position = (0, 0)
    mira.energy = 0.2
    rest = resolver.apply(mira, "rest", {"thought": "Catch my breath."})
    assert rest.success
    assert mira.energy > 0.2

    mira.position = (0, 0)
    mira.energy = 0.2
    sleep = resolver.apply(mira, "sleep", {"thought": "Rest."})
    assert not sleep.success

    granary = world.public_projects["granary"]
    mira.position = granary.site
    mira.inventory["wood"] = 3
    mira.inventory["wheat"] = 4
    contribution = resolver.apply(
        mira,
        "contribute_project",
        {
            "project_name": "granary",
            "contribution": {"wood": 2, "wheat": 3},
            "thought": "Help the village.",
        },
    )
    assert contribution.success
    assert world.public_projects["granary"].progress["wood"] == 2
    assert world.public_projects["granary"].progress["wheat"] == 3

    fen.position = fen.house_position
    mira.position = (fen.house_position[0], fen.house_position[1] - 1)
    mira.inventory["flowers"] = 12
    gift = resolver.apply(
        mira,
        "give_gift",
        {
            "target_agent": "Fen",
            "item": "flowers",
            "quantity": 2,
            "message": "These are for you.",
            "thought": "A visit and gift should help the relationship.",
        },
    )
    assert gift.success
    assert fen.inventory["flowers"] >= 12
    assert relationships.get("Fen", "Mira").favor > 0

    alliance_offer = resolver.apply(
        mira,
        "propose_alliance",
        {
            "target_agent": "Fen",
            "message": "Let's back each other up.",
            "thought": "Closer cooperation could help both of us.",
        },
    )
    assert alliance_offer.success
    proposal_id = next(iter(world.pending_alliances.keys()))
    alliance_accept = resolver.apply(
        fen,
        "accept_alliance",
        {"proposal_id": proposal_id, "thought": "That partnership sounds worthwhile."},
    )
    assert alliance_accept.success
    assert relationships.are_allies("Mira", "Fen")

    mira.position = mira.house_position
    fire = resolver.apply(mira, "light_fire", {"thought": "A warm house will make the night easier."})
    assert fire.success
    assert mira.house_fire_ticks > 0

    mira.position = (10, 10)
    fen.position = (11, 10)
    broadcast = resolver.apply(
        mira,
        "speak",
        {"message": "Market at the plaza soon.", "target": "everyone", "thought": "Anyone nearby should hear this."},
    )
    assert broadcast.success
    assert fen.last_social_tick == world.tick_count
