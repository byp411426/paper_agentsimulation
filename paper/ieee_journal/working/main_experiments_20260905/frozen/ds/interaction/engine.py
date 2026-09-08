"""Interaction engine (spec v2 §2.4).

Owns message queues and the warning-delivery model. Tracks, per agent, the channel
through which they FIRST heard about the emergency (official / family / neighbor /
social). Those shares may be evaluated only against an independent target; Carr's
current delivery calibration margin is not independent. Direct messages are
delivered at the end of their send step and therefore enter recipient cognition
on the next decision step; community messages add one further delivery step.
"""

from __future__ import annotations

from typing import Any

from ds.households import HouseholdCommitment
from ds.interaction.delivery import DeliveryModel
from ds.interaction.messages import Message, MessageReceipt
from ds.kernel.clock import Clock
from ds.kernel.rng import stream_seed


class InteractionEngine:
    def __init__(
        self,
        agents_by_id: dict[str, Any],
        delivery: DeliveryModel | None = None,
        *,
        households_by_id: dict[str, Any] | None = None,
        social_enabled: bool = True,
        run_seed: int = 0,
        message_delivery_probability: float = 1.0,
        dm_delivery_probability: float | None = None,
        community_delivery_probability: float | None = None,
    ):
        if not 0.0 <= message_delivery_probability <= 1.0:
            raise ValueError(
                "message delivery probability must be within [0, 1]"
            )
        self.agents = agents_by_id
        self.delivery = delivery or DeliveryModel()
        self.households = households_by_id or {}
        self.social_enabled = social_enabled
        self.run_seed = run_seed
        self.message_delivery_probability = message_delivery_probability
        self.dm_delivery_probability = (
            message_delivery_probability
            if dm_delivery_probability is None
            else dm_delivery_probability
        )
        self.community_delivery_probability = (
            message_delivery_probability
            if community_delivery_probability is None
            else community_delivery_probability
        )
        for channel, probability in (
            ("dm", self.dm_delivery_probability),
            ("community", self.community_delivery_probability),
        ):
            if not 0.0 <= probability <= 1.0:
                raise ValueError(
                    f"{channel} delivery probability must be within [0, 1]"
                )
        self.pending: list[Message] = []          # queued for future delivery
        self.first_heard: dict[str, str] = {}      # agent_id -> channel
        self.msg_count = 0
        self._last_delivered = 0
        self._last_dropped = 0
        self.sent_by_channel: dict[str, int] = {}
        self.delivered_by_channel: dict[str, int] = {}
        self.dropped_by_channel: dict[str, int] = {}
        self.receipts: dict[str, MessageReceipt] = {}
        self.invalid_proposal_attempts = 0
        self.invalid_proposal_reasons: dict[str, int] = {}
        self.invalid_acceptance_attempts = 0
        self.invalid_acceptance_reasons: dict[str, int] = {}

    # ① official warnings, probabilistic reception ------------------------- #
    def deliver_warnings(self, events: list, agents: list, clock: Clock,
                         run_seed: int) -> None:
        warn_events = [e for e in events if _is_warning(e)]
        if not warn_events:
            return
        for a in sorted(agents, key=lambda x: x.id):
            if not any(_covers(e, a) for e in warn_events):
                continue
            if self.delivery.delivers(a.id, run_seed, clock.t, clock.sim_minutes):
                a.state.warned = True
                if a.state.warned_step < 0:
                    a.state.warned_step = clock.t
                a.inbox.append({"channel": "official",
                                "content": _warn_text(warn_events)})
                if _mechanism_enabled(a, "memory"):
                    a.memory.write_text(
                        clock.t, _warn_text(warn_events), kind="warning"
                    )
                self.first_heard.setdefault(a.id, "official")

    # ② agents emit messages ----------------------------------------------- #
    def emit(self, agent: Any, decision: Any, clock: Clock) -> None:
        if not self.social_enabled:
            return
        for om in getattr(decision, "messages", []) or []:
            channel = "dm" if om.to not in ("neighbors", "community") else "community"
            if om.kind == "proposal":
                reason = _proposal_payload_error(
                    om.payload,
                    earliest_depart_step=clock.t + 1,
                )
                if reason is not None:
                    self.invalid_proposal_attempts += 1
                    self.invalid_proposal_reasons[reason] = (
                        self.invalid_proposal_reasons.get(reason, 0) + 1
                    )
                    continue
            deliver_step = clock.t if channel == "dm" else clock.t + 1
            message_id = f"m{self.msg_count + 1:08d}"
            self.pending.append(Message(
                message_id=message_id,
                sender=agent.id, channel=channel, kind=om.kind, content=om.content,
                payload=om.payload,
                sent_step=clock.t, deliver_step=deliver_step, recipients=om.to,
            ))
            self.msg_count += 1
            self.sent_by_channel[channel] = (
                self.sent_by_channel.get(channel, 0) + 1
            )
            hook = getattr(agent, "record_emitted_message", None)
            if hook is not None:
                hook(self.pending[-1])

    # ③ deliver due messages ----------------------------------------------- #
    def deliver(self, clock: Clock) -> None:
        if not self.social_enabled:
            return
        still: list[Message] = []
        for m in self.pending:
            if m.deliver_step <= clock.t:
                self._route(m)
            else:
                still.append(m)
        self.pending = still

    def _route(self, m: Message) -> None:
        targets = self._resolve(m)
        src_channel = "neighbor" if m.channel == "community" else "family"
        for tid in targets:
            a = self.agents.get(tid)
            if a is None or tid == m.sender:
                continue
            draw = stream_seed(
                self.run_seed,
                "network_delivery",
                entity_id=f"{m.message_id}:{m.sender}:{tid}",
                step=m.deliver_step,
            ) / (2**32)
            delivery_probability = (
                self.dm_delivery_probability
                if m.channel == "dm"
                else self.community_delivery_probability
            )
            if draw >= delivery_probability:
                self._last_dropped += 1
                self.dropped_by_channel[m.channel] = (
                    self.dropped_by_channel.get(m.channel, 0) + 1
                )
                continue
            receipt_id = f"{m.message_id}:{tid}"
            receipt = MessageReceipt(
                receipt_id=receipt_id,
                message_id=m.message_id,
                sender=m.sender,
                recipient=tid,
                kind=m.kind,
                content=m.content,
                payload=m.payload,
                sent_step=m.sent_step,
                delivered_step=m.deliver_step,
            )
            self.receipts[receipt_id] = receipt
            a.inbox.append({
                "message_id": m.message_id,
                "receipt_id": receipt_id,
                "sender": m.sender,
                "channel": m.channel,
                "kind": m.kind,
                "content": m.content,
                "payload": m.payload,
            })
            self.first_heard.setdefault(tid, src_channel)
            self._last_delivered += 1
            self.delivered_by_channel[m.channel] = (
                self.delivered_by_channel.get(m.channel, 0) + 1
            )

    def process(self, agent: Any, decision: Any, clock: Clock) -> None:
        """Record that delivered messages entered cognition this step."""
        if not self.social_enabled:
            agent.inbox.clear()
            return
        responses = {
            response.message_id: response
            for response in getattr(decision, "message_responses", []) or []
        }
        for inbox_item in list(getattr(agent, "inbox", [])):
            receipt_id = inbox_item.get("receipt_id")
            if receipt_id is None or receipt_id not in self.receipts:
                continue
            receipt = self.receipts[receipt_id]
            receipt.status = "processed"
            receipt.processed_step = clock.t
            response = responses.get(receipt.message_id)
            if response is not None:
                receipt.disposition_step = clock.t
                receipt.disposition_reason = response.reason
                if response.disposition == "accepted" and receipt.kind == "proposal":
                    reason = self._accept_household_commitment(agent, receipt, clock)
                    if reason is None:
                        receipt.status = "accepted"
                    else:
                        receipt.status = "rejected"
                        receipt.disposition_reason = reason
                        self.invalid_acceptance_attempts += 1
                        self.invalid_acceptance_reasons[reason] = (
                            self.invalid_acceptance_reasons.get(reason, 0) + 1
                        )
                else:
                    receipt.status = response.disposition
            if _mechanism_enabled(agent, "memory"):
                agent.memory.write_text(
                    clock.t, receipt.content, kind="message"
                )
        agent.inbox.clear()

    def _resolve(self, m: Message) -> list[str]:
        if m.recipients in ("neighbors", "community", "all"):
            return sorted(self.agents.keys())
        if isinstance(m.recipients, (list, tuple, set)):
            return sorted(m.recipients)
        return [m.recipients]  # single id

    def snapshot(self) -> dict:
        return {
            "social_enabled": self.social_enabled,
            "pending": len(self.pending),
            "msg_count": self.msg_count,
            "delivered": self._last_delivered,
            "dropped": self._last_dropped,
            "sent_by_channel": dict(sorted(self.sent_by_channel.items())),
            "delivered_by_channel": dict(
                sorted(self.delivered_by_channel.items())
            ),
            "dropped_by_channel": dict(
                sorted(self.dropped_by_channel.items())
            ),
            "message_delivery_probability": (
                self.message_delivery_probability
            ),
            "dm_delivery_probability": self.dm_delivery_probability,
            "community_delivery_probability": (
                self.community_delivery_probability
            ),
            "invalid_proposal_attempts": self.invalid_proposal_attempts,
            "invalid_proposal_reasons": dict(
                sorted(self.invalid_proposal_reasons.items())
            ),
            "invalid_acceptance_attempts": self.invalid_acceptance_attempts,
            "invalid_acceptance_reasons": dict(
                sorted(self.invalid_acceptance_reasons.items())
            ),
            "receipt_states": _counts(
                receipt.status for receipt in self.receipts.values()
            ),
            "first_heard_counts": _counts(self.first_heard.values()),
        }

    def _accept_household_commitment(
        self,
        agent: Any,
        receipt: MessageReceipt,
        clock: Clock,
    ) -> str | None:
        household_id = getattr(getattr(agent, "static", None), "household_id", "")
        household = self.households.get(household_id)
        if household is None:
            return "recipient household is unavailable"
        decision_members = set(household.decision_member_ids)
        if receipt.sender not in decision_members:
            return "proposal sender is not a decision household member"
        if receipt.recipient not in decision_members:
            return "proposal recipient is not a decision household member"
        reason = _proposal_payload_error(
            receipt.payload,
            earliest_depart_step=clock.t,
        )
        if reason is not None:
            return reason
        vehicle_id = receipt.payload["vehicle_id"]
        if vehicle_id not in household.vehicles:
            return "proposal references an unknown household vehicle"
        household.accept_commitment(
            HouseholdCommitment(
                id=f"commitment:{receipt.message_id}",
                proposal=receipt.content,
                accepted_by=frozenset({receipt.sender, receipt.recipient}),
                created_step=clock.t,
                route_id=receipt.payload["route_id"],
                vehicle_id=vehicle_id,
                depart_step=receipt.payload["depart_step"],
            )
        )
        return None

    def channel_shares(self) -> dict[str, float]:
        """First-heard channel marginals for a declared calibration or evaluation use."""
        counts = _counts(self.first_heard.values())
        total = sum(counts.values()) or 1
        return {k: v / total for k, v in counts.items()}


