"""Individual-level metrics for auxiliary respondent evaluation.

`empirical_prob` turns discrete LLM actions
into a probability by sampling k times with derived seeds so the cache
does not collapse the k draws into one identical answer.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import numpy as np

from ds.kernel.rng import derive


async def empirical_prob(
    decide_once: Callable[[int], Awaitable],
    base_seed: int,
    k: int = 8,
    positive: str = "evacuate",
) -> float:
    """Fraction of k samples whose .action == positive.

    decide_once(seed) -> awaitable returning an object with `.action`.
    Each of the k calls uses derive(base_seed, i) so their cache keys differ.
    """
    hits = 0
    for i in range(k):
        out = await decide_once(derive(base_seed, i))
        if getattr(out, "action", None) == positive:
            hits += 1
    return hits / k


def accuracy_f1(y_true, y_pred) -> dict:
    """Accuracy + macro-F1 without a sklearn dependency at import time."""
    y_true = list(y_true)
    y_pred = list(y_pred)
    n = len(y_true)
    acc = sum(int(a == b) for a, b in zip(y_true, y_pred)) / n if n else 0.0
    labels = sorted(set(y_true) | set(y_pred))
    f1s = []
    for lab in labels:
        tp = sum(1 for a, b in zip(y_true, y_pred) if a == lab and b == lab)
        fp = sum(1 for a, b in zip(y_true, y_pred) if a != lab and b == lab)
        fn = sum(1 for a, b in zip(y_true, y_pred) if a == lab and b != lab)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if (prec + rec) else 0.0)
    return {"accuracy": acc, "macro_f1": float(np.mean(f1s)) if f1s else 0.0}


def brier(y_true, p) -> float:
    y_true = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    return float(np.mean((p - y_true) ** 2))


def ece(y_true, p, n_bins: int = 10) -> float:
    """Expected Calibration Error over n_bins equal-width probability bins."""
    y_true = np.asarray(y_true, dtype=float)
    p = np.asarray(p, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = len(p)
    err = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (p >= lo) & (p < hi) if i < n_bins - 1 else (p >= lo) & (p <= hi)
        if not mask.any():
            continue
        conf = p[mask].mean()
        acc = y_true[mask].mean()
        err += (mask.sum() / total) * abs(conf - acc)
    return float(err)


def decision_confidence_to_positive_probability(
    predictions,
    confidence,
) -> np.ndarray:
    """Convert confidence-in-the-chosen-class to P(y=1).

    Historical Carr LLM outputs stored a binary decision and confidence in that
    decision.  Treating confidence as P(evacuated) for a "no" decision reverses
    its meaning and invalidates Brier/ECE.
    """
    predictions = np.asarray(predictions, dtype=int)
    confidence = np.asarray(confidence, dtype=float)
    if predictions.shape != confidence.shape:
        raise ValueError("predictions and confidence must have the same shape")
    if not np.isin(predictions, [0, 1]).all():
        raise ValueError("predictions must be binary")
    if ((confidence < 0.0) | (confidence > 1.0)).any():
        raise ValueError("confidence must be within [0, 1]")
    return np.where(predictions == 1, confidence, 1.0 - confidence)
