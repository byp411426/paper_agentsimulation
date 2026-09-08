"""Carr-S E1 natural-timing empirical scenario on the common kernel.

This runner intentionally differs from the controlled E2 mechanism matrix: it
does not seed a route plan or departure step.  It evaluates synthetic focal
residents and household processes against aggregate Carr survey references
within an explicitly Carr-informed, non-historical scenario.
"""

from __future__ import annotations

import asyncio
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ds.agents.carr import MechanismFlags
from ds.agents.carr_empirical import CarrEmpiricalResident
from ds.agents.state import StaticAttrs
from ds.eventpack import ListEventSource, load_eventpack, load_warning_events
from ds.eval.carr_protocol import file_sha256
from ds.households import DependentMemberState, Household, VehicleResource
from ds.interaction.delivery import DeliveryModel
from ds.interaction.engine import InteractionEngine
from ds.interaction.messages import Event, Message
from ds.kernel.engine import Engine
from ds.kernel.logger import RunLogger
from ds.kernel.rng import stream_seed
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMGateway
from ds.population.networks import build_social_graph
from ds.provenance import write_provenance
from ds.world.carr import CarrWorld
from experiments.carr.runner import _gateway_configuration, _route_states


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class CarrCalibratedDeliveryModel(DeliveryModel):
    """Implement the declared Carr survey-calibrated delivery parameters."""

    def __init__(self, parameters: dict[str, Any], *, start_hour: int) -> None:
        self.device = float(parameters["device_ownership"])
        self.coverage = float(parameters["wea_coverage"])
        self.day_start_hour = int(parameters["day_start_hour"])
        self.day_end_hour = int(parameters["day_end_hour"])
        self.awake_check_prob = float(parameters["awake_check_prob"])
        self.asleep_check_prob = float(parameters["asleep_check_prob"])
        self.start_hour = int(start_hour)

    def receive_prob(self, sim_minutes: int) -> float:
        hour = (self.start_hour + sim_minutes / 60) % 24
        check = (
            self.awake_check_prob
            if self.day_start_hour <= hour < self.day_end_hour
            else self.asleep_check_prob
        )
        return self.device * self.coverage * check


