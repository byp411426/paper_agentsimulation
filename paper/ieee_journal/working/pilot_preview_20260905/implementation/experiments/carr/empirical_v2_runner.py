"""Carr E1 v2 runner assembly (W5 contract, offline-wireable)."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx
import yaml

from ds.agents.carr_empirical_v2 import CarrEmpiricalResidentV2
from ds.households.state import CareRequirement, Household, VehicleResource
from ds.interaction.carr_empirical_v2 import CarrEmpiricalInteractionV2
from ds.kernel.engine import Engine
from ds.kernel.logger import RunLogger
from ds.kernel.rng import stream_rng
from ds.llm.gateway import LLMGateway
from ds.population.networks import build_social_graph
from ds.world.carr_empirical_v2 import CarrEmpiricalWorldV2


@dataclass(frozen=True)
class OfficialOrderEvent:
    event_id: str
    kind: str = "official_order"
    severity: str = "voluntary"
    issued_step: int = 0
    recipient_id: str | None = None

    def recipient_covers(self, agent: Any) -> bool:
        return self.recipient_id is None or agent.id == self.recipient_id


@dataclass(frozen=True)
class RouteClosureEvent:
    event_id: str
    kind: str = "route_closure"
    route_id: str = "tiger_primary"
    issued_step: int = 0


class E1EventSource:
    def __init__(self, events: list):
        self.by_step: dict[int, list] = {}
        for event in events:
            self.by_step.setdefault(event.issued_step, []).append(event)

    def events_due(self, step: int) -> list:
        return self.by_step.get(step, [])


def hamilton_quotas(proportions: dict[str, float], n: int) -> dict[str, int]:
    """Hamilton largest-remainder allocation of n households to sequences."""
    if n <= 0:
        return {key: 0 for key in proportions}
    raw = {key: value * n for key, value in proportions.items()}
    floors = {key: math.floor(value) for key, value in raw.items()}
    remainder = n - sum(floors.values())
    order = sorted(
        proportions.keys(),
        key=lambda key: (raw[key] - floors[key], key),
        reverse=True,
    )
    for key in order[:remainder]:
        floors[key] += 1
    return floors


def _centroid_locations(
    households_csv: Path, tracts_geojson: Path
) -> dict[str, tuple[float, float]]:
    import geopandas as gpd
    import pandas as pd

    households = pd.read_csv(households_csv)
    tracts = gpd.read_file(tracts_geojson).to_crs("EPSG:4326")
    centroids = {}
    for _, row in tracts.iterrows():
        geoid = str(row.get("GEOID") or "")
        if geoid:
            point = row.geometry.centroid
            centroids[geoid] = (float(point.x), float(point.y))
    lon_values = [value[0] for value in centroids.values()]
    lat_values = [value[1] for value in centroids.values()]
    ref_lon = sum(lon_values) / len(lon_values)
    ref_lat = sum(lat_values) / len(lat_values)
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(ref_lat))
    locations: dict[str, tuple[float, float]] = {}
    for _, row in households.iterrows():
        geoid = str(row["geoid"])[-11:]
        if geoid not in centroids:
            continue
        lon, lat = centroids[geoid]
        locations[str(row["synthetic_household_id"])] = (
            (lon - ref_lon) * m_per_deg_lon,
            (lat - ref_lat) * 111_320.0,
        )
    return locations


def build_e1_v2_components(
    *,
    cfg: dict,
    profiles_path: Path,
    n_households: int,
    run_seed: int,
    gateway: LLMGateway,
    households_csv: Path | None = None,
    tracts_geojson: Path | None = None,
) -> tuple[dict, dict, dict, Any, Any, Any, list[Any]]:
    """Return (households, residents, profiles_by_household, world, ix, events, agents)."""
    exp = cfg["experiment"]
    profiles = [
        json.loads(line)
        for line in profiles_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][:n_households]
    if len(profiles) != n_households:
        raise ValueError(
            f"need {n_households} profiles, found {len(profiles)}"
        )

    vehicle_capacity = int(exp["vehicles"]["capacity"])
    households: dict[str, Household] = {}
    residents: dict[str, CarrEmpiricalResidentV2] = {}
    decision_capable: dict[str, bool] = {}
    care_requirements: dict[str, CareRequirement] = {}
    profiles_by_household: dict[str, dict] = {}

    locations = {}
    if households_csv is not None and tracts_geojson is not None:
        locations = _centroid_locations(households_csv, tracts_geojson)

    for profile in profiles:
        household_id = profile["household_id"]
        shared = profile["shared_attributes"]
        members = list(profile["member_profiles"])
        member_ids = tuple(member["resident_id"] for member in members)
        decision_ids = tuple(
            member["resident_id"]
            for member in members
            if member["decision_capable"]
        )
        dependent_ids = tuple(
            member["resident_id"]
            for member in members
            if not member["decision_capable"]
        )
        vehicle_count = int(shared.get("vehicle_count", 0))
        vehicles = {
            f"{household_id}:vehicle:{index}": VehicleResource(
                id=f"{household_id}:vehicle:{index}",
                location=("home", household_id),
                capacity=vehicle_capacity,
            )
            for index in range(1, vehicle_count + 1)
        }
        household = Household(
            id=household_id,
            member_ids=member_ids,
            decision_member_ids=decision_ids,
            dependent_ids=dependent_ids,
            vehicles=vehicles,
        )
        household.profile = profile
        households[household_id] = household
        profiles_by_household[household_id] = profile

        for member in members:
            resident_id = member["resident_id"]
            decision_capable[resident_id] = bool(member["decision_capable"])
            if member.get("needs_execution_assistance"):
                assistance_type = (
                    "minor"
                    if member["age"] < 18
                    else "independent_living"
                )
                care_requirements[resident_id] = CareRequirement(
                    member_id=resident_id,
                    assistance_type=assistance_type,
                    caregiver_id=None,
                )
            if not member["decision_capable"]:
                continue
            resident = CarrEmpiricalResidentV2(
                agent_id=resident_id,
                household_id=household_id,
                profile=member,
                vehicles={
                    vehicle_id: {
                        "id": vehicle_id,
                        "capacity": vehicle.capacity,
                        "location": vehicle.location,
                    }
                    for vehicle_id, vehicle in vehicles.items()
                },
                initial_routes={
                    exp["routes"]["primary_route_id"]: {
                        "open": True,
                        "name": exp["routes"]["primary_route_id"],
                    },
                    exp["routes"]["alternate_route_id"]: {
                        "open": True,
                        "name": exp["routes"]["alternate_route_id"],
                    },
                },
            )
            residents[resident_id] = resident

    graph_agents = [
        {
            "id": resident_id,
            "household_id": resident.household_id,
            "location": locations.get(
                resident.household_id, (float(hash(resident_id) % 1000), 0.0)
            ),
        }
        for resident_id, resident in residents.items()
    ]
    graph_cfg = exp["social_graph"]
    graph = build_social_graph(
        graph_agents,
        radius_m=float(graph_cfg["radius_m"]),
        k_neighbors=int(graph_cfg["k_neighbors"]),
        k_friends=int(graph_cfg["k_friends"]),
        rewire_p=float(graph_cfg["rewire_p"]),
        seed=stream_rng(run_seed, "e1_network_delivery_seed").randrange(2**31),
    )

    calibration = json.loads(
        Path(exp["order_calibration"]).read_text(encoding="utf-8")
    )
    proportions = calibration["calibration"]["main_excluding_15_contradictions"][
        "proportions"
    ]
    quotas = hamilton_quotas(proportions, n_households)
    rng = stream_rng(run_seed, "e1_order_assignment")
    ordered_ids = sorted(households.keys())
    rng.shuffle(ordered_ids)
    sequence_by_household: dict[str, str] = {}
    cursor = 0
    for sequence, count in quotas.items():
        for _ in range(count):
            sequence_by_household[ordered_ids[cursor]] = sequence
            cursor += 1

    orders_cfg = exp["orders"]
    events: list[Any] = []
    event_index = 0
    for household_id, sequence in sequence_by_household.items():
        focal = profile_focal(profiles_by_household[household_id])
        if sequence in ("voluntary_only", "voluntary_then_mandatory"):
            event_index += 1
            events.append(
                OfficialOrderEvent(
                    event_id=f"order_v_{event_index}",
                    severity="voluntary",
                    issued_step=int(orders_cfg["voluntary_step"]),
                    recipient_id=focal,
                )
            )
        if sequence in ("mandatory_only", "voluntary_then_mandatory"):
            event_index += 1
            events.append(
                OfficialOrderEvent(
                    event_id=f"order_m_{event_index}",
                    severity="mandatory",
                    issued_step=int(orders_cfg["mandatory_step"]),
                    recipient_id=focal,
                )
            )
    events.append(
        RouteClosureEvent(
            event_id="closure_1",
            route_id=exp["routes"]["primary_route_id"],
            issued_step=int(exp["routes"]["closure_step"]),
        )
    )

    world = CarrEmpiricalWorldV2(
        households=households,
        residents=residents,
        config={
            **exp["hazard"],
            **exp["routes"],
            "safe_zone": exp["safe_zone"],
            "care_requirements": care_requirements,
        },
        run_seed=run_seed,
    )
    ix = CarrEmpiricalInteractionV2(
        run_seed=run_seed,
        household_dm_probability=float(exp["delivery"]["household_dm_probability"]),
        community_message_probability=float(
            exp["delivery"]["community_message_probability"]
        ),
        social_graph=graph,
        residents=residents,
        households=households,
        decision_capable=decision_capable,
        care_requirements=care_requirements,
    )
    event_source = E1EventSource(events)
    agents = list(residents.values())
    return (
        households,
        residents,
        profiles_by_household,
        world,
        ix,
        event_source,
        agents,
    )


def profile_focal(profile: dict) -> str:
    return profile.get("focal_resident_id") or profile.get("coordinator_id")


def run_e1_v2(
    *,
    cfg: dict,
    out_dir: Path,
    gateway: LLMGateway,
    run_seed: int,
    n_households: int,
    profiles_path: Path,
    households_csv: Path | None = None,
    tracts_geojson: Path | None = None,
) -> dict:
    run_dir = out_dir / cfg["run"]["run_id"]
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = RunLogger(run_dir / "events")
    (
        households,
        residents,
        profiles_by_household,
        world,
        ix,
        event_source,
        agents,
    ) = build_e1_v2_components(
        cfg=cfg,
        profiles_path=profiles_path,
        n_households=n_households,
        run_seed=run_seed,
        gateway=gateway,
        households_csv=households_csv,
        tracts_geojson=tracts_geojson,
    )
    engine = Engine(
        run_seed=run_seed,
        total_steps=int(cfg["run"]["total_steps"]),
        step_minutes=int(cfg["run"]["step_minutes"]),
        world=world,
        agents=agents,
        interaction=ix,
        events=event_source,
        gateway=gateway,
        logger=logger,
        decision_model=cfg["llm"]["decision_model"],
        temperature=float(cfg["llm"]["temperature"]),
        fallback_threshold=float(cfg["llm"]["fallback_threshold"]),
    )
    result = await_engine(engine)
    logger.close()

    raw_profiles = [
        json.loads(line)
        for line in profiles_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ][:n_households]
    payload = {
        "run_id": cfg["run"]["run_id"],
        "status": result["status"],
        "reason_code": result.get("reason_code"),
        "n_households": n_households,
        "n_residents": len(residents),
        "n_orders": len(
            [
                event
                for event in event_source.by_step.values()
                for event in event
                if event.kind == "official_order"
            ]
        ),
        "route_state_final": world.route_state,
        "world": world.snapshot(),
        "messages": ix.snapshot(),
        "receipts": ix.snapshot()["receipts"],
        "member_profiles": [
            member
            for profile in raw_profiles
            for member in profile["member_profiles"]
        ],
        "residents": {
            agent_id: resident.snapshot()
            for agent_id, resident in residents.items()
        },
        "households": {
            household_id: {
                "v2_commitments": {
                    key: {
                        "id": value.id,
                        "status": value.status,
                        "created_step": value.created_step,
                        "accepted_by": sorted(value.accepted_by),
                        "household_id": household_id,
                        "supersedes_id": value.supersedes_id,
                        "party": {
                            "traveler_ids": sorted(value.party.traveler_ids),
                            "accompanying_member_ids": sorted(
                                value.party.accompanying_member_ids
                            ),
                            "caregiver_by_member": value.party.caregiver_by_member,
                            "vehicle_id": value.party.vehicle_id,
                            "route_id": value.party.route_id,
                            "depart_step": value.party.depart_step,
                        },
                    }
                    for key, value in household.v2_commitments.items()
                },
                "departure_records": [
                    record.__dict__ for record in household.departure_records
                ],
            }
            for household_id, household in households.items()
        },
    }
    (run_dir / "run_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    write_ledgers(run_dir, payload)
    return result


def await_engine(engine: Engine) -> dict:
    import asyncio

    return asyncio.run(engine.run())


def write_ledgers(run_dir: Path, payload: dict) -> None:
    lines = {
        "official_receipts.jsonl": [
            receipt for receipt in payload["receipts"]
        ],
        "message_ledger.jsonl": [
            message for message in payload["messages"]["messages"].values()
        ],
        "household_departure_ledger.jsonl": [
            record
            for household in payload["households"].values()
            for record in household["departure_records"]
        ],
        "commitment_ledger.jsonl": [
            commitment
            for household in payload["households"].values()
            for commitment in household["v2_commitments"].values()
        ],
        "resident_state_timeline.jsonl": [
            snapshot for snapshot in payload["residents"].values()
        ],
        "member_profiles.jsonl": [
            member for member in payload["member_profiles"]
        ],
    }
    for name, records in lines.items():
        with (run_dir / name).open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(
                    json.dumps(record, ensure_ascii=False, default=str) + "\n"
                )
