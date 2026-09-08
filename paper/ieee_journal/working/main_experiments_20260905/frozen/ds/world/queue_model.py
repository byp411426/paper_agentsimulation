"""Point-queue road loading with BPR travel time.

Each edge holds a FIFO queue. Per step it releases min(queue, capacity*step) vehicles;
travel time follows BPR: t = t0 * (1 + 0.15 * (v/c)^4). Vehicle conservation holds:
nothing is created or lost, only moved. The component currently has software tests;
it has not been empirically validated for Carr or another disaster case.

This is graph-agnostic: an edge is any hashable key with a (free_time, capacity).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EdgeState:
    free_time: float          # t0, minutes to traverse when empty
    capacity: float           # vehicles per step it can release
    queue: deque = field(default_factory=deque)
    closed: bool = False

    @property
    def load(self) -> int:
        return len(self.queue)

    def travel_time(self) -> float:
        v, c = self.load, max(self.capacity, 1e-9)
        return self.free_time * (1 + 0.15 * (v / c) ** 4)


class PointQueueNetwork:
    def __init__(self):
        self.edges: dict[Any, EdgeState] = {}

    def add_edge(self, key: Any, free_time: float, capacity: float) -> None:
        self.edges[key] = EdgeState(free_time=free_time, capacity=capacity)

    def close(self, key: Any) -> None:
        if key in self.edges:
            self.edges[key].closed = True

    def enqueue(self, key: Any, vehicle: Any) -> None:
        self.edges[key].queue.append(vehicle)

    def total_vehicles(self) -> int:
        return sum(e.load for e in self.edges.values())

    def step(self) -> dict[Any, list]:
        """Release up to capacity vehicles from each open edge (sorted for determinism).

        Returns {edge_key: [released vehicles]} — conservation: released are removed
        from their queue exactly once.
        """
        released: dict[Any, list] = {}
        for key in sorted(self.edges.keys(), key=str):
            e = self.edges[key]
            if e.closed:
                released[key] = []
                continue
            n = int(min(e.load, e.capacity))
            out = [e.queue.popleft() for _ in range(n)]
            released[key] = out
        return released
