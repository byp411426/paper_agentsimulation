"""Run leakage-controlled Carr-R baselines without opening the test split.

Run from ``disastersociety/``:

    uv run --extra ml python experiments/baselines/train_carr_r_frozen.py

The tracked configuration deliberately evaluates only the validation split.
Respondent identifiers are used transiently to link the restricted evaluation
table to cleaned features and are dropped before modeling or export.
"""

from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import sklearn
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from ds.eval.carr_protocol import file_sha256, load_field_roles
from ds.eval.individual import ece


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "experiments/baselines/configs/carr_r_validation_pilot.yaml"
)


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_config(path: str | Path = DEFAULT_CONFIG) -> tuple[Path, dict[str, Any]]:
    config_path = resolve_project_path(path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("baseline configuration must be a mapping")
    return config_path, config


def load_model_table(config: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    data_spec = config["data"]
    clean_path = resolve_project_path(data_spec["clean_survey"])
    linkage_path = resolve_project_path(data_spec["evaluation_linkage"])
    split_path = resolve_project_path(data_spec["split"])
    field_roles_path = resolve_project_path(data_spec["field_roles"])

    clean = pd.read_csv(clean_path)
    linkage = pd.read_csv(linkage_path)
    split = pd.read_csv(split_path)
    protocol = load_field_roles(field_roles_path)
    experiment_id = config["experiment"]["field_role_experiment"]
    features = list(
        protocol["experiments"][experiment_id]["roles"]["runtime_input"]
    )
    if not features:
        raise ValueError("Carr-R baseline needs at least one runtime_input field")

    required_linkage = {"evaluation_index", "respondent_id", "evacuated"}
    if not required_linkage <= set(linkage.columns):
        raise ValueError("evaluation linkage is missing required columns")
    required_clean = {"respondent_id", "evacuated", *features}
    if not required_clean <= set(clean.columns):
        raise ValueError("clean survey is missing frozen Carr-R fields")
    if linkage["respondent_id"].duplicated().any():
        raise ValueError("evaluation linkage respondent_id must be unique")
    if clean["respondent_id"].duplicated().any():
        raise ValueError("clean survey respondent_id must be unique")

    # Transient restricted linkage. respondent_id is removed immediately after
    # the one-to-one merge and is never returned to the caller.
    table = linkage.merge(
        clean[["respondent_id", "evacuated", *features]],
        on=["respondent_id", "evacuated"],
        how="left",
        validate="one_to_one",
    )
    if table[features].isna().all(axis=1).any():
        raise ValueError("one or more evaluation records did not link to features")
    table = table.drop(columns=["respondent_id"])
    table = table.merge(
        split,
        on="evaluation_index",
        how="left",
        validate="one_to_one",
    )
    if table["split"].isna().any():
        raise ValueError("frozen split does not cover every evaluation record")
    if table["evaluation_index"].duplicated().any():
        raise ValueError("evaluation_index must remain unique after linkage")
    return table, features


def make_model(name: str, spec: dict[str, Any], features: list[str]):
    kind = spec["kind"]
    if kind == "constant_prevalence":
        return None

    preprocessing = ColumnTransformer(
        [
            (
                "categorical_codes",
                Pipeline(
                    [
                        (
                            "impute",
                            SimpleImputer(
                                strategy="constant",
                                fill_value=-1,
                            ),
                        ),
                        (
                            "one_hot",
                            OneHotEncoder(
                                handle_unknown="ignore",
                            ),
                        ),
                    ]
                ),
                features,
            )
        ],
        remainder="drop",
    )
    if kind == "logistic_regression":
        estimator = LogisticRegression(
            class_weight=spec.get("class_weight"),
            max_iter=int(spec["max_iter"]),
            random_state=int(spec["random_state"]),
        )
    elif kind == "random_forest":
        estimator = RandomForestClassifier(
            class_weight=spec.get("class_weight"),
            n_estimators=int(spec["n_estimators"]),
            max_depth=int(spec["max_depth"]),
            min_samples_leaf=int(spec["min_samples_leaf"]),
            random_state=int(spec["random_state"]),
            n_jobs=1,
        )
    else:
        raise ValueError(f"{name}: unsupported model kind {kind!r}")
    return Pipeline([("preprocess", preprocessing), ("model", estimator)])


def classification_metrics(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    *,
    threshold: float,
    ece_bins: int,
    predictions: np.ndarray | None = None,
) -> dict[str, Any]:
    y_true = np.asarray(y_true, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    if predictions is None:
        predictions = (probabilities >= threshold).astype(int)
    else:
        predictions = np.asarray(predictions, dtype=int)
        if predictions.shape != y_true.shape:
            raise ValueError("predictions and y_true must have the same shape")
        if not np.isin(predictions, [0, 1]).all():
            raise ValueError("predictions must be binary")
    return {
        "n": int(len(y_true)),
        "outcome_prevalence": float(y_true.mean()),
        "predicted_positive_rate": float(predictions.mean()),
        "accuracy": float(accuracy_score(y_true, predictions)),
        "macro_f1": float(
            f1_score(
                y_true,
                predictions,
                labels=[0, 1],
                average="macro",
                zero_division=0,
            )
        ),
        "brier": float(brier_score_loss(y_true, probabilities)),
        "ece": float(ece(y_true, probabilities, n_bins=ece_bins)),
        "confusion_matrix_labels_0_1": confusion_matrix(
            y_true,
            predictions,
            labels=[0, 1],
        ).astype(int).tolist(),
    }


def conditional_stratified_bootstrap(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    *,
    threshold: float,
    ece_bins: int,
    replicates: int,
    seed: int,
    predictions: np.ndarray | None = None,
) -> dict[str, list[float]]:
    """Percentile intervals conditional on already fitted predictions."""
    y_true = np.asarray(y_true, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    if predictions is not None:
        predictions = np.asarray(predictions, dtype=int)
    groups = [np.flatnonzero(y_true == label) for label in (0, 1)]
    if any(len(group) == 0 for group in groups):
        raise ValueError("stratified bootstrap requires both outcome classes")
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {
        name: [] for name in ("accuracy", "macro_f1", "brier", "ece")
    }
    for _ in range(replicates):
        indices = np.concatenate(
            [rng.choice(group, size=len(group), replace=True) for group in groups]
        )
        values = classification_metrics(
            y_true[indices],
            probabilities[indices],
            threshold=threshold,
            ece_bins=ece_bins,
            predictions=(
                predictions[indices]
                if predictions is not None
                else None
            ),
        )
        for name in draws:
            draws[name].append(float(values[name]))
    return {
        name: [
            float(np.quantile(values, 0.025)),
            float(np.quantile(values, 0.975)),
        ]
        for name, values in draws.items()
    }


def stable_seed(base_seed: int, *parts: str) -> int:
    digest = hashlib.sha256(
        "|".join([str(base_seed), *parts]).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") % (2**32)


def run(config_path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path, config = load_config(config_path)
    table, features = load_model_table(config)
    experiment = config["experiment"]
    train_name = experiment["train_split"]
    evaluation_splits = list(experiment["evaluation_splits"])
    sealed_splits = set(experiment.get("sealed_splits", []))
    if sealed_splits & set(evaluation_splits):
        raise ValueError("sealed split requested for evaluation")
    if "test" in evaluation_splits:
        raise ValueError(
            "tracked validation pilot must not open the frozen test split"
        )

    train = table.loc[table["split"].eq(train_name)].copy()
    if train.empty:
        raise ValueError("training split is empty")
    threshold = float(experiment["decision_threshold"])
    ece_bins = int(experiment["ece_bins"])
    bootstrap_replicates = int(experiment["bootstrap_replicates"])
    bootstrap_seed = int(experiment["bootstrap_seed"])
    train_prevalence = float(train["evacuated"].mean())

    result_models: dict[str, Any] = {}
    prediction_frames: list[pd.DataFrame] = []
    for model_name, model_spec in config["models"].items():
        model = make_model(model_name, model_spec, features)
        if model is not None:
            model.fit(train[features], train["evacuated"].astype(int))

        split_results: dict[str, Any] = {}
        for split_name in evaluation_splits:
            evaluation = table.loc[table["split"].eq(split_name)].copy()
            if evaluation.empty:
                raise ValueError(f"evaluation split {split_name!r} is empty")
            y_true = evaluation["evacuated"].to_numpy(dtype=int)
            if model is None:
                probabilities = np.full(len(evaluation), train_prevalence)
            else:
                probabilities = model.predict_proba(evaluation[features])[:, 1]
            values = classification_metrics(
                y_true,
                probabilities,
                threshold=threshold,
                ece_bins=ece_bins,
            )
            values["conditional_stratified_bootstrap_95pct"] = (
                conditional_stratified_bootstrap(
                    y_true,
                    probabilities,
                    threshold=threshold,
                    ece_bins=ece_bins,
                    replicates=bootstrap_replicates,
                    seed=stable_seed(
                        bootstrap_seed,
                        model_name,
                        split_name,
                    ),
                )
            )
            split_results[split_name] = values
            prediction_frames.append(
                pd.DataFrame(
                    {
                        "evaluation_index": evaluation[
                            "evaluation_index"
                        ].astype(int),
                        "split": split_name,
                        "model": model_name,
                        "y_true": y_true,
                        "probability_evacuated": probabilities,
                        "y_pred": (probabilities >= threshold).astype(int),
                    }
                )
            )
        result_models[model_name] = {
            "configuration": model_spec,
            "metrics": split_results,
        }

    data_spec = config["data"]
    artifact_paths = {
        name: resolve_project_path(value)
        for name, value in data_spec.items()
    }
    result = {
        "status": config["status"],
        "track": config["track"],
        "test_split_opened": False,
        "claim_boundary": (
            "Validation-only development evidence. It does not support a "
            "formal model comparison or a platform-validity claim."
        ),
        "configuration": {
            "path": str(config_path.relative_to(PROJECT_ROOT)),
            "sha256": file_sha256(config_path),
            "features": features,
            "feature_encoding": (
                "missing-category imputation followed by one-hot encoding"
            ),
            "train_split": train_name,
            "evaluation_splits": evaluation_splits,
            "sealed_splits": sorted(sealed_splits),
            "decision_threshold": threshold,
            "ece_bins": ece_bins,
            "bootstrap_replicates": bootstrap_replicates,
            "bootstrap_interval_scope": (
                "conditional on fitted predictions; training uncertainty omitted"
            ),
        },
        "sample": {
            "total_frozen": int(len(table)),
            "train_n": int(len(train)),
            "train_outcome_prevalence": train_prevalence,
            "evaluation_n": {
                split_name: int(table["split"].eq(split_name).sum())
                for split_name in evaluation_splits
            },
        },
        "provenance": {
            "runner": {
                "path": str(Path(__file__).relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(Path(__file__)),
            },
            "artifacts": {
                name: {
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "sha256": file_sha256(path),
                }
                for name, path in artifact_paths.items()
            },
            "respondent_id_exported": False,
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "command": (
                "uv run --extra ml python "
                "experiments/baselines/train_carr_r_frozen.py"
            ),
        },
        "models": result_models,
    }

    result_path = resolve_project_path(
        config["reporting"]["result_json"]
    )
    predictions_path = resolve_project_path(
        config["reporting"]["predictions_csv"]
    )
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    pd.concat(prediction_frames, ignore_index=True).sort_values(
        ["model", "evaluation_index"]
    ).to_csv(predictions_path, index=False)
    return result


def main() -> None:
    result = run()
    print(
        f"status={result['status']} "
        f"test_split_opened={result['test_split_opened']}"
    )
    for model_name, model in result["models"].items():
        for split_name, metrics in model["metrics"].items():
            print(
                f"{model_name} {split_name}: "
                f"macro_f1={metrics['macro_f1']:.3f}, "
                f"brier={metrics['brier']:.3f}, "
                f"ece={metrics['ece']:.3f}"
            )


if __name__ == "__main__":
    main()
