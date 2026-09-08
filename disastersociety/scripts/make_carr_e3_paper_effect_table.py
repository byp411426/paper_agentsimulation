"""Render the E3 cross-model paper table with paired effect sizes (mean [95% CI]).

Each row is one model; each cell reports the mean paired difference across the
four frozen seeds with a 95% t-interval. All numbers come from the actual VALID
mechanism_metrics.json artifacts.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS = PROJECT_ROOT / "experiments/carr/runs"
OUT_MD = PROJECT_ROOT / "experiments/carr/results/carr_s_e3_paper_effect_table.md"
OUT_JSON = PROJECT_ROOT / "experiments/carr/results/carr_s_e3_paper_effect_table.json"

MODELS = ["qwen", "glm", "gpt54mini", "qwen27b", "gemma4", "qwen36", "deepseek"]
SEEDS = [2107, 2209, 2303, 2411]
T_CRIT = {3: 3.182446, 27: 2.051831}


def load(m: str, c: str, s: int) -> dict | None:
    p = RUNS / f"carr_s_e3_v1_{m}_{c}_seed{s}" / "mechanism_metrics.json"
    return json.loads(p.read_text()) if p.exists() else None


def is_valid(m: str, c: str, s: int) -> bool:
    p = RUNS / f"carr_s_e3_v1_{m}_{c}_seed{s}" / "summary.json"
    return p.exists() and json.loads(p.read_text()).get("status") == "VALID"


def paired_diffs(m: str, full_key: str, drop_key: str, metric: str) -> list[float]:
    diffs = []
    for s in SEEDS:
        full = load(m, "full", s)
        drop = load(m, drop_key, s)
        if (
            full is None
            or drop is None
            or not is_valid(m, "full", s)
            or not is_valid(m, drop_key, s)
        ):
            continue
        diffs.append(full[metric] - drop[metric])
    return diffs


def fmt(diffs: list[float], tcrit: float) -> str:
    n = len(diffs)
    if n == 0:
        return "—"
    mean = sum(diffs) / n
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = tcrit * sd / (n ** 0.5)
    return f"{mean:.3f} [{mean - half:.3f}, {mean + half:.3f}]"


def main() -> None:
    rows = []
    all_fb_manip: list[float] = []
    all_fb_down: list[float] = []
    all_it_manip: list[float] = []
    all_it_down: list[float] = []
    for m in MODELS:
        fb_manip = paired_diffs(
            m, "full", "full_minus_feedback",
            "preclosure_primary_to_postclosure_alternate_update_rate",
        )
        fb_down = paired_diffs(
            m, "full", "full_minus_feedback",
            "closed_route_rejections_per_household",
        )
        it_manip = paired_diffs(
            m, "full", "full_minus_interaction",
            "post_closure_feasible_commitment_rate",
        )
        it_down = paired_diffs(
            m, "full", "full_minus_interaction",
            "coordinated_departure_rate",
        )
        all_fb_manip += fb_manip
        all_fb_down += fb_down
        all_it_manip += it_manip
        all_it_down += it_down
        rows.append(
            {
                "model": m,
                "feedback_manipulation": fmt(fb_manip, T_CRIT[3]),
                "feedback_downstream": fmt(fb_down, T_CRIT[3]),
                "interaction_manipulation": fmt(it_manip, T_CRIT[3]),
                "interaction_downstream": fmt(it_down, T_CRIT[3]),
            }
        )

    n_pool = len(all_fb_manip)
    tcrit_pool = T_CRIT.get(n_pool - 1, 1.96)
    rows.append(
        {
            "model": "All models (pooled)",
            "feedback_manipulation": fmt(all_fb_manip, tcrit_pool),
            "feedback_downstream": fmt(all_fb_down, tcrit_pool),
            "interaction_manipulation": fmt(all_it_manip, tcrit_pool),
            "interaction_downstream": fmt(all_it_down, tcrit_pool),
        }
    )

    md = [
        "# E3 跨模型配对效应表（均值 [95% CI]，4 seed）",
        "",
        "| 模型 | 反馈：换路更新率 Δ | 反馈：关闭路拒绝 Δ/户 | 互动：可行承诺率 Δ | 互动：协调出发率 Δ |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in rows:
        md.append(
            f"| {r['model']} | {r['feedback_manipulation']} | "
            f"{r['feedback_downstream']} | {r['interaction_manipulation']} | "
            f"{r['interaction_downstream']} |"
        )
    md += [
        "",
        "注：Δ = full − full_minus_module，正值表示移除该模块后指标下降（即模块有正向作用）；关闭路拒绝为负值表示 full 下拒绝更少。95% CI 为配对 t 区间（每模型 n=4 seed；pooled 行 n=28）。",
        "",
    ]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps({"rows": rows, "note": md[-2]}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(OUT_MD)


if __name__ == "__main__":
    main()
