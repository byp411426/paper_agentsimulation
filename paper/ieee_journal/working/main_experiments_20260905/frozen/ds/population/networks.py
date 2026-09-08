"""Social network construction (spec §2.2, §6.4).

Family (clique) + neighborhood (nearest-k within radius) + friends (small-world) +
an institutional 'official' node per zone (directed receive). Kept dependency-light:
takes plain agent records with (id, household_id, location, zone).
"""

from __future__ import annotations

import math
from typing import Any

import networkx as nx


def build_social_graph(agents: list[dict], radius_m: float = 300.0,
                       k_neighbors: int = 6, k_friends: int = 4,
                       rewire_p: float = 0.1, seed: int = 42) -> nx.Graph:
    G = nx.Graph()
    for a in agents:
        G.add_node(a["id"], **a)

    # ① family: clique within each household
    by_house: dict[str, list[str]] = {}
    for a in agents:
        by_house.setdefault(a.get("household_id", a["id"]), []).append(a["id"])
    for members in by_house.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                G.add_edge(members[i], members[j], kind="family")

    # ② neighborhood: nearest-k within radius (deterministic by id order)
    ids = [a["id"] for a in agents]
    locs = {a["id"]: a.get("location", (0.0, 0.0)) for a in agents}
    for a in sorted(agents, key=lambda x: x["id"]):
        here = locs[a["id"]]
        cand = []
        for b in ids:
            if b == a["id"]:
                continue
            d = _dist(here, locs[b])
            if d <= radius_m:
                cand.append((d, b))
        cand.sort()
        for _, b in cand[:k_neighbors]:
            G.add_edge(a["id"], b, kind="neighbor")

    # ③ friends: small-world overlay (Watts-Strogatz on the id ring)
    if len(ids) > k_friends + 1:
        ws = nx.watts_strogatz_graph(len(ids), k_friends, rewire_p, seed=seed)
        remap = {i: ids[i] for i in range(len(ids))}
        for u, v in ws.edges():
            G.add_edge(remap[u], remap[v], kind="friend")

    return G


def _dist(p, q) -> float:
    return math.hypot(p[0] - q[0], p[1] - q[1])
