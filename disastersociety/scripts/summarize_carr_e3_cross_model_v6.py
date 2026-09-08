"""Summarize the bounded four-model Carr-S v6 robustness pilot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import (
    CONDITIONS,
    PRIMARY_MECHANISM_METRICS_V6,
    paired_mechanism_analysis,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJECT_ROOT / "experiments/carr/runs"
OUTPUT = (
    PROJECT_ROOT
    / "experiments/carr/results/carr_s_e3_cross_model_v6_pilot_summary.json"
)

MODEL_RUN_PREFIXES = {
    "packy-qwen3.5-plus": "carr_s_e3_qwen35_v6_thinking_pilot_r1",
    "packy-glm-5": "carr_s_e3_glm5_v6_thinking_pilot_r1",
    "packy-minimax-m2.7": "carr_s_e3_minimax_m27_v6_thinking_pilot_r3",
}

DEEPSEEK_SELECTED_RUNS = {
    (101, "full"): "carr_s_deepseek_v6_thinking_high_pilot_r1_full_seed101",
    (101, "full_minus_memory"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r1_full_minus_memory_seed101"
    ),
    (101, "full_minus_feedback"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_feedback_seed101"
    ),
    (101, "full_minus_planning"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_planning_seed101"
    ),
    (101, "full_minus_interaction"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_interaction_seed101"
    ),
    (202, "full"): "carr_s_deepseek_v6_thinking_high_pilot_r2_full_seed202",
    (202, "full_minus_memory"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_memory_seed202"
    ),
    (202, "full_minus_feedback"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_feedback_seed202"
    ),
    (202, "full_minus_planning"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_planning_seed202"
    ),
    (202, "full_minus_interaction"): (
        "carr_s_deepseek_v6_thinking_high_pilot_r2_full_minus_interaction_seed202"
    ),
}

TECHNICAL_EXCLUSIONS = [
    "carr_s_deepseek_v6_thinking_high_pilot_full_seed101",
    "carr_s_deepseek_v6_thinking_high_pilot_r1_full_minus_feedback_seed101",
    "carr_s_e3_minimax_m27_v6_thinking_pilot_r1_full_minus_planning_seed101",
    "carr_s_e3_minimax_m27_v6_thinking_pilot_r2_full_minus_planning_seed101",
]


def _selected_run_id(model: str, seed: int, condition: str) -> str:
    if model == "packy-deepseek-v4-flash":
        return DEEPSEEK_SELECTED_RUNS[(seed, condition)]
    return f"{MODEL_RUN_PREFIXES[model]}_{condition}_seed{seed}"


def _load_run(
    model: str,
    seed: int,
    condition: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], set[str]]:
    run_id = _selected_run_id(model, seed, condition)
    run_dir = RUNS_ROOT / run_id
    summary_path = run_dir / "summary.json"
    metrics_path = run_dir / "mechanism_metrics.json"
    provenance_path = run_dir / "provenance.json"
    calls_path = run_dir / "llm_calls.jsonl"
    for path in (summary_path, metrics_path, provenance_path, calls_path):
        if not path.exists():
            raise FileNotFoundError(path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    if summary["status"] != "VALID":
        raise ValueError(f"selected run is not VALID: {run_id}")
    if metrics["condition"] != condition or int(metrics["seed"]) != seed:
        raise ValueError(f"selected run identity mismatch: {run_id}")
    row = dict(metrics)
    row["run_terminal_status"] = summary["status"]
    artifact = {
        "model": model,
        "seed": seed,
        "condition": condition,
        "run_dir": str(run_dir.relative_to(PROJECT_ROOT)),
        "summary_sha256": file_sha256(summary_path),
        "mechanism_metrics_sha256": file_sha256(metrics_path),
        "provenance_sha256": file_sha256(provenance_path),
        "llm_calls_sha256": file_sha256(calls_path),
    }
    response_models: set[str] = set()
    for line in calls_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("response_model"):
            response_models.add(str(record["response_model"]))
    return row, summary, artifact, response_models


def build_summary() -> dict[str, Any]:
    models = [
        "packy-deepseek-v4-flash",
        "packy-qwen3.5-plus",
        "packy-glm-5",
        "packy-minimax-m2.7",
    ]
    all_paired: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    model_summaries: dict[str, Any] = {}
    selected_gateway_totals = {
        "n_ok": 0,
        "n_cache": 0,
        "n_failed": 0,
        "n_fallback": 0,
    }
    for model in models:
        rows: list[dict[str, Any]] = []
        summaries: list[dict[str, Any]] = []
        observed_response_models: set[str] = set()
        for seed in (101, 202):
            for condition in CONDITIONS:
                row, summary, artifact, observed = _load_run(
                    model,
                    seed,
                    condition,
                )
                rows.append(row)
                summaries.append(summary)
                artifacts.append(artifact)
                observed_response_models.update(observed)
        paired, paired_summary = paired_mechanism_analysis(
            rows,
            metric_map=PRIMARY_MECHANISM_METRICS_V6,
            require_valid=True,
        )
        for item in paired:
            item["model"] = model
        all_paired.extend(paired)
        full_rows = {
            int(row["seed"]): row
            for row in rows
            if row["condition"] == "full"
        }
        model_gateway = {
            key: sum(int(summary["gateway"][key]) for summary in summaries)
            for key in selected_gateway_totals
        }
        for key, value in model_gateway.items():
            selected_gateway_totals[key] += value
        model_summaries[model] = {
            "selected_run_status_counts": {"VALID": len(rows)},
            "gateway_totals": model_gateway,
            "observed_response_models": sorted(observed_response_models),
            "paired_summary": paired_summary,
            "full_condition_opportunity_diagnostics": [
                {
                    "seed": seed,
                    "planned_primary_count": int(
                        full_rows[seed]["planned_primary_count"]
                    ),
                    "feedback_or_replanning_opportunity_observed": bool(
                        full_rows[seed]["planned_primary_count"] > 0
                    ),
                    "messages_sent": int(full_rows[seed]["messages_sent"]),
                    "post_closure_feasible_commitment_rate": float(
                        full_rows[seed][
                            "post_closure_feasible_commitment_rate"
                        ]
                    ),
                    "invalid_proposal_attempts": int(
                        full_rows[seed]["invalid_proposal_attempts"]
                    ),
                    "invalid_acceptance_attempts": int(
                        full_rows[seed]["invalid_acceptance_attempts"]
                    ),
                }
                for seed in (101, 202)
            ],
        }

    cross_model_module_summary: list[dict[str, Any]] = []
    for module in PRIMARY_MECHANISM_METRICS_V6:
        values = [
            float(item["paired_difference"])
            for item in all_paired
            if item["module"] == module
        ]
        cross_model_module_summary.append(
            {
                "module": module,
                "metric": PRIMARY_MECHANISM_METRICS_V6[module],
                "n_model_seed_pairs": len(values),
                "positive_pairs": sum(value > 0 for value in values),
                "zero_pairs": sum(value == 0 for value in values),
                "negative_pairs": sum(value < 0 for value in values),
                "positive_fraction": sum(value > 0 for value in values)
                / len(values),
                "claim_boundary": (
                    "Descriptive model-by-seed sign stability only; the eight "
                    "pairs are not eight independent model replications."
                ),
            }
        )

    exclusions: list[dict[str, Any]] = []
    for run_id in TECHNICAL_EXCLUSIONS:
        run_dir = RUNS_ROOT / run_id
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        exclusions.append(
            {
                "run_dir": str(run_dir.relative_to(PROJECT_ROOT)),
                "status": summary["status"],
                "reason_code": summary.get("reason_code"),
                "abort_reason": summary.get("abort_reason"),
                "summary_sha256": file_sha256(summary_path),
                "scientific_pair_used": False,
            }
        )

    return {
        "status": "PILOT",
        "activity_type": "E3_CROSS_MODEL_ROBUSTNESS_PILOT_DERIVED_SUMMARY",
        "case_semantics": "Carr-informed controlled mechanism scenario",
        "metric_protocol_version": "v6",
        "n_households_per_run": 2,
        "seeds": [101, 202],
        "conditions": list(CONDITIONS),
        "models": models,
        "selected_run_status_counts": {"VALID": len(artifacts)},
        "selected_gateway_totals": selected_gateway_totals,
        "model_summaries": model_summaries,
        "paired_primary_differences": all_paired,
        "cross_model_module_summary": cross_model_module_summary,
        "selected_artifacts": artifacts,
        "technical_exclusions": exclusions,
        "interpretation": {
            "strongest_directional_stability": "memory",
            "not_yet_cross_model_stable": [
                "feedback",
                "planning",
                "interaction",
            ],
            "opportunity_caveat": (
                "MiniMax full runs formed no primary-route plan, so its zero "
                "feedback and planning contrasts also reflect absent exposure "
                "to the intended adaptation opportunity."
            ),
            "formal_claim_allowed": False,
            "next_action": (
                "Increase households per run and predeclare an opportunity-"
                "eligible cohort/scenario before formal seed sizing."
            ),
        },
        "limitations": [
            "Two seeds and two households per run are insufficient for formal inference.",
            "All model families were accessed through the same Packy proxy.",
            "Model-native thinking and structured-output transports differ by endpoint.",
            "The controlled route obstruction is not a historical Carr closure.",
            "The cohort is selected for mechanism identification and is not population-representative.",
        ],
    }


def main() -> None:
    payload = build_summary()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
