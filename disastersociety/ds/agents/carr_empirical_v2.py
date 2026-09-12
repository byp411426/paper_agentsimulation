"""Carr E1 v2 generative resident with private cognition (W5 contract).

The resident keeps inbox / memory / perceived_routes / my_commitments /
recent_execution_feedback private.  Prompts never read the real world route
state; route beliefs change only through sourced messages, execution
rejections, or controlled local observations.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal

from ds.agents.decide import OutMsg, ResidentDecision
from ds.agents.e1_contracts import E1ActionRequest as E1ResidentDecision
from ds.agents.state import Resident, StaticAttrs
from ds.kernel.rng import stream_seed
from ds.llm.gateway import LLMGateway


@dataclass(frozen=True)
class OfficialInformationReceipt:
    receipt_id: str
    resident_id: str
    source_event_id: str
    severity: Literal["voluntary", "mandatory"]
    channel: str
    issued_step: int
    delivered_step: int
    processed_step: int | None


class CarrEmpiricalResidentV2(Resident):
    """E1 v2 resident: one generative unit per decision-capable adult."""

    def __init__(
        self,
        *,
        agent_id: str,
        household_id: str,
        profile: dict[str, Any],
        vehicles: dict[str, Any],
        initial_routes: dict[str, dict[str, Any]] | None = None,
    ):
        age = int(profile.get("age", 40))
        static = StaticAttrs(
            age=age,
            decision_capable=bool(profile.get("decision_capable", age >= 18)),
            decision_policy="generative" if age >= 18 else "dependent",
            household_id=household_id,
            home=("home", household_id),
            functional_limitations=profile.get("functional_limitations", {}),
        )
        super().__init__(
            agent_id,
            static=static,
            persona=(
                f"a {age}-year-old resident of household {household_id}"
            ),
        )
        self.household_id = household_id
        self.profile = profile
        self.vehicles = vehicles
        self.inbox: list[dict[str, Any]] = []
        self.memories: list[dict[str, Any]] = []
        self.perceived_routes: dict[str, dict[str, Any]] = deepcopy(
            initial_routes
            or {
                "primary": {"open": True, "name": "primary"},
                "alternate": {"open": True, "name": "alternate"},
            }
        )
        self.current_plan: dict[str, Any] | None = None
        self.plan_history: list[dict[str, Any]] = []
        self.my_commitments: list[dict[str, Any]] = []
        self.recent_execution_feedback: list[dict[str, Any]] = []
        self._receipts: dict[str, OfficialInformationReceipt] = {}
        self._processed_message_ids: set[str] = set()
        self._delivered_message_ids: set[str] = set()
        self._decision_inbox_step: int | None = None
        self._decision_inbox_keys: set[tuple] = set()

    # ---- receipt lifecycle ------------------------------------------------ #
    def deliver_receipt(self, receipt: OfficialInformationReceipt) -> None:
        if receipt.resident_id != self.id:
            raise ValueError("official receipt addressed to another resident")
        if receipt.receipt_id in self._receipts:
            return
        self._receipts[receipt.receipt_id] = receipt
        self.inbox.append(
            {
                "kind": "official_receipt",
                "receipt_id": receipt.receipt_id,
                "source_event_id": receipt.source_event_id,
                "severity": receipt.severity,
                "channel": receipt.channel,
                "issued_step": receipt.issued_step,
                "delivered_step": receipt.delivered_step,
                "processed_step": None,
            }
        )

    def deliver_message(self, message: dict[str, Any]) -> None:
        message_id = message.get("message_id")
        if message_id and message_id in self._delivered_message_ids:
            return
        item = deepcopy(message)
        if message_id:
            self._delivered_message_ids.add(message_id)
        item["message_kind"] = item.get("kind")
        item["kind"] = "message"
        item["delivered_step"] = item.get("delivered_step")
        item["processed_step"] = None
        self.inbox.append(item)

    def process_inbox(self, *, step: int) -> list[dict[str, Any]]:
        """Move delivered items into memory and stamp processing time."""
        processed: list[dict[str, Any]] = []
        remaining: list[dict[str, Any]] = []
        for item in self.inbox:
            key = (item.get("kind"), item.get("receipt_id") or item.get("message_id"))
            if self._decision_inbox_step == step and key not in self._decision_inbox_keys:
                # Notices delivered during arbitration were not in this decision's input.
                remaining.append(item)
                continue
            if item["kind"] == "official_receipt":
                receipt = self._receipts[item["receipt_id"]]
                self._receipts[item["receipt_id"]] = OfficialInformationReceipt(
                    **{
                        **receipt.__dict__,
                        "processed_step": step,
                    }
                )
                item["processed_step"] = step
                self.memories.append(
                    {
                        "kind": "official_receipt",
                        "severity": item["severity"],
                        "source_event_id": item["source_event_id"],
                        "processed_step": step,
                    }
                )
                processed.append(item)
            elif item["kind"] == "message":
                item["processed_step"] = step
                self.memories.append(
                    {
                        "kind": "message",
                        "message_id": item.get("message_id"),
                        "content": item.get("content"),
                        "source_event_id": item.get("source_event_id"),
                        "source_message_id": item.get("source_message_id"),
                        "processed_step": step,
                    }
                )
                self._processed_message_ids.add(item.get("message_id", ""))
                processed.append(item)
            else:
                remaining.append(item)
        self.inbox = remaining
        return processed

    # ---- wake gate -------------------------------------------------------- #
    def should_wake(self, *, events: list, world: Any, step: int) -> bool:
        if self.state.evacuating or world.member_locations.get(self.id) == world.safe_zone:
            return False
        if not self.static.decision_capable:
            return False
        if self.current_plan and self.current_plan['status'] == 'active':
            if any(x['due_step'] <= step for x in self.current_plan['steps']):
                return True
        if self.inbox or self.recent_execution_feedback:
            return True
        if world.party_due_for(self.id, step):
            return True
        try:
            if world.hazard_distance_for(self.household_id, step) < 3000:
                return True
        except Exception:
            pass
        return False

    # ---- prompt assembly (private cognition only) -------------------------- #
    def _observed_now(self, *, world: Any, step: int) -> dict[str, Any]:
        local = world.observe_resident(self.id, step)
        return {
            "inbox": [
                {
                    "kind": item["kind"],
                    "message_kind": item.get("message_kind"),
                    "message_id": item.get("message_id"),
                    "severity": item.get("severity"),
                    "content": item.get("content"),
                    "payload": item.get("payload"),
                    "source_event_id": item.get("source_event_id"),
                    "source_message_id": item.get("source_message_id"),
                    "channel": item.get("channel"),
                }
                for item in self.inbox
            ],
            "observation_id": local["observation_id"],
            "hazard_distance_m": local["content"]["hazard_distance_m"],
            "perceived_routes": deepcopy(self.perceived_routes),
            "shared_resource_reservations": local["content"]["shared_resource_reservations"],
        }

    def _prompt_payload(self, *, world: Any, step: int) -> dict[str, Any]:
        household = world.households[self.household_id]
        latent_traits = {
            key: value
            for key, value in self.profile.get("latent_traits", {}).items()
            if not key.endswith("_band")
        }
        return {
            "current_step": step,
            "resident_id": self.id,
            "household_id": self.household_id,
            "current_location": world.member_locations.get(self.id),
            "new_proposal_earliest_depart_step": step + 2,
            "received_proposal_earliest_depart_step": step + 1,
            "own_commitment_statuses": world.commitment_statuses_for(self.id),
            "coordination_capabilities": {
                "version": "household_coordination_20260912",
                "scope": "within_household",
                "traveler_ids": sorted(household.decision_member_ids),
                "accompanying_member_ids": sorted(household.dependent_ids),
                "vehicle_ids": sorted(household.vehicles),
                "cross_household_transport": False,
                "return_pickup": False,
                "walking_departure": False,
                "safe_zone_residents_decide": False,
                "message_group_aliases": ["household", "family", "community", "neighbors"],
            },
            "resident_profile": {
                "static": self.profile.get("pums_static", {}),
                "functional_limitations": self.profile.get(
                    "functional_limitations", {}
                ),
                "needs_execution_assistance": self.profile.get(
                    "needs_execution_assistance", False
                ),
                "latent_traits": latent_traits,
            },
            "household_profile": {
                "members": [
                    {
                        "resident_id": member.get("resident_id"),
                        "age": member.get("age"),
                        "relationship": member.get("relationship"),
                        "location": member.get("location"),
                        "needs_execution_assistance": member.get(
                            "needs_execution_assistance", False
                        ),
                    }
                    for member in world.member_summaries(self.household_id)
                ],
                "vehicles": [
                    {
                        "id": vehicle["id"],
                        "capacity": vehicle["capacity"],
                        "location": vehicle["location"],
                    }
                    for vehicle in world.vehicle_summaries(self.household_id)
                ],
                "housing": world.housing_summary(self.household_id),
                "pets": world.pet_state(self.household_id),
                "livestock": world.livestock_state(self.household_id),
            },
            "observed_now": self._observed_now(world=world, step=step),
            "private_process": {
                "memories": self.memories[-12:],
                "current_plan": self.current_plan,
                "my_accepted_commitments": self.my_commitments,
                "recent_execution_feedback": self.recent_execution_feedback,
            },
        }

    @staticmethod
    def decision_system_prompt() -> str:
        return (
            "You are one resident making protective-action decisions with private memory and a persistent plan. "
            "Use only the supplied observations. Give a short assessment and JSON; do not invent roads or resources. "
            "You may stay, prepare, seek_help, offer_help, or evacuate. Staying is allowed. "
            "Set plan_update only to create or revise a 1-3 step plan; null preserves the existing plan. "
            "Do not return an empty plan object or steps:[]; use plan_update:null if no new plan is intended. "
            "To coordinate, use party_proposal with explicit traveler IDs, dependents, caregivers, route and vehicle. "
            "The coordination_capabilities field lists the supported household member roles and resources. "
            "traveler_ids contains only decision-making members of YOUR household, including yourself; "
            "non-decision members belong in accompanying_member_ids and need a listed accompanying caregiver. "
            "Any traveler explicitly requiring execution assistance also needs another participating caregiver; "
            "having decision capacity does not remove that assistance requirement. "
            "This world supports household vehicle departures, not cross-household pickup, walking, or return trips. "
            "After arrival at the safe zone a resident no longer makes decisions. "
            "Neighbors can exchange information and express requests/offers, but these expressions do not provide a transport service. "
            "Use a supplied message group alias or a known reachable resident ID, not invented broadcast aliases. "
            "For a NEW proposal, use new_proposal_earliest_depart_step or later. "
            "For an ALREADY RECEIVED proposal, use received_proposal_earliest_depart_step (current_step+1). "
            "Do not apply the NEW-proposal bound to accepting an existing proposal; it already spent one step in delivery. "
            "These are protocol timing bounds, not personal preparedness thresholds. "
            "While negotiating choose prepare or another non-departure action. Proposals do not reserve vehicles. "
            "Respond to received proposals through message_responses; accept only if you agree to that exact party. "
            "For a confirmed trip, evacuate at its due step using departure_mode=commitment and its commitment_id. "
            "For an explicitly independent trip, use departure_mode=solo; accompany_dependents lists exactly whom you take. "
            "Evacuate means leave NOW: depart_step must equal current_step. Future intentions belong in the plan. "
            "To postpone or change a confirmed group trip, cancel_commitment_ids and propose a new version; do not silently change it. "
            "Only physically executed actions change locations. seek_help/offer_help express requests/offers and do not themselves move anyone. "
            "Information messages use messages with kind=notice. Output JSON matching this schema:\n"
            + json.dumps(E1ResidentDecision.model_json_schema(), ensure_ascii=False)
        )

    async def decide(
        self, *, events, world: Any, gateway: LLMGateway, step: int
    ) -> E1ResidentDecision:
        self._decision_inbox_step = step
        self._decision_inbox_keys = {
            (item.get("kind"), item.get("receipt_id") or item.get("message_id"))
            for item in self.inbox
        }
        payload = self._prompt_payload(world=world, step=step)
        system = self.decision_system_prompt()
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    payload, ensure_ascii=False, default=str
                ),
            },
        ]
        audit_path = gateway.log_path.parent / "decision_inputs.jsonl"
        with audit_path.open("a") as handle:
            handle.write(json.dumps({"step": step, "resident_id": self.id,
                "payload": payload}, ensure_ascii=False, default=str) + "\n")
        seed = stream_seed(
            gateway.run_seed,
            "llm_decision",
            entity_id=self.id,
            step=step,
        )
        decision = await gateway.complete(
            step=step,
            agent_id=self.id,
            model=gateway.decision_model,
            messages=messages,
            schema=E1ResidentDecision,
            seed=seed,
            temperature=gateway.temperature,
        )
        decision = self._resolve_departure_reference(decision, payload=payload, gateway=gateway, step=step)
        return self._normalize_proposal(decision, step=step)

    def _resolve_departure_reference(self, decision, *, payload, gateway, step):
        """Resolve only omitted copies of fields from an explicitly cited known party.

        Never choose a party, consent, vehicle, route or time for the resident;
        preserve explicit conflicting arguments for environment rejection.
        """
        if decision.action != 'evacuate' or decision.departure_mode != 'commitment':
            return decision
        source = next((c for c in payload['own_commitment_statuses']
            if c['commitment_id'] == decision.commitment_id and c['status'] == 'accepted'), None)
        if source is None:
            return decision
        fill = {k: source[k] for k in ('vehicle_id', 'route_id', 'depart_step')
                if getattr(decision, k) is None}
        if not fill:
            return decision
        with (gateway.log_path.parent/'decision_reference_resolutions.jsonl').open('a') as handle:
            handle.write(json.dumps({'step':step, 'resident_id':self.id,
                'raw_request':decision.model_dump(), 'commitment_id':decision.commitment_id,
                'source':'decision_inputs.own_commitment_statuses', 'source_record':source,
                'resolved_fields':fill}, ensure_ascii=False, default=str)+'\n')
        return decision.model_copy(update=fill)

    def _normalize_proposal(
        self, decision: E1ResidentDecision, *, step: int
    ) -> E1ResidentDecision:
        """Serialize an explicit typed proposal; never invent travelers or shift times."""
        proposal = decision.party_proposal
        messages = list(decision.messages)
        if proposal is not None:
            payload = proposal.model_dump(exclude={'content'})
            payload['protocol_version'] = 'e1_party_v2'
            messages.append(OutMsg(to='household', kind='proposal',
                content=proposal.content, payload=payload))
        return decision.model_copy(update={'messages': messages})

    def rule_fallback(self, *, step: int = -1) -> ResidentDecision:
        return E1ResidentDecision(assessment='backend unavailable; no generative decision', action='stay')

    # ---- execution feedback ------------------------------------------------ #
    def commit_execution(self, decision: ResidentDecision, outcome: Any, *, step: int) -> None:
        from copy import deepcopy
        update = getattr(decision, 'plan_update', None)
        if update is not None:
            if self.current_plan is not None:
                self.plan_history.append({**deepcopy(self.current_plan), 'ended_step': step, 'end_reason': 'revised'})
            self.current_plan = {**update.model_dump(), 'created_step': step, 'status': 'active'}
        status = getattr(outcome, "status", "unknown")
        reason = getattr(outcome, "reason", None)
        requested = getattr(decision, "action", None)
        # Older outcome objects may put the requested action in executed_action.
        executed = getattr(outcome, "executed_action", None) if status == "executed" else None
        self.memories.append({"kind": "execution", "step": step, "status": status,
            "requested_action": requested, "action": executed, "reason": reason})
        self.recent_execution_feedback.append(
            {
                "step": step,
                "status": status,
                "requested_action": requested,
                "executed_action": executed,
                "reason": reason,
            }
        )
        if status == "executed" and executed == "evacuate":
            self.state.evacuating = True
            self.state.evac_step = step
            if self.current_plan:
                self.current_plan['status'] = 'completed'
                self.current_plan['completed_step'] = step
        if (
            reason
            and "closed" in str(reason)
            and decision is not None
            and decision.route_id in self.perceived_routes
        ):
            self.perceived_routes[decision.route_id]["open"] = False
        if self.current_plan and status == 'rejected':
            self.current_plan['last_failure'] = {'step': step, 'reason': reason}
        if status == "rejected" and reason:
            self.recent_execution_feedback[-1]["last_failure"] = reason
        self.recent_execution_feedback = self.recent_execution_feedback[-5:]

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "household_id": self.household_id,
            "evacuating": self.state.evacuating,
            "evac_step": self.state.evac_step,
            "inbox": self.inbox,
            "memories": self.memories,
            "perceived_routes": self.perceived_routes,
            "my_commitments": self.my_commitments,
            "current_plan": self.current_plan,
            "plan_history": self.plan_history,
            "recent_execution_feedback": self.recent_execution_feedback,
            "receipts": [
                receipt.__dict__ for receipt in self._receipts.values()
            ],
        }
