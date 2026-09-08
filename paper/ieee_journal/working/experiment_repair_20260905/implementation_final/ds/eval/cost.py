"""Cost & population-quality metrics (spec §8)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def cost_report(llm_calls_jsonl: str | Path) -> dict:
    """Aggregate the gateway call log: tokens / USD / wake rate / cache / fallback."""
    rows = []
    with open(llm_calls_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    n = len(rows)
    ok = sum(r.get("status") == "ok" for r in rows)
    cache = sum(r.get("status") == "cache_hit" for r in rows)
    failed = sum(r.get("status") == "failed" for r in rows)
    fallback = sum(r.get("status") == "fallback_rule" for r in rows)
    tokens = sum((r.get("pt") or 0) + (r.get("ct") or 0) for r in rows)
    cost = sum(r.get("cost") or 0.0 for r in rows)
    return {
        "calls": n, "ok": ok, "cache_hit": cache,
        "failed": failed, "fallback": fallback,
        "cache_hit_rate": cache / n if n else 0.0,
        "resolved_decisions": ok + cache + fallback,
        "fallback_rate": (
            fallback / (ok + cache + fallback)
            if (ok + cache + fallback) else 0.0
        ),
        "total_tokens": tokens, "total_cost_usd": round(cost, 6),
    }


def srmse(simulated: pd.Series, census: pd.Series) -> float:
    """Standardized Root Mean Squared Error — synthetic-population standard metric.

    Compares two category-count distributions. Reported per attribute (spec §6.5).
    """
    p = simulated / simulated.sum()
    q = census / census.sum()
    q = q.reindex(p.index).fillna(0.0)
    m = len(p)
    qbar = q.mean()
    if qbar == 0:
        return float("nan")
    return float(np.sqrt(((p - q) ** 2).sum() / m) / qbar)
