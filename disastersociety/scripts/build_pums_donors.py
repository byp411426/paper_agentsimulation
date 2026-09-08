#!/usr/bin/env python3
"""Build de-identified Carr donor household/person tables from raw PUMS ZIPs.

Public modelling tables never contain SERIALNO. The restricted linkage output
must remain outside version control and must not be copied into run logs.

v1: frozen Carr-S population pipeline columns.
v2 (Carr E1): extended static profile fields per
docs/NEXT_IMPLEMENTATION.md W1, including ADJINC-adjusted income, official
codebook decoding, and the W1 QA contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import yaml

from ds.population.synth import (
    INCOME_BINS,
    INCOME_LABELS,
    build_donor_tables,
    prepare_carr_donor_features,
)


PUMS_SCHEMAS = {
    "v1": {
        "housing": [
            "SERIALNO", "PUMA", "TYPE", "NP", "WGTP", "HINCP", "VEH", "HHT",
        ],
        "person": [
            "SERIALNO", "SPORDER", "RELP", "AGEP", "PWGTP", "DIS", "DEAR",
            "DEYE", "DREM", "DPHY", "DOUT", "DRAT",
        ],
    },
    "v2": {
        "housing": [
            "SERIALNO", "PUMA", "TYPE", "NP", "WGTP", "HINCP", "ADJINC",
            "VEH", "HHT", "TEN", "BLD", "ACCESS", "HISPEED", "SMARTPHONE",
            "NOC", "NRC", "HUPAC", "HUPAOC", "HUPARC", "WIF", "BDSP", "RMSP",
        ],
        "person": [
            "SERIALNO", "SPORDER", "RELP", "AGEP", "PWGTP", "SEX", "SCHL",
            "ESR", "WKW", "WKHP", "JWTR", "JWMNP", "DIS", "DEAR", "DEYE",
            "DREM", "DPHY", "DOUT", "DDRS", "DRAT",
        ],
    },
}

DEFAULT_CODEBOOK = (
    Path(__file__).resolve().parents[1]
    / "eventpacks/carr_2018/population/pums_2018_v2_codebook.yaml"
)


def read_csv_member(path: Path, *, usecols: list[str], **kwargs) -> pd.DataFrame:
    with ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"{path} must contain exactly one CSV member")
        with archive.open(members[0]) as handle:
            return pd.read_csv(handle, usecols=usecols, **kwargs)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def adjusted_income_2018(housing: pd.DataFrame) -> pd.DataFrame:
    """HINCP * ADJINC / 1_000_000 with strict missing and negative rules."""
    raw = pd.to_numeric(housing["HINCP"], errors="coerce")
    factor = pd.to_numeric(housing["ADJINC"], errors="coerce")
    both_present = raw.notna() & factor.notna()
    adjusted = pd.Series(pd.NA, index=housing.index, dtype="object")
    adjusted[both_present] = (raw[both_present] * factor[both_present]) / 1_000_000
    adjusted_numeric = pd.to_numeric(adjusted, errors="coerce").astype("float64")
    housing = housing.copy()
    housing["HINCP_ADJUSTED_2018"] = adjusted_numeric
    negative = pd.Series(False, index=housing.index, dtype=bool)
    negative.loc[both_present] = adjusted_numeric.loc[both_present] < 0
    negative.loc[~both_present & raw.notna()] = (
        raw.loc[~both_present & raw.notna()] < 0
    )
    housing["negative_income"] = negative
    return housing


def decode_coded_fields(
    frame: pd.DataFrame, codebook: dict, *, prefix: str
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Map official PUMS codes to labels; unknown codes fail fast."""
    unknown_counts: dict[str, int] = {}
    frame = frame.copy()
    for field, spec in codebook["fields"].items():
        if field not in frame.columns:
            continue
        codes = {str(code): label for code, label in spec["codes"].items()}
        na_codes = {str(spec["na_code"])} if spec.get("na_code") else set()
        numeric_field = bool(spec.get("numeric"))
        values = frame[field].astype("string").str.strip()
        known = values.map(lambda v: codes.get(v) if v not in na_codes else None)
        if not numeric_field:
            unknown_mask = values.notna() & ~values.isin(set(codes) | na_codes)
            if unknown_mask.any():
                counts = values[unknown_mask].value_counts().to_dict()
                unknown_counts[f"{prefix}:{field}"] = counts
        frame[f"{field}_label"] = known
    if unknown_counts:
        raise ValueError(f"unknown PUMS codes: {unknown_counts}")
    return frame, unknown_counts


