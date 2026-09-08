"""Build the predeclared paired Carr-R validation prompt-sensitivity summary."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

import pandas as pd
from scipy.stats import t as student_t

from ds.eval.carr_protocol import file_sha256
from experiments.baselines.train_carr_r_frozen import load_model_table
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_RESULT = PROJECT_ROOT / "experiments/baselines/results/carr_r_deepseek_validation_pilot.json"
BASE_PREDICTIONS = PROJECT_ROOT / "experiments/baselines/results/carr_r_deepseek_validation_pilot_predictions.csv"
CONTEXT_RESULT = PROJECT_ROOT / "experiments/baselines/results/carr_r_deepseek_context_validation_pilot.json"
CONTEXT_PREDICTIONS = PROJECT_ROOT / "experiments/baselines/results/carr_r_deepseek_context_validation_pilot_predictions.csv"
CONTEXT_CONFIG = PROJECT_ROOT / "experiments/baselines/configs/carr_r_deepseek_context_validation.yaml"
FREEZE = PROJECT_ROOT / "experiments/carr/protocol/carr_r_deepseek_context_validation_freeze.json"
OUTPUT = PROJECT_ROOT / "experiments/baselines/results/carr_r_deepseek_context_validation_paired_summary.json"


def _group_row(
    table: pd.DataFrame,
    *,
    name: str,
    mask: pd.Series,
) -> dict[str, Any]:
    subset = table.loc[mask]
    return {
        "group": name,
        "n": int(len(subset)),
        "outcome_prevalence": float(subset["y_true"].mean()) if len(subset) else None,
        "base_error_rate": float(
            subset["base_decision"].ne(subset["y_true"]).mean()
        ) if len(subset) else None,
        "context_error_rate": float(
            subset["context_decision"].ne(subset["y_true"]).mean()
        ) if len(subset) else None,
        "base_mean_probability": float(subset["base_probability"].mean()) if len(subset) else None,
        "context_mean_probability": float(subset["context_probability"].mean()) if len(subset) else None,
    }


def build_summary() -> dict[str, Any]:
    base_result = json.loads(BASE_RESULT.read_text(encoding="utf-8"))
    context_result = json.loads(CONTEXT_RESULT.read_text(encoding="utf-8"))
    base = pd.read_csv(BASE_PREDICTIONS).rename(
        columns={
            "decision": "base_label",
            "probability_evacuated": "base_probability",
        }
    )
    context = pd.read_csv(CONTEXT_PREDICTIONS).rename(
        columns={
            "decision": "context_label",
            "probability_evacuated": "context_probability",
        }
    )
    paired = base.merge(
        context,
        on=["evaluation_index", "split", "y_true"],
        validate="one_to_one",
    )
    if len(paired) != 66 or set(paired["split"]) != {"validation"}:
        raise ValueError("paired validation summary requires the same 66 validation rows")
    paired["base_decision"] = paired["base_label"].eq("evacuate").astype(int)
    paired["context_decision"] = paired["context_label"].eq("evacuate").astype(int)
    paired["probability_difference"] = (
        paired["context_probability"] - paired["base_probability"]
    )
    differences = paired["probability_difference"].astype(float).tolist()
    mean = statistics.mean(differences)
    sd = statistics.stdev(differences)
    mcse = sd / math.sqrt(len(differences))
    half_width = float(student_t.ppf(0.975, df=len(differences) - 1)) * mcse

    config = yaml.safe_load(CONTEXT_CONFIG.read_text(encoding="utf-8"))
    model_table, _ = load_model_table(config)
    features = model_table.loc[model_table["split"].eq("validation")].copy()
    paired = paired.merge(
        features[
            [
                "evaluation_index",
                "age_group",
                "household_size",
                "vehicle_count",
                "income_bracket",
            ]
        ],
        on="evaluation_index",
        validate="one_to_one",
    )
    subgroup_rows = [
        _group_row(paired, name="age_65plus", mask=paired["age_group"].ge(7)),
        _group_row(paired, name="age_under65", mask=paired["age_group"].lt(7)),
        _group_row(paired, name="household_size_3plus", mask=paired["household_size"].ge(3)),
        _group_row(paired, name="household_size_1to2", mask=paired["household_size"].le(2)),
        _group_row(paired, name="zero_vehicles", mask=paired["vehicle_count"].eq(0)),
        _group_row(paired, name="oneplus_vehicles", mask=paired["vehicle_count"].ge(1)),
        _group_row(paired, name="income_below_50k", mask=paired["income_bracket"].le(5)),
        _group_row(paired, name="income_50k_plus", mask=paired["income_bracket"].ge(6)),
    ]
    base_to_context = pd.crosstab(
        paired["base_label"], paired["context_label"], dropna=False
    ).to_dict()
    return {
        "status": "PILOT_VALIDATION_ONLY",
        "track": "Carr-R",
        "n_paired": int(len(paired)),
        "test_split_opened": False,
        "prompt_versions": {
            "base": base_result["prompt_version"],
            "context": context_result["prompt_version"],
        },
        "metric_comparison": {
            metric: {
                "base": float(base_result["metrics"][metric]),
                "context": float(context_result["metrics"][metric]),
                "context_minus_base": float(
                    context_result["metrics"][metric]
                    - base_result["metrics"][metric]
                ),
            }
            for metric in ("accuracy", "macro_f1", "brier", "ece")
        },
        "decision_switches": {
            "n_switched": int(paired["base_label"].ne(paired["context_label"]).sum()),
            "base_to_context_table": base_to_context,
        },
        "paired_probability_difference": {
            "estimand": "context minus demographic-only probability_evacuated",
            "mean": mean,
            "sd": sd,
            "mcse": mcse,
            "paired_t_95_ci": [mean - half_width, mean + half_width],
            "median": float(paired["probability_difference"].median()),
            "minimum": float(paired["probability_difference"].min()),
            "maximum": float(paired["probability_difference"].max()),
        },
        "subgroup_diagnostics": subgroup_rows,
        "interpretation": {
            "context_improved_macro_f1": bool(
                context_result["metrics"]["macro_f1"]
                > base_result["metrics"]["macro_f1"]
            ),
            "context_improved_brier": bool(
                context_result["metrics"]["brier"]
                < base_result["metrics"]["brier"]
            ),
            "context_improved_ece": bool(
                context_result["metrics"]["ece"]
                < base_result["metrics"]["ece"]
            ),
            "context_true_non_evacuated_identified": int(
                context_result["metrics"]["confusion_matrix_labels_0_1"][0][0]
            ),
        },
        "claim_boundary": (
            "Paired validation-only prompt-context sensitivity. This cannot select "
            "a final prompt by test performance and is not platform-validity evidence."
        ),
        "provenance": {
            "base_result_sha256": file_sha256(BASE_RESULT),
            "base_predictions_sha256": file_sha256(BASE_PREDICTIONS),
            "context_result_sha256": file_sha256(CONTEXT_RESULT),
            "context_predictions_sha256": file_sha256(CONTEXT_PREDICTIONS),
            "context_config_sha256": file_sha256(CONTEXT_CONFIG),
            "freeze_sha256": file_sha256(FREEZE),
            "runner_sha256": file_sha256(Path(__file__)),
        },
    }


def main() -> None:
    summary = build_summary()
    OUTPUT.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
