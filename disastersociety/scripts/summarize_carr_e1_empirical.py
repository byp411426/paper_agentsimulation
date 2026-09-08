"""Audit the frozen five-seed Carr-S E1 empirical scenario."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

import yaml
from scipy.stats import t as student_t

from ds.eval.carr_protocol import file_sha256


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "experiments/carr/configs/carr_s_e1_empirical_deepseek_v1.yaml"
DEFAULT_RESULTS = PROJECT_ROOT / "experiments/carr/results"


def _interval(values: list[float]) -> dict[str, Any]:
    n = len(values)
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    mcse = sd / math.sqrt(n)
    half_width = float(student_t.ppf(0.975, df=n - 1)) * mcse if n > 1 else None
    return {
        "n_seeds": n,
        "mean": mean,
        "sd": sd,
        "mcse": mcse,
        "t_95_ci": (
            [mean - half_width, mean + half_width]
            if half_width is not None
            else None
        ),
        "minimum": min(values),
        "maximum": max(values),
    }


def _interval_or_none(values: list[float]) -> dict[str, Any] | None:
    return _interval(values) if values else None


def build_summary(
    *,
    config_path: Path = DEFAULT_CONFIG,
    results_dir: Path = DEFAULT_RESULTS,
) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    protocol = cfg["experiment"]["formal_protocol"]
    seeds = [int(seed) for seed in protocol["seeds"]]
    selected: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for seed in seeds:
        path = results_dir / f"carr_s_e1_empirical_v1_seed{seed}.json"
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["protocol_id"] != protocol["protocol_id"]:
            raise ValueError(f"E1 protocol identity mismatch: {path}")
        if int(payload["seed"]) != seed:
            raise ValueError(f"E1 seed identity mismatch: {path}")
        selected.append(payload)
        sources.append(
            {
                "seed": seed,
                "path": str(path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(path),
            }
        )

    completed_seeds = [int(payload["seed"]) for payload in selected]
    valid = [
        payload for payload in selected if payload["terminal_status"] == "VALID"
    ]
    scalar_metrics = [
        "focal_evacuation_rate",
        "focal_minus_survey_evacuation_rate",
        "complete_household_safe_departure_rate",
        "coordinated_departure_rate",
        "dependent_safety_rate",
        "execution_rejections_per_household",
        "dependent_left_behind_rejections_per_household",
        "resource_conflict_rejections_per_household",
        "messages_sent",
        "n_logical_decisions",
        "fallback_rate",
        "cost_usd",
        "wall_clock_seconds",
    ]
    estimates = {
        metric: _interval(
            [float(payload["metrics"][metric]) for payload in valid]
        )
        for metric in scalar_metrics
        if valid
    }
    if valid:
        cdf_horizons = [
            str(value) for value in cfg["experiment"]["cdf_horizons_hours"]
        ]
        timing = {
            "eligible_simulated_focal_count": _interval(
                [
                    float(payload["metrics"]["order_to_departure"][
                        "eligible_simulated_focal_count"
                    ])
                    for payload in valid
                ]
            ),
            "mean_hours": _interval_or_none(
                [
                    float(payload["metrics"]["order_to_departure"]["mean_hours"])
                    for payload in valid
                    if payload["metrics"]["order_to_departure"]["mean_hours"]
                    is not None
                ]
            ),
            "median_hours": _interval_or_none(
                [
                    float(payload["metrics"]["order_to_departure"]["median_hours"])
                    for payload in valid
                    if payload["metrics"]["order_to_departure"]["median_hours"]
                    is not None
                ]
            ),
            "mean_absolute_cdf_difference": _interval_or_none(
                [
                    float(payload["metrics"]["order_to_departure"][
                        "mean_absolute_cdf_difference"
                    ])
                    for payload in valid
                    if payload["metrics"]["order_to_departure"][
                        "mean_absolute_cdf_difference"
                    ] is not None
                ]
            ),
            "cdf_by_horizon": {
                horizon: _interval_or_none(
                    [
                        float(payload["metrics"]["order_to_departure"][
                            "simulated_cdf"
                        ][horizon])
                        for payload in valid
                        if payload["metrics"]["order_to_departure"][
                            "simulated_cdf"
                        ][horizon] is not None
                    ]
                )
                for horizon in cdf_horizons
            },
            "survey_main_cdf": valid[0]["metrics"]["order_to_departure"][
                "survey_main_cdf"
            ],
        }
    else:
        timing = {}

    subgroup_summary: list[dict[str, Any]] = []
    if valid:
        contrasts = [
            row["contrast"]
            for row in valid[0]["metrics"]["subgroup_evacuation_gaps"]
        ]
        for contrast in contrasts:
            rows = [
                next(
                    row
                    for row in payload["metrics"]["subgroup_evacuation_gaps"]
                    if row["contrast"] == contrast
                )
                for payload in valid
            ]
            available = [row for row in rows if row["signed_gap"] is not None]
            subgroup_summary.append(
                {
                    "contrast": contrast,
                    "available_seed_count": len(available),
                    "simulation_gap": (
                        _interval([float(row["signed_gap"]) for row in available])
                        if available
                        else None
                    ),
                    "simulation_minus_survey_gap": (
                        _interval(
                            [
                                float(row["simulation_minus_survey_gap"])
                                for row in available
                                if row["simulation_minus_survey_gap"] is not None
                            ]
                        )
                        if any(
                            row["simulation_minus_survey_gap"] is not None
                            for row in available
                        )
                        else None
                    ),
                    "survey_status": rows[0]["survey_status"],
                    "survey_signed_gap": rows[0]["survey_signed_gap"],
                }
            )

    matrix_complete = completed_seeds == seeds and len(valid) == len(seeds)
    return {
        "status": (
            "READY_FOR_LEDGER_AUDIT" if matrix_complete else "PILOT_IN_PROGRESS"
        ),
        "activity_type": "CARR_S_E1_EMPIRICAL_MULTI_SEED_AUDIT",
        "protocol_id": protocol["protocol_id"],
        "decision_model": cfg["llm"]["decision_model"],
        "prompt_version": cfg["experiment"]["prompt_version"],
        "completion": {
            "declared_seeds": seeds,
            "completed_seeds": completed_seeds,
            "valid_seeds": [int(payload["seed"]) for payload in valid],
            "remaining_seeds": [seed for seed in seeds if seed not in completed_seeds],
            "matrix_complete": matrix_complete,
            "carr_r_test_split_opened": False,
        },
        "estimates_across_independent_seeds": estimates,
        "order_to_departure": timing,
        "subgroup_evacuation_gaps": subgroup_summary,
        "seed_results": [payload["metrics"] for payload in selected],
        "source": {
            "configuration": {
                "path": str(config_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(config_path),
            },
            "seed_results": sources,
            "summarizer_sha256": file_sha256(Path(__file__)),
        },
        "claim_boundary": (
            "Carr-informed controlled empirical-reasonableness evidence. Survey "
            "agreement is not historical reconstruction, and official warning "
            "receipt remains calibration rather than independent validation."
        ),
        "blind_human_or_expert_rating_status": "PLANNED_SEPARATE_PACKET_AND_RATERS",
    }


def main() -> None:
    summary = build_summary()
    output = PROJECT_ROOT / (
        "experiments/carr/results/carr_s_e1_empirical_v1_cumulative_summary.json"
    )
    output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
