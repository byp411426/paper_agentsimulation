"""Freeze the non-identifying Carr-R split and experiment field roles.

Run from ``disastersociety/``:

    uv run python scripts/freeze_carr_protocol.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ds.eval.carr_protocol import (
    CarrProtocolArtifacts,
    build_split_manifest,
    freeze_stratified_split,
    load_field_roles,
    validate_field_roles,
    write_protocol_artifacts,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATION = (
    PROJECT_ROOT
    / "eventpacks/carr_2018/behavior/evaluation_respondents.csv"
)
CLEAN = PROJECT_ROOT / "eventpacks/carr_2018/behavior/survey_clean.csv"
PROTOCOL_DIR = PROJECT_ROOT / "experiments/carr/protocol"
FIELD_ROLES = PROTOCOL_DIR / "field_roles.yaml"
SPLIT_OUT = PROTOCOL_DIR / "carr_r_split.csv"
MANIFEST_OUT = PROTOCOL_DIR / "carr_r_split_manifest.json"
SEED = 20260731
PROPORTIONS = {"train": 0.60, "validation": 0.20, "test": 0.20}


def main() -> None:
    evaluation = pd.read_csv(EVALUATION)
    clean = pd.read_csv(CLEAN)
    protocol = load_field_roles(FIELD_ROLES)
    validate_field_roles(protocol, set(clean.columns))
    split = freeze_stratified_split(
        evaluation,
        seed=SEED,
        proportions=PROPORTIONS,
    )
    manifest = build_split_manifest(
        evaluation=evaluation,
        split=split,
        source_path=EVALUATION,
        seed=SEED,
        proportions=PROPORTIONS,
        field_roles_path=FIELD_ROLES,
    )
    write_protocol_artifacts(
        CarrProtocolArtifacts(split=split, manifest=manifest),
        split_path=SPLIT_OUT,
        manifest_path=MANIFEST_OUT,
    )
    print(f"Wrote {SPLIT_OUT.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {MANIFEST_OUT.relative_to(PROJECT_ROOT)}")
    print(manifest["counts"])


if __name__ == "__main__":
    main()
