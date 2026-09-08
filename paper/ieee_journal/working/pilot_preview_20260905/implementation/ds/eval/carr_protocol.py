"""Frozen Carr-R split and field-role protocol helpers.

The public split artifact uses only ``evaluation_index``.  Raw Qualtrics
respondent identifiers remain in ignored/restricted derived data and never enter
model features or the tracked protocol files.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd
import yaml


FieldRole = Literal[
    "runtime_input",
    "calibration",
    "evaluation_only",
    "excluded",
]
SplitName = Literal["train", "validation", "test"]


@dataclass(frozen=True)
class CarrProtocolArtifacts:
    split: pd.DataFrame
    manifest: dict


def file_sha256(path: str | Path) -> str:
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_field_roles(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "experiments" not in data:
        raise ValueError("Carr field-role protocol needs an experiments mapping")
    return data


def validate_field_roles(protocol: dict, available_columns: set[str]) -> None:
    """Require every declared experiment to assign every source field once."""
    allowed: set[str] = {
        "runtime_input",
        "calibration",
        "evaluation_only",
        "excluded",
    }
    for experiment_id, spec in protocol["experiments"].items():
        roles = spec.get("roles", {})
        unknown_roles = set(roles) - allowed
        if unknown_roles:
            raise ValueError(
                f"{experiment_id}: unknown field roles {sorted(unknown_roles)}"
            )
        assignments: dict[str, list[str]] = {}
        for role, fields in roles.items():
            for field in fields:
                assignments.setdefault(field, []).append(role)
        duplicate = {
            field: roles
            for field, roles in assignments.items()
            if len(roles) != 1
        }
        if duplicate:
            raise ValueError(
                f"{experiment_id}: fields assigned more than once: {duplicate}"
            )
        declared = set(assignments)
        missing = available_columns - declared
        extra = declared - available_columns
        if missing or extra:
            raise ValueError(
                f"{experiment_id}: field-role mismatch; "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )
        overlap = (
            set(roles.get("runtime_input", []))
            & set(roles.get("evaluation_only", []))
        )
        if overlap:
            raise ValueError(
                f"{experiment_id}: runtime/evaluation overlap {sorted(overlap)}"
            )


def freeze_stratified_split(
    evaluation: pd.DataFrame,
    *,
    seed: int,
    proportions: dict[SplitName, float] | None = None,
) -> pd.DataFrame:
    """Create a deterministic outcome-stratified split without exporting labels."""
    proportions = proportions or {
        "train": 0.60,
        "validation": 0.20,
        "test": 0.20,
    }
    if set(proportions) != {"train", "validation", "test"}:
        raise ValueError("split proportions must define train/validation/test")
    if abs(sum(proportions.values()) - 1.0) > 1e-12:
        raise ValueError("split proportions must sum to 1")
    required = {"evaluation_index", "evacuated"}
    if not required <= set(evaluation.columns):
        raise ValueError(f"evaluation table needs {sorted(required)}")
    if evaluation["evaluation_index"].duplicated().any():
        raise ValueError("evaluation_index must be unique")
    if not set(evaluation["evacuated"].dropna().astype(int).unique()) <= {0, 1}:
        raise ValueError("evacuated must be binary")

    ordered_splits: tuple[SplitName, ...] = ("train", "validation", "test")
    strata = [
        (int(outcome), stratum)
        for outcome, stratum in evaluation.groupby("evacuated", sort=True)
    ]
    allocations = _stratified_sizes(
        [len(stratum) for _, stratum in strata],
        [proportions[name] for name in ordered_splits],
    )

    assignment: dict[int, SplitName] = {}
    for stratum_index, (outcome, stratum) in enumerate(strata):
        indices = [int(value) for value in stratum["evaluation_index"]]
        indices.sort(
            key=lambda index: hashlib.sha256(
                f"{seed}|{int(outcome)}|{index}".encode()
            ).hexdigest()
        )
        sizes = allocations[stratum_index]
        cursor = 0
        for name, size in zip(ordered_splits, sizes):
            for index in indices[cursor : cursor + size]:
                assignment[index] = name
            cursor += size

    out = pd.DataFrame(
        {
            "evaluation_index": sorted(assignment),
            "split": [assignment[index] for index in sorted(assignment)],
        }
    )
    if len(out) != len(evaluation):
        raise RuntimeError("split assignment lost evaluation rows")
    return out


def build_split_manifest(
    *,
    evaluation: pd.DataFrame,
    split: pd.DataFrame,
    source_path: str | Path,
    seed: int,
    proportions: dict[str, float],
    field_roles_path: str | Path,
) -> dict:
    joined = evaluation.merge(
        split,
        on="evaluation_index",
        how="left",
        validate="one_to_one",
    )
    counts = {
        name: {
            "n": int(len(group)),
            "n_evacuated": int(group["evacuated"].sum()),
            "n_not_evacuated": int(group["evacuated"].eq(0).sum()),
        }
        for name, group in joined.groupby("split", sort=True)
    }
    return {
        "status": "VERIFIED_PROTOCOL_ARTIFACT",
        "track": "Carr-R",
        "source_sha256": file_sha256(source_path),
        "source_rows": int(len(evaluation)),
        "public_key": "evaluation_index",
        "respondent_id_exported": False,
        "algorithm": "outcome-stratified SHA-256 ordering with largest-remainder allocation",
        "seed": int(seed),
        "proportions": proportions,
        "counts": counts,
        "field_roles_sha256": file_sha256(field_roles_path),
        "channel_inconsistency_rule": {
            "main": (
                "Exclude order_response_inconsistent=True records from "
                "order-channel prevalence estimands only."
            ),
            "sensitivity": (
                "Retain them using affirmative-order priority: a reported "
                "mandatory/voluntary receipt and its selected channels take "
                "precedence over the contradictory no-official-order response."
            ),
            "evacuation_outcome": (
                "Do not exclude otherwise eligible Q9.1 outcomes solely for "
                "this channel inconsistency."
            ),
        },
    }


def write_protocol_artifacts(
    artifacts: CarrProtocolArtifacts,
    *,
    split_path: str | Path,
    manifest_path: str | Path,
) -> None:
    split_path = Path(split_path)
    manifest_path = Path(manifest_path)
    split_path.parent.mkdir(parents=True, exist_ok=True)
    artifacts.split.to_csv(split_path, index=False)
    manifest_path.write_text(
        json.dumps(artifacts.manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _largest_remainder_sizes(total: int, proportions: list[float]) -> list[int]:
    raw = [total * proportion for proportion in proportions]
    sizes = [int(value) for value in raw]
    remaining = total - sum(sizes)
    order = sorted(
        range(len(raw)),
        key=lambda index: (-(raw[index] - sizes[index]), index),
    )
    for index in order[:remaining]:
        sizes[index] += 1
    return sizes


def _stratified_sizes(
    stratum_totals: list[int],
    proportions: list[float],
) -> list[list[int]]:
    """Round a stratum-by-split table while preserving both margins."""
    expected = [
        [stratum_total * proportion for proportion in proportions]
        for stratum_total in stratum_totals
    ]
    allocated = [
        [int(value) for value in row]
        for row in expected
    ]
    row_deficit = [
        total - sum(row)
        for total, row in zip(stratum_totals, allocated)
    ]
    column_targets = _largest_remainder_sizes(
        sum(stratum_totals),
        proportions,
    )
    column_deficit = [
        target - sum(allocated[row][column] for row in range(len(allocated)))
        for column, target in enumerate(column_targets)
    ]
    while any(row_deficit):
        candidates = [
            (
                expected[row][column] - allocated[row][column],
                -row,
                -column,
                row,
                column,
            )
            for row in range(len(allocated))
            for column in range(len(proportions))
            if row_deficit[row] > 0 and column_deficit[column] > 0
        ]
        if not candidates:
            raise RuntimeError("cannot round stratified split margins")
        _, _, _, row, column = max(candidates)
        allocated[row][column] += 1
        row_deficit[row] -= 1
        column_deficit[column] -= 1
    if any(column_deficit):
        raise RuntimeError("stratified split column margins did not close")
    return allocated
