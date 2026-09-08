#!/usr/bin/env python3
"""Summarize Carr E1 v2 ledgers into E1 household metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    def load(name: str) -> list[dict]:
        path = args.run_dir / name
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    departures = load("household_departure_ledger.jsonl")
    receipts = load("official_receipts.jsonl")
    messages = load("message_ledger.jsonl")
    commitments = load("commitment_ledger.jsonl")
    member_profiles = load("member_profiles.jsonl")

    executed = [record for record in departures if record["outcome"] == "executed"]
    rejected = [record for record in departures if record["outcome"] == "rejected"]
    households_with_members = {
        member.get("household_id") for member in member_profiles
    }
    departed_households = {
        record["household_id"] for record in executed
    }
    coordinated = [
        record for record in executed if record.get("coordinated")
    ]
    split_households = {
        household_id
        for household_id in departed_households
        if sum(
            1
            for record in executed
            if record["household_id"] == household_id
        )
        > 1
    }
    summary = {
        "n_households": len(households_with_members),
        "n_executed_parties": len(executed),
        "n_rejected_parties": len(rejected),
        "complete_safe_household_departure_rate": (
            len(departed_households) / len(households_with_members)
            if households_with_members
            else 0.0
        ),
        "coordinated_household_rate": (
            len({record["household_id"] for record in coordinated})
            / len(households_with_members)
            if households_with_members
            else 0.0
        ),
        "split_departure_household_rate": (
            len(split_households) / len(households_with_members)
            if households_with_members
            else 0.0
        ),
        "care_recipient_left_behind_count": sum(
            1
            for record in rejected
            if record.get("reason_code") == "missing_traveler_intent"
            and record["accompanying_member_ids"]
        ),
        "vehicle_conflict_count": sum(
            1
            for record in rejected
            if record.get("reason_code") == "vehicle_in_use"
        ),
        "capacity_rejection_count": sum(
            1
            for record in rejected
            if record.get("reason_code") == "vehicle_capacity"
        ),
        "caregiver_violation_count": sum(
            1
            for record in rejected
            if record.get("reason_code") == "caregiver_not_traveler"
        ),
        "message_funnel": {
            "sent": len(messages),
            "delivered": sum(1 for m in messages if m.get("delivered_step") is not None),
            "processed": sum(1 for m in messages if m.get("processed_step") is not None),
            "accepted": sum(1 for m in messages if m.get("status") == "accepted"),
            "rejected": sum(1 for m in messages if m.get("status") == "rejected"),
        },
        "official_receipt_counts": {
            severity: sum(
                1 for receipt in receipts if receipt["severity"] == severity
            )
            for severity in ("voluntary", "mandatory")
        },
        "commitment_counts": {
            status: sum(
                1 for commitment in commitments if commitment["status"] == status
            )
            for status in ("accepted", "cancelled", "executed", "rejected")
        },
        "rejection_reasons": {
            reason: sum(
                1
                for record in rejected
                if record.get("reason_code") == reason
            )
            for reason in sorted(
                {record.get("reason_code") for record in rejected}
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
