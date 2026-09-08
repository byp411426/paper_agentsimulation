"""Derive controlled Carr route candidates from sourced TIGER road geometry.

Requires the ``geo`` optional dependencies:

    uv run --extra geo python scripts/build_carr_controlled_routes.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import networkx as nx
import pandas as pd
import yaml
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, Point, box
from shapely.ops import linemerge, unary_union

from ds.eval.carr_protocol import file_sha256


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "experiments/carr/configs/carr_controlled_routes.yaml"
)


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_config(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("route configuration must be a mapping")
    return data


def build_routes(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(config_path)
    roads_path = resolve_path(config["sources"]["roads"])
    perimeter_path = resolve_path(config["sources"]["perimeter"])
    output_path = resolve_path(config["outputs"]["route_asset"])
    geojson_path = resolve_path(config["outputs"]["route_geojson"])
    selection = config["selection"]
    bbox_wgs84 = tuple(float(value) for value in selection["bbox_wgs84"])
    projected_crs = str(selection["projected_crs"])
    allowed_mtfcc = {str(value) for value in selection["allowed_mtfcc"]}
    rounding = int(round(-__import__("math").log10(
        float(selection["node_rounding_m"])
    )))

    roads_wgs84 = gpd.read_file(roads_path)
    if str(roads_wgs84.crs).upper() != "EPSG:4326":
        roads_wgs84 = roads_wgs84.to_crs("EPSG:4326")
    selected_wgs84 = (
        roads_wgs84.loc[roads_wgs84["MTFCC"].isin(allowed_mtfcc)]
        .clip(box(*bbox_wgs84))
        .explode(index_parts=False)
        .reset_index(drop=True)
    )
    selected = selected_wgs84.to_crs(projected_crs)
    perimeter = (
        gpd.read_file(perimeter_path)
        .to_crs(projected_crs)
        .geometry.union_all()
    )
    graph = _noded_graph(selected, rounding=rounding)
    component_nodes = max(nx.connected_components(graph), key=len)
    component = graph.subgraph(component_nodes).copy()
    home, safe = _select_anchors(
        component,
        perimeter=perimeter,
        vertical_band_m=float(selection["safe_anchor_vertical_band_m"]),
    )
    primary = nx.shortest_path(
        component,
        home,
        safe,
        weight="length_m",
    )
    obstruction, alternate = _select_obstruction_and_alternate(
        component,
        primary,
        maximum_length_ratio=float(
            selection["maximum_alternate_length_ratio"]
        ),
    )

    to_wgs84 = Transformer.from_crs(
        projected_crs,
        "EPSG:4326",
        always_xy=True,
    )
    source_index = selected.sindex
    route_ids = config["route_ids"]
    primary_record = _route_record(
        component,
        primary,
        route_id=str(route_ids["primary"]),
        selected_roads=selected,
        source_index=source_index,
        to_wgs84=to_wgs84,
    )
    alternate_record = _route_record(
        component,
        alternate,
        route_id=str(route_ids["alternate"]),
        selected_roads=selected,
        source_index=source_index,
        to_wgs84=to_wgs84,
    )
    obstruction_record = _edge_record(
        component,
        *obstruction,
        selected_roads=selected,
        source_index=source_index,
        to_wgs84=to_wgs84,
    )
    primary_edges = {
        frozenset(edge) for edge in zip(primary, primary[1:])
    }
    alternate_edges = {
        frozenset(edge) for edge in zip(alternate, alternate[1:])
    }
    overlap = len(primary_edges & alternate_edges) / len(primary_edges)
    primary_length = float(primary_record["length_m"])
    alternate_length = float(alternate_record["length_m"])
    home_wgs84 = to_wgs84.transform(*home)
    safe_wgs84 = to_wgs84.transform(*safe)

    asset = {
        "schema_version": 1,
        "status": "CONTROLLED_DERIVED_ASSET",
        "case_semantics": config["case_semantics"],
        "source": {
            "roads": {
                "path": str(roads_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(roads_path),
                "vintage": 2018,
                "publisher": "U.S. Census Bureau TIGER/Line",
            },
            "perimeter": {
                "path": str(perimeter_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(perimeter_path),
                "semantics": "CAL FIRE final perimeter, not a time series",
            },
            "configuration": {
                "path": str(config_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(config_path),
            },
            "builder": {
                "path": str(Path(__file__).relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(Path(__file__)),
            },
        },
        "selection": {
            **selection,
            "selected_source_segments": int(len(selected)),
            "noded_graph_nodes": int(graph.number_of_nodes()),
            "noded_graph_edges": int(graph.number_of_edges()),
            "largest_component_nodes": int(component.number_of_nodes()),
            "largest_component_edges": int(component.number_of_edges()),
            "largest_component_node_fraction": float(
                component.number_of_nodes() / graph.number_of_nodes()
            ),
        },
        "anchors": {
            "home": {
                "method": (
                    "easternmost largest-component road node covered by the "
                    "final Carr perimeter inside the controlled bounding box"
                ),
                "longitude": home_wgs84[0],
                "latitude": home_wgs84[1],
                "inside_final_perimeter": True,
            },
            "safe": {
                "method": (
                    "easternmost largest-component node outside the final "
                    "perimeter and within the declared north-south band"
                ),
                "longitude": safe_wgs84[0],
                "latitude": safe_wgs84[1],
                "inside_final_perimeter": False,
            },
        },
        "routes": {
            primary_record["route_id"]: primary_record,
            alternate_record["route_id"]: alternate_record,
        },
        "controlled_obstruction": {
            "scenario_control": True,
            "historical_closure_observed": False,
            "closed_route_id": primary_record["route_id"],
            "edge": obstruction_record,
        },
        "qa": {
            "common_endpoints": (
                primary[0] == alternate[0]
                and primary[-1] == alternate[-1]
            ),
            "obstruction_absent_from_alternate": (
                frozenset(obstruction) not in alternate_edges
            ),
            "primary_alternate_edge_overlap_fraction": overlap,
            "alternate_primary_length_ratio": (
                alternate_length / primary_length
            ),
            "safe_anchor_outside_final_perimeter": (
                not perimeter.covers(Point(safe))
            ),
            "home_anchor_inside_final_perimeter": perimeter.covers(
                Point(home)
            ),
        },
        "claim_boundary": config["claim_boundary"],
    }
    _validate_asset(asset)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asset, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_route_geojson(
        geojson_path,
        primary_record=primary_record,
        alternate_record=alternate_record,
        obstruction_record=obstruction_record,
    )
    print(
        f"routes={output_path.relative_to(PROJECT_ROOT)} "
        f"primary_km={primary_length / 1000:.3f} "
        f"alternate_km={alternate_length / 1000:.3f} "
        f"overlap={overlap:.3f}"
    )
    return asset


def _noded_graph(
    selected_roads: gpd.GeoDataFrame,
    *,
    rounding: int,
) -> nx.Graph:
    noded = unary_union(selected_roads.geometry.tolist())
    geometries = list(noded.geoms) if hasattr(noded, "geoms") else [noded]
    graph = nx.Graph()
    for geometry in geometries:
        if geometry.is_empty or geometry.length < 1.0:
            continue
        coordinates = list(geometry.coords)
        start = tuple(round(value, rounding) for value in coordinates[0])
        end = tuple(round(value, rounding) for value in coordinates[-1])
        if start == end:
            continue
        length = float(geometry.length)
        if (
            graph.has_edge(start, end)
            and float(graph[start][end]["length_m"]) <= length
        ):
            continue
        graph.add_edge(
            start,
            end,
            length_m=length,
            geometry=geometry,
        )
    if graph.number_of_nodes() == 0:
        raise ValueError("controlled road selection produced an empty graph")
    return graph


def _select_anchors(
    graph: nx.Graph,
    *,
    perimeter: Any,
    vertical_band_m: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    inside = [node for node in graph if perimeter.covers(Point(node))]
    if not inside:
        raise ValueError("no largest-component nodes fall inside the perimeter")
    home = max(inside, key=lambda node: node[0])
    safe_candidates = [
        node
        for node in graph
        if not perimeter.covers(Point(node))
        and abs(node[1] - home[1]) <= vertical_band_m
    ]
    if not safe_candidates:
        raise ValueError("no outside-perimeter safe anchor candidate found")
    safe = max(safe_candidates, key=lambda node: node[0])
    return home, safe


def _select_obstruction_and_alternate(
    graph: nx.Graph,
    primary: list[tuple[float, float]],
    *,
    maximum_length_ratio: float,
) -> tuple[
    tuple[tuple[float, float], tuple[float, float]],
    list[tuple[float, float]],
]:
    primary_length = nx.path_weight(graph, primary, "length_m")
    primary_edges = list(zip(primary, primary[1:]))
    primary_edge_set = {frozenset(edge) for edge in primary_edges}
    bridges = {frozenset(edge) for edge in nx.bridges(graph)}
    candidates = []
    for index, edge in enumerate(primary_edges):
        if frozenset(edge) in bridges:
            continue
        modified = graph.copy()
        modified.remove_edge(*edge)
        try:
            alternate = nx.shortest_path(
                modified,
                primary[0],
                primary[-1],
                weight="length_m",
            )
        except nx.NetworkXNoPath:
            continue
        alternate_length = nx.path_weight(
            modified,
            alternate,
            "length_m",
        )
        ratio = alternate_length / primary_length
        if ratio > maximum_length_ratio:
            continue
        alternate_edges = {
            frozenset(item)
            for item in zip(alternate, alternate[1:])
        }
        overlap = len(primary_edge_set & alternate_edges) / len(
            primary_edge_set
        )
        candidates.append(
            (
                overlap,
                ratio,
                abs(index - len(primary_edges) / 2),
                index,
                edge,
                alternate,
            )
        )
    if not candidates:
        raise ValueError("no controlled obstruction with an alternate route found")
    candidates.sort(key=lambda item: item[:4])
    selected = candidates[0]
    return selected[4], selected[5]


def _route_record(
    graph: nx.Graph,
    path: list[tuple[float, float]],
    *,
    route_id: str,
    selected_roads: gpd.GeoDataFrame,
    source_index: Any,
    to_wgs84: Transformer,
) -> dict[str, Any]:
    edges = [
        _edge_record(
            graph,
            start,
            end,
            selected_roads=selected_roads,
            source_index=source_index,
            to_wgs84=to_wgs84,
        )
        for start, end in zip(path, path[1:])
    ]
    return {
        "route_id": route_id,
        "length_m": float(sum(edge["length_m"] for edge in edges)),
        "node_count": len(path),
        "edge_count": len(edges),
        "edge_source_linearids": sorted(
            {edge["source_linearid"] for edge in edges}
        ),
        "edges": edges,
    }


def _edge_record(
    graph: nx.Graph,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    selected_roads: gpd.GeoDataFrame,
    source_index: Any,
    to_wgs84: Transformer,
) -> dict[str, Any]:
    data = graph[start][end]
    geometry = data["geometry"]
    nearest = source_index.nearest(
        geometry.interpolate(0.5, normalized=True),
        return_all=False,
    )
    source_row = selected_roads.iloc[int(nearest[1][0])]
    coordinates = [
        list(to_wgs84.transform(x, y))
        for x, y in geometry.coords
    ]
    return {
        "start_wgs84": coordinates[0],
        "end_wgs84": coordinates[-1],
        "length_m": float(data["length_m"]),
        "source_linearid": str(source_row["LINEARID"]),
        "source_fullname": (
            None
            if pd.isna(source_row["FULLNAME"])
            else str(source_row["FULLNAME"])
        ),
        "source_mtfcc": str(source_row["MTFCC"]),
        "coordinates_wgs84": coordinates,
    }


def _write_route_geojson(
    path: Path,
    *,
    primary_record: dict[str, Any],
    alternate_record: dict[str, Any],
    obstruction_record: dict[str, Any],
) -> None:
    features = []
    for route in (primary_record, alternate_record):
        lines = [
            LineString(edge["coordinates_wgs84"])
            for edge in route["edges"]
        ]
        merged = linemerge(MultiLineString(lines))
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "route",
                    "route_id": route["route_id"],
                    "length_m": route["length_m"],
                    "historical_closure_observed": False,
                },
                "geometry": merged.__geo_interface__,
            }
        )
    features.append(
        {
            "type": "Feature",
            "properties": {
                "kind": "controlled_obstruction",
                "route_id": primary_record["route_id"],
                "source_linearid": obstruction_record["source_linearid"],
                "historical_closure_observed": False,
            },
            "geometry": LineString(
                obstruction_record["coordinates_wgs84"]
            ).__geo_interface__,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "name": "west_redding_controlled_routes",
                "crs": {
                    "type": "name",
                    "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
                },
                "features": features,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _validate_asset(asset: dict[str, Any]) -> None:
    qa = asset["qa"]
    required_true = (
        "common_endpoints",
        "obstruction_absent_from_alternate",
        "safe_anchor_outside_final_perimeter",
        "home_anchor_inside_final_perimeter",
    )
    failures = [name for name in required_true if not qa[name]]
    if failures:
        raise ValueError(f"controlled route QA failed: {failures}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config_path = (
        args.config
        if args.config.is_absolute()
        else PROJECT_ROOT / args.config
    )
    build_routes(config_path)


if __name__ == "__main__":
    main()
