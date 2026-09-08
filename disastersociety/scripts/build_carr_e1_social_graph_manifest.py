#!/usr/bin/env python3
"""Build the Carr E1 v2 social-graph manifest (W5.7.8 offline artifact).

Nodes are synthetic households placed at their 2018 TIGER tract centroid
(local planar metres).  The graph depends only on synthetic geography and
household membership; it never uses Carr outcomes or latent traits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd

from ds.kernel.rng import derive
from ds.population.networks import build_social_graph


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--households", type=Path, required=True)
    parser.add_argument("--persons", type=Path, required=True)
    parser.add_argument("--tracts", type=Path, required=True)
    parser.add_argument("--profile-seed", type=int, default=4201)
    parser.add_argument("--radius-m", type=float, default=1500.0)
    parser.add_argument("--k-neighbors", type=int, default=6)
    parser.add_argument("--k-friends", type=int, default=4)
    parser.add_argument("--rewire-p", type=float, default=0.1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    households = pd.read_csv(args.households)
    persons = pd.read_csv(args.persons)
    tracts = gpd.read_file(args.tracts)
    tracts = tracts.to_crs("EPSG:4326")
    centroids = {}
    for _, row in tracts.iterrows():
        geoid = str(row.get("GEOID") or row.get("geoid") or "")
        if not geoid:
            continue
        point = row.geometry.centroid
        centroids[geoid] = (float(point.x), float(point.y))

    # Local planar metres around the tract centroid average.
    lon_values = [value[0] for value in centroids.values()]
    lat_values = [value[1] for value in centroids.values()]
    ref_lon = sum(lon_values) / len(lon_values)
    ref_lat = sum(lat_values) / len(lat_values)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(ref_lat))

    agents = []
    missing = 0
    household_locations = {}
    for _, row in households.iterrows():
        geoid = str(row["geoid"])[-11:]
        if geoid not in centroids:
            missing += 1
            continue
        lon, lat = centroids[geoid]
        x = (lon - ref_lon) * m_per_deg_lon
        y = (lat - ref_lat) * m_per_deg_lat
        household_id = str(row["synthetic_household_id"])
        household_locations[household_id] = (x, y)
    for _, row in persons.iterrows():
        if not bool(row["decision_capable"]):
            continue
        household_id = str(row["synthetic_household_id"])
        if household_id not in household_locations:
            missing += 1
            continue
        x, y = household_locations[household_id]
        agents.append(
            {
                "id": str(row["resident_id"]),
                "household_id": household_id,
                "location": (x, y),
            }
        )
    if not agents:
        raise ValueError("no households placed on tract centroids")

    network_seed = derive(args.profile_seed, "e1_network_delivery_seed")
    graph = build_social_graph(
        agents,
        radius_m=args.radius_m,
        k_neighbors=args.k_neighbors,
        k_friends=args.k_friends,
        rewire_p=args.rewire_p,
        seed=network_seed,
    )
    degrees = [degree for _, degree in graph.degree()]
    components = list(nx.connected_components(graph))
    edges_sorted = sorted(
        (u, v, data.get("kind", "")) for u, v, data in graph.edges(data=True)
    )
    edge_hash = sha256_text(repr(edges_sorted))
    manifest = {
        "n_nodes": graph.number_of_nodes(),
        "n_edges": graph.number_of_edges(),
        "n_households_placed": len(agents),
        "n_households_missing_centroid": missing,
        "mean_degree": round(sum(degrees) / len(degrees), 4) if degrees else 0,
        "degree_distribution": {
            str(degree): degrees.count(degree)
            for degree in sorted(set(degrees))
        },
        "n_connected_components": len(components),
        "largest_component_fraction": round(
            max(len(component) for component in components) / len(agents),
            4,
        ),
        "parameters": {
            "radius_m": args.radius_m,
            "k_neighbors": args.k_neighbors,
            "k_friends": args.k_friends,
            "rewire_p": args.rewire_p,
            "network_delivery_seed": network_seed,
            "placement": "2018 TIGER tract centroid, local planar metres",
        },
        "edge_kind_counts": {
            kind: sum(
                1
                for _, _, edge_kind in edges_sorted
                if edge_kind == kind
            )
            for kind in ("family", "neighbor", "friend")
        },
        "edge_sha256": edge_hash,
        "provenance": {
            "graph_algorithm": "ds.population.networks.build_social_graph",
            "no_outcome_or_trait_dependence": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
