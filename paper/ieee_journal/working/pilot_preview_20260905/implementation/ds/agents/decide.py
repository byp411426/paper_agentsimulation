"""Resident decision schemas + prompt assembly. Agent-facing prompts are English.

``Resident`` is the generative decision unit. ``Household`` is a shared resource
and coordination object, not a single replacement LLM. The richer schema below
is retained as a planned resident-level interface while the Carr runner is built.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class OutMsg(BaseModel):
    to: str  # an agent_id, "neighbors", or "community"
    content: str
    kind: Literal["proposal", "acknowledgement", "acceptance", "notice"] = "proposal"
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload", mode="before")
    @classmethod
    def normalize_empty_payload(cls, value: Any) -> Any:
        """Treat JSON null as an empty payload for non-proposal messages."""
        return {} if value is None else value


class MessageResponse(BaseModel):
    message_id: str
    disposition: Literal["accepted", "rejected"]
    reason: str | None = None


class Decision(BaseModel):
    """Toy-village decision schema."""
    thought: str = Field(default="", max_length=200)
    action: Literal["stay", "prepare", "evacuate", "seek_help"]
    messages: list[OutMsg] = Field(default_factory=list)
    message_responses: list[MessageResponse] = Field(default_factory=list)
    remember: list[str] = Field(default_factory=list)
    importance: int = Field(default=1, ge=1, le=5)


class ResidentDecision(BaseModel):
    """Carr resident intention; household/world constraints decide execution."""
    assessment: str = Field(default="", max_length=240)
    action: Literal["stay", "prepare", "evacuate", "seek_help", "offer_help"]
    destination_id: str | None = None  # MUST be from the offered candidate list
    route_id: str | None = None
    vehicle_id: str | None = None
    depart_step: int | None = None
    accompany_dependents: list[str] = Field(default_factory=list)
    messages: list[OutMsg] = Field(default_factory=list)
    message_responses: list[MessageResponse] = Field(default_factory=list)
    remember: list[str] = Field(default_factory=list)

    @field_validator("assessment", mode="before")
    @classmethod
    def normalize_assessment_length(cls, value: Any) -> str:
        """Keep non-semantic explanatory text inside the schema boundary."""
        text = "" if value is None else str(value)
        return text[:240]


class E1ResidentDecision(ResidentDecision):
    """E1 v2 decision schema: also captures model-emitted proposal fields.

    The shared ResidentDecision (used by E2/E3) stays untouched so cross-model
    replication keeps an identical contract.  E1 models sometimes emit the
    household proposal under `household_proposal` or
    `household_proposal_message` instead of the `messages` array; the runner
    normalizes either field into a standard household proposal message.
    """

    household_proposal: dict[str, Any] | None = None
    household_proposal_message: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_proposal_fields(cls, data: Any) -> Any:
        """Capture any top-level *proposal* dict the model emits.

        Real E1 calls produced `household_proposal_message`,
        `household_proposal`, and `proposal`; the model does not reliably use
        the `messages` array.  Whatever name it uses, the payload is folded
        into the standard messages array before validation.
        """
        if not isinstance(data, dict):
            return data
        messages = list(data.get("messages") or [])
        for key in list(data):
            if "proposal" in key.lower() and isinstance(data[key], dict):
                payload = dict(data[key])
                messages.append(
                    {
                        "to": "household",
                        "kind": "proposal",
                        "content": "Household evacuation proposal",
                        "payload": payload,
                    }
                )
                del data[key]
        if messages:
            data["messages"] = messages
        return data

# --------------------------------------------------------------------------- #
# prompt assembly (context engineering, spec §4 — English, JSON-only)          #
# --------------------------------------------------------------------------- #
def build_toy_messages(persona: str, traits: str, location, family_safe: bool,
                       fire_m: float, new_info: list[str], memories: list[str]) -> list:
    fam = "safe" if family_safe else "unconfirmed"
    info = "; ".join(new_info) if new_info else "none"
    mem = "; ".join(memories) if memories else "none"
    return [
        {"role": "system", "content":
         f"You are role-playing a real wildfire-zone resident: {persona}. "
         f"Personality: {traits}. Decide based on the information and your "
         f"personality. Output ONLY JSON with fields: "
         f"thought, action (stay|prepare|evacuate|seek_help), messages, "
         f"remember, importance (1-5)."},
        {"role": "user", "content":
         f"Current state: location {location}, family {fam}, "
         f"fire distance: {fire_m:.0f}m. "
         f"New information: {info}. "
         f"You remember: {mem}. "
         f"What do you do?"},
    ]
