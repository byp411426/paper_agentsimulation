#!/usr/bin/env python3
"""Create a separate corrected input version using original HHT, never old behavior."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from ds.population.profile_validation import HHT_STRUCTURE, validate_e1_profiles


def prepare(profiles_path: Path, households_csv: Path, output: Path) -> dict:
    profiles_path, households_csv, output = (p.resolve() for p in (profiles_path, households_csv, output))
    if (output == profiles_path.parent or output in profiles_path.parents
            or profiles_path.parent in output.parents):
        raise ValueError("Use a separate new input directory")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Existing input directory is protected: {output}")
    profiles = [json.loads(s) for s in profiles_path.read_text().splitlines() if s.strip()]
    with households_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_id = {r["synthetic_household_id"]: r for r in rows}
    if len(by_id) != len(rows):
        raise ValueError("duplicate synthetic household IDs in source CSV")
    changes = []
    for p in profiles:
        hid = p["household_id"]
        source = by_id[hid]
        raw_code = float(source["HHT"])
        if not raw_code.is_integer() or int(raw_code) not in HHT_STRUCTURE:
            raise ValueError(f"{hid}: unsupported HHT {source['HHT']}")
        if float(source["NP"]) != len(p["member_profiles"]):
            raise ValueError(f"{hid}: source member count disagrees with profile")
        expected = HHT_STRUCTURE[int(raw_code)]
        previous = p["shared_attributes"].get("household_structure")
        if expected != previous:
            p["shared_attributes"]["household_structure"] = expected
            changes.append({"household_id": hid, "HHT": int(raw_code),
                "member_count": len(p["member_profiles"]), "before": previous, "after": expected})
    validate_e1_profiles(profiles)
    report = {"kind": "corrected_input_only", "correction": "2018_PUMS_HHT_5_6_mapping",
        "households": len(profiles), "changes": changes, "new_simulations": 0,
        "sources_sha256": {"profiles": hashlib.sha256(profiles_path.read_bytes()).hexdigest(),
                           "synthetic_households_csv": hashlib.sha256(households_csv.read_bytes()).hexdigest()},
        "old_behavior_relabelled": False}
    output.mkdir(parents=True, exist_ok=True)
    corrected = output / "profiles.jsonl"
    corrected.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in profiles), encoding="utf-8")
    report["corrected_profiles_sha256"] = hashlib.sha256(corrected.read_bytes()).hexdigest()
    (output / "changes.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profiles", type=Path, required=True)
    ap.add_argument("--households-csv", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    print(json.dumps(prepare(args.profiles, args.households_csv, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
