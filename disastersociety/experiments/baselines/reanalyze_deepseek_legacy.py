"""Re-evaluate historical DeepSeek responses on corrected Carr-R validation labels.

This does not turn the old run into formal evidence: the old runner lacked the
current gateway provenance, exported respondent IDs, and was executed before the
comparison protocol was frozen.  It is nevertheless a useful no-cost pilot
because the stored prompt inputs were demographic-only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ds.eval.carr_protocol import file_sha256
from ds.eval.individual import (
    decision_confidence_to_positive_probability,
)
from experiments.baselines.train_carr_r_frozen import (
    classification_metrics,
    conditional_stratified_bootstrap,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LEGACY_PREDICTIONS = (
    PROJECT_ROOT
    / "experiments/baselines/results/"
    "llm_static_deepseek-v4-flash_predictions.csv"
)
LEGACY_SUMMARY = (
    PROJECT_ROOT
    / "experiments/baselines/results/"
    "llm_static_deepseek-v4-flash.json"
)
LEGACY_LOG = (
    PROJECT_ROOT
    / "experiments/baselines/results/llm_static_full.log"
)
EVALUATION = (
    PROJECT_ROOT
    / "eventpacks/carr_2018/behavior/evaluation_respondents.csv"
)
SPLIT = PROJECT_ROOT / "experiments/carr/protocol/carr_r_split.csv"
RESULT = (
    PROJECT_ROOT
    / "experiments/baselines/results/"
    "deepseek_v4flash_legacy_validation_reanalysis.json"
)
PREDICTIONS = (
    PROJECT_ROOT
    / "experiments/baselines/results/"
    "deepseek_v4flash_legacy_validation_reanalysis_predictions.csv"
)


def main() -> None:
    legacy = pd.read_csv(LEGACY_PREDICTIONS)
    evaluation = pd.read_csv(EVALUATION)
    split = pd.read_csv(SPLIT)
    required = {
        "respondent_id",
        "evacuated",
        "llm_pred",
        "llm_confidence",
    }
    if not required <= set(legacy.columns):
        raise ValueError("legacy DeepSeek predictions lack required fields")
    if legacy["respondent_id"].duplicated().any():
        raise ValueError("legacy respondent IDs are not unique")

    # respondent_id is used only for restricted one-to-one linkage. It is not
    # included in the reanalysis artifact.
    joined = evaluation.merge(
        legacy,
        on="respondent_id",
        how="left",
        validate="one_to_one",
        suffixes=("_corrected", "_legacy"),
    ).merge(
        split,
        on="evaluation_index",
        how="left",
        validate="one_to_one",
    )
    if joined[["llm_pred", "llm_confidence", "split"]].isna().any().any():
        raise ValueError("legacy responses do not cover the frozen evaluation set")
    validation = joined.loc[joined["split"].eq("validation")].copy()
    probability = decision_confidence_to_positive_probability(
        validation["llm_pred"],
        validation["llm_confidence"],
    )
    y_true = validation["evacuated_corrected"].to_numpy(dtype=int)
    y_pred = validation["llm_pred"].to_numpy(dtype=int)
    metrics = classification_metrics(
        y_true,
        probability,
        threshold=0.5,
        ece_bins=10,
        predictions=y_pred,
    )
    metrics["conditional_stratified_bootstrap_95pct"] = (
        conditional_stratified_bootstrap(
            y_true,
            probability,
            threshold=0.5,
            ece_bins=10,
            replicates=2000,
            seed=20260731,
            predictions=y_pred,
        )
    )
    result = {
        "status": "PILOT_LEGACY_REANALYSIS",
        "track": "Carr-R",
        "model": "deepseek-v4-flash",
        "split": "validation",
        "test_split_opened": False,
        "n": int(len(validation)),
        "legacy_label_mismatches_in_frozen_330": int(
            joined["evacuated_corrected"]
            .ne(joined["evacuated_legacy"])
            .sum()
        ),
        "probability_semantics": (
            "P(evacuated) = confidence for yes decisions and "
            "1-confidence for no decisions"
        ),
        "metrics": metrics,
        "claim_boundary": (
            "No-cost reanalysis of stored demographic-only model responses. "
            "The run predates the frozen protocol and lacks current gateway "
            "provenance, so it is not a formal model comparison."
        ),
        "provenance": {
            "respondent_id_exported_in_new_artifact": False,
            "runner": {
                "path": str(Path(__file__).relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(Path(__file__)),
            },
            "source_files": {
                str(path.relative_to(PROJECT_ROOT)): file_sha256(path)
                for path in (
                    LEGACY_PREDICTIONS,
                    LEGACY_SUMMARY,
                    LEGACY_LOG,
                    EVALUATION,
                    SPLIT,
                )
            },
            "command": (
                "uv run --extra ml python "
                "experiments/baselines/reanalyze_deepseek_legacy.py"
            ),
        },
    }
    RESULT.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    pd.DataFrame(
        {
            "evaluation_index": validation["evaluation_index"].astype(int),
            "split": "validation",
            "model": "deepseek-v4-flash-legacy-response",
            "y_true": y_true,
            "probability_evacuated": probability,
            "y_pred": y_pred,
        }
    ).sort_values("evaluation_index").to_csv(PREDICTIONS, index=False)
    print(
        "DeepSeek legacy-response validation reanalysis: "
        f"n={len(validation)}, macro_f1={metrics['macro_f1']:.3f}, "
        f"brier={metrics['brier']:.3f}, ece={metrics['ece']:.3f}"
    )


if __name__ == "__main__":
    main()
