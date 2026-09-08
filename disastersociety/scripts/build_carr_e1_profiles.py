#!/usr/bin/env python3
"""Build Carr E1 v2 empirical profiles (W3 contract).

Combines the PUMS v2 synthetic pilot population with Carr train trait donors
and writes household/member profiles with provenance and QA.  Offline only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from ds.population.e1_profiles import assemble_e1_profiles


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if value is pd.NA:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--households", type=Path, required=True)
    parser.add_argument("--persons", type=Path, required=True)
    parser.add_argument("--household-traits", type=Path, required=True)
    parser.add_argument("--person-traits", type=Path, required=True)
    parser.add_argument("--profile-seed", type=int, default=4201)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument("--restricted-dir", type=Path, required=True)
    parser.add_argument(
        "--donor-persons",
        type=Path,
        default=PROJECT_ROOT / "eventpacks/carr_2018/population/donors_v2/donor_persons.csv",
    )
    parser.add_argument(
        "--pums-household-linkage",
        type=Path,
        default=PROJECT_ROOT
        / "eventpacks/carr_2018/restricted/pilot_seed42_n1000_v2/synthetic_donor_provenance.csv",
    )
    args = parser.parse_args()

    households = pd.read_csv(args.households)
    persons = pd.read_csv(args.persons)
    household_traits = pd.read_csv(args.household_traits)
    person_traits = pd.read_csv(args.person_traits)
    donor_persons = pd.read_csv(args.donor_persons)
    pums_household_linkage = pd.read_csv(args.pums_household_linkage)

    result = assemble_e1_profiles(
        households=households,
        persons=persons,
        household_traits=household_traits,
        person_traits=person_traits,
        donor_persons=donor_persons,
        pums_household_linkage=pums_household_linkage,
        profile_seed=args.profile_seed,
    )
    args.public_dir.mkdir(parents=True, exist_ok=True)
    args.restricted_dir.mkdir(parents=True, exist_ok=True)

    profile_path = args.public_dir / f"e1_profiles_seed{args.profile_seed}.jsonl"
    linkage_path = (
        args.restricted_dir / f"e1_restricted_linkage_seed{args.profile_seed}.csv"
    )
    with profile_path.open("w", encoding="utf-8") as handle:
        for profile in result.households:
            handle.write(
                json.dumps(_jsonable(asdict(profile)), ensure_ascii=False) + "\n"
            )
    result.restricted_linkage.to_csv(linkage_path, index=False)
    qa = {
        **result.qa,
        "output_sha256": {
            profile_path.name: sha256(profile_path),
            linkage_path.name: sha256(linkage_path),
        },
        "input_sha256": {
            "synthetic_households.csv": sha256(args.households),
            "synthetic_persons.csv": sha256(args.persons),
            "carr_household_trait_donors_v1.csv": sha256(args.household_traits),
            "carr_person_trait_donors_v1.csv": sha256(args.person_traits),
        },
    }
    qa_path = args.public_dir / f"e1_profile_qa_seed{args.profile_seed}.json"
    qa_path.write_text(
        json.dumps(qa, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(qa, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
