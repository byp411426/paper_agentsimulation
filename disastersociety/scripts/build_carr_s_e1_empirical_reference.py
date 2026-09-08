"""Build aggregate Carr-S E1 empirical reference artifacts.

Outputs contain no respondent identifiers. Channel prevalence is retained as
multi-select prevalence; the overall official-warning receipt margin is marked
as calibration because `delivery_params.yaml` was tuned to the same survey.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SURVEY = (
    PROJECT_ROOT / "eventpacks/carr_2018/behavior/survey_clean.csv"
)
DEFAULT_PROTOCOL = (
    PROJECT_ROOT
    / "experiments/carr/protocol/carr_s_e1_empirical_reference_v1_1_freeze.json"
)
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "experiments/carr/results/carr_s_e1_empirical_reference"
)
CHANNELS = (
    "reverse_911",
    "text",
    "television",
    "radio",
    "flyer",
    "public_official",
    "social_media",
    "subscribed_service",
    "website",
    "smartphone_app",
    "interpersonal",
    "billboard",
    "other",
)
HORIZON_HOURS = (0, 0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 24, 48)
BOOTSTRAP_SEED = 20260802
BOOTSTRAP_REPLICATES = 20_000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--survey", type=Path, default=DEFAULT_SURVEY)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def _bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> list[float]:
    if n <= 0:
        return [math.nan, math.nan]
    proportion = successes / n
    denominator = 1 + z * z / n
    center = (proportion + z * z / (2 * n)) / denominator
    half = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / n + z * z / (4 * n * n)
        )
        / denominator
    )
    return [center - half, center + half]


def proportion_summary(values: pd.Series) -> dict[str, Any]:
    clean = values.dropna().astype(int)
    successes = int(clean.sum())
    n = int(len(clean))
    return {
        "n": n,
        "successes": successes,
        "proportion": successes / n if n else math.nan,
        "wilson_95_ci": wilson_interval(successes, n),
    }


def delay_summary(values: pd.Series) -> dict[str, Any]:
    array = values.dropna().to_numpy(dtype=float)
    quantiles = (0, 0.25, 0.5, 0.75, 0.9, 0.95, 1)
    return {
        "n": int(len(array)),
        "mean_hours": float(np.mean(array)),
        "sd_hours": float(np.std(array, ddof=1)),
        "quantiles_hours": {
            str(q): float(np.quantile(array, q)) for q in quantiles
        },
        "cdf": {
            str(horizon): float(np.mean(array <= horizon))
            for horizon in HORIZON_HOURS
        },
    }


def subgroup_gap(
    frame: pd.DataFrame,
    *,
    name: str,
    group_a: Callable[[pd.DataFrame], pd.Series],
    group_b: Callable[[pd.DataFrame], pd.Series],
    group_a_label: str,
    group_b_label: str,
) -> dict[str, Any]:
    subset = frame[frame["evacuated"].notna()].copy()
    a = subset.loc[group_a(subset), "evacuated"].astype(float).to_numpy()
    b = subset.loc[group_b(subset), "evacuated"].astype(float).to_numpy()
    if len(a) == 0 or len(b) == 0:
        return {
            "contrast": name,
            "definition": f"{group_a_label} minus {group_b_label}",
            "status": "UNAVAILABLE_EMPTY_GROUP",
            "group_a": {
                "label": group_a_label,
                "n": int(len(a)),
                "successes": int(a.sum()),
                "proportion": float(a.mean()) if len(a) else None,
                "wilson_95_ci": (
                    wilson_interval(int(a.sum()), len(a)) if len(a) else None
                ),
            },
            "group_b": {
                "label": group_b_label,
                "n": int(len(b)),
                "successes": int(b.sum()),
                "proportion": float(b.mean()) if len(b) else None,
                "wilson_95_ci": (
                    wilson_interval(int(b.sum()), len(b)) if len(b) else None
                ),
            },
            "signed_gap": None,
            "bootstrap_percentile_95_ci": None,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates": 0,
            "replacement_contrast_added": False,
        }
    gap = float(a.mean() - b.mean())
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    boot = np.empty(BOOTSTRAP_REPLICATES, dtype=float)
    for index in range(BOOTSTRAP_REPLICATES):
        boot[index] = (
            rng.choice(a, size=len(a), replace=True).mean()
            - rng.choice(b, size=len(b), replace=True).mean()
        )
    return {
        "contrast": name,
        "definition": f"{group_a_label} minus {group_b_label}",
        "status": "ESTIMABLE",
        "group_a": {
            "label": group_a_label,
            **proportion_summary(pd.Series(a)),
        },
        "group_b": {
            "label": group_b_label,
            **proportion_summary(pd.Series(b)),
        },
        "signed_gap": gap,
        "bootstrap_percentile_95_ci": [
            float(np.quantile(boot, 0.025)),
            float(np.quantile(boot, 0.975)),
        ],
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
    }


def build_reference(survey: pd.DataFrame) -> dict[str, Any]:
    eligible = survey[_bool(survey["evacuation_eval_eligible"])].copy()
    consistent = ~_bool(survey["order_response_inconsistent"])
    warned = survey["warned_official"].eq(1)

    channel_cohorts = {
        "main_consistent_warned": survey[warned & consistent],
        "sensitivity_affirmative_order_priority": survey[warned],
    }
    channel_rows: list[dict[str, Any]] = []
    for cohort, frame in channel_cohorts.items():
        for channel in CHANNELS:
            channel_rows.append(
                {
                    "cohort": cohort,
                    "channel": channel,
                    **proportion_summary(frame[f"heard_{channel}"]),
                }
            )

    valid_delay = (
        eligible["evacuated"].eq(1)
        & eligible["first_evacuation_order_at"].notna()
        & eligible["evacuated_at"].notna()
        & ~_bool(eligible["warning_after_evacuation"])
    )
    delay_base = eligible[valid_delay].copy()
    delay_base["delay_hours"] = (
        delay_base["evacuated_at"]
        - delay_base["first_evacuation_order_at"]
    ).dt.total_seconds() / 3600
    delay_cohorts = {
        "main_consistent_temporal_order": delay_base[
            ~_bool(delay_base["order_response_inconsistent"])
        ],
        "sensitivity_affirmative_order_priority": delay_base,
    }

    subgroup_frame = eligible.copy()
    subgroup_results = [
        subgroup_gap(
            subgroup_frame[subgroup_frame["age_group"].notna()],
            name="age_65plus_minus_under65",
            group_a=lambda d: d["age_group"].ge(7),
            group_b=lambda d: d["age_group"].lt(7),
            group_a_label="age 65+",
            group_b_label="age under 65",
        ),
        subgroup_gap(
            subgroup_frame[subgroup_frame["household_size"].notna()],
            name="household_3plus_minus_1to2",
            group_a=lambda d: d["household_size"].ge(3),
            group_b=lambda d: d["household_size"].le(2),
            group_a_label="household size 3+",
            group_b_label="household size 1-2",
        ),
        subgroup_gap(
            subgroup_frame[subgroup_frame["vehicle_count"].notna()],
            name="zero_vehicle_minus_oneplus",
            group_a=lambda d: d["vehicle_count"].eq(0),
            group_b=lambda d: d["vehicle_count"].ge(1),
            group_a_label="zero vehicles",
            group_b_label="one or more vehicles",
        ),
        subgroup_gap(
            subgroup_frame[subgroup_frame["income_bracket"].notna()],
            name="income_under50k_minus_50kplus",
            group_a=lambda d: d["income_bracket"].le(5),
            group_b=lambda d: d["income_bracket"].ge(6),
            group_a_label="income under $50k",
            group_b_label="income $50k+",
        ),
    ]

    return {
        "status": "VERIFIED_AGGREGATE_REFERENCE_CONSTRUCTION",
        "evidence_boundary": (
            "These are respondent-sample aggregate references, not weighted "
            "population truth or proof that Carr-S behavior is realistic."
        ),
        "evacuation_outcome": {
            "cohort": "Q9.1 evaluation-eligible finished respondents",
            **proportion_summary(eligible["evacuated"]),
        },
        "order_to_departure_delay": {
            cohort: delay_summary(frame["delay_hours"])
            for cohort, frame in delay_cohorts.items()
        },
        "warning_channel_prevalence": {
            "estimand": "multi-select prevalence among reported order recipients",
            "overall_official_receipt_role": "CALIBRATION",
            "comparison_to_first_heard_prohibited": True,
            "rows": channel_rows,
        },
        "subgroup_evacuation_gaps": subgroup_results,
    }


def main() -> None:
    args = parse_args()
    survey_path = _resolve(args.survey).resolve()
    protocol_path = _resolve(args.protocol).resolve()
    output_dir = _resolve(args.output_dir).resolve()
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol["status"] != "FROZEN_BEFORE_REFERENCE_BUILD":
        raise ValueError("Carr-S E1 reference protocol is not frozen")
    for source in protocol["frozen_sources"]:
        path = PROJECT_ROOT / source["path"]
        if file_sha256(path) != source["sha256"]:
            raise ValueError(f"frozen source hash mismatch: {path}")

    survey = pd.read_csv(
        survey_path,
        parse_dates=["first_evacuation_order_at", "evacuated_at"],
    )
    result = build_reference(survey)
    result["source"] = {
        "survey": str(survey_path.relative_to(PROJECT_ROOT)),
        "survey_sha256": file_sha256(survey_path),
        "protocol": str(protocol_path.relative_to(PROJECT_ROOT)),
        "protocol_sha256": file_sha256(protocol_path),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "reference_summary.json"
    summary_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    channel_frame = pd.DataFrame(
        result["warning_channel_prevalence"]["rows"]
    )
    channel_frame.to_csv(output_dir / "channel_prevalence.csv", index=False)
    subgroup_frame_out = pd.DataFrame(result["subgroup_evacuation_gaps"])
    subgroup_frame_out.to_json(
        output_dir / "subgroup_evacuation_gaps.jsonl",
        orient="records",
        lines=True,
        force_ascii=False,
    )
    cdf_rows = []
    for cohort, summary in result["order_to_departure_delay"].items():
        for horizon, proportion in summary["cdf"].items():
            cdf_rows.append(
                {
                    "cohort": cohort,
                    "horizon_hours": float(horizon),
                    "cumulative_departure_proportion": proportion,
                    "n": summary["n"],
                }
            )
    pd.DataFrame(cdf_rows).to_csv(
        output_dir / "order_to_departure_cdf.csv", index=False
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
