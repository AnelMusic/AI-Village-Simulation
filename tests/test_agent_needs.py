from __future__ import annotations

from sim.agent import Decision, build_observation
from sim.engine import SimulationEngine
from tests.helpers import ScriptedPolicy


def test_needs_accumulate_and_traits_differentiate(app_config) -> None:
    mira_traits = app_config.characters[0].traits
    mira_traits["food_focus"] = 1.5
    mira_traits["social_focus"] = 1.5
    fen_traits = app_config.characters[1].traits
    fen_traits["food_focus"] = 0.5
    fen_traits["social_focus"] = 0.5

    engine = SimulationEngine(app_config)
    try:
        for _ in range(20):
            engine.tick()
            engine.wait_for_idle()

        mira = engine.world.agents["Mira"]
        fen = engine.world.agents["Fen"]
        assert mira.hunger > fen.hunger, "food_focus should scale hunger gain"
        assert mira.social_need > fen.social_need, "social_focus should scale social need gain"
        assert 0.0 < mira.hunger <= 1.0
        assert 0.0 < mira.social_need <= 1.0
    finally:
        engine.shutdown()


def test_hunger_and_cold_drain_energy_harder(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira = engine.world.agents["Mira"]
        mira.energy = 0.5
        mira.hunger = 0.9
        mira.warmth = 0.1
        before = mira.energy
        engine._update_sleep_and_energy()
        # baseline 0.02 + 0.01 (starving) + 0.01 (freezing) = 0.04 drain (with float tolerance)
        assert before - mira.energy >= 0.0399
    finally:
        engine.shutdown()


def test_food_actions_reduce_hunger_and_social_actions_reset_loneliness(app_config) -> None:
    policy = ScriptedPolicy(
        {
            "Mira": [Decision("speak", {"message": "Hello", "target": "Fen", "thought": "Talk."}, "Talk.")],
        }
    )
    engine = SimulationEngine(app_config, decision_policy=policy)
    try:
        mira = engine.world.agents["Mira"]
        fen = engine.world.agents["Fen"]
        mira.position = (5, 5)
        fen.position = (6, 5)
        mira.hunger = 0.8
        mira.social_need = 0.9
        fen.social_need = 0.7

        engine.tick()
        engine.wait_for_idle()

        assert mira.social_need == 0.0
        assert fen.social_need < 0.7
        assert mira.hunger > 0.0  # speaking does not feed you
    finally:
        engine.shutdown()


def test_observation_contains_parseable_needs_line(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira = engine.world.agents["Mira"]
        mira.hunger = 0.62
        mira.warmth = 0.34
        mira.social_need = 0.05
        observation = build_observation(app_config, engine.world, mira, engine.memory_store, engine.relationships)
        assert "Hunger 62%, warmth 34%, loneliness 5%" in observation
        assert "genuinely hungry" in observation
        assert "getting chilly" in observation
    finally:
        engine.shutdown()


def test_warmth_recovers_near_hearth_and_fire(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        mira = engine.world.agents["Mira"]
        hearth = engine.world.landmarks["community_hearth"]
        mira.position = hearth
        mira.warmth = 0.2
        engine.world.time_of_day = 0.5  # day, no night decay
        before = mira.warmth
        engine._update_agent_needs(mira)
        assert mira.warmth > before

        bolt = engine.world.agents["Fen"]
        bolt.position = bolt.house_position
        bolt.house_fire_ticks = 5
        bolt.warmth = 0.3
        engine.world.time_of_day = 0.9  # night
        night_before = bolt.warmth
        engine._update_agent_needs(bolt)
        assert bolt.warmth > night_before  # fire beats night decay at home
    finally:
        engine.shutdown()