def income_bin(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    binned = pd.cut(
        numeric,
        bins=INCOME_BINS,
        labels=INCOME_LABELS,
        include_lowest=True,
    ).astype("object")
    return pd.Series(
        ["missing_income" if pd.isna(v) else str(v) for v in binned],
        index=values.index,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--housing-zip", type=Path, required=True)
    parser.add_argument("--person-zip", type=Path, required=True)
    parser.add_argument("--puma", type=int, default=8900)
    parser.add_argument("--schema-version", choices=("v1", "v2"), default="v1")
    parser.add_argument("--codebook", type=Path, default=DEFAULT_CODEBOOK)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument("--restricted-dir", type=Path, required=True)
    args = parser.parse_args()

    schema = PUMS_SCHEMAS[args.schema_version]
    codebook = (
        yaml.safe_load(args.codebook.read_text(encoding="utf-8"))
        if args.schema_version == "v2"
        else None
    )
    string_fields = {"SERIALNO", "PUMA"}
    if codebook is not None:
        string_fields |= set(codebook["fields"])

    housing = read_csv_member(
        args.housing_zip,
        usecols=schema["housing"],
        dtype={
            field: "string"
            for field in string_fields
            if field in schema["housing"]
        },
        low_memory=False,
    )
    puma_mask = pd.to_numeric(housing["PUMA"], errors="coerce") == args.puma
    occupied_mask = pd.to_numeric(housing["NP"], errors="coerce") > 0
    household_mask = pd.to_numeric(housing["TYPE"], errors="coerce") == 1
    n_excluded_vacant = int((puma_mask & ~occupied_mask).sum())
    n_excluded_group_quarters = int(
        (puma_mask & occupied_mask & ~household_mask).sum()
    )
    housing = housing[puma_mask & occupied_mask & household_mask].copy()
    if housing.empty:
        raise ValueError(f"no housing records found for PUMA {args.puma}")
    serials = set(housing["SERIALNO"])

    person_chunks: list[pd.DataFrame] = []
    with ZipFile(args.person_zip) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError("person ZIP must contain exactly one CSV member")
        with archive.open(members[0]) as handle:
            for chunk in pd.read_csv(
                handle,
                usecols=schema["person"],
                chunksize=250_000,
                dtype={
                    field: "string"
                    for field in string_fields
                    if field in schema["person"]
                },
            ):
                selected = chunk[chunk["SERIALNO"].isin(serials)]
                if not selected.empty:
                    person_chunks.append(selected)
    persons = pd.concat(person_chunks, ignore_index=True)

    if args.schema_version == "v2":
        housing = adjusted_income_2018(housing)
        housing, unknown_h = decode_coded_fields(housing, codebook, prefix="housing")
        persons, unknown_p = decode_coded_fields(persons, codebook, prefix="person")
        raw_bin = income_bin(housing["HINCP"])
        adj_bin = income_bin(housing["HINCP_ADJUSTED_2018"])
        adjusted_income_changed_fine_bin_count = int((raw_bin != adj_bin).sum())
    else:
        unknown_h = {}
        unknown_p = {}
        adjusted_income_changed_fine_bin_count = 0

    # Whole-household structural QA (the builder itself raises on violations).
    np_mismatch = housing.merge(
        persons.groupby("SERIALNO").size().rename("n_linked"),
        on="SERIALNO",
        how="left",
    )
    np_mismatch_count = int(
        (
            pd.to_numeric(np_mismatch["NP"], errors="coerce")
            != pd.to_numeric(np_mismatch["n_linked"], errors="coerce")
        ).sum()
    )
    duplicate_sporder_count = int(
        persons.duplicated(["SERIALNO", "SPORDER"]).sum()
    )
    reference_counts = (
        persons.assign(
            _ref=persons["RELP"].astype(str).str.strip().isin({"0", "00"})
        )
        .groupby("SERIALNO")["_ref"]
        .sum()
        .reindex(housing["SERIALNO"])
        .fillna(0)
    )
    invalid_reference_person_count = int((reference_counts != 1).sum())
    households_without_persons = int(reference_counts.isna().sum())

    donors = prepare_carr_donor_features(
        build_donor_tables(housing, persons),
        income_column=(
            "HINCP_ADJUSTED_2018" if args.schema_version == "v2" else "HINCP"
        ),
        missing_income_fill=(None if args.schema_version == "v2" else 0),
    )
    args.public_dir.mkdir(parents=True, exist_ok=True)
    args.restricted_dir.mkdir(parents=True, exist_ok=True)
    households_path = args.public_dir / "donor_households.csv"
    persons_path = args.public_dir / "donor_persons.csv"
    linkage_path = args.restricted_dir / "donor_serialno_linkage.csv"
    donors.households.to_csv(households_path, index=False)
    donors.persons.to_csv(persons_path, index=False)
    donors.restricted_linkage.to_csv(linkage_path, index=False)

    qa = {
        "schema_version": args.schema_version,
        "puma": args.puma,
        "n_households": len(donors.households),
        "n_persons": len(donors.persons),
        "n_excluded_vacant_housing_units": n_excluded_vacant,
        "n_excluded_group_quarters_records": n_excluded_group_quarters,
        "np_mismatch_count": np_mismatch_count,
        "duplicate_sporder_count": duplicate_sporder_count,
        "invalid_reference_person_count": invalid_reference_person_count,
        "households_without_persons": households_without_persons,
        "adjusted_income_changed_fine_bin_count": (
            adjusted_income_changed_fine_bin_count
        ),
        "unknown_code_counts": {**unknown_h, **unknown_p},
        "housing_zip_sha256": sha256(args.housing_zip),
        "person_zip_sha256": sha256(args.person_zip),
        "codebook_sha256": (
            sha256(args.codebook) if args.schema_version == "v2" else None
        ),
        "output_sha256": {
            "donor_households.csv": sha256(households_path),
            "donor_persons.csv": sha256(persons_path),
            "donor_serialno_linkage.csv": sha256(linkage_path),
        },
        "serialno_in_public_households": (
            "SERIALNO" in donors.households.columns
        ),
        "serialno_in_public_persons": "SERIALNO" in donors.persons.columns,
    }
    (args.public_dir / "donor_build_qa.json").write_text(
        json.dumps(qa, indent=2), encoding="utf-8"
    )
    print(json.dumps(qa, indent=2))


if __name__ == "__main__":
    main()
