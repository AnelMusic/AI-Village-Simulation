from __future__ import annotations

from sim.agent import build_board_notice, build_observation
from sim.engine import SimulationEngine


def test_contributors_are_credited_and_gain_reputation(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira = engine.world.agents["Mira"]
        fen = engine.world.agents["Fen"]
        granary = engine.world.public_projects["granary"]
        mira.position = granary.site
        fen.position = (granary.site[0] + 1, granary.site[1])
        mira.inventory.update({"wood": 6, "wheat": 10})
        fen.inventory.update({"wood": 6, "wheat": 10})

        trust_before = engine.relationships.get("Mira", "Fen").trust
        engine.action_resolver.apply(
            mira,
            "contribute_project",
            {"project_name": "granary", "contribution": {"wood": 6, "wheat": 5}, "thought": "Build."},
        )
        assert granary.total_contribution("Mira") == 11
        assert not granary.completed

        engine.action_resolver.apply(
            fen,
            "contribute_project",
            {"project_name": "granary", "contribution": {"wood": 0, "wheat": 5}, "thought": "Finish it."},
        )
        assert granary.completed
        assert granary.total_contribution("Mira") == 11
        assert granary.total_contribution("Fen") == 5

        # Reputation: the village trusts visible builders a little more.
        assert engine.relationships.get("Mira", "Fen").trust > trust_before
        assert "Mira" in granary.contributor_summary()
        assert "Fen" in granary.contributor_summary()
    finally:
        engine.shutdown()


def test_board_notice_suggests_roles(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        bolt = engine.world.agents["Mira"]
        bolt.inventory["wood"] = 4
        notice = build_board_notice(engine.world)
        assert "could bring wood" in notice

        observation = build_observation(
            app_config, engine.world, bolt, engine.memory_store, engine.relationships
        )
        assert "Role suggestion" in observation or "could bring" in observation
    finally:
        engine.shutdown()


def test_project_observation_shows_progress_credit(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira = engine.world.agents["Mira"]
        granary = engine.world.public_projects["granary"]
        mira.position = granary.site
        mira.inventory.update({"wood": 2, "wheat": 0})
        engine.action_resolver.apply(
            mira,
            "contribute_project",
            {"project_name": "granary", "contribution": {"wood": 2, "wheat": 0}, "thought": "Help."},
        )
        observation = build_observation(
            app_config, engine.world, mira, engine.memory_store, engine.relationships
        )
        assert "Contributions so far" in observation
        assert "Mira (wood:2)" in observation
    finally:
        engine.shutdown()
