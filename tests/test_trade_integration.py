from __future__ import annotations

from sim.agent import Decision
from sim.engine import SimulationEngine

from tests.helpers import ScriptedPolicy


def test_trade_completes_end_to_end(app_config) -> None:
    policy = ScriptedPolicy(
        {
            "Mira": [
                Decision(
                    "offer_trade",
                    {
                        "target_agent": "Fen",
                        "offer": {"wood": 1},
                        "request": {"wheat": 1},
                        "message": "Wood for wheat?",
                        "thought": "I need food.",
                    },
                    "I need food.",
                ),
                Decision("wait", {"thought": "Done."}, "Done."),
            ],
            "Fen": [
                Decision("wait", {"thought": "Observe first."}, "Observe first."),
                Decision("accept_trade", {"trade_id": "PLACEHOLDER", "thought": "That works for me."}, "That works for me."),
            ],
        }
    )
    engine = SimulationEngine(app_config, decision_policy=policy)
    engine.world.agents["Mira"].position = (5, 5)
    engine.world.agents["Fen"].position = (6, 5)

    engine.tick()
    engine.wait_for_idle()
    engine.update(0.01)

    trade_id = next(iter(engine.world.pending_trades.keys()))
    policy.plans["Fen"][0].arguments["trade_id"] = trade_id

    engine.tick()
    engine.wait_for_idle()
    engine.update(0.01)

    trade = engine.world.pending_trades[trade_id]
    assert trade.status == "accepted"
    assert engine.world.agents["Mira"].inventory["wheat"] >= 3
    assert engine.world.agents["Fen"].inventory["wood"] >= 2
    assert engine.relationships.get("Mira", "Fen").trade_count == 1
    assert engine.world.agents["Mira"].comfort_ticks > 0
    assert engine.world.agents["Fen"].comfort_ticks > 0
    engine.shutdown()
