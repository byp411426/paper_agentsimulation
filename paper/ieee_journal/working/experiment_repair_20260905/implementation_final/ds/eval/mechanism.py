"""Mechanism-level metrics and reference diffusion models.

Reference curves are used as software/mechanism pre-checks under matched assumptions.
Agreement can reveal whether basic propagation behaves as configured; it is not
empirical validation of disaster communication or resident behavior.
"""

from __future__ import annotations

import numpy as np
import networkx as nx


def independent_cascade(G: nx.Graph, seeds: list, p: float,
                        max_steps: int, rng: np.random.Generator) -> list[float]:
    """Independent-cascade informed-fraction curve over max_steps.

    Each newly-informed node gets ONE chance to inform each neighbor w.p. p.
    Returns cumulative informed fraction per step (index 0 = initial seeds).
    """
    n = G.number_of_nodes()
    informed = set(seeds)
    newly = set(seeds)
    curve = [len(informed) / n]
    nodes = {node: i for i, node in enumerate(sorted(G.nodes(), key=str))}
    for _ in range(max_steps):
        nxt = set()
        for u in sorted(newly, key=str):
            for v in sorted(G.neighbors(u), key=str):
                if v in informed:
                    continue
                # deterministic draw keyed by (u,v) via rng stream
                if rng.random() < p:
                    nxt.add(v)
        informed |= nxt
        newly = nxt
        curve.append(len(informed) / n)
        if not newly:
            # pad the rest of the curve flat
            curve.extend([curve[-1]] * (max_steps - len(curve) + 1))
            break
    return curve[: max_steps + 1]


def sir_curve(beta: float, gamma: float, i0: float, steps: int) -> list[float]:
    """Deterministic SIR informed(=I+R) fraction curve (compartmental ODE, Euler)."""
    s, i, r = 1.0 - i0, i0, 0.0
    curve = [i + r]
    for _ in range(steps):
        ds = -beta * s * i
        di = beta * s * i - gamma * i
        dr = gamma * i
        s, i, r = s + ds, i + di, r + dr
        curve.append(i + r)
    return curve


def diffusion_curve_rmse(sim_informed_frac: list[float],
                         reference_curve: list[float]) -> float:
    a = np.asarray(sim_informed_frac, dtype=float)
    b = np.asarray(reference_curve, dtype=float)
    n = min(len(a), len(b))
    return float(np.sqrt(np.mean((a[:n] - b[:n]) ** 2)))
