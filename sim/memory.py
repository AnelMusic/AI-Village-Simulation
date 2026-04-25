from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json
from typing import Any


@dataclass
class MemoryEntry:
    tick: int
    day: int
    summary: str
    salience: int = 1
    tags: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tags"] = list(self.tags or [])
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        return cls(
            tick=int(data["tick"]),
            day=int(data["day"]),
            summary=data["summary"],
            salience=int(data.get("salience", 1)),
            tags=list(data.get("tags", [])),
        )


class AgentMemory:
    def __init__(self, agent_name: str, base_dir: str | Path, recent_limit: int = 20):
        self.agent_name = agent_name
        self.base_dir = Path(base_dir)
        self.recent_limit = recent_limit
        self.recent: list[MemoryEntry] = []
        self.summaries: list[MemoryEntry] = []
        self.path = self.base_dir / f"{self.agent_name.lower()}_memory.json"
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.recent = [MemoryEntry.from_dict(item) for item in data.get("recent", [])]
        self.summaries = [MemoryEntry.from_dict(item) for item in data.get("summaries", [])]

    def save(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "recent": [entry.to_dict() for entry in self.recent[-self.recent_limit :]],
            "summaries": [entry.to_dict() for entry in self.summaries[-12:]],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def remember(self, tick: int, day: int, summary: str, salience: int = 1, tags: list[str] | None = None) -> None:
        self.recent.append(MemoryEntry(tick=tick, day=day, summary=summary, salience=salience, tags=tags or []))
        self.recent = self.recent[-self.recent_limit :]
        self._summarize_if_needed()
        self.save()

    def _summarize_if_needed(self) -> None:
        if len(self.recent) < self.recent_limit:
            return
        batch = self.recent[:6]
        text = "; ".join(item.summary for item in batch[:4])
        summary = MemoryEntry(
            tick=batch[-1].tick,
            day=batch[-1].day,
            summary=f"Summary of recent events: {text}",
            salience=max(item.salience for item in batch),
            tags=["summary"],
        )
        self.summaries.append(summary)
        self.summaries = self.summaries[-12:]
        self.recent = self.recent[6:]

    def recall_lines(self, limit: int = 5) -> list[str]:
        ranked = sorted(self.recent, key=lambda item: (item.salience, item.tick), reverse=True)[: max(2, limit - 2)]
        recent_lines = [f"[Day {item.day}] {item.summary}" for item in ranked]
        summary_lines = [f"[Day {item.day}] {item.summary}" for item in self.summaries[-2:]]
        return summary_lines + recent_lines[:limit]


class MemoryStore:
    def __init__(self, base_dir: str | Path, agent_names: list[str]):
        self.base_dir = Path(base_dir)
        self.memories: dict[str, AgentMemory] = {
            name: AgentMemory(name, self.base_dir) for name in agent_names
        }

    def get(self, agent_name: str) -> AgentMemory:
        return self.memories[agent_name]

    def save_all(self) -> None:
        for memory in self.memories.values():
            memory.save()
