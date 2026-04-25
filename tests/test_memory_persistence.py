from __future__ import annotations

from sim.engine import SimulationEngine


def test_memory_persists_across_restart(app_config) -> None:
    engine = SimulationEngine(app_config)
    engine.memory_store.get("Mira").remember(1, 1, "I shared food with Fen.", salience=3, tags=["trade"])
    engine.save_all()
    engine.shutdown()

    loaded = SimulationEngine.load_or_create(app_config)
    memories = loaded.memory_store.get("Mira").recall_lines()
    assert any("shared food" in line for line in memories)
    loaded.shutdown()