class NetworkedInteractionEngine(InteractionEngine):
    """Route community messages only to declared graph neighbors."""

    def __init__(self, *args: Any, social_graph: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.social_graph = social_graph

    def _resolve(self, message: Message) -> list[str]:
        if message.recipients in ("neighbors", "community"):
            if message.sender not in self.social_graph:
                return []
            return sorted(self.social_graph.neighbors(message.sender))
        return super()._resolve(message)

    def snapshot(self) -> dict[str, Any]:
        base = super().snapshot()
        base["social_graph_nodes"] = int(self.social_graph.number_of_nodes())
        base["social_graph_edges"] = int(self.social_graph.number_of_edges())
        return base


@dataclass
class CarrEmpiricalResult:
    seed: int
    summary: dict[str, Any]
    metrics: dict[str, Any]
    run_dir: Path


def _vehicle_count(value: Any) -> int:
    text = str(value)
    return 4 if text == "4_plus" else int(float(text))


def load_empirical_cohort(
    *,
    eventpack_root: Path,
    cohort_seed: int,
    n_households: int,
) -> dict[str, pd.DataFrame]:
    base = eventpack_root / "population/pilot_seed42_n1000"
    households = pd.read_csv(base / "synthetic_households.csv", dtype={"geoid": str})
    persons = pd.read_csv(base / "synthetic_persons.csv", dtype={"geoid": str})
    adult_counts = persons["AGEP"].ge(18).groupby(
        persons["synthetic_household_id"]
    ).sum()
    eligible_ids = set(adult_counts[adult_counts.between(1, 2)].index)
    eligible = households[
        households["synthetic_household_id"].isin(eligible_ids)
    ].copy()
    eligible["_order"] = eligible["synthetic_household_id"].map(
        lambda household_id: stream_seed(
            cohort_seed,
            "e1_population_selection",
            entity_id=str(household_id),
        )
    )
    selected_households = (
        eligible.sort_values(["_order", "synthetic_household_id"])
        .head(n_households)
        .drop(columns="_order")
        .reset_index(drop=True)
    )
    if len(selected_households) != n_households:
        raise ValueError(
            f"E1 cohort requires {n_households} households; "
            f"found {len(selected_households)} eligible households"
        )
    selected_ids = set(selected_households["synthetic_household_id"])
    selected_persons = persons[
        persons["synthetic_household_id"].isin(selected_ids)
    ].copy()
    return {"households": selected_households, "persons": selected_persons}


def _tract_centers(eventpack_root: Path) -> dict[str, tuple[float, float]]:
    path = eventpack_root / "population/tiger/tracts/shasta_tracts.geojson"
    payload = json.loads(path.read_text(encoding="utf-8"))
    centers: dict[str, tuple[float, float]] = {}
    for feature in payload["features"]:
        properties = feature["properties"]
        geoid = f"14000US{properties['GEOID']}"
        latitude = float(properties["INTPTLAT"])
        longitude = float(properties["INTPTLON"])
        x = longitude * 111_320 * math.cos(math.radians(latitude))
        y = latitude * 110_540
        centers[geoid] = (x, y)
    return centers


def _social_location(
    *,
    geoid: str,
    household_id: str,
    centers: dict[str, tuple[float, float]],
    cohort_seed: int,
) -> tuple[float, float]:
    x, y = centers[geoid]
    angle_draw = stream_seed(
        cohort_seed, "e1_network_angle", entity_id=household_id
    ) / 2**32
    radius_draw = stream_seed(
        cohort_seed, "e1_network_radius", entity_id=household_id
    ) / 2**32
    angle = 2 * math.pi * angle_draw
    radius = 800 * math.sqrt(radius_draw)
    return x + radius * math.cos(angle), y + radius * math.sin(angle)


def build_empirical_parts(
    *,
    cfg: dict[str, Any],
    seed: int,
    eventpack_root: Path,
) -> dict[str, Any]:
    run_cfg = cfg["run"]
    experiment = cfg["experiment"]
    cohort_seed = int(experiment["cohort_seed"])
    population = load_empirical_cohort(
        eventpack_root=eventpack_root,
        cohort_seed=cohort_seed,
        n_households=int(experiment["n_households"]),
    )
    centers = _tract_centers(eventpack_root)
    mechanisms = MechanismFlags()
    households: dict[str, Household] = {}
    agents: list[CarrEmpiricalResident] = []
    network_records: list[dict[str, Any]] = []

    for household_row in population["households"].to_dict(orient="records"):
        household_id = str(household_row["synthetic_household_id"])
        members = population["persons"][
            population["persons"]["synthetic_household_id"].eq(household_id)
        ].sort_values(["SPORDER", "resident_id"])
        adults = members[members["AGEP"].ge(18)]
        dependents = members[members["AGEP"].lt(18)]
        decision_ids = tuple(adults["resident_id"].astype(str))
        dependent_ids = tuple(dependents["resident_id"].astype(str))
        member_ids = decision_ids + dependent_ids
        vehicle_count = _vehicle_count(household_row["vehicle_count"])
        vehicles = {
            f"{household_id}:vehicle:{index}": VehicleResource(
                id=f"{household_id}:vehicle:{index}",
                location="home",
                capacity=max(5, len(member_ids)),
            )
            for index in range(1, vehicle_count + 1)
        }
        household = Household(
            id=household_id,
            member_ids=member_ids,
            decision_member_ids=decision_ids,
            dependent_ids=dependent_ids,
            vehicles=vehicles,
            dependent_states={
                dependent_id: DependentMemberState(
                    id=dependent_id,
                    location="home",
                    caregiver_id=decision_ids[0],
                )
                for dependent_id in dependent_ids
            },
        )
        households[household_id] = household
        household_profile = {
            "household_size": int(household_row["household_size"]),
            "vehicle_count": vehicle_count,
            "income_band": str(household_row["household_income"]),
            "income_value": float(household_row["HINCP"]),
            "household_structure": str(household_row["household_structure"]),
            "tract_geoid": str(household_row["geoid"]),
        }
        location = _social_location(
            geoid=str(household_row["geoid"]),
            household_id=household_id,
            centers=centers,
            cohort_seed=cohort_seed,
        )
        vehicle_ids = sorted(vehicles)
        for adult_index, (_, adult) in enumerate(adults.iterrows()):
            agent_id = str(adult["resident_id"])
            limitations = {
                field.lower(): bool(adult.get(field) == 1)
                for field in ("DEAR", "DEYE", "DOUT", "DPHY", "DRAT", "DREM")
                if pd.notna(adult.get(field))
            }
            agent = CarrEmpiricalResident(
                agent_id,
                static=StaticAttrs(
                    age=int(adult["AGEP"]),
                    decision_capable=True,
                    decision_policy="generative",
                    functional_limitations=limitations,
                    household_id=household_id,
                    zone=str(experiment["controlled_zone"]),
                    home="home",
                ),
                household=household,
                role="coordinator" if adult_index == 0 else "partner",
                partner_id=(
                    decision_ids[1 - adult_index]
                    if len(decision_ids) == 2
                    else ""
                ),
                vehicle_id=vehicle_ids[0] if vehicle_ids else "",
                dependent_ids=dependent_ids,
                mechanisms=mechanisms,
                depart_step=-1,
                primary_route_id=str(experiment["primary_route_id"]),
                alternate_route_id=str(experiment["alternate_route_id"]),
                persona=(
                    f"adult resident age {int(adult['AGEP'])} in a "
                    f"{len(member_ids)}-person household"
                ),
                prompt_version=str(experiment["prompt_version"]),
                coordination_deadline_step=None,
                route_observation_mode="live_world",
                household_profile=household_profile,
                followup_interval_steps=int(
                    experiment["followup_interval_steps"]
                ),
                step_minutes=int(run_cfg["step_minutes"]),
            )
            agents.append(agent)
            network_records.append(
                {
                    "id": agent_id,
                    "household_id": household_id,
                    "location": location,
                    "zone": str(experiment["controlled_zone"]),
                }
            )

    social_graph = build_social_graph(
        network_records,
        radius_m=float(experiment["network_radius_m"]),
        k_neighbors=int(experiment["network_k_neighbors"]),
        k_friends=int(experiment["network_k_friends"]),
        rewire_p=float(experiment["network_rewire_probability"]),
        seed=cohort_seed,
    )
    world = CarrWorld(
        households=households,
        routes=_route_states(
            experiment_cfg=experiment,
            eventpack_root=eventpack_root,
        ),
        run_seed=seed,
        initial_hazard_distance_m=float(experiment["initial_hazard_distance_m"]),
        hazard_approach_per_step_m=float(experiment["hazard_approach_per_step_m"]),
    )
    world.bind_agents(agents)
    delivery_path = eventpack_root / "warnings/delivery_params.yaml"
    delivery_parameters = yaml.safe_load(delivery_path.read_text(encoding="utf-8"))
    interaction = NetworkedInteractionEngine(
        {agent.id: agent for agent in agents},
        delivery=CarrCalibratedDeliveryModel(
            delivery_parameters,
            start_hour=int(experiment["scenario_start_hour"]),
        ),
        households_by_id=households,
        social_enabled=True,
        run_seed=seed,
        dm_delivery_probability=float(
            experiment["household_dm_delivery_probability"]
        ),
        community_delivery_probability=float(
            experiment["community_message_delivery_probability"]
        ),
        social_graph=social_graph,
    )
    source = load_warning_events(eventpack_root / "warnings/warnings_multi.csv")
    mandatory = next(
        event
        for event in source.events
        if event.payload.get("severity") == "mandatory"
        and event.zone == str(experiment["controlled_zone"])
    )
    events = ListEventSource(
        [
            Event(
                step=int(experiment["order_step"]),
                kind="warning",
                text=mandatory.text,
                zone=str(experiment["controlled_zone"]),
                recipients="all",
                payload={
                    **mandatory.payload,
                    "scenario_control": "single Carr-informed order checkpoint",
                    "source_event_step": mandatory.step,
                },
            )
        ]
    )
    return {
        "population": population,
        "households": households,
        "agents": agents,
        "world": world,
        "interaction": interaction,
        "events": events,
        "social_graph": social_graph,
        "delivery_parameters_path": delivery_path,
    }


def _subgroup_gap(
    focal_rows: pd.DataFrame,
    *,
    contrast: str,
    mask: pd.Series,
) -> dict[str, Any]:
    group_a = focal_rows.loc[mask]
    group_b = focal_rows.loc[~mask]
    if group_a.empty or group_b.empty:
        return {
            "contrast": contrast,
            "status": "UNAVAILABLE_EMPTY_GROUP",
            "n_a": int(len(group_a)),
            "n_b": int(len(group_b)),
            "signed_gap": None,
        }
    return {
        "contrast": contrast,
        "status": "ESTIMABLE",
        "n_a": int(len(group_a)),
        "n_b": int(len(group_b)),
        "proportion_a": float(group_a["evacuated"].mean()),
        "proportion_b": float(group_b["evacuated"].mean()),
        "signed_gap": float(
            group_a["evacuated"].mean() - group_b["evacuated"].mean()
        ),
    }


def empirical_metrics(
    *,
    cfg: dict[str, Any],
    seed: int,
    parts: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    experiment = cfg["experiment"]
    agents: list[CarrEmpiricalResident] = parts["agents"]
    households: dict[str, Household] = parts["households"]
    world: CarrWorld = parts["world"]
    interaction: NetworkedInteractionEngine = parts["interaction"]
    focal = [agent for agent in agents if agent.role == "coordinator"]
    focal_rows = pd.DataFrame(
        [
            {
                "agent_id": agent.id,
                "household_id": agent.static.household_id,
                "age": agent.static.age,
                "household_size": int(
                    agent.household_profile["household_size"]
                ),
                "vehicle_count": int(
                    agent.household_profile["vehicle_count"]
                ),
                "income_value": float(
                    agent.household_profile["income_value"]
                ),
                "evacuated": int(world.is_safe(agent.id)),
                "evac_step": agent.state.evac_step,
                "first_order_received_step": agent.first_order_received_step,
            }
            for agent in focal
        ]
    )
    order_delay_rows = focal_rows[
        focal_rows["first_order_received_step"].notna()
        & focal_rows["evac_step"].ge(0)
        & focal_rows["evac_step"].ge(
            focal_rows["first_order_received_step"].fillna(10**9)
        )
    ].copy()
    order_delay_rows["delay_hours"] = (
        order_delay_rows["evac_step"]
        - order_delay_rows["first_order_received_step"]
    ) * int(cfg["run"]["step_minutes"]) / 60
    horizons = [float(value) for value in experiment["cdf_horizons_hours"]]
    simulated_cdf = {
        str(horizon): (
            float(order_delay_rows["delay_hours"].le(horizon).mean())
            if len(order_delay_rows)
            else None
        )
        for horizon in horizons
    }
    reference_path = PROJECT_ROOT / str(experiment["empirical_reference"])
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference_cdf = reference["order_to_departure_delay"][
        "main_consistent_temporal_order"
    ]["cdf"]
    cdf_absolute_differences = {
        str(horizon): (
            abs(simulated_cdf[str(horizon)] - float(reference_cdf[str(horizon)]))
            if simulated_cdf[str(horizon)] is not None
            else None
        )
        for horizon in horizons
    }
    reference_gaps = {
        row["contrast"]: row
        for row in reference["subgroup_evacuation_gaps"]
    }
    subgroup_rows = [
        _subgroup_gap(
            focal_rows,
            contrast="age_65plus_minus_under65",
            mask=focal_rows["age"].ge(65),
        ),
        _subgroup_gap(
            focal_rows,
            contrast="household_3plus_minus_1to2",
            mask=focal_rows["household_size"].ge(3),
        ),
        _subgroup_gap(
            focal_rows,
            contrast="zero_vehicle_minus_oneplus",
            mask=focal_rows["vehicle_count"].eq(0),
        ),
        _subgroup_gap(
            focal_rows,
            contrast="income_under50k_minus_50kplus",
            mask=focal_rows["income_value"].lt(50_000),
        ),
    ]
    for row in subgroup_rows:
        reference_row = reference_gaps[row["contrast"]]
        row["survey_status"] = reference_row["status"]
        row["survey_signed_gap"] = reference_row.get("signed_gap")
        row["simulation_minus_survey_gap"] = (
            row["signed_gap"] - reference_row["signed_gap"]
            if row["signed_gap"] is not None
            and reference_row.get("signed_gap") is not None
            else None
        )

    receipt_by_agent = {agent.id: set() for agent in focal}
    for receipt in interaction.receipts.values():
        if receipt.recipient not in receipt_by_agent:
            continue
        receipt_by_agent[receipt.recipient].add(
            "family" if receipt.sender in households[
                next(
                    agent.static.household_id
                    for agent in focal
                    if agent.id == receipt.recipient
                )
            ].member_ids else "neighbor"
        )
    channel_prevalence = {
        "official_calibrated": sum(agent.state.warned for agent in focal)
        / len(focal),
        "family_message": sum(
            "family" in receipt_by_agent[agent.id] for agent in focal
        ) / len(focal),
        "neighbor_message": sum(
            "neighbor" in receipt_by_agent[agent.id] for agent in focal
        ) / len(focal),
    }
    complete_safe = [
        set(household.decision_member_ids).issubset(world.evacuated)
        and set(household.dependent_ids).issubset(world.safe_dependents)
        for household in households.values()
    ]
    total_dependents = sum(
        len(household.dependent_ids) for household in households.values()
    )
    gateway = summary["gateway"]
    result = {
        "status": (
            "PILOT_PENDING_MULTI_SEED_AUDIT"
            if summary["status"] == "VALID"
            else "INVALID_RUN"
        ),
        "seed": seed,
        "run_terminal_status": summary["status"],
        "n_households": len(households),
        "n_decision_residents": len(agents),
        "n_focal_residents": len(focal),
        "focal_evacuation_rate": float(focal_rows["evacuated"].mean()),
        "survey_evacuation_rate": float(
            reference["evacuation_outcome"]["proportion"]
        ),
        "focal_minus_survey_evacuation_rate": float(
            focal_rows["evacuated"].mean()
            - reference["evacuation_outcome"]["proportion"]
        ),
        "order_to_departure": {
            "eligible_simulated_focal_count": int(len(order_delay_rows)),
            "received_order_focal_count": int(
                focal_rows["first_order_received_step"].notna().sum()
            ),
            "evacuated_before_received_order_count": int(
                (
                    focal_rows["first_order_received_step"].notna()
                    & focal_rows["evac_step"].ge(0)
                    & focal_rows["evac_step"].lt(
                        focal_rows["first_order_received_step"].fillna(-1)
                    )
                ).sum()
            ),
            "mean_hours": (
                float(order_delay_rows["delay_hours"].mean())
                if len(order_delay_rows)
                else None
            ),
            "median_hours": (
                float(order_delay_rows["delay_hours"].median())
                if len(order_delay_rows)
                else None
            ),
            "simulated_cdf": simulated_cdf,
            "survey_main_cdf": {
                str(horizon): float(reference_cdf[str(horizon)])
                for horizon in horizons
            },
            "cdf_absolute_differences": cdf_absolute_differences,
            "mean_absolute_cdf_difference": (
                statistics.mean(
                    value
                    for value in cdf_absolute_differences.values()
                    if value is not None
                )
                if order_delay_rows.shape[0]
                else None
            ),
            "administrative_horizon_hours": (
                (
                    int(cfg["run"]["total_steps"])
                    - int(experiment["order_step"])
                )
                * int(cfg["run"]["step_minutes"])
                / 60
            ),
        },
        "subgroup_evacuation_gaps": subgroup_rows,
        "channel_prevalence": channel_prevalence,
        "channel_claim_boundary": (
            "Official receipt is a calibration check. Family/neighbor values are "
            "simulation message prevalence and are not directly equated to the "
            "survey multi-select warning-channel prevalence."
        ),
        "complete_household_safe_departure_rate": sum(complete_safe)
        / len(complete_safe),
        "coordinated_departure_rate": world.coordinated_movements
        / len(households),
        "dependent_safety_rate": (
            len(world.safe_dependents) / total_dependents
            if total_dependents
            else 1.0
        ),
        "execution_rejections_per_household": sum(world.rejections.values())
        / len(households),
        "dependent_left_behind_rejections_per_household": world.rejections.get(
            "dependent member would be left behind", 0
        ) / len(households),
        "resource_conflict_rejections_per_household": sum(
            count
            for reason, count in world.rejections.items()
            if "vehicle" in reason or "allocated" in reason or "reserved" in reason
        ) / len(households),
        "messages_sent": interaction.msg_count,
        "message_receipt_states": interaction.snapshot()["receipt_states"],
        "first_heard_counts": interaction.snapshot()["first_heard_counts"],
        "n_logical_decisions": int(
            gateway["n_ok"] + gateway["n_cache"] + gateway["n_fallback"]
        ),
        "n_failed": int(gateway["n_failed"]),
        "n_fallback": int(gateway["n_fallback"]),
        "fallback_rate": float(gateway["fallback_rate"]),
        "cost_usd": float(gateway["spent"]),
        "wall_clock_seconds": float(summary["wall_clock_seconds"]),
        "claim_boundary": (
            "Carr-informed controlled E1 empirical-reasonableness evidence using "
            "a development synthetic population. It is not a historical Carr "
            "reconstruction or a claim that person-level population margins are calibrated."
        ),
        "reference_sha256": file_sha256(reference_path),
    }
    return result


def run_empirical_seed(
    cfg: dict[str, Any],
    *,
    config_path: Path,
    seed: int,
    runs_dir: Path,
) -> CarrEmpiricalResult:
    eventpack_root = PROJECT_ROOT / str(cfg["experiment"]["eventpack_root"])
    eventpack_root = eventpack_root.resolve()
    pack = load_eventpack(eventpack_root)
    parts = build_empirical_parts(
        cfg=cfg,
        seed=seed,
        eventpack_root=eventpack_root,
    )
    llm_cfg = cfg["llm"]
    decision_model = str(llm_cfg["decision_model"])
    if decision_model == "mock":
        raise ValueError("E1 behavior evidence requires the declared real backend")
    models_cfg, models_path, credential_name = _gateway_configuration(
        llm_cfg=llm_cfg,
        decision_model=decision_model,
    )
    run_id = f"{cfg['run']['run_id']}_seed{seed}"
    run_dir = runs_dir / run_id
    if run_dir.exists():
        raise FileExistsError(
            f"E1 run directory already exists and will not be overwritten: {run_dir}"
        )
    cache = LLMCache(run_dir / "cache.sqlite")
    gateway = LLMGateway(
        run_id=run_id,
        models_cfg=models_cfg,
        budget_usd=float(llm_cfg["budget_usd"]),
        max_concurrency=int(llm_cfg["max_concurrency"]),
        log_dir=runs_dir,
        cache=cache,
        abort_on_call_failure=bool(llm_cfg["abort_on_call_failure"]),
    )
    logger = RunLogger(run_dir)
    write_provenance(
        run_dir,
        config={
            **cfg,
            "run": {**cfg["run"], "seed": seed, "run_id": run_id},
        },
        models=[decision_model],
        extra={
            "eventpack_id": pack.manifest.event_id,
            "models_config": {
                "path": str(models_path.relative_to(PROJECT_ROOT)),
                "sha256": file_sha256(models_path),
            },
            "credential_environment_name": credential_name,
            "credential_value_recorded": False,
            "source_files": {
                name: {
                    "path": str(path.relative_to(PROJECT_ROOT)),
                    "sha256": file_sha256(path),
                }
                for name, path in {
                    "empirical_runner": Path(__file__),
                    "empirical_resident": PROJECT_ROOT
                    / "ds/agents/carr_empirical.py",
                    "kernel": PROJECT_ROOT / "ds/kernel/engine.py",
                    "world": PROJECT_ROOT / "ds/world/carr.py",
                    "interaction": PROJECT_ROOT / "ds/interaction/engine.py",
                    "gateway": PROJECT_ROOT / "ds/llm/gateway.py",
                }.items()
            },
        },
    )
    engine = Engine(
        run_seed=seed,
        total_steps=int(cfg["run"]["total_steps"]),
        step_minutes=int(cfg["run"]["step_minutes"]),
        world=parts["world"],
        agents=parts["agents"],
        interaction=parts["interaction"],
        events=parts["events"],
        gateway=gateway,
        logger=logger,
        decision_model=decision_model,
        temperature=float(llm_cfg["temperature"]),
        fallback_threshold=float(llm_cfg["fallback_threshold"]),
    )

    async def _run() -> dict[str, Any]:
        try:
            return await engine.run()
        finally:
            await gateway.aclose()

    try:
        summary = asyncio.run(_run())
    finally:
        logger.close()
        cache.close()
    metrics = empirical_metrics(
        cfg=cfg,
        seed=seed,
        parts=parts,
        summary=summary,
    )
    (run_dir / "empirical_metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return CarrEmpiricalResult(
        seed=seed,
        summary=summary,
        metrics=metrics,
        run_dir=run_dir,
    )
