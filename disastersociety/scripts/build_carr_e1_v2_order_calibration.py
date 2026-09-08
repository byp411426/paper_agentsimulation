#!/usr/bin/env python3
"""Build Carr E1 v2 order-sequence calibration (W5 offline data artifact).

Uses only Q5/Q6/Q7-derived command type/time fields on the 330 Q9.1 eligible
respondents.  Main analysis excludes the 15 contradictory order records;
sensitivity uses affirmative-command priority.  This is a calibration input,
not a channel validation or outcome-conditioned assignment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from scripts.clean_survey import build_clean, load_qualtrics


SEQUENCES = ["none", "voluntary_only", "mandatory_only", "voluntary_then_mandatory"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(row: pd.Series, *, affirmative_priority: bool) -> str:
    """Classify one respondent's reported order sequence."""
    voluntary = bool(row["received_voluntary_order"])
    mandatory = bool(row["received_mandatory_order"])
    no_order = bool(row["reported_no_official_order"])
    if no_order and not voluntary and not mandatory:
        return "none"
    if voluntary and not mandatory:
        return "voluntary_only"
    if mandatory and not voluntary:
        return "mandatory_only"
    if voluntary and mandatory:
        voluntary_at = row["voluntary_order_at"]
        mandatory_at = row["mandatory_order_at"]
        if pd.isna(voluntary_at) and pd.isna(mandatory_at):
            return "unclassifiable_both_orders"
        if pd.isna(voluntary_at):
            return "unclassifiable_both_orders"
        if pd.isna(mandatory_at):
            return "unclassifiable_both_orders"
        if voluntary_at <= mandatory_at:
            return "voluntary_then_mandatory"
        return "mandatory_then_voluntary"
    if no_order and (voluntary or mandatory):
        return "unclassifiable_conflict"
    return "none"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-survey", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    clean = build_clean(load_qualtrics(args.raw_survey))
    eligible = clean[clean["evacuation_eval_eligible"]].copy()
    if len(eligible) != 330:
        raise ValueError(f"expected 330 eligible respondents, got {len(eligible)}")

    main_frame = eligible[~eligible["order_response_inconsistent"].fillna(False)].copy()
    sensitivity_frame = eligible.copy()
    # Affirmative-first sensitivity: contradictory records keep reported orders.
    sensitivity_frame["order_response_inconsistent"] = False

    results = {}
    for label, frame in (
        ("main_excluding_15_contradictions", main_frame),
        ("sensitivity_affirmative_priority", sensitivity_frame),
    ):
        classified = frame.apply(
            lambda row: classify(row, affirmative_priority=(label != "main")),
            axis=1,
        )
        counts = classified.value_counts().to_dict()
        total = len(frame)
        results[label] = {
            "n": total,
            "counts": {sequence: counts.get(sequence, 0) for sequence in SEQUENCES},
            "proportions": {
                sequence: round(counts.get(sequence, 0) / total, 6)
                for sequence in SEQUENCES
            },
            "extra_reported": {
                key: value
                for key, value in counts.items()
                if key not in SEQUENCES
            },
        }

    payload = {
        "source": "Carr 2018 survey Q5/Q6/Q7-derived command type and time fields",
        "eligible_n": 330,
        "excluded_contradictory_n": int(
            eligible["order_response_inconsistent"].fillna(False).sum()
        ),
        "sequences": SEQUENCES,
        "calibration": results,
        "usage": (
            "Fixed scenario quotas by Hamilton largest-remainder; "
            "assignment uses named stream e1_order_assignment, not traits or outcomes"
        ),
        "input_sha256": sha256(args.raw_survey),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