def _is_warning(e: Any) -> bool:
    kind = getattr(e, "kind", None) or (e.get("kind") if isinstance(e, dict) else None)
    return kind in ("warning", "order")


def _covers(e: Any, agent: Any) -> bool:
    if hasattr(e, "recipient_covers"):
        return e.recipient_covers(agent)
    return True


def _warn_text(events: list) -> str:
    for e in events:
        t = getattr(e, "text", None) or (e.get("text") if isinstance(e, dict) else None)
        if t:
            return t
    return "Official evacuation warning issued."


def _counts(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def _mechanism_enabled(agent: Any, name: str) -> bool:
    mechanisms = getattr(agent, "mechanisms", None)
    if mechanisms is None:
        return True
    return bool(getattr(mechanisms, name, True))


def _proposal_payload_error(
    payload: Any,
    *,
    earliest_depart_step: int,
) -> str | None:
    if not isinstance(payload, dict):
        return "proposal payload must be an object"
    route_id = payload.get("route_id")
    if not isinstance(route_id, str) or not route_id.strip():
        return "proposal route_id must be a non-empty string"
    vehicle_id = payload.get("vehicle_id")
    if not isinstance(vehicle_id, str) or not vehicle_id.strip():
        return "proposal vehicle_id must be a non-empty string"
    depart_step = payload.get("depart_step")
    if not isinstance(depart_step, int) or isinstance(depart_step, bool):
        return "proposal depart_step must be an integer"
    if depart_step < earliest_depart_step:
        return "proposal depart_step is no longer feasible"
    return None
