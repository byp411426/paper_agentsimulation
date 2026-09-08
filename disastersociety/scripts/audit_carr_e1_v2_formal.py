"""Audit the three E1 v2 formal minimal-sample runs and render the paper table.

Checks terminal status, step completeness, llm_calls health, summarizes seed
variance and compares to the Carr aggregate reference with explicit estimand
labels. Writes experiments/carr/results/carr_s_e1_v2_formal_audit.{md,json}.
"""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT_ROOT / "experiments/carr/results"
RUNS = PROJECT_ROOT / "experiments/carr/runs"
REFERENCE = (
    RESULTS / "carr_s_e1_empirical_reference" / "reference_summary.json"
)
OUT_MD = RESULTS / "carr_s_e1_v2_formal_audit.md"
OUT_JSON = RESULTS / "carr_s_e1_v2_formal_audit.json"

SEEDS = [
    (7201, "e1_formal_r7_seed7201", "carr_s_e1_v2_formal_r7_seed7201_summary.json"),
    (8301, "e1_formal_r10_seed8301", "carr_s_e1_v2_formal_r10_seed8301_summary.json"),
    (9401, "e1_formal_r9_seed9401", "carr_s_e1_v2_formal_r9_seed9401_summary.json"),
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def sd(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def main() -> None:
    reference = load(REFERENCE)
    rows = []
    for seed, run_dir_name, summary_name in SEEDS:
        run_dir = RUNS / run_dir_name / "carr_s_e1_v2_formal"
        run_summary = load(run_dir / "run_summary.json")
        events_summary = load(run_dir / "events" / "summary.json")
        calls = [
            json.loads(line)
            for line in (run_dir / "llm_calls.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        status_counts: dict[str, int] = {}
        for call in calls:
            status_counts[call["status"]] = status_counts.get(call["status"], 0) + 1
        summary = load(RESULTS / summary_name)
        rows.append(
            {
                "seed": seed,
                "run_status": run_summary["status"],
                "reason_code": run_summary.get("reason_code"),
                "planned_steps": events_summary["planned_steps"],
                "completed_steps": events_summary["completed_steps"],
                "n_llm_calls": len(calls),
                "llm_status_counts": status_counts,
                "complete_safe_household_departure_rate": summary[
                    "complete_safe_household_departure_rate"
                ],
                "coordinated_household_rate": summary[
                    "coordinated_household_rate"
                ],
                "split_departure_household_rate": summary[
                    "split_departure_household_rate"
                ],
                "violation_counts": {
                    "care_recipient_left_behind": summary[
                        "care_recipient_left_behind_count"
                    ],
                    "vehicle_conflict": summary["vehicle_conflict_count"],
                    "capacity_rejection": summary["capacity_rejection_count"],
                    "caregiver_violation": summary["caregiver_violation_count"],
                },
                "message_funnel": summary["message_funnel"],
                "official_receipt_counts": summary["official_receipt_counts"],
            }
        )

    safe = [r["complete_safe_household_departure_rate"] for r in rows]
    coord = [r["coordinated_household_rate"] for r in rows]
    split = [r["split_departure_household_rate"] for r in rows]
    funnel_totals = {
        key: sum(r["message_funnel"][key] for r in rows)
        for key in ("sent", "delivered", "processed", "accepted", "rejected")
    }
    violations_total = {
        key: sum(r["violation_counts"][key] for r in rows)
        for key in (
            "care_recipient_left_behind",
            "vehicle_conflict",
            "capacity_rejection",
            "caregiver_violation",
        )
    }
    all_valid = all(
        r["run_status"] == "VALID"
        and r["reason_code"] is None
        and r["completed_steps"] == r["planned_steps"]
        and r["llm_status_counts"].get("failed", 0) == 0
        and r["llm_status_counts"].get("fatal_backend_error", 0) == 0
        for r in rows
    )

    ref_evac = reference["evacuation_outcome"]
    ref_delay = reference["order_to_departure_delay"]["main_consistent_temporal_order"]

    audit = {
        "protocol": "carr_s_e1_v2_formal_minimal_sample",
        "seeds": rows,
        "aggregate": {
            "n_runs": len(rows),
            "all_runs_valid_and_complete": all_valid,
            "complete_safe_household_departure_rate_mean": mean(safe),
            "complete_safe_household_departure_rate_sd": sd(safe),
            "per_seed_values": safe,
            "coordinated_household_rate_mean": mean(coord),
            "coordinated_household_rate_sd": sd(coord),
            "per_seed_values_coordinated": coord,
            "split_departure_household_rate_mean": mean(split),
            "message_funnel_totals": funnel_totals,
            "violation_totals": violations_total,
        },
        "reference_comparison": {
            "survey_individual_evacuation_rate": ref_evac["proportion"],
            "survey_wilson_95_ci": ref_evac["wilson_95_ci"],
            "survey_order_to_departure_5h_cdf": ref_delay["cdf"].get("5"),
            "simulation_estimand": "complete safe household departure (all members reach safe zone)",
            "comparison_status": "DIRECTIONAL_ONLY_DIFFERENT_ESTIMANDS",
        },
        "evidence_label": "RUNNING_PENDING_AUDIT",
        "claim_boundary": "Carr-informed controlled scenario; not historical reconstruction, not population representative, not individual-level validation.",
    }

    md = [
        "# Carr-S E1 v2 正式最小样本审计（3 seed × 24 户 × 25 步）",
        "",
        f"- 全部 run VALID 且步数完整、0 failed/fatal：**{all_valid}**",
        f"- 完整安全整户出发率：{mean(safe):.3f} ± {sd(safe):.3f}（seed 值 {[f'{v:.3f}' for v in safe]}）",
        f"- 协调出发户率：{mean(coord):.3f} ± {sd(coord):.3f}（seed 值 {[f'{v:.3f}' for v in coord]}）",
        f"- 拆分出发户率：{mean(split):.3f}（{[f'{v:.3f}' for v in split]}）",
        f"- 消息漏斗合计：{funnel_totals['sent']} sent → {funnel_totals['delivered']} delivered → {funnel_totals['processed']} processed → {funnel_totals['accepted']} accepted / {funnel_totals['rejected']} rejected",
        f"- 约束违规合计：照护遗留 {violations_total['care_recipient_left_behind']}、车辆冲突 {violations_total['vehicle_conflict']}、超载 {violations_total['capacity_rejection']}、照护违规 {violations_total['caregiver_violation']}",
        "",
        "## 与 Carr 问卷参照（仅方向性，不同 estimand）",
        "",
        f"- 问卷个体撤离率 {ref_evac['proportion']:.3f}（Wilson 95% CI {ref_evac['wilson_95_ci']}）；仿真是“整户安全到达”口径，均值 {mean(safe):.3f}，两者不可直接相等比较。",
        f"- 问卷首次命令后 5 小时内出发累计 {ref_delay['cdf'].get('5', float('nan')):.3f}；仿真大部分出发集中在强制令当天，方向一致但时间标尺不同。",
        "",
        "## 证据边界",
        "",
        "- 标签 `RUNNING_PENDING_AUDIT`：本文件是审计中间产物；完整 provenance 复核后按 `VERIFIED` 规则再提升。",
        "- 37 名未撤离者样本很小，问卷参照只用于方向合理性，不构成行为验证。",
        "",
    ]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    OUT_JSON.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(OUT_JSON)


if __name__ == "__main__":
    main()
