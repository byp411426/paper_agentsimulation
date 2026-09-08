"""Carr E1 v2 generative resident with private cognition (W5 contract).

The resident keeps inbox / memory / perceived_routes / my_commitments /
recent_execution_feedback private.  Prompts never read the real world route
state; route beliefs change only through sourced messages, execution
rejections, or controlled local observations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from ds.agents.decide import E1ResidentDecision, OutMsg, ResidentDecision
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
        self.perceived_routes: dict[str, dict[str, Any]] = dict(
            initial_routes
            or {
                "primary": {"open": True, "name": "primary"},
                "alternate": {"open": True, "name": "alternate"},
            }
        )
        self.my_commitments: list[dict[str, Any]] = []
        self.recent_execution_feedback: list[dict[str, Any]] = []
        self._receipts: dict[str, OfficialInformationReceipt] = {}
        self._processed_message_ids: set[str] = set()

    # ---- receipt lifecycle ------------------------------------------------ #
    def deliver_receipt(self, receipt: OfficialInformationReceipt) -> None:
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
        item = dict(message)
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
        if not self.static.decision_capable:
            return False
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
        hazard = world.hazard_distance_for(self.household_id, step)
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
            "hazard_distance_m": hazard,
            "perceived_routes": self.perceived_routes,
            "shared_resource_reservations": world.visible_reservations(
                self.household_id, viewer_id=self.id
            ),
        }

    def _prompt_payload(self, *, world: Any, step: int) -> dict[str, Any]:
        latent_traits = {
            key: value
            for key, value in self.profile.get("latent_traits", {}).items()
            if not key.endswith("_band")
        }
        return {
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
                "current_plan": None,
                "my_accepted_commitments": self.my_commitments,
                "recent_execution_feedback": self.recent_execution_feedback,
            },
        }

    async def decide(
        self, *, events, world: Any, gateway: LLMGateway, step: int
    ) -> E1ResidentDecision:
        payload = self._prompt_payload(world=world, step=step)
        system = (
            "You are a wildfire-zone resident in a shared household. "
            "Decide one action for this step: stay, prepare, evacuate, "
            "seek_help, or offer_help. When evacuating you MUST pick a "
            "route_id and vehicle_id from the provided household profile and "
            "a depart_step at or after the current step, and send a household "
            "proposal via the messages array exactly as defined in the JSON "
            "schema below (kind=proposal, to=household). When you receive a "
            "feasible proposal, respond accepted. Output ONLY valid JSON "
            "matching the schema. Treat 'unverified' information without a "
            "source as rumor.\n\nJSON SCHEMA:\n"
            + json.dumps(
                E1ResidentDecision.model_json_schema(),
                ensure_ascii=False,
                default=str,
            )
        )
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    payload, ensure_ascii=False, default=str
                ),
            },
        ]
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
        return self._normalize_proposal(decision, step=step)

    def _normalize_proposal(
        self, decision: E1ResidentDecision, *, step: int
    ) -> E1ResidentDecision:
        """Normalize depart steps on the decision and any proposal payloads."""
        depart_step = decision.depart_step
        if depart_step is not None:
            depart_step = max(int(depart_step), step + 1)
        messages = []
        for message in decision.messages:
            payload = dict(message.payload or {})
            payload.setdefault("protocol_version", "e1_party_v2")
            payload.setdefault("traveler_ids", [self.id])
            payload.setdefault("vehicle_id", decision.vehicle_id)
            payload.setdefault("route_id", decision.route_id)
            payload.setdefault("accompanying_member_ids", [])
            payload.setdefault("caregiver_by_member", {})
            payload_depart = payload.get("depart_step")
            if isinstance(payload_depart, (int, float)):
                payload["depart_step"] = max(int(payload_depart), step + 1)
            else:
                payload["depart_step"] = depart_step or step + 1
            messages.append(
                message.model_copy(update={"payload": payload})
            )
        return decision.model_copy(
            update={"messages": messages, "depart_step": depart_step}
        )

    def rule_fallback(self, *, step: int = -1) -> ResidentDecision:
        mandatory = any(
            memory.get("kind") == "official_receipt"
            and memory.get("severity") == "mandatory"
            for memory in self.memories
        )
        if mandatory:
            return ResidentDecision(
                assessment="mandatory order received",
                action="evacuate",
                route_id="primary",
                vehicle_id=next(iter(self.vehicles), None),
                depart_step=max(step, 1),
            )
        return ResidentDecision(assessment="no urgent signal", action="stay")

    # ---- execution feedback ------------------------------------------------ #
    def commit_execution(self, decision: ResidentDecision, outcome: Any, *, step: int) -> None:
        status = getattr(outcome, "status", "unknown")
        reason = getattr(outcome, "reason", None)
        executed = getattr(outcome, "executed_action", None)
        self.recent_execution_feedback.append(
            {
                "step": step,
                "status": status,
                "executed_action": executed,
                "reason": reason,
            }
        )
        if status == "executed" and executed == "evacuate":
            self.state.evacuating = True
            self.state.evac_step = step
        if (
            reason
            and "closed" in str(reason)
            and decision is not None
            and decision.route_id in self.perceived_routes
        ):
            self.perceived_routes[decision.route_id]["open"] = False
        if status == "rejected" and reason:
            self.recent_execution_feedback[-1]["last_failure"] = reason
        self.recent_execution_feedback = self.recent_execution_feedback[-5:]

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "household_id": self.household_id,
            "inbox": self.inbox,
            "memories": self.memories,
            "perceived_routes": self.perceived_routes,
            "my_commitments": self.my_commitments,
            "recent_execution_feedback": self.recent_execution_feedback,
            "receipts": [
                receipt.__dict__ for receipt in self._receipts.values()
            ],
        }
