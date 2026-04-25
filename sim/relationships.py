from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
from typing import Any


@dataclass
class Relationship:
    trust: float = 0.0
    trade_count: int = 0
    last_interaction_day: int = 0
    allied: bool = False
    favor: float = 0.0
    gifts_given: int = 0
    notes: list[str] = field(default_factory=list)

    def record(self, day: int, trust_delta: float, note: str) -> None:
        self.trust = max(-1.0, min(1.0, self.trust + trust_delta))
        self.last_interaction_day = day
        if note:
            self.notes.append(note)
            self.notes = self.notes[-5:]

    def describe(self) -> str:
        if self.trust >= 0.45:
            mood = "warm"
        elif self.trust >= 0.1:
            mood = "friendly"
        elif self.trust <= -0.45:
            mood = "hostile"
        elif self.trust <= -0.1:
            mood = "cold"
        else:
            mood = "neutral"
        note = self.notes[-1] if self.notes else "no notable interactions yet"
        alliance = " allied," if self.allied else ""
        return f"{mood},{alliance} trades={self.trade_count}, note={note}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Relationship":
        return cls(
            trust=float(data.get("trust", 0.0)),
            trade_count=int(data.get("trade_count", 0)),
            last_interaction_day=int(data.get("last_interaction_day", 0)),
            allied=bool(data.get("allied", False)),
            favor=float(data.get("favor", 0.0)),
            gifts_given=int(data.get("gifts_given", 0)),
            notes=list(data.get("notes", [])),
        )


class RelationshipGraph:
    def __init__(self, agent_names: list[str]):
        self.graph: dict[str, dict[str, Relationship]] = {name: {} for name in agent_names}
        for name in agent_names:
            for other in agent_names:
                if name == other:
                    continue
                self.graph[name][other] = Relationship()

    def get(self, name: str, other: str) -> Relationship:
        return self.graph[name][other]

    def record(self, name: str, other: str, day: int, trust_delta: float, note: str) -> None:
        self.graph[name][other].record(day, trust_delta, note)
        self.graph[other][name].record(day, trust_delta, note)

    def record_trade(self, name: str, other: str, day: int, note: str) -> None:
        self.record(name, other, day, 0.1, note)
        self.graph[name][other].trade_count += 1
        self.graph[other][name].trade_count += 1

    def record_gift(self, giver: str, receiver: str, day: int, note: str, favor_delta: float = 0.6) -> None:
        self.graph[giver][receiver].record(day, 0.08, note)
        self.graph[receiver][giver].record(day, 0.18, note)
        self.graph[receiver][giver].favor = min(3.0, self.graph[receiver][giver].favor + favor_delta)
        self.graph[giver][receiver].gifts_given += 1

    def spend_favor(self, name: str, other: str, amount: float) -> None:
        self.graph[name][other].favor = max(0.0, self.graph[name][other].favor - amount)

    def form_alliance(self, name: str, other: str, day: int, note: str) -> None:
        self.graph[name][other].allied = True
        self.graph[other][name].allied = True
        self.graph[name][other].record(day, 0.2, note)
        self.graph[other][name].record(day, 0.2, note)

    def are_allies(self, name: str, other: str) -> bool:
        return self.graph[name][other].allied

    def allies_of(self, name: str) -> list[str]:
        return [other for other, relationship in self.graph[name].items() if relationship.allied]

    def summary_for(self, agent_name: str) -> list[str]:
        lines: list[str] = []
        for other, rel in sorted(self.graph[agent_name].items()):
            parts = [rel.describe()]
            if rel.favor >= 0.25:
                parts.append(f"you owe {other} a favor ({rel.favor:.1f})")
            inverse = self.graph[other][agent_name]
            if inverse.favor >= 0.25:
                parts.append(f"{other} owes you a favor ({inverse.favor:.1f})")
            lines.append(f"{other}: {'; '.join(parts)}")
        return lines

    def to_dict(self) -> dict[str, Any]:
        return {
            name: {other: relationship.to_dict() for other, relationship in others.items()}
            for name, others in self.graph.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RelationshipGraph":
        instance = cls(list(data.keys()))
        instance.graph = {
            name: {other: Relationship.from_dict(rel) for other, rel in others.items()}
            for name, others in data.items()
        }
        return instance

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "RelationshipGraph":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
