from __future__ import annotations

from pathlib import Path

from sim.agent import Decision
from sim.engine import SimulationEngine
from sim.world import WorldState
from tests.helpers import ScriptedPolicy


def hearth_cook_plan() -> Decision:
    return Decision(
        "submit_plan",
        {
            "goal": "Cook wheat at the hearth",
            "steps": [
                {"tool": "move", "arguments": {"target": "community_hearth", "thought": "Head to the hearth."}},
                {"tool": "cook_meal", "arguments": {"ingredient": "wheat", "quantity": 1, "thought": "Cook it."}},
            ],
            "thought": "The village needs food, so I will walk to the hearth and cook.",
        },
        "The village needs food, so I will walk to the hearth and cook.",
    )


def test_plan_executes_steps_without_consulting_policy(app_config) -> None:
    policy = ScriptedPolicy({"Mira": [hearth_cook_plan()]})
    engine = SimulationEngine(app_config, decision_policy=policy)
    try:
        mira = engine.world.agents["Mira"]
        mira.inventory["wheat"] = 2
        mira.inventory["wood"] = 2

        for _ in range(40):
            engine.tick()
            engine.wait_for_idle()
            if mira.plan is None and mira.inventory.get("meal", 0) > 0:
                break

        assert mira.inventory.get("meal", 0) > 0, "plan should have cooked a meal"
        assert mira.position == engine.world.landmarks["community_hearth"]
        # Only consulted for the initial plan submission; steps ran engine-side.
        assert policy.calls["Mira"] <= 2, f"policy consulted too often: {policy.calls['Mira']}"
        events = [event.kind for event in engine.world.recent_events]
        assert "plan_start" in events
    finally:
        engine.shutdown()


def test_failed_step_aborts_plan_and_reconsults(app_config) -> None:
    bad_plan = Decision(
        "submit_plan",
        {
            "goal": "Cook somewhere impossible",
            "steps": [
                {"tool": "cook_meal", "arguments": {"ingredient": "wheat", "quantity": 1, "thought": "Cook it."}},
            ],
            "thought": "I will cook right here.",
        },
        "I will cook right here.",
    )
    policy = ScriptedPolicy({"Mira": [bad_plan]})
    engine = SimulationEngine(app_config, decision_policy=policy)
    try:
        mira = engine.world.agents["Mira"]
        mira.position = (2, 2)
        mira.inventory["wheat"] = 2
        mira.inventory["wood"] = 2
        assert mira.position != engine.world.landmarks["community_hearth"]

        for _ in range(6):
            engine.tick()
            engine.wait_for_idle()

        assert mira.plan is None, "plan should have been aborted"
        aborts = [event for event in engine.world.recent_events if event.kind == "plan_abort"]
        assert aborts and aborts[-1].metadata["reason"] == "step_failed"
        assert policy.calls["Mira"] >= 2, "agent should be re-consulted after failure"
    finally:
        engine.shutdown()


def test_being_spoken_to_interrupts_active_plan(app_config) -> None:
    plan = Decision(
        "submit_plan",
        {
            "goal": "Wait around a while",
            "steps": [
                {"tool": "wait", "arguments": {"thought": "Pause."}},
                {"tool": "wait", "arguments": {"thought": "Pause again."}},
                {"tool": "wait", "arguments": {"thought": "Pause more."}},
            ],
            "thought": "I will observe for a while.",
        },
        "I will observe for a while.",
    )
    policy = ScriptedPolicy({"Mira": [plan]})
    engine = SimulationEngine(app_config, decision_policy=policy)
    try:
        mira = engine.world.agents["Mira"]
        fen = engine.world.agents["Fen"]

        engine.tick()
        engine.wait_for_idle()
        assert mira.plan is not None, "plan should be installed"

        fen.position = (mira.position[0] + 1, mira.position[1])
        result = engine.action_resolver.apply(
            fen,
            "speak",
            {"message": "Mira, wait!", "target": "Mira", "thought": "Stop her."},
        )
        assert result.success
        assert mira.interrupt_flag

        engine.tick()
        engine.wait_for_idle()
        assert mira.plan is None, "interrupted plan should abort"
        aborts = [event for event in engine.world.recent_events if event.kind == "plan_abort"]
        assert aborts and aborts[-1].metadata["reason"] == "interrupted"
        assert policy.calls["Mira"] >= 2, "interrupted agent should be re-consulted"
    finally:
        engine.shutdown()


def test_energy_crash_interrupts_plan(app_config) -> None:
    plan = Decision(
        "submit_plan",
        {
            "goal": "Long observation",
            "steps": [
                {"tool": "wait", "arguments": {"thought": "One."}},
                {"tool": "wait", "arguments": {"thought": "Two."}},
                {"tool": "wait", "arguments": {"thought": "Three."}},
                {"tool": "wait", "arguments": {"thought": "Four."}},
            ],
            "thought": "I will observe for a while.",
        },
        "I will observe for a while.",
    )
    policy = ScriptedPolicy({"Mira": [plan]})
    engine = SimulationEngine(app_config, decision_policy=policy)
    try:
        mira = engine.world.agents["Mira"]
        engine.tick()
        engine.wait_for_idle()
        assert mira.plan is not None

        mira.energy = 0.05
        engine.tick()
        engine.wait_for_idle()
        assert mira.plan is None
        aborts = [event for event in engine.world.recent_events if event.kind == "plan_abort"]
        assert aborts
    finally:
        engine.shutdown()


def test_plan_survives_save_load_roundtrip(app_config, tmp_path: Path) -> None:
    policy = ScriptedPolicy({"Mira": [hearth_cook_plan()]})
    engine = SimulationEngine(app_config, decision_policy=policy)
    try:
        mira = engine.world.agents["Mira"]
        mira.inventory["wheat"] = 2
        mira.inventory["wood"] = 2
        engine.tick()
        engine.wait_for_idle()
        assert mira.plan is not None

        save_path = tmp_path / "world_state.json"
        engine.world.save(save_path)
        loaded = WorldState.load(save_path)
        assert loaded.agents["Mira"].plan is not None
        assert loaded.agents["Mira"].plan.goal == "Cook wheat at the hearth"
        assert loaded.agents["Mira"].plan.steps[0]["tool"] == "move"
    finally:
        engine.shutdown()


def test_heuristic_policy_emits_plans_under_food_pressure(app_config) -> None:
    engine = SimulationEngine(app_config)
    try:
        engine.world.village_food = 4.0
        for agent in engine.world.agents.values():
            agent.inventory["wheat"] = 2
            agent.inventory["wood"] = 2

        saw_plan = False
        for _ in range(60):
            engine.tick()
            engine.wait_for_idle()
            if any(event.kind == "plan_start" for event in engine.world.recent_events):
                saw_plan = True
                break
        assert saw_plan, "heuristic policy should submit plans under food pressure"
    finally:
        engine.shutdown()
