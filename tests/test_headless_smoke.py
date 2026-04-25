from __future__ import annotations

from pathlib import Path

from sim.agent import Decision
from sim.engine import SimulationEngine

from tests.helpers import ScriptedPolicy


def test_headless_engine_creates_logs_and_autosave(app_config) -> None:
    policy = ScriptedPolicy(
        {
            "Mira": [Decision("speak", {"message": "Hello there", "target": "Fen", "thought": "Greet Fen."}, "Greet Fen.")],
            "Fen": [Decision("wait", {"thought": "Listen."}, "Listen.")],
        }
    )
    engine = SimulationEngine(app_config, decision_policy=policy)
    engine.world.agents["Mira"].position = (5, 5)
    engine.world.agents["Fen"].position = (6, 5)
    engine.last_autosave_monotonic -= 10

    engine.tick()
    engine.wait_for_idle()
    engine.update(0.2)

    assert Path(app_config.save_file).exists()
    log_path = Path(app_config.event_log_file)
    assert log_path.exists()
    contents = log_path.read_text(encoding="utf-8")
    assert "Hello there" in contents
    engine.shutdown()


def test_repetitive_chopping_gets_rerouted(app_config) -> None:
    repeated_chops = [
        Decision("chop_wood", {"tile_position": "2,8", "thought": "Keep chopping."}, "Keep chopping.")
        for _ in range(5)
    ]
    policy = ScriptedPolicy({"Mira": repeated_chops})
    engine = SimulationEngine(app_config, decision_policy=policy)
    try:
        mira = engine.world.agents["Mira"]
        mira.position = (2, 9)
        mira.inventory["wood"] = 0

        for _ in range(4):
            engine.tick()
            engine.wait_for_idle()
            engine.update(0.01)

        assert mira.last_tool == "move"
        assert mira.move_target_label in {"wood_shed_site", "village_plaza", "communal_farm", "berry_grove"}
    finally:
        engine.shutdown()
