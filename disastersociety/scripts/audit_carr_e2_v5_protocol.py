"""Diagnose the paused Carr-S E2 v5 interaction protocol without rerunning it.

The audit reads the preserved full-condition event logs for completed seeds. It
does not alter raw artifacts, open Carr-R test data, or make an effect claim.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from ds.eval.carr_protocol import file_sha256


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_DIR = PROJECT_ROOT / "experiments/carr/runs"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "experiments/carr/results/carr_s_formal_e2_v5_protocol_diagnostic.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--seeds", type=int, nargs="+", default=[101, 202])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def load_event_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def diagnose_event_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Reconstruct the observable message funnel from immutable step logs."""
    records = list(records)
    if not records:
        raise ValueError("event log is empty")
    messages: dict[str, dict[str, Any]] = {}
    response_count = 0
    stale_response_count = 0
    accepted_response_count = 0
    accepted_feasible_at_response_count = 0

    for record in records:
        step = int(record["step"])
        decisions = record.get("decisions", [])

        # The kernel processes responses before it emits this step's messages.
        for row in decisions:
            decision = row.get("decision", {})
            for response in decision.get("message_responses", []) or []:
                response_count += 1
                message = messages.get(str(response.get("message_id")))
                if message is None or message.get("kind") != "proposal":
                    continue
                depart_step = message.get("payload", {}).get("depart_step")
                feasible = (
                    isinstance(depart_step, int)
                    and not isinstance(depart_step, bool)
                    and depart_step >= step
                )
                if not feasible:
                    stale_response_count += 1
                if response.get("disposition") == "accepted":
                    accepted_response_count += 1
                    if feasible:
                        accepted_feasible_at_response_count += 1

        for row in decisions:
            decision = row.get("decision", {})
            sender = str(row.get("agent", ""))
            for outgoing in decision.get("messages", []) or []:
                message_id = f"m{len(messages) + 1:08d}"
                messages[message_id] = {
                    **outgoing,
                    "sender": sender,
                    "sent_step": step,
                }

    final_interaction = records[-1]["interaction"]
    receipt_states = final_interaction.get("receipt_states", {})
    delivered = sum(int(value) for value in receipt_states.values())
    unprocessed = int(receipt_states.get("delivered", 0))
    processed = delivered - unprocessed
    return {
        "messages_sent": int(final_interaction["msg_count"]),
        "messages_reconstructed": len(messages),
        "messages_delivered": delivered,
        "messages_dropped": int(final_interaction["dropped"]),
        "messages_processed": processed,
        "messages_delivered_unprocessed_at_end": unprocessed,
        "message_responses_observed": response_count,
        "accepted_receipts_at_end": int(receipt_states.get("accepted", 0)),
        "rejected_receipts_at_end": int(receipt_states.get("rejected", 0)),
        "stale_proposal_responses": stale_response_count,
        "accepted_proposal_responses": accepted_response_count,
        "accepted_feasible_at_response": accepted_feasible_at_response_count,
        "receipt_states_at_end": receipt_states,
        "configured_legacy_delivery_probability": float(
            final_interaction["message_delivery_probability"]
        ),
    }


def build_diagnostic(runs_dir: Path, seeds: list[int]) -> dict[str, Any]:
    per_seed: list[dict[str, Any]] = []
    for seed in seeds:
        run_dir = runs_dir / f"carr_s_formal_e2_v5_full_seed{seed}"
        events_path = run_dir / "events.jsonl"
        metrics_path = run_dir / "mechanism_metrics.json"
        if not events_path.exists() or not metrics_path.exists():
            raise FileNotFoundError(f"missing preserved v5 artifact: {run_dir}")
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        funnel = diagnose_event_records(load_event_records(events_path))
        compatible_count = round(
            float(metrics["compatible_commitment_rate"])
            * int(metrics["n_households"])
        )
        per_seed.append(
            {
                "seed": seed,
                "run_terminal_status": metrics["run_terminal_status"],
                "funnel": funnel,
                "current_metric_compatible_commitments": compatible_count,
                "source": {
                    "events": str(events_path.relative_to(PROJECT_ROOT)),
                    "events_sha256": file_sha256(events_path),
                    "mechanism_metrics": str(
                        metrics_path.relative_to(PROJECT_ROOT)
                    ),
                    "mechanism_metrics_sha256": file_sha256(metrics_path),
                },
            }
        )

    aggregate_keys = (
        "messages_sent",
        "messages_delivered",
        "messages_dropped",
        "messages_processed",
        "messages_delivered_unprocessed_at_end",
        "accepted_receipts_at_end",
        "rejected_receipts_at_end",
        "stale_proposal_responses",
        "accepted_proposal_responses",
        "accepted_feasible_at_response",
    )
    aggregate = {
        key: sum(int(item["funnel"][key]) for item in per_seed)
        for key in aggregate_keys
    }
    aggregate["current_metric_compatible_commitments"] = sum(
        int(item["current_metric_compatible_commitments"])
        for item in per_seed
    )
    return {
        "status": "PILOT_DIAGNOSTIC",
        "protocol": "carr_s_formal_e2_v5",
        "completed_full_condition_seeds": seeds,
        "per_seed": per_seed,
        "aggregate_funnel": aggregate,
        "diagnosis": [
            {
                "code": "INTERACTION_EXPOSURE_FAILURE",
                "evidence": (
                    "Household direct messages shared the 0.15 delivery "
                    "probability intended for social propagation."
                ),
            },
            {
                "code": "PROPOSAL_TEMPORAL_MISMATCH",
                "evidence": (
                    "Messages are processed in a later decision phase, while "
                    "v5 allowed proposals whose depart_step was already past."
                ),
            },
            {
                "code": "METRIC_OPPORTUNITY_MISALIGNMENT",
                "evidence": (
                    "The v5 interaction metric required one exact route, "
                    "vehicle, and fixed departure step instead of measuring "
                    "validated commitment formation after exposure."
                ),
            },
        ],
        "claim_boundary": (
            "This read-only diagnostic explains why v5 is unsuitable for a "
            "formal interaction-effect claim. It does not invalidate the raw "
            "runs, estimate a corrected effect, or use the Carr-R test split."
        ),
    }


def main() -> None:
    args = parse_args()
    runs_dir = args.runs_dir.resolve()
    output = args.output.resolve()
    diagnostic = build_diagnostic(runs_dir, args.seeds)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(diagnostic, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(diagnostic, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
