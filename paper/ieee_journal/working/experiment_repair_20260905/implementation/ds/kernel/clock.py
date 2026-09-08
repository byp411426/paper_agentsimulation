"""Simulation clock (spec §3)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Clock:
    step_minutes: int
    t: int = 0  # current step index

    def tick(self) -> None:
        self.t += 1

    @property
    def sim_minutes(self) -> int:
        return self.t * self.step_minutes

    @property
    def sim_hours(self) -> float:
        return self.sim_minutes / 60.0
