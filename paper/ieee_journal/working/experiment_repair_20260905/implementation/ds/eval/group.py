"""Group-level metrics (SciPy-backed).

Metric availability does not establish that a target is independent or valid.
Callers must record whether a comparison is calibration-internal or evaluative.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import ks_2samp, wasserstein_distance


def evac_curve_rmse(sim_curve, real_curve) -> float:
    """RMSE between two cumulative evacuation curves sampled at the same steps."""
    a = np.asarray(sim_curve, dtype=float)
    b = np.asarray(real_curve, dtype=float)
    n = min(len(a), len(b))
    return float(np.sqrt(np.mean((a[:n] - b[:n]) ** 2)))


def curve_ks(sim_samples, real_samples) -> float:
    """KS distance between two samples of departure times (or any 1-D quantity)."""
    if len(sim_samples) == 0 or len(real_samples) == 0:
        return float("nan")
    return float(ks_2samp(sim_samples, real_samples).statistic)


def dist_wasserstein(sim_samples, real_samples) -> float:
    if len(sim_samples) == 0 or len(real_samples) == 0:
        return float("nan")
    return float(wasserstein_distance(sim_samples, real_samples))


def flow_mae(sim_flows: dict, real_flows: dict) -> float:
    """Mean absolute error over shared (station, hour) keys."""
    keys = sorted(set(sim_flows) & set(real_flows), key=str)
    if not keys:
        return float("nan")
    return float(np.mean([abs(sim_flows[k] - real_flows[k]) for k in keys]))


def channel_share_l1(sim_shares: dict, survey_shares: dict) -> float:
    """L1 distance between channel shares and a declared comparison distribution."""
    keys = sorted(set(sim_shares) | set(survey_shares))
    return float(sum(abs(sim_shares.get(k, 0.0) - survey_shares.get(k, 0.0))
                     for k in keys))


def bimodality_coefficient(samples) -> float:
    """Sarle's bimodality coefficient; > 0.555 is a heuristic indication."""
    x = np.asarray(samples, dtype=float)
    n = len(x)
    if n < 4:
        return float("nan")
    from scipy.stats import kurtosis, skew

    g = skew(x)
    k = kurtosis(x, fisher=True)  # excess kurtosis
    denom = (k + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3)))
    if denom == 0:
        return float("nan")
    return float((g**2 + 1) / denom)
