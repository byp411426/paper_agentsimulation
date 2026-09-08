"""Checks for the sourced, controlled Carr road-route adapter."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ds.eval.carr_protocol import file_sha256
from experiments.carr.runner import run_carr_condition


ROOT = Path(__file__).resolve().parents[1]
ASSET = (
    ROOT
    / "eventpacks/carr_2018/environment/"
    "west_redding_controlled_routes.json"
)
CONFIG = (
    ROOT
    / "experiments/carr/configs/"
    "carr_s_tiger_routes_integration.yaml"
)


def test_controlled_route_asset_has_sourced_geometry_and_boundary():
    asset = json.loads(ASSET.read_text(encoding="utf-8"))
    assert asset["status"] == "CONTROLLED_DERIVED_ASSET"
    assert set(asset["routes"]) == {"tiger_primary", "tiger_alternate"}
    assert asset["anchors"]["home"]["inside_final_perimeter"] is True
    assert asset["anchors"]["safe"]["inside_final_perimeter"] is False
    assert asset["controlled_obstruction"]["scenario_control"] is True
    assert (
        asset["controlled_obstruction"]["historical_closure_observed"]
        is False
    )
    assert asset["qa"]["common_endpoints"] is True
    assert asset["qa"]["obstruction_absent_from_alternate"] is True
    assert 0.0 < asset["qa"][
        "primary_alternate_edge_overlap_fraction"
    ] < 1.0
    for source in ("roads", "perimeter", "configuration", "builder"):
        record = asset["source"][source]
        assert file_sha256(ROOT / record["path"]) == record["sha256"]


def test_tiger_route_asset_enters_common_carr_world(tmp_path):
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    cfg["experiment"]["n_households"] = 2
    result = run_carr_condition(
        cfg,
        condition="full",
        seed=202,
        runs_dir=tmp_path,
    )
    routes = result.world.snapshot()["routes"]
    assert routes["tiger_primary"]["asset_status"] == (
        "CONTROLLED_DERIVED_ASSET"
    )
    assert routes["tiger_primary"]["length_m"] > 7000
    assert routes["tiger_alternate"]["length_m"] > 7000
    assert routes["tiger_primary"]["open"] is False
