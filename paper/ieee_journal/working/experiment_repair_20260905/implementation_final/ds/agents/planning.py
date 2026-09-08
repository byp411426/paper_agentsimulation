"""Executable resident plans used by the Carr controlled-case adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class ExecutablePlan:
    id: str
    route_id: str
    vehicle_id: str
    depart_step: int
    dependent_ids: tuple[str, ...] = ()
    status: Literal[
        "planned",
        "blocked",
        "executing",
        "completed",
        "cancelled",
    ] = "planned"
    created_step: int = 0
    last_failure: str | None = None
