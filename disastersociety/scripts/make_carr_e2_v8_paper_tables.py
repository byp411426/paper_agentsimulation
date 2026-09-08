"""Render the E2 v8 r7 publication tables (paper-ready markdown + JSON).

Reads the frozen cumulative summary and publication audit; writes
experiments/carr/results/carr_s_e2_v8_formal_r7_paper_tables.{md,json}.
"""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "experiments/carr/results"
CUMULATIVE = RESULTS / "carr_s_e2_v8_formal_r7_cumulative_summary.json"
AUDIT = RESULTS / "carr_s_e2_v8_formal_r7_publication_audit.json"
OUT_MD = RESULTS / "carr_s_e2_v8_formal_r7_paper_tables.md"
OUT_JSON = RESULTS / "carr_s_e2_v8_formal_r7_paper_tables.json"


def fmt_ci(low: float | None, high: float | None, digits: int = 3) -> str:
    if low is None or high is None:
        return "—"
    return f"[{low:.{digits}f}, {high:.{digits}f}]"


def main() -> None:
    cumulative = json.loads(CUMULATIVE.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))

    primary = cumulative["paired_primary_summary"]
    downstream = cumulative["paired_downstream_summary"]
    runs = cumulative["runs"]

    primary_rows = []
    for row in primary:
        primary_rows.append(
            {
                "module": row["module"],
                "metric": row["metric"],
                "mean_diff": row["mean_paired_difference"],
                "sd_diff": row["sd_paired_difference"],
                "mcse": row["mcse"],
                "ci95": [row["paired_t_95_ci"][0], row["paired_t_95_ci"][1]],
                "positive_fraction": row["positive_direction_fraction"],
                "dz": row["standardized_paired_effect_dz"],
                "variance_informative": row["variance_informative"],
            }
        )

    downstream_rows = []
    for row in downstream:
        downstream_rows.append(
            {
                "module": row["module"],
                "metric": row["metric"],
                "predicted_direction": row["predicted_direction"],
                "mean_directional_diff": row["mean_directional_difference"],
                "sd_diff": row["sd_directional_difference"],
                "mcse": row["mcse"],
                "ci95": [row["paired_t_95_ci"][0], row["paired_t_95_ci"][1]],
                "positive_fraction": row["positive_direction_fraction"],
                "zero_fraction": row["zero_difference_fraction"],
                "dz": row["standardized_paired_effect_dz"],
                "variance_informative": row["variance_informative"],
            }
        )

    run_stats = []
    wall = [r["wall_clock_seconds"] for r in runs]
    ok = [r["n_ok"] for r in runs]
    cache = [r["n_cache"] for r in runs]
    failed = [r["n_failed"] for r in runs]
    fallback = [r["n_fallback"] for r in runs]
    run_stats = {
        "n_runs": len(runs),
        "n_valid": audit["n_valid_cells"],
        "terminal_status_counts": audit["terminal_status_counts"],
        "total_wall_clock_seconds": sum(wall),
        "mean_wall_clock_seconds": sum(wall) / len(wall) if wall else None,
        "total_llm_calls": sum(ok) + sum(cache),
        "total_ok": sum(ok),
        "total_cache": sum(cache),
        "total_failed": sum(failed),
        "total_fallback": sum(fallback),
    }

    md = [
        "# E2 v8 r7 机制矩阵论文表格（60 格，COMPLETE_VALID）",
        "",
        f"- 协议：`{audit['protocol_id']}`；审计状态：`{audit['audit_status']}`",
        f"- 格子：{audit['expected_cells']} 计划 / {audit['actual_cells']} 实际 / {audit['n_valid_cells']} VALID",
        f"- 终态计数：{json.dumps(audit['terminal_status_counts'], ensure_ascii=False)}",
        f"- 总墙钟：{run_stats['total_wall_clock_seconds']:.0f}s（均值 {run_stats['mean_wall_clock_seconds']:.0f}s/格）",
        f"- LLM 调用：ok {run_stats['total_ok']} + cache {run_stats['total_cache']} = {run_stats['total_llm_calls']}；失败 {run_stats['total_failed']}；fallback {run_stats['total_fallback']}",
        "",
        "## 操纵检查（配对 full − full-minus-module，12 seed）",
        "",
        "| 模块 | 指标 | 平均配对差 | SD | MCSE | 95% CI | 正方向占比 | dz |",
        "|---|---|---:|---:|---:|---|---:|---:|",
    ]
    for row in primary_rows:
        md.append(
            "| {module} | {metric} | {mean:.4f} | {sd:.4f} | {mcse:.4f} | {ci} | {pos:.2f} | {dz} |".format(
                module=row["module"],
                metric=row["metric"],
                mean=row["mean_diff"],
                sd=row["sd_diff"],
                mcse=row["mcse"],
                ci=fmt_ci(row["ci95"][0], row["ci95"][1]),
                pos=row["positive_fraction"],
                dz=(
                    f"{row['dz']:.2f}"
                    if row["dz"] is not None
                    else "—"
                ),
            )
        )
    md += [
        "",
        "## 下游行为后果（配对方向）",
        "",
        "| 模块 | 指标 | 预测方向 | 平均方向差 | 95% CI | 正方向占比 | 零差占比 | dz |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in downstream_rows:
        md.append(
            "| {module} | {metric} | {direction} | {mean:.4f} | {ci} | {pos:.2f} | {zero:.2f} | {dz} |".format(
                module=row["module"],
                metric=row["metric"],
                direction=row["predicted_direction"],
                mean=row["mean_directional_diff"],
                ci=fmt_ci(row["ci95"][0], row["ci95"][1]),
                pos=row["positive_fraction"],
                zero=row["zero_fraction"],
                dz=(
                    f"{row['dz']:.2f}"
                    if row["dz"] is not None
                    else "—"
                ),
            )
        )
    md += [
        "",
        "## 证据边界",
        "",
        "- 重复单位是独立的 seed × condition run（n=12 seed 对）；不把 resident/household/step 当独立样本。",
        "- memory 的操纵检查差为结构上限且方差为 0；其下游差跨 0，不能写成下游机制已通过。",
        "- 正式结论需结合 EVIDENCE_LEDGER 的 `RUNNING_PENDING_AUDIT` 转 `VERIFIED` 流程，本文档只是表格化中间产物。",
        "",
    ]

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(
            {
                "protocol_id": audit["protocol_id"],
                "audit_status": audit["audit_status"],
                "primary_manipulation_checks": primary_rows,
                "downstream_outcomes": downstream_rows,
                "run_stats": run_stats,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(OUT_JSON)


if __name__ == "__main__":
    main()
