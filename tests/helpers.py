from __future__ import annotations

from collections import defaultdict

from sim.agent import Decision, DecisionPolicy


class ScriptedPolicy(DecisionPolicy):
    def __init__(self, plans: dict[str, list[Decision]]):
        self.plans = {name: list(items) for name, items in plans.items()}
        self.calls = defaultdict(int)

    def decide(self, request):
        self.calls[request.agent_name] += 1
        queue = self.plans.get(request.agent_name, [])
        if queue:
            return queue.pop(0)
        return Decision("wait", {"thought": "Nothing urgent."}, "Nothing urgent.")
