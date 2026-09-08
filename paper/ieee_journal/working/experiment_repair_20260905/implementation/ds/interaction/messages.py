"""Messages, claims, events (spec v2 §2.4).

A Message carries an optional Claim (a checkable assertion about the world). When a
resident later observes the world confirming/refuting a claim, its source's trust
updates. Rumor = a Message whose Claim.truth is False, injected by an experiment.

Event is the EventPack-driven world/warning event (never AI-made).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Claim(BaseModel):
    predicate: Literal["fire_at", "road_closed", "shelter_open", "order_issued"]
    args: dict = Field(default_factory=dict)
    truth: bool | None = None  # None = evaluated by the world; False = injected rumor


class Message(BaseModel):
    message_id: str
    sender: str
    channel: Literal["dm", "community", "official"]
    kind: Literal["proposal", "acknowledgement", "acceptance", "notice"] = "proposal"
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)
    claim: Claim | None = None
    sent_step: int = 0
    deliver_step: int = 0  # dm: same step; community: +1
    recipients: Any = "all"  # "all", list of ids, or a zone tag


class MessageReceipt(BaseModel):
    receipt_id: str
    message_id: str
    sender: str
    recipient: str
    kind: Literal["proposal", "acknowledgement", "acceptance", "notice"]
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)
    sent_step: int
    delivered_step: int
    status: Literal["delivered", "processed", "accepted", "rejected"] = "delivered"
    processed_step: int | None = None
    disposition_step: int | None = None
    disposition_reason: str | None = None


class Event(BaseModel):
    """EventPack event (warning / closure / shelter open)."""
    step: int
    kind: Literal["warning", "road_closed", "shelter_open", "hazard_update", "order"]
    text: str = ""
    zone: str | None = None
    recipients: Any = "all"
    payload: dict = Field(default_factory=dict)

    def recipient_covers(self, agent: Any) -> bool:
        if self.recipients == "all":
            if self.zone in (None, "all"):
                return True
            return getattr(getattr(agent, "static", None), "zone", None) == self.zone
        if isinstance(self.recipients, str):
            if self.recipients == getattr(
                getattr(agent, "static", None), "zone", None
            ):
                return True
            return self.recipients == agent.id
        try:
            return agent.id in self.recipients
        except Exception:
            return False
