"""Agentic memory (spec v2 §2.3 — corrected eviction).

Write path is rule-scored (no LLM cost). Eviction never drops PROTECTED kinds
(warning / injury / family) and, among the rest, drops LOW-importance + OLD first
(v2 fix: the old M0-M3 code sorted by -step and dropped the newest by mistake).
Recall = importance x time-decay, top-k (Generative-Agents style, reproducible).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    step: int
    text: str
    importance: int = Field(ge=1, le=5)
    kind: str  # warning | observation | message | family | injury | reflection


class Memory:
    PROTECTED = {"warning", "injury", "family"}
    AUTO_IMPORTANCE = {"warning": 5, "injury": 5, "family": 4,
                       "message": 3, "reflection": 2, "observation": 2}

    def __init__(self, capacity: int = 200):
        self.capacity = capacity
        self.items: list[MemoryItem] = []

    def write(self, item: MemoryItem) -> None:
        self.items.append(item)
        if len(self.items) <= self.capacity:
            return
        # never evict protected kinds
        evictable = [m for m in self.items if m.kind not in self.PROTECTED]
        # low importance + old first
        evictable.sort(key=lambda m: (m.importance, m.step))
        n_drop = len(self.items) - self.capacity
        drop = set(id(m) for m in evictable[:n_drop])
        self.items = [m for m in self.items if id(m) not in drop]

    def write_text(self, step: int, text: str, kind: str,
                   importance: int | None = None) -> None:
        imp = importance if importance is not None else self.AUTO_IMPORTANCE.get(kind, 2)
        self.write(MemoryItem(step=step, text=text, importance=imp, kind=kind))

    def recall(self, step: int, k: int = 6) -> list[str]:
        scored = [(m.importance * 0.95 ** (step - m.step), m) for m in self.items]
        return [m.text for _, m in sorted(scored, key=lambda t: -t[0])[:k]]
