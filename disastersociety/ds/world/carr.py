"""Carr-informed controlled world with routes, vehicles, and care constraints."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from ds.households import Household, VehicleRequest
from ds.kernel.actions import ExecutionOutcome, IntentEnvelope, ResolvedIntent
from ds.kernel.clock import Clock
from ds.kernel.rng import stream_seed


@dataclass
class RouteState:
    id: str
    capacity_per_step: int
    open: bool = True
    length_m: float | None = None
    edge_source_linearids: tuple[str, ...] = ()
    asset_status: str | None = None


@dataclass(frozen=True)
class CarrNoop:
    intent: str


@dataclass(frozen=True)
class CarrRejected:
    intent: str
    reason: str


@dataclass(frozen=True)
class CarrMove:
    intent: str
    movement_id: str
    household_id: str
    route_id: str
    vehicle_id: str
    member_ids: tuple[str, ...]
    dependent_ids: tuple[str, ...]
    coordinated: bool


@dataclass
class _Movement:
    id: str
    household: Household
    route_id: str
    vehicle_id: str
    envelopes: list[IntentEnvelope]
    dependent_ids: tuple[str, ...]
    coordinated: bool


class CarrWorld:
    def __init__(
        self,
        *,
        households: dict[str, Household],
        routes: dict[str, RouteState],
        run_seed: int,
        initial_hazard_distance_m: float = 6000,
        hazard_approach_per_step_m: float = 700,
    ):
        self.households = households
        self.routes = routes
        self.run_seed = run_seed
        self.initial_hazard_distance_m = initial_hazard_distance_m
        self.hazard_approach_per_step_m = hazard_approach_per_step_m
        self.current_step = -1
        self.agents: dict[str, Any] = {}
        self.evacuated: set[str] = set()
        self.safe_dependents: set[str] = set()
        self.rejections: Counter[str] = Counter()
        self.coordinated_movements = 0
        self.uncoordinated_movements = 0
        self.route_closures: list[dict[str, Any]] = []

    def bind_agents(self, agents: list[Any]) -> None:
        self.agents = {agent.id: agent for agent in agents}

    def update(self, clock: Clock) -> None:
        self.current_step = clock.t

    def apply_events(self, events: list, clock: Clock) -> None:
        for event in events:
            kind = getattr(event, "kind", None)
            if kind != "road_closed":
                continue
            route_id = getattr(event, "payload", {}).get("route_id")
            if route_id not in self.routes:
                raise ValueError(f"closure references unknown route {route_id}")
            self.routes[route_id].open = False
            self.route_closures.append(
                {"step": clock.t, "route_id": route_id}
            )

    def distance_to_fire(self, loc: Any) -> float:
        if loc == "controlled_safe_zone":
            return float("inf")
        return max(
            0.0,
            self.initial_hazard_distance_m
            - max(self.current_step, 0) * self.hazard_approach_per_step_m,
        )

    def is_safe(self, agent_id: str) -> bool:
        return agent_id in self.evacuated

    def route_snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            route_id: {
                "open": route.open,
                "capacity_per_step": route.capacity_per_step,
                "length_m": route.length_m,
                "source_linearid_count": len(route.edge_source_linearids),
                "asset_status": route.asset_status,
            }
            for route_id, route in sorted(self.routes.items())
        }

    def resolve_batch(
        self,
        intents: list[IntentEnvelope],
        clock: Clock,
        run_seed: int,
    ) -> list[ResolvedIntent]:
        actions: dict[str, Any] = {}
        evacuations_by_household: dict[str, list[IntentEnvelope]] = {}
        for envelope in intents:
            action = getattr(envelope.decision, "action", "stay")
            if action != "evacuate":
                actions[envelope.decision_id] = CarrNoop(intent=action)
                continue
            household_id = envelope.agent.static.household_id
            evacuations_by_household.setdefault(household_id, []).append(envelope)

        movements: list[_Movement] = []
        for household_id, envelopes in sorted(evacuations_by_household.items()):
            household = self.households[household_id]
            movements.extend(
                self._household_movements(
                    household,
                    envelopes,
                    actions,
                    clock=clock,
                    run_seed=run_seed,
                )
            )

        movements_by_route: dict[str, list[_Movement]] = {}
        for movement in movements:
            movements_by_route.setdefault(movement.route_id, []).append(movement)
        for route_id, route_movements in sorted(movements_by_route.items()):
            route = self.routes.get(route_id)
            if route is None or not route.open:
                reason = "unknown route" if route is None else "route closed"
                for movement in route_movements:
                    self._reject_movement(movement, actions, reason)
                continue
            ordered = sorted(
                route_movements,
                key=lambda movement: stream_seed(
                    run_seed,
                    "arbitration",
                    entity_id=movement.id,
                    step=clock.t,
                ),
            )
            for index, movement in enumerate(ordered):
                if index >= route.capacity_per_step:
                    self._reject_movement(
                        movement, actions, "route capacity exhausted"
                    )
                    continue
                for envelope in movement.envelopes:
                    actions[envelope.decision_id] = CarrMove(
                        intent="evacuate",
                        movement_id=movement.id,
                        household_id=movement.household.id,
                        route_id=movement.route_id,
                        vehicle_id=movement.vehicle_id,
                        member_ids=tuple(
                            item.agent_id for item in movement.envelopes
                        ),
                        dependent_ids=movement.dependent_ids,
                        coordinated=movement.coordinated,
                    )

        return [
            ResolvedIntent(
                decision_id=envelope.decision_id,
                agent_id=envelope.agent_id,
                agent=envelope.agent,
                decision=envelope.decision,
                action=actions[envelope.decision_id],
            )
            for envelope in intents
        ]

    def apply_batch(
        self,
        resolved: list[ResolvedIntent],
        clock: Clock,
    ) -> dict[str, ExecutionOutcome]:
        outcomes: dict[str, ExecutionOutcome] = {}
        applied_movements: set[str] = set()
        for item in resolved:
            action = item.action
            if isinstance(action, CarrRejected):
                self.rejections[action.reason] += 1
                outcomes[item.decision_id] = ExecutionOutcome(
                    decision_id=item.decision_id,
                    agent_id=item.agent_id,
                    status="rejected",
                    executed_action=None,
                    reason=action.reason,
                )
                continue
            if isinstance(action, CarrNoop):
                outcomes[item.decision_id] = ExecutionOutcome(
                    decision_id=item.decision_id,
                    agent_id=item.agent_id,
                    status="executed",
                    executed_action=action.intent,
                )
                continue

            if action.movement_id not in applied_movements:
                self._apply_movement(action)
                applied_movements.add(action.movement_id)
            outcomes[item.decision_id] = ExecutionOutcome(
                decision_id=item.decision_id,
                agent_id=item.agent_id,
                status="executed",
                executed_action="evacuate",
                resource_allocations={
                    "vehicle_id": action.vehicle_id,
                    "route_id": action.route_id,
                },
                state_delta={"location": "controlled_safe_zone"},
            )
        return outcomes

    def snapshot(self) -> dict:
        return {
            "step": self.current_step,
            "hazard_distance_m": self.distance_to_fire("home"),
            "routes": self.route_snapshot(),
            "n_evacuated_residents": len(self.evacuated),
            "n_safe_dependents": len(self.safe_dependents),
            "coordinated_movements": self.coordinated_movements,
            "uncoordinated_movements": self.uncoordinated_movements,
            "rejections": dict(sorted(self.rejections.items())),
            "route_closures": list(self.route_closures),
        }

    def _household_movements(
        self,
        household: Household,
        envelopes: list[IntentEnvelope],
        actions: dict[str, Any],
        *,
        clock: Clock,
        run_seed: int,
    ) -> list[_Movement]:
        by_signature: dict[tuple, list[IntentEnvelope]] = {}
        for envelope in envelopes:
            decision = envelope.decision
            signature = (
                decision.route_id,
                decision.vehicle_id,
                decision.depart_step,
            )
            by_signature.setdefault(signature, []).append(envelope)

        for signature, matching in by_signature.items():
            route_id, vehicle_id, depart_step = signature
            if (
                route_id
                and vehicle_id
                and depart_step is not None
                and set(item.agent_id for item in matching)
                == set(household.decision_member_ids)
                and household.compatible_commitment(
                    route_id=route_id,
                    vehicle_id=vehicle_id,
                    depart_step=depart_step,
                )
                is not None
            ):
                if depart_step > clock.t:
                    for item in matching:
                        actions[item.decision_id] = CarrRejected(
                            "evacuate", "departure scheduled for a future step"
                        )
                    return []
                dependents = tuple(household.dependent_ids)
                vehicle = household.vehicles.get(vehicle_id)
                if vehicle is None:
                    for item in matching:
                        actions[item.decision_id] = CarrRejected(
                            "evacuate", "unknown household vehicle"
                        )
                    return []
                if vehicle.capacity < len(household.member_ids):
                    for item in matching:
                        actions[item.decision_id] = CarrRejected(
                            "evacuate", "vehicle capacity insufficient for household"
                        )
                    return []
                return [
                    _Movement(
                        id=f"{household.id}:{vehicle_id}:{clock.t}:coordinated",
                        household=household,
                        route_id=route_id,
                        vehicle_id=vehicle_id,
                        envelopes=matching,
                        dependent_ids=dependents,
                        coordinated=True,
                    )
                ]

        requests = []
        envelopes_by_id = {}
        for envelope in envelopes:
            decision = envelope.decision
            if not decision.route_id or not decision.vehicle_id:
                actions[envelope.decision_id] = CarrRejected(
                    "evacuate", "evacuation intent lacks executable route or vehicle"
                )
                continue
            if decision.depart_step is not None and decision.depart_step > clock.t:
                actions[envelope.decision_id] = CarrRejected(
                    "evacuate", "departure scheduled for a future step"
                )
                continue
            requests.append(
                VehicleRequest(
                    decision_id=envelope.decision_id,
                    agent_id=envelope.agent_id,
                    vehicle_id=decision.vehicle_id,
                    request_step=clock.t,
                    priority=10
                    if set(decision.accompany_dependents)
                    == set(household.dependent_ids)
                    else 0,
                )
            )
            envelopes_by_id[envelope.decision_id] = envelope
        if not requests:
            return []
        allocations = household.resolve_vehicle_requests(
            requests,
            run_seed=run_seed,
            step=clock.t,
        )
        movements = []
        for decision_id, allocation in allocations.items():
            envelope = envelopes_by_id[decision_id]
            if allocation.status == "rejected":
                actions[decision_id] = CarrRejected(
                    "evacuate", allocation.reason or "vehicle resource conflict"
                )
                continue
            dependents = tuple(envelope.decision.accompany_dependents)
            if set(dependents) != set(household.dependent_ids):
                actions[decision_id] = CarrRejected(
                    "evacuate", "dependent member would be left behind"
                )
                continue
            vehicle = household.vehicles[allocation.vehicle_id]
            if vehicle.capacity < 1 + len(dependents):
                actions[decision_id] = CarrRejected(
                    "evacuate", "vehicle capacity insufficient for caregiver party"
                )
                continue
            movements.append(
                _Movement(
                    id=f"{household.id}:{allocation.vehicle_id}:{clock.t}:{decision_id}",
                    household=household,
                    route_id=envelope.decision.route_id,
                    vehicle_id=allocation.vehicle_id,
                    envelopes=[envelope],
                    dependent_ids=dependents,
                    coordinated=False,
                )
            )
        return movements

    def _reject_movement(
        self,
        movement: _Movement,
        actions: dict[str, Any],
        reason: str,
    ) -> None:
        for envelope in movement.envelopes:
            actions[envelope.decision_id] = CarrRejected("evacuate", reason)

    def _apply_movement(self, action: CarrMove) -> None:
        household = self.households[action.household_id]
        vehicle = household.vehicles[action.vehicle_id]
        vehicle.reserved_by = action.member_ids[0]
        vehicle.occupied_by.update(action.member_ids)
        vehicle.occupied_by.update(action.dependent_ids)
        for member_id in action.member_ids:
            agent = self.agents[member_id]
            agent.state.location = "controlled_safe_zone"
            self.evacuated.add(member_id)
        for dependent_id in action.dependent_ids:
            dependent = household.dependent_states.get(dependent_id)
            if dependent is not None:
                dependent.location = "controlled_safe_zone"
                dependent.safe = True
                dependent.in_transit = False
            self.safe_dependents.add(dependent_id)
        if action.coordinated:
            self.coordinated_movements += 1
        else:
            self.uncoordinated_movements += 1
