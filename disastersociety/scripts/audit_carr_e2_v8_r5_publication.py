"""Publication audit for the frozen Carr-S E2 v8 recovery matrix.

Checks the 12 x 5 keyset, terminal/status consistency, frozen artifact
hashes, per-cell accounting, valid paired contrasts, exclusion reasons, and
mechanism opportunity denominators.  The audit never modifies run artifacts.
The protocol id is read from the audited config so the same script audits the
r5 or r6 attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "experiments/carr/configs/carr_s_e2_v8_formal_r7.yaml"
DEFAULT_FREEZE = (
    PROJECT_ROOT
    / "experiments/carr/protocol/carr_s_e2_v8_formal_r7_backend_recovery_freeze.json"
)
DEFAULT_RESULTS = PROJECT_ROOT / "experiments/carr/results"
DEFAULT_RUNS = PROJECT_ROOT / "experiments/carr/runs"
DEFAULT_OUTPUT = PROJECT_ROOT / "experiments/carr/results/carr_s_e2_v8_formal_r7_publication_audit.json"

MODULES = ["memory", "feedback", "planning", "interaction"]
CONDITION_TO_MODULE = {
    "full_minus_memory": "memory",
    "full_minus_feedback": "feedback",
    "full_minus_planning": "planning",
    "full_minus_interaction": "interaction",
}
OPPORTUNITY_FIELDS = {
    "memory": ["warning_exposed_coordinator_count", "n_decision_residents"],
    "feedback": ["preclosure_primary_plan_count", "n_decision_residents"],
    "planning": ["postclosure_replanned_household_count", "n_households"],
    "interaction": ["n_households", "post_closure_feasible_commitment_count"],
}


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = _resolve(args.config).resolve()
    freeze_path = _resolve(args.freeze).resolve()
    results_dir = _resolve(args.results_dir).resolve()
    runs_dir = _resolve(args.runs_dir).resolve()
    output_path = _resolve(args.output).resolve()

    import yaml

    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    protocol = cfg["experiment"]["formal_protocol"]
    protocol_id = str(protocol["protocol_id"])
    run_dir_re = re.compile(rf"^{re.escape(protocol_id)}_(.+)_seed(\d+)$")
    conditions = list(protocol["conditions"])
    seeds = [int(seed) for seed in protocol["seeds"]]
    expected_cells = {(seed, condition) for seed in seeds for condition in conditions}

    # 1-2. Keyset from actual run directories.
    actual_cells: set[tuple[int, str]] = set()
    cell_dirs: dict[tuple[int, str], Path] = {}
    for directory in runs_dir.iterdir():
        match = run_dir_re.match(directory.name)
        if match is None:
            continue
        condition, seed_text = match.groups()
        cell = (int(seed_text), condition)
        actual_cells.add(cell)
        cell_dirs[cell] = directory

    missing_cells = sorted(expected_cells - actual_cells)
    unexpected_cells = sorted(actual_cells - expected_cells)
    seed_condition_counts: dict[int, dict[str, int]] = {}
    for seed, condition in sorted(actual_cells):
        counts = seed_condition_counts.setdefault(seed, {})
        counts[condition] = counts.get(condition, 0) + 1
    duplicate_seeds = {
        seed: {condition: count for condition, count in counts.items() if count != 1}
        for seed, counts in seed_condition_counts.items()
        if any(count != 1 for count in counts.values())
    }

    # 3, 5. Per-cell terminal and accounting checks.
    cells: list[dict[str, object]] = []
    problems: list[str] = []
    for cell in sorted(expected_cells):
        seed, condition = cell
        directory = cell_dirs.get(cell)
        if directory is None:
            cells.append(
                {
                    "seed": seed,
                    "condition": condition,
                    "present": False,
                    "status": "MISSING",
                    "exclusion_reason": "run directory missing",
                }
            )
            problems.append(f"missing run directory: {condition}/seed{seed}")
            continue
        summary_path = directory / "summary.json"
        metrics_path = directory / "mechanism_metrics.json"
        provenance_path = directory / "provenance.json"
        if not all(path.exists() for path in (summary_path, metrics_path, provenance_path)):
            cells.append(
                {
                    "seed": seed,
                    "condition": condition,
                    "present": True,
                    "status": "INCOMPLETE_ARTIFACTS",
                    "exclusion_reason": "missing summary/metrics/provenance",
                }
            )
            problems.append(f"incomplete artifacts: {condition}/seed{seed}")
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))

        provenance_run_id = provenance.get("run_id")
        if provenance_run_id is None:
            provenance_run_id = (
                provenance.get("config", {}).get("run", {}).get("run_id")
            )
        identity_ok = (
            metrics.get("condition") == condition
            and int(metrics.get("seed", -1)) == seed
            and provenance_run_id == f"{protocol_id}_{condition}_seed{seed}"
            and summary.get("run_seed") == seed
        )
        if not identity_ok:
            problems.append(
                f"identity mismatch: {condition}/seed{seed} "
                f"(metrics={metrics.get('condition')}/{metrics.get('seed')}, "
                f"provenance={provenance_run_id})"
            )
        gateway = summary.get("gateway") or {}
        accounting_ok = (
            isinstance(gateway.get("n_ok"), int)
            and isinstance(gateway.get("n_failed"), int)
            and isinstance(gateway.get("n_fallback"), int)
            and isinstance(gateway.get("spent"), (int, float))
            and isinstance(summary.get("wall_clock_seconds"), (int, float))
            and isinstance(metrics.get("n_logical_decisions"), int)
        )
        if not accounting_ok:
            problems.append(f"accounting fields missing: {condition}/seed{seed}")

        status = str(summary.get("status", "UNKNOWN"))
        metrics_status = metrics.get("run_terminal_status")
        status_ok = status == metrics_status
        if not status_ok:
            problems.append(
                f"terminal status mismatch: {condition}/seed{seed} "
                f"(summary={status}, metrics={metrics_status})"
            )
        cells.append(
            {
                "seed": seed,
                "condition": condition,
                "present": True,
                "status": status,
                "identity_ok": identity_ok,
                "accounting_ok": accounting_ok,
                "terminal_status_consistent": status_ok,
                "n_ok": gateway.get("n_ok"),
                "n_failed": gateway.get("n_failed"),
                "n_fallback": gateway.get("n_fallback"),
                "fallback_rate": gateway.get("fallback_rate"),
                "spent_usd": gateway.get("spent"),
                "wall_clock_seconds": summary.get("wall_clock_seconds"),
                "n_logical_decisions": metrics.get("n_logical_decisions"),
                "opportunity_denominators": {
                    module: {
                        field: metrics.get(field)
                        for field in OPPORTUNITY_FIELDS[module]
                    }
                    for module in MODULES
                },
            }
        )

    # 4. Frozen artifact hashes.
    hash_checks: dict[str, dict[str, object]] = {}
    for artifact_name, artifact in freeze["frozen_artifacts"].items():
        artifact_path = PROJECT_ROOT / artifact["path"]
        if not artifact_path.exists():
            hash_checks[artifact_name] = {"path": artifact["path"], "ok": False, "reason": "missing"}
            problems.append(f"frozen artifact missing: {artifact['path']}")
            continue
        actual = sha256(artifact_path)
        expected = artifact["sha256"]
        ok = actual == expected
        hash_checks[artifact_name] = {
            "path": artifact["path"],
            "ok": ok,
            "actual": actual,
            "expected": expected,
        }
        if not ok:
            problems.append(f"frozen artifact hash mismatch: {artifact['path']}")

    # 6. Valid paired contrasts per module with exclusion reasons.
    paired: dict[str, dict[str, object]] = {}
    for module in MODULES:
        drop_condition = f"full_minus_{module}"
        valid_pairs = 0
        excluded: list[dict[str, object]] = []
        for seed in seeds:
            full_cell = next(
                (cell for cell in cells if cell["seed"] == seed and cell["condition"] == "full"),
                None,
            )
            drop_cell = next(
                (cell for cell in cells if cell["seed"] == seed and cell["condition"] == drop_condition),
                None,
            )
            full_ok = full_cell is not None and full_cell["status"] == "VALID"
            drop_ok = drop_cell is not None and drop_cell["status"] == "VALID"
            if full_ok and drop_ok:
                valid_pairs += 1
            else:
                excluded.append(
                    {
                        "seed": seed,
                        "full_status": full_cell["status"] if full_cell else "MISSING",
                        f"{drop_condition}_status": drop_cell["status"] if drop_cell else "MISSING",
                        "reason": "one or both paired runs not VALID",
                    }
                )
        paired[module] = {"valid_pairs": valid_pairs, "n_seeds": len(seeds), "excluded": excluded}

    # 7. Opportunity denominators summary per module.
    opportunity_summary: dict[str, dict[str, object]] = {}
    for module in MODULES:
        field = OPPORTUNITY_FIELDS[module][0]
        denominators = [
            cell["opportunity_denominators"][module][field]
            for cell in cells
            if cell.get("present") and cell["status"] == "VALID"
            and cell["opportunity_denominators"][module].get(field) is not None
        ]
        opportunity_summary[module] = {
            "primary_denominator_field": field,
            "valid_cell_denominator_values": denominators,
            "n_cells_with_zero_or_missing_denominator": sum(
                1 for value in denominators if value == 0
            ),
        }

    terminal_statuses: dict[str, int] = {}
    for cell in cells:
        status = str(cell["status"])
        terminal_statuses[status] = terminal_statuses.get(status, 0) + 1
    n_valid = terminal_statuses.get("VALID", 0)
    if missing_cells or unexpected_cells or duplicate_seeds or problems or n_valid != 60:
        status = "NOT_READY_FOR_CLAIM"
    elif any(terminal_statuses.get(status, 0) for status in ("INVALID",)):
        status = "COMPLETE_WITH_EXCLUSIONS"
    else:
        status = "COMPLETE_VALID"

    report = {
        "protocol_id": protocol_id,
        "audit_status": status,
        "expected_cells": len(expected_cells),
        "actual_cells": len(actual_cells),
        "n_valid_cells": n_valid,
        "terminal_status_counts": terminal_statuses,
        "missing_cells": missing_cells,
        "unexpected_cells": unexpected_cells,
        "duplicate_seed_conditions": duplicate_seeds,
        "frozen_artifact_hashes": hash_checks,
        "cells": cells,
        "paired_contrasts": paired,
        "opportunity_denominators": opportunity_summary,
        "problems": problems,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
