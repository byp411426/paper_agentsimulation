"""Trust dynamics (spec §7, v2 §2.4).

One trust score in [0,1] per source category. A claim that later matches the world
pushes trust toward 1; a refuted claim pushes it toward 0. Whether a claim is
verified is decided by rules (did the world confirm what it asserted), never by an
LLM. Rumor = an injected claim with truth=False.
"""

from __future__ import annotations

SOURCES = ("official", "family", "neighbor", "social")


class Trust:
    def __init__(self, prior: float = 0.5, lr: float = 0.15,
                 init: dict[str, float] | None = None):
        self.lr = lr
        self.scores: dict[str, float] = {s: prior for s in SOURCES}
        if init:
            self.scores.update(init)

    def update(self, source: str, verified: bool) -> None:
        if source not in self.scores:
            return
        s = self.scores[source]
        self.scores[source] = s + self.lr * ((1.0 if verified else 0.0) - s)

    def get(self, source: str) -> float:
        return self.scores.get(source, 0.5)
