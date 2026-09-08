"""Carr E1 v2 interaction: separated household DM and community delivery."""

from __future__ import annotations

from typing import Any

import networkx as nx

from ds.agents.carr_empirical_v2 import (
    CarrEmpiricalResidentV2,
    OfficialInformationReceipt,
)
from ds.households.state import (
    CareRequirement,
    DepartureParty,
    HouseholdCommitmentV2,
)
from ds.kernel.clock import Clock
from ds.kernel.rng import stream_rng


class CarrEmpiricalInteractionV2:
    """Message lifecycle: sent -> delivered -> processed -> accepted/rejected."""

    def __init__(
        self,
        *,
        run_seed: int,
        household_dm_probability: float,
        community_message_probability: float,
        social_graph: nx.Graph,
        residents: dict[str, CarrEmpiricalResidentV2],
        households: dict[str, Any],
        decision_capable: dict[str, bool],
        care_requirements: dict[str, CareRequirement],
    ):
        self.run_seed = run_seed
        self.household_dm_probability = household_dm_probability
        self.community_message_probability = community_message_probability
        self.graph = social_graph
        self.residents = residents
        self.households = households
        self.decision_capable = decision_capable
        self.care_requirements = care_requirements
        self.messages: dict[str, dict[str, Any]] = {}
        self.receipts: list[OfficialInformationReceipt] = []
        self._receipts_by_id: dict[str, OfficialInformationReceipt] = {}
        self._step = 0
        self.commitment_notifications: list[dict] = []

    # ---- official orders -------------------------------------------------- #
    def deliver_warnings(
        self, events: list, agents: list, clock: Clock, run_seed: int
    ) -> None:
        self._step = clock.t
        for event in events:
            if event.kind != "official_order":
                continue
            covered = [
                agent
                for agent in agents
                if event.recipient_covers(agent)
            ]
            for agent in covered:
                if not hasattr(agent, "deliver_receipt"):
                    continue
                receipt = OfficialInformationReceipt(
                    receipt_id=(
                        f"receipt_{event.event_id}_{agent.id}"
                    ),
                    resident_id=agent.id,
                    source_event_id=event.event_id,
                    severity=event.severity,
                    channel="official_direct",
                    issued_step=event.issued_step,
                    delivered_step=clock.t,
                    processed_step=None,
                )
                agent.deliver_receipt(receipt)
                self.receipts.append(receipt)
                self._receipts_by_id[receipt.receipt_id] = receipt

    # ---- emission --------------------------------------------------------- #
    def emit(self, agent: Any, decision: Any, clock: Clock) -> None:
        for index, message in enumerate(decision.messages):
            message_id = f"m{clock.t}:{agent.id}:{index}"
            payload = dict(message.payload or {})
            source_event_id = payload.get("source_event_id")
            source_message_id = payload.get("source_message_id")
            if payload.get("forward_official"):
                # Forwarded official info must reference a source the sender
                # actually holds; otherwise it stays unverified rumor.
                owned = any(
                    memory.get("source_event_id") == source_event_id
                    for memory in agent.memories
                )
                if not owned:
                    payload["verified"] = False
                    payload["source_event_id"] = None
                    payload["unverified_rumor"] = True
            if message.to in ("household", "family"):
                channel = "household_dm"
                recipients = [
                    member_id
                    for member_id in self.households[agent.household_id].decision_member_ids
                    if member_id != agent.id
                ]
            else:
                channel = "community"
                recipients = [
                    neighbor
                    for neighbor in (
                        [] if self.graph is None else self.graph.neighbors(agent.id)
                    )
                    if neighbor != agent.id
                ]
            record = {
                "message_id": message_id,
                "sender_id": agent.id,
                "recipient_ids": recipients,
                "kind": message.kind,
                "content": message.content,
                "channel": channel,
                "payload": payload,
                "issued_step": clock.t,
                "delivered_step": None,
                "processed_step": None,
                "status": "sent",
                "disposition": None,
                "recipient_states": {r: {"delivered_step": None,
                    "processed_step": None, "disposition": None, "response_step": None}
                    for r in recipients},
            }
            self.messages[message_id] = record
            if (
                message.to in ("household", "family")
                and not recipients
                and message.kind == "proposal"
            ):
                self._accept_party_proposal(
                    agent, record, clock.t, self_accept=True
                )

    # ---- processing ------------------------------------------------------- #
    def process(self, agent: Any, decision: Any, clock: Clock) -> None:
        processed = agent.process_inbox(step=clock.t)
        for item in processed:
            message_id = item.get("message_id")
            if message_id and message_id in self.messages:
                self.messages[message_id]["processed_step"] = clock.t
                self.messages[message_id]["status"] = "processed"
                delivery = self.messages[message_id]["recipient_states"].get(agent.id)
                if delivery is not None:
                    delivery["processed_step"] = clock.t
        for response in decision.message_responses:
            message = self.messages.get(response.message_id)
            if message is None:
                continue
            delivery = message.get("recipient_states", {}).get(agent.id)
            if delivery is None or delivery["processed_step"] is None:
                continue
            delivery.update(disposition=response.disposition, response_step=clock.t)
            message["disposition"] = response.disposition
            message["status"] = (
                "accepted" if response.disposition == "accepted" else "rejected"
            )
            if (
                response.disposition == "accepted"
                and message["payload"].get("protocol_version") == "e1_party_v2"
            ):
                self._accept_party_proposal(agent, message, clock.t)

    def _accept_party_proposal(
        self,
        agent: Any,
        message: dict,
        step: int,
        *,
        self_accept: bool = False,
    ) -> None:
        household = self.households[agent.household_id]
        if message.get("acceptance", {}).get("accepted"):
            return
        payload = message["payload"]
        required = {
            "traveler_ids",
            "vehicle_id",
            "route_id",
            "depart_step",
        }
        if not required <= set(payload):
            message["acceptance"] = {
                "accepted": False,
                "commitment_id": None,
                "reason_code": "missing_party_fields",
                "missing": sorted(required - set(payload)),
            }
            return
        travelers = frozenset(
            str(member) for member in payload["traveler_ids"]
        )
        raw_caregivers = payload.get("caregiver_by_member", {})
        caregiver_by_member = tuple(
            (
                str(member),
                str(value[0] if isinstance(value, list) else value),
            )
            for member, value in raw_caregivers.items()
        )
        party = DepartureParty(
            traveler_ids=travelers,
            accompanying_member_ids=(
                frozenset(
                    str(member)
                    for member in payload.get("accompanying_member_ids", [])
                )
                - travelers
            ),
            caregiver_by_member=caregiver_by_member,
            vehicle_id=payload["vehicle_id"],
            route_id=payload["route_id"],
            depart_step=int(payload["depart_step"]),
        )
        commitment = HouseholdCommitmentV2(
            id=f"commit_{step}_{message['message_id']}",
            protocol_version="e1_party_v2",
            party=party,
            accepted_by=frozenset({message["sender_id"]}) | frozenset(
                member for member, state in message.get("recipient_states", {}).items()
                if state["disposition"] == "accepted" and state["processed_step"] is not None),
            created_step=step,
        )
        result = household.try_accept_commitment_v2(
            commitment=commitment,
            decision_capable=self.decision_capable,
            care_requirements=self.care_requirements,
            earliest_depart_step=step + 1,
            party_origin=("home", household.id),
        )
        message["acceptance"] = {
            "accepted": result.accepted,
            "commitment_id": result.commitment_id,
            "reason_code": result.reason_code,
        }
        if result.accepted:
            # Explicit protocol acknowledgement, only to the consenting travelers.
            for member_id in sorted(party.traveler_ids & commitment.accepted_by):
                notice = {"commitment_id": commitment.id,
                    "source_message_id": message["message_id"],
                    "recipient_id": member_id, "delivered_step": step,
                    "depart_step": party.depart_step, "route_id": party.route_id,
                    "vehicle_id": party.vehicle_id,
                    "traveler_ids": sorted(party.traveler_ids)}
                self.residents[member_id].my_commitments.append(dict(notice))
                self.commitment_notifications.append(notice)
            if self_accept:
                message["status"] = "accepted"
                message["disposition"] = "accepted"
                message["delivered_step"] = step
                message["processed_step"] = step
                message["acceptance"] = {
                    "accepted": True,
                    "commitment_id": commitment.id,
                    "reason_code": None,
                    "self_accept": True,
                }

    # ---- delivery --------------------------------------------------------- #
    def deliver(self, clock: Clock) -> None:
        for message in self.messages.values():
            for recipient_id in message["recipient_ids"]:
                recipient_state = message["recipient_states"][recipient_id]
                if recipient_state["delivered_step"] is not None:
                    continue
                recipient = self.residents.get(recipient_id)
                if recipient is None:
                    continue
                probability = (
                    self.household_dm_probability
                    if message["channel"] == "household_dm"
                    else self.community_message_probability
                )
                rng = stream_rng(
                    self.run_seed,
                    "e1_message_delivery",
                    entity_id=message["message_id"],
                    step=clock.t,
                    draw_index=hash(recipient_id) % 1000,
                )
                if rng.random() >= probability:
                    continue
                recipient_state["delivered_step"] = clock.t
                recipient.deliver_message({**message, "delivered_step": clock.t})
                message["delivered_step"] = message["delivered_step"] or clock.t
                message["status"] = "delivered"

    def snapshot(self) -> dict:
        current_receipts = []
        for receipt in self.receipts:
            resident = self.residents.get(receipt.resident_id)
            updated = (
                resident._receipts.get(receipt.receipt_id)
                if resident is not None
                else None
            )
            current_receipts.append(
                (updated or receipt).__dict__
            )
        return {
            "messages": self.messages,
            "receipts": current_receipts,
            "commitment_notifications": self.commitment_notifications,
        }
