"""Deterministic, component-isolated randomness.

Formal comparisons use common exogenous randomness across conditions. A draw is
therefore keyed by ``(run_seed, stream_name, entity_id, step, draw_index)``.
Condition names are deliberately not part of this key: removing a module must
not silently redraw warning delivery, hazard spread, or arbitration order.
"""

from __future__ import annotations

import hashlib
import random


def derive(base: int, *parts) -> int:
    """Derive a fresh 32-bit seed from a base seed and any string/int tags.

    v2 fix: empirical_prob draws k samples with derive(base, i) so the cache key
    differs each draw — otherwise the same seed returns k identical answers and
    the calibration curve collapses to all-0/all-1.
    """
    tag = "|".join(str(p) for p in parts)
    h = hashlib.sha256(f"{base}|{tag}".encode()).hexdigest()
    return int(h, 16) % (2**32)


def stream_seed(
    run_seed: int,
    stream_name: str,
    *,
    entity_id: str = "",
    step: int = 0,
    draw_index: int = 0,
) -> int:
    """Return one counter-derived seed for a named stochastic component."""
    return derive(
        run_seed, "stream", stream_name, entity_id, step, draw_index
    )


def stream_rng(
    run_seed: int,
    stream_name: str,
    *,
    entity_id: str = "",
    step: int = 0,
    draw_index: int = 0,
) -> random.Random:
    """Create a deterministic RNG local to one named component/counter."""
    return random.Random(
        stream_seed(
            run_seed,
            stream_name,
            entity_id=entity_id,
            step=step,
            draw_index=draw_index,
        )
    )


def agent_rng(run_seed: int, agent_id: str, step: int) -> random.Random:
    """Backward-compatible private RNG for one agent at one step."""
    return stream_rng(run_seed, "agent", entity_id=agent_id, step=step)


def step_rng(run_seed: int, step: int) -> random.Random:
    """Backward-compatible RNG for legacy step-global draws."""
    return stream_rng(run_seed, "legacy_step", step=step)
