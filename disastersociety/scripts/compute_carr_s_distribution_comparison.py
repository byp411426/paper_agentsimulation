#!/usr/bin/env python3
"""Distribution-level comparison of Carr-S simulated process against the frozen
Carr-R respondent-sample aggregate reference (carr_s_e1_empirical_reference_v1_1).

Estimand alignment follows the frozen reference contract:
- order_to_departure_delay: hours from first delivered official order (mandatory
  or voluntary) to the household's first executed departure party, per
  household; empirical CDF reported on the frozen survey grid. Simulated steps
  are 30 minutes.
- warning_channels: multi-select prevalence among order-recipient households.
  The freeze PROHIBITS comparison to simulated first-heard shares and any
  normalized distribution distance; this script therefore reports per-channel
  multi-select prevalence only, with the same cohort definition (order
  recipients), and never computes a distance or a first-heard share.
- evacuation_outcome: individual departure share (residents in executed parties
  / all members), reported with the survey respondent-sample proportion as a
  level reference; cohorts differ (survey includes unwarned respondents), so
  this is a descriptive level, not a validation claim.

Inputs: the three E1 v2 formal runs (24 households) and the two E3c scale-100
runs (100 households). Output: results/carr_s_e1_distribution_comparison.{json,md}.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    ("e1_v2", 24, ROOT / "experiments/carr/runs/e1_formal_r7_seed7201/carr_s_e1_v2_formal", 7201),
    ("e1_v2", 24, ROOT / "experiments/carr/runs/e1_formal_r10_seed8301/carr_s_e1_v2_formal", 8301),
    ("e1_v2", 24, ROOT / "experiments/carr/runs/e1_formal_r9_seed9401/carr_s_e1_v2_formal", 9401),
    ("e3c_scale100", 100, ROOT / "experiments/carr/runs/e1_scale_100_packy_seed101_r5/carr_s_e1_scale_100_packy", 101),
    ("e3c_scale100", 100, ROOT / "experiments/carr/runs/e1_scale_100_packy_seed202_r2/carr_s_e1_scale_100_packy", 202),
]
REFERENCE_PATH = ROOT / "experiments/carr/results/carr_s_e1_empirical_reference/reference_summary.json"
REFERENCE_SHA256 = "0d899eb35bce343903ab91e05f885e9a329d5d66194edaac437b2712b423d691"
STEP_HOURS = 0.5
GRID_HOURS = [0, 0.5, 1, 2, 3, 4, 5, 6, 8, 10, 12, 24, 48]
OUT_JSON = ROOT / "experiments/carr/results/carr_s_e1_distribution_comparison.json"
OUT_MD = ROOT / "experiments/carr/results/carr_s_e1_distribution_comparison.md"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def household_of(resident_id: str) -> str:
    return resident_id.rsplit("_r", 1)[0]


def analyze_run(run_dir: Path) -> dict:
    receipts = read_jsonl(run_dir / "official_receipts.jsonl")
    messages = read_jsonl(run_dir / "message_ledger.jsonl")
    departures = read_jsonl(run_dir / "household_departure_ledger.jsonl")
    members = read_jsonl(run_dir / "member_profiles.jsonl")

    member_households = {m["resident_id"]: m.get("household_id") or household_of(m["resident_id"]) for m in members}
    all_households = sorted(set(member_households.values()))

    # Cohort: households with >=1 delivered official order receipt (any severity).
    delivered = [r for r in receipts if r.get("delivered_step") is not None]
    recipient_households = sorted({household_of(r["resident_id"]) for r in delivered})
    first_order_step = {}
    for r in delivered:
        h = household_of(r["resident_id"])
        first_order_step[h] = min(first_order_step.get(h, 1 << 30), r["delivered_step"])

    # Channel prevalence among recipient households (multi-select, delivered only).
    delivered_msgs = [m for m in messages if m.get("delivered_step") is not None]
    chan_hits = {h: set() for h in recipient_households}
    for h in recipient_households:
        chan_hits[h].add("official_direct")
    for m in delivered_msgs:
        chan = m.get("channel")
        # delivery is per listed recipient for every channel, community included
        for rid in (m.get("recipient_ids") or []):
            h = household_of(rid)
            if h in chan_hits:
                chan_hits[h].add(chan)
    prevalence = {}
    for chan in ("official_direct", "community", "household_dm"):
        k = sum(1 for h in recipient_households if chan in chan_hits[h])
        prevalence[chan] = {"n": len(recipient_households), "k": k,
                            "share": (k / len(recipient_households)) if recipient_households else None}
    k_any_inter = sum(1 for h in recipient_households if chan_hits[h] & {"community", "household_dm"})
    prevalence["any_interpersonal"] = {"n": len(recipient_households), "k": k_any_inter,
                                       "share": (k_any_inter / len(recipient_households)) if recipient_households else None}

    # Order-to-departure delay: first executed party per recipient household.
    executed = [d for d in departures if d.get("outcome") == "executed" and d.get("step") is not None]
    first_depart_step = {}
    for d in executed:
        h = d["household_id"]
        first_depart_step[h] = min(first_depart_step.get(h, 1 << 30), d["step"])
    delays = []
    for h in recipient_households:
        if h in first_depart_step:
            delays.append((first_depart_step[h] - first_order_step[h]) * STEP_HOURS)
    delays.sort()
    cdf = {str(g): (sum(1 for x in delays if x <= g) / len(delays)) if delays else None for g in GRID_HOURS}
    mean_h = (sum(delays) / len(delays)) if delays else None
    median_h = (delays[len(delays) // 2] if len(delays) % 2 == 1
                else (delays[len(delays) // 2 - 1] + delays[len(delays) // 2]) / 2) if delays else None

    # Individual departure share: residents in executed parties / all members.
    departed_residents = set()
    for d in executed:
        departed_residents.update(d.get("traveler_ids") or [])
        departed_residents.update(d.get("accompanying_member_ids") or [])
        cg = d.get("caregiver_by_member") or []
        pairs = cg.items() if isinstance(cg, dict) else cg
        for pair in pairs:
            departed_residents.update(pair)
    indiv = {"departed": len(departed_residents), "members": len(members),
             "share": (len(departed_residents) / len(members)) if members else None}
    recip_members = [rid for rid, h in member_households.items() if h in first_order_step]
    recip_departed = [rid for rid in recip_members if rid in departed_residents]
    indiv_recipient_cohort = {"departed": len(recip_departed), "members": len(recip_members),
                              "share": (len(recip_departed) / len(recip_members)) if recip_members else None}

    return {
        "n_households": len(all_households),
        "n_members": len(members),
        "n_order_recipient_households": len(recipient_households),
        "channel_prevalence": prevalence,
        "order_to_departure": {"n_households": len(delays), "mean_hours": mean_h,
                               "median_hours": median_h, "cdf": cdf,
                               "max_delay_hours": (delays[-1] if delays else None)},
        "individual_departure": indiv,
        "individual_departure_recipient_cohort": indiv_recipient_cohort,
    }


def pooled_cdf(run_results: list[dict], run_dirs: list[Path]) -> dict:
    delays = []
    for rd in run_dirs:
        receipts = read_jsonl(rd / "official_receipts.jsonl")
        departures = read_jsonl(rd / "household_departure_ledger.jsonl")
        delivered = [r for r in receipts if r.get("delivered_step") is not None]
        first_order, recipients = {}, set()
        for r in delivered:
            h = household_of(r["resident_id"])
            recipients.add(h)
            first_order[h] = min(first_order.get(h, 1 << 30), r["delivered_step"])
        first_depart = {}
        for d in departures:
            if d.get("outcome") == "executed" and d.get("step") is not None:
                h = d["household_id"]
                first_depart[h] = min(first_depart.get(h, 1 << 30), d["step"])
        for h in recipients:
            if h in first_depart:
                delays.append((first_depart[h] - first_order[h]) * STEP_HOURS)
    delays.sort()
    n = len(delays)
    return {"n_households": n,
            "mean_hours": (sum(delays) / n) if n else None,
            "median_hours": (delays[n // 2] if n % 2 == 1 else (delays[n // 2 - 1] + delays[n // 2]) / 2) if n else None,
            "cdf": {str(g): (sum(1 for x in delays if x <= g) / n) if n else None for g in GRID_HOURS}}


def main() -> None:
    ref_bytes = REFERENCE_PATH.read_bytes()
    sha = hashlib.sha256(ref_bytes).hexdigest()
    if sha != REFERENCE_SHA256:
        raise SystemExit(f"reference summary hash mismatch: {sha}")
    reference = json.loads(ref_bytes)

    run_results = []
    for study, n_hh, run_dir, seed in RUNS:
        res = analyze_run(run_dir)
        res.update({"study": study, "seed": seed, "run_dir": str(run_dir.relative_to(ROOT)),
                    "config_n_households": n_hh})
        run_results.append(res)

    pooled = pooled_cdf(run_results, [r[2] for r in RUNS])
    tot_members = sum(r["n_members"] for r in run_results)
    tot_departed = sum(r["individual_departure"]["departed"] for r in run_results)
    tot_rm = sum(r["individual_departure_recipient_cohort"]["members"] for r in run_results)
    tot_rd = sum(r["individual_departure_recipient_cohort"]["departed"] for r in run_results)
    tot_recip = sum(r["n_order_recipient_households"] for r in run_results)
    pooled_channels = {}
    for chan in ("official_direct", "community", "household_dm", "any_interpersonal"):
        k = sum(r["channel_prevalence"][chan]["k"] for r in run_results)
        pooled_channels[chan] = {"n": tot_recip, "k": k, "share": k / tot_recip if tot_recip else None}

    out = {
        "status": "DISTRIBUTION_LEVEL_COMPARISON",
        "evidence_boundary": (
            "Survey values are respondent-sample aggregate references (frozen "
            "carr_s_e1_empirical_reference_v1_1), not weighted population truth. "
            "The freeze prohibits comparing survey channel prevalence to simulated "
            "first-heard shares and prohibits any normalized distribution distance; "
            "this artifact reports estimand-aligned multi-select prevalence only. "
            "The simulated scenario window is 25 steps x 0.5 h = 12.5 h, so CDF "
            "grid points beyond 12.5 h are saturated by construction and carry no "
            "information about the survey's 24/48 h tail."),
        "step_hours": STEP_HOURS,
        "grid_hours": GRID_HOURS,
        "runs": run_results,
        "pooled": {
            "n_runs": len(run_results),
            "channel_prevalence": pooled_channels,
            "order_to_departure": pooled,
            "individual_departure": {"departed": tot_departed, "members": tot_members,
                                     "share": tot_departed / tot_members if tot_members else None},
            "individual_departure_recipient_cohort": {"departed": tot_rd, "members": tot_rm,
                                                      "share": tot_rd / tot_rm if tot_rm else None},
        },
        "survey_reference": {
            "sha256": sha,
            "evacuation_outcome": reference["evacuation_outcome"],
            "order_to_departure_delay_main": reference["order_to_departure_delay"]["main_consistent_temporal_order"],
            "warning_channel_prevalence_main": [r for r in reference["warning_channel_prevalence"]["rows"]
                                                if r["cohort"] == "main_consistent_warned"],
        },
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=1))

    lines = ["# Carr-S distribution-level comparison vs frozen Carr-R reference", "",
             f"Runs: {len(run_results)} (3 x E1 v2 24-household, 2 x E3c scale-100). "
             f"Survey reference sha256 {sha[:16]}... (frozen v1_1).", ""]
    lines.append("## Channel prevalence (multi-select, among order recipients)")
    lines.append("| channel | sim pooled (k/n) | sim share | survey share [Wilson 95] |")
    lines.append("|---|---|---|---|")
    survey_ch = {r["channel"]: r for r in out["survey_reference"]["warning_channel_prevalence_main"]}
    for chan in ("official_direct", "community", "household_dm", "any_interpersonal"):
        p = pooled_channels[chan]
        lines.append(f"| {chan} | {p['k']}/{p['n']} | {p['share']:.3f} | -- |")
    for key, label in [("reverse_911", "survey reverse_911"), ("text", "survey text"),
                       ("interpersonal", "survey interpersonal")]:
        r = survey_ch[key]
        lines.append(f"| {label} | {r['successes']}/{r['n']} | -- | {r['proportion']:.3f} "
                     f"[{r['wilson_95_ci'][0]:.3f}, {r['wilson_95_ci'][1]:.3f}] |")
    lines += ["", "## Order-to-departure delay CDF (hours from first delivered order to first executed household departure)",
              "| hours | sim pooled | survey main (n=186) |", "|---|---|---|"]
    surv_cdf = out["survey_reference"]["order_to_departure_delay_main"]["cdf"]
    for g in GRID_HOURS:
        sp = pooled["cdf"][str(g)]
        sv = surv_cdf[str(g)]
        lines.append(f"| {g} | {sp:.3f} | {sv:.3f} |")
    lines.append(f"\nsim pooled n={pooled['n_households']}, mean={pooled['mean_hours']:.2f} h, "
                 f"median={pooled['median_hours']:.2f} h; survey n=186, mean="
                 f"{out['survey_reference']['order_to_departure_delay_main']['mean_hours']:.2f} h, "
                 f"median={out['survey_reference']['order_to_departure_delay_main']['quantiles_hours']['0.5']} h.")
    lines += ["", "## Individual departure share",
              f"sim pooled (all members): {tot_departed}/{tot_members} = {tot_departed / tot_members:.3f}; "
              f"sim pooled (order-recipient households): {tot_rd}/{tot_rm} = {tot_rd / tot_rm:.3f}; "
              f"survey evacuation proportion: {reference['evacuation_outcome']['proportion']:.3f} "
              f"[{reference['evacuation_outcome']['wilson_95_ci'][0]:.3f}, "
              f"{reference['evacuation_outcome']['wilson_95_ci'][1]:.3f}] (n=330).",
              "", "Per-run detail:", "```json"]
    for r in run_results:
        lines.append(json.dumps({
            "run": f"{r['study']}/seed{r['seed']}",
            "recipient_households": r["n_order_recipient_households"],
            "channels": {c: round(v["share"], 3) for c, v in r["channel_prevalence"].items()},
            "delay_n": r["order_to_departure"]["n_households"],
            "delay_cdf": {k: (round(v, 3) if v is not None else None)
                          for k, v in r["order_to_departure"]["cdf"].items()},
            "indiv_departure": round(r["individual_departure"]["share"], 3),
        }, ensure_ascii=False))
    lines.append("```")
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()
