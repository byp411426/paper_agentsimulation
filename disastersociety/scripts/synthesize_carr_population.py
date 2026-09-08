#!/usr/bin/env python3
"""Create a reproducible Carr-S household/person population artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from ds.population.synth import DonorTables, synthesize_by_tract


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--donor-households", type=Path, required=True)
    parser.add_argument("--donor-persons", type=Path, required=True)
    parser.add_argument("--restricted-linkage", type=Path, required=True)
    parser.add_argument("--acs-marginals", type=Path, required=True)
    parser.add_argument("--target-n", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument("--restricted-dir", type=Path, required=True)
    args = parser.parse_args()

    donors = DonorTables(
        households=pd.read_csv(args.donor_households),
        persons=pd.read_csv(args.donor_persons),
        restricted_linkage=pd.read_csv(args.restricted_linkage),
    )
    marginals = pd.read_csv(
        args.acs_marginals,
        dtype={"geoid": str, "category": str},
    )
    population = synthesize_by_tract(
        donors,
        marginals,
        target_n=args.target_n,
        run_seed=args.seed,
    )

    args.public_dir.mkdir(parents=True, exist_ok=True)
    args.restricted_dir.mkdir(parents=True, exist_ok=True)
    population.households.to_csv(
        args.public_dir / "synthetic_households.csv", index=False
    )
    population.persons.to_csv(
        args.public_dir / "synthetic_persons.csv", index=False
    )
    population.restricted_sample_provenance.to_csv(
        args.restricted_dir / "synthetic_donor_provenance.csv", index=False
    )
    qa = dict(population.qa)
    qa["run_seed"] = args.seed
    qa["target_n"] = args.target_n
    qa["input_sha256"] = {
        "donor_households": sha256(args.donor_households),
        "donor_persons": sha256(args.donor_persons),
        "acs_marginals": sha256(args.acs_marginals),
    }
    qa["serialno_in_public_households"] = (
        "SERIALNO" in population.households.columns
    )
    qa["serialno_in_public_persons"] = "SERIALNO" in population.persons.columns
    (args.public_dir / "synthetic_population_qa.json").write_text(
        json.dumps(qa, indent=2, ensure_ascii=False, default=json_default),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
