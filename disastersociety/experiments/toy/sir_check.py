"""Rule-agent diffusion mechanism pre-check.

Compares information-diffusion machinery with a matched reference implementation
before any LLM tokens are spent. Two independent code paths model the same
timed independent-cascade process:

  * agent path : pure rule agents forward a message to each graph neighbor with
                 prob p exactly once when first informed, through timed message
                 queues (the same delivery discipline the InteractionEngine uses).
  * reference  : the standalone independent_cascade() in ds/eval/mechanism.py.

Both are averaged over K trials. If the interaction mechanism is sound the two
averaged informed-fraction curves agree (low RMSE). A broken forwarding/delivery
path makes them diverge — that's the point. A mean-field SIR curve is also
reported for context. No LLM is used. Passing this check supports implementation
consistency under the toy assumptions, not empirical disaster-behavior validity.
"""

from __future__ import annotations

import numpy as np
import networkx as nx

from ds.eval.mechanism import diffusion_curve_rmse, independent_cascade, sir_curve


def _random_regular(n: int, degree: int, seed: int) -> nx.Graph:
    degree = min(degree, n - 1)
    if (n * degree) % 2 != 0:
        degree += 1  # regular graph needs even n*degree
    return nx.random_regular_graph(degree, n, seed=seed)


def agent_cascade_curve(G: nx.Graph, seeds: list, p: float, steps: int,
                        run_seed: int) -> np.ndarray:
    """Agent-based independent cascade via timed message forwarding.

    Each agent, the step AFTER it is first informed, forwards to each neighbor
    with prob p (once). Message delivery is one-step (like community channel).
    Returns cumulative informed fraction per step.
    """
    n = G.number_of_nodes()
    informed = set(seeds)
    to_forward = set(seeds)          # agents who will forward next step
    curve = [len(informed) / n]
    rng = np.random.default_rng(run_seed)
    nodes = sorted(G.nodes(), key=str)

    for _ in range(steps):
        # deliver forwards from agents that became informed last step
        newly = set()
        for u in sorted(to_forward, key=str):
            for v in sorted(G.neighbors(u), key=str):
                if v in informed:
                    continue
                if rng.random() < p:
                    newly.add(v)
        informed |= newly
        to_forward = newly            # only the freshly-informed forward next step
        curve.append(len(informed) / n)
        if not newly:
            curve.extend([curve[-1]] * (steps - len(curve) + 1))
            break
    return np.asarray(curve[: steps + 1])


def run_sir_check(n: int = 500, seed: int = 1, p: float = 0.25,
                  steps: int = 30, trials: int = 40,
                  degree: int = 10, threshold: float = 0.03,
                  min_spread: float = 0.5) -> dict:
    G = _random_regular(n, degree, seed)
    seeds = sorted(G.nodes(), key=str)[: max(1, n // 100)]  # ~1% initial seeds

    # average both independent code paths over `trials`
    agent_curves, ref_curves = [], []
    for t in range(trials):
        agent_curves.append(agent_cascade_curve(G, seeds, p, steps, run_seed=seed * 1000 + t))
        ref_curves.append(
            independent_cascade(G, seeds, p, steps, rng=np.random.default_rng(seed * 7919 + t))
        )
    agent_mean = np.mean(agent_curves, axis=0)
    ref_mean = np.mean([np.asarray(c) for c in ref_curves], axis=0)

    rmse = diffusion_curve_rmse(agent_mean, ref_mean)

    # mean-field SIR for context (β≈p·degree, γ=1: forward once then done)
    sir = sir_curve(beta=p * degree, gamma=1.0, i0=len(seeds) / n, steps=steps)

    return {
        "rmse_cascade": rmse,
        "threshold": threshold,
        "final_agent": float(agent_mean[-1]),
        "final_ref": float(ref_mean[-1]),
        # supercritical: R0 = p*degree should be > 1 so the cascade actually spreads
        "r0": p * degree,
        "min_spread": min_spread,
        "spread_ok": float(agent_mean[-1]) >= min_spread,
        "agent_curve": agent_mean.tolist(),
        "ref_curve": ref_mean.tolist(),
        "sir_curve": list(sir),
        "n": n, "p": p, "degree": degree, "trials": trials,
    }
