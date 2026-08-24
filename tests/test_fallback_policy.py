from __future__ import annotations

from sim.agent import HeuristicDecisionPolicy
from sim.engine import SimulationEngine


def test_fallback_policy_runs_engine_without_waiting_forever(app_config) -> None:
    engine = SimulationEngine(app_config)
    assert isinstance(engine.decision_policy, HeuristicDecisionPolicy)

    observed_tools: list[str] = []
    original_apply = engine._apply_decision

    def collecting_apply(agent, decision):
        observed_tools.append(decision.tool_name)
        return original_apply(agent, decision)

    engine._apply_decision = collecting_apply
    try:
        for _ in range(100):
            engine.tick()
            engine.wait_for_idle()
    finally:
        engine.shutdown()

    assert observed_tools, "fallback policy never returned a decision"
    non_wait = [tool for tool in observed_tools if tool != "wait"]
    assert len(non_wait) >= 10, f"fallback policy mostly waits; observed: {observed_tools[:30]}"
    assert len(set(non_wait)) >= 2, f"fallback policy has no variety; observed: {sorted(set(observed_tools))}"


def test_fallback_policy_moves_agents_off_home_tiles(app_config) -> None:
    engine = SimulationEngine(app_config)
    start_positions = {name: agent.position for name, agent in engine.world.agents.items()}
    try:
        for _ in range(100):
            engine.tick()
            engine.wait_for_idle()
        moved = [
            name
            for name, agent in engine.world.agents.items()
            if agent.position != start_positions[name]
        ]
        assert moved, "no agent ever moved under the fallback policy"
    finally:
        engine.shutdown()
