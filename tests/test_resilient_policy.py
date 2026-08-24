from __future__ import annotations

import pytest

from sim.agent import Decision, DecisionRequest, ResilientDecisionPolicy


class FakePrimaryPolicy:
    def __init__(self, outcomes: list[Decision | Exception]):
        self.outcomes = list(outcomes)
        self.calls = 0

    def decide(self, request):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else Decision("wait", {"thought": "done"}, "done")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeFallbackPolicy:
    def __init__(self):
        self.calls = 0

    def decide(self, request):
        self.calls += 1
        return Decision("rest", {"thought": "fallback"}, "fallback")


def make_request() -> DecisionRequest:
    return DecisionRequest(agent_name="Mira", observation="", system_prompt="", tools=[])


def make_policy(primary, **kwargs) -> ResilientDecisionPolicy:
    defaults = dict(
        retryable_errors=(ValueError,),
        max_attempts=3,
        base_delay=0.0,
        max_delay=0.0,
        failure_threshold=2,
        cooldown_calls=3,
        sleeper=lambda _seconds: None,
        jitter=lambda: 0.0,
    )
    defaults.update(kwargs)
    return ResilientDecisionPolicy(primary, FakeFallbackPolicy(), **defaults)


def test_transient_errors_are_retried_with_backoff() -> None:
    success = Decision("chop_wood", {"tile_position": "1,2", "thought": "work"}, "work")
    primary = FakePrimaryPolicy([ValueError("429"), ValueError("429"), success])
    sleeps: list[float] = []
    policy = make_policy(primary, sleeper=sleeps.append)

    decision = policy.decide(make_request())

    assert decision is success
    assert primary.calls == 3
    assert len(sleeps) == 2
    assert sleeps[1] >= sleeps[0]
    assert policy.fallback.calls == 0


def test_exhausted_retries_fall_back_to_heuristics() -> None:
    primary = FakePrimaryPolicy([ValueError("429"), ValueError("429"), ValueError("429")])
    policy = make_policy(primary)

    decision = policy.decide(make_request())

    assert decision.tool_name == "rest"
    assert primary.calls == 3
    assert policy.fallback.calls == 1


def test_permanent_errors_skip_retries_and_fall_back() -> None:
    primary = FakePrimaryPolicy([RuntimeError("401 unauthorized")])
    policy = make_policy(primary)

    decision = policy.decide(make_request())

    assert decision.tool_name == "rest"
    assert primary.calls == 1
    assert policy.fallback.calls == 1


def test_circuit_opens_after_threshold_and_skips_api() -> None:
    primary = FakePrimaryPolicy([RuntimeError("down"), RuntimeError("down"), RuntimeError("down")])
    policy = make_policy(primary)

    for _ in range(5):
        policy.decide(make_request())

    assert primary.calls == 2
    assert policy.fallback.calls == 5
    assert policy._open_remaining == 0


def test_circuit_recovers_after_cooldown() -> None:
    success = Decision("wait", {"thought": "back"}, "back")
    primary = FakePrimaryPolicy([RuntimeError("down"), RuntimeError("down"), success])
    policy = make_policy(primary)

    policy.decide(make_request())
    policy.decide(make_request())
    assert policy._open_remaining == 3

    for _ in range(3):
        policy.decide(make_request())
    assert primary.calls == 2

    decision = policy.decide(make_request())
    assert decision is success
    assert primary.calls == 3
    assert policy._consecutive_failures == 0


def test_engine_wraps_openai_policy_with_resilience(app_config) -> None:
    from sim.agent import OpenAIDecisionPolicy
    from sim.engine import SimulationEngine

    app_config.openai_key = "test-key"
    try:
        engine = SimulationEngine(app_config)
        try:
            assert isinstance(engine.decision_policy, ResilientDecisionPolicy)
            assert isinstance(engine.decision_policy.primary, OpenAIDecisionPolicy)
        finally:
            engine.shutdown()
    finally:
        app_config.openai_key = None


def test_real_openai_errors_classified_as_retryable() -> None:
    from sim.agent import RETRYABLE_API_ERRORS
    from openai import APIConnectionError, InternalServerError, RateLimitError

    for error_type in (RateLimitError, APIConnectionError, InternalServerError):
        assert error_type in RETRYABLE_API_ERRORS
