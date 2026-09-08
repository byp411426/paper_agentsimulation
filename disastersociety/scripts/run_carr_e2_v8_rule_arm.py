"""Execute the frozen Carr-S E2 v8 deterministic rule reference arm.

Runs carr_controlled_policy (MockBackend, zero LLM calls) through the identical
kernel/message/arbitration pipeline on the full v8 condition for the 12 frozen
r7 seeds, then aggregates levels against the generative full-condition runs.
Protocol: experiments/carr/protocol/carr_s_e2_v8_rule_arm_freeze.json.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import yaml

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import run_carr_condition

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "experiments/carr/configs/carr_s_e2_v8_rule_arm.yaml"
DEFAULT_RUNS_DIR = PROJECT_ROOT / "experiments/carr/runs"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "experiments/carr/results"

LEVEL_METRICS = [
    "complete_household_safe_departure_rate",
    "coordinated_departure_rate",
    "closed_route_rejections_per_household",
    "decision_resident_evacuation_rate",
    "dependent_safety_rate",
    "execution_rejections_per_household",
]
CHECK_METRICS = [
    "conditional_warning_retention_rate",
    "preclosure_primary_to_postclosure_alternate_update_rate",
    "successful_postclosure_replan_rate",
    "post_closure_feasible_commitment_rate",
]


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    args = parser.parse_args()
    config_path = _resolve(args.config).resolve()
    runs_dir = _resolve(args.runs_dir).resolve()
    results_dir = _resolve(args.results_dir).resolve()

    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    proto = cfg["experiment"]["rule_arm_protocol"]
    seeds = [int(s) for s in proto["seeds"]]
    conditions = [str(c) for c in proto["conditions"]]
    if conditions != ["full"]:
        raise ValueError("rule arm is frozen as full-condition only")
    if cfg["llm"]["decision_model"] != "mock":
        raise ValueError("rule arm must use the deterministic mock backend")
    if cfg["experiment"]["metric_protocol_version"] != "v8":
        raise ValueError("rule arm requires metric protocol v8")

    rows = []
    for seed in seeds:
        result = run_carr_condition(
            cfg, condition="full", seed=seed, runs_dir=runs_dir
        )
        summary = result.summary
        metrics = json.loads(
            (result.run_dir / "mechanism_metrics.json").read_text(encoding="utf-8")
        )
        flat = {
            k: v for k, v in {**summary, **metrics}.items()
            if isinstance(v, (int, float))
        }
        row = {
            "seed": seed,
            "terminal_status": summary["status"],
            "run_dir": str(result.run_dir.relative_to(PROJECT_ROOT)),
            "n_ok": int(summary["gateway"]["n_ok"]),
            "n_failed": int(summary["gateway"]["n_failed"]),
            "n_fallback": int(summary["gateway"]["n_fallback"]),
            "spent_usd": float(summary["gateway"].get("spent", 0.0)),
        }
        for name in LEVEL_METRICS + CHECK_METRICS:
            if name in flat:
                row[name] = float(flat[name])
            elif isinstance(metrics.get(name), dict) and "value" in metrics[name]:
                row[name] = float(metrics[name]["value"])
        rows.append(row)
        print(json.dumps({"seed": seed, "status": summary["status"],
                          **{m: row.get(m) for m in LEVEL_METRICS}}))

    aggregate = {}
    for name in LEVEL_METRICS + CHECK_METRICS:
        vals = [r[name] for r in rows if name in r]
        if vals:
            aggregate[name] = {
                "n": len(vals),
                "mean": statistics.fmean(vals),
                "sd": statistics.stdev(vals) if len(vals) > 1 else 0.0,
                "values": vals,
            }

    out = {
        "protocol_id": proto["protocol_id"],
        "status": "RULE_REFERENCE_ARM_COMPLETE",
        "reference_protocol_id": proto["reference_protocol_id"],
        "decision_policy": proto["decision_policy"],
        "llm_calls_total": int(sum(r["n_ok"] + r["n_failed"] for r in rows)),
        "spent_usd_total": float(sum(r["spent_usd"] for r in rows)),
        "terminal_status_counts": {
            s: sum(1 for r in rows if r["terminal_status"] == s)
            for s in sorted({r["terminal_status"] for r in rows})
        },
        "config_sha256": file_sha256(config_path),
        "runs": rows,
        "aggregate_full_condition": aggregate,
        "claim_boundary": proto["claim_boundary"],
    }
    results_dir.mkdir(parents=True, exist_ok=True)
    out_path = results_dir / f"{proto['protocol_id']}_summary.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"wrote {out_path}")
    print(json.dumps({k: {"mean": round(v["mean"], 4), "sd": round(v["sd"], 4)}
                      for k, v in aggregate.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
