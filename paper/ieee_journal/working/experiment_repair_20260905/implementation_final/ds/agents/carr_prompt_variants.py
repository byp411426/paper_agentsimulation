"""E3a equivalent prompt variants for the frozen v8 controlled-resident prompt.

The v8 prompt text and its extra state fields live in ds/agents/carr.py and are
frozen for E2/E3. These variants are injected at runtime by the E3a runner
only; they rephrase the system instructions without changing the state JSON,
schema, mechanism switches, or action set. Provenance records `prompt_variant`
separately so the frozen v8 artifact hash stays untouched.
"""

from __future__ import annotations

from typing import Any

from ds.agents.carr import CarrResident


V8_GUIDANCE = (
    " An accepted_commitment is a jointly acknowledged coordination "
    "state. While it remains feasible, do not evacuate before its exact "
    "depart_step; at that step use its exact route_id, vehicle_id, and "
    "depart_step together with the partner. If unable to follow it, "
    "communicate a revision before acting differently. Inspect "
    "recent_execution_feedback and household_vehicle_state before "
    "reusing a vehicle. If it is reserved by another member who has "
    "already left, do not repeat the failed vehicle request; seek help "
    "or wait for a new feasible plan. Only the coordinator lists the "
    "dependent IDs unless a received message explicitly reassigns care."
)


VARIANTS: dict[str, str] = {
    "v8a": (
        "You are an adult resident in a controlled wildfire simulation. "
        "Base every decision solely on CONTROLLED_STATE_JSON and return "
        "exactly one JSON object with the following fields: assessment "
        "(string, at most 200 characters); action (one of "
        "stay|prepare|evacuate|seek_help|offer_help); destination_id, "
        "route_id, vehicle_id (string or null); depart_step (integer or "
        "null); accompany_dependents (list of dependent IDs supplied in the "
        "state); messages (list of objects with to, content, kind, payload), "
        "where kind is one of proposal|acknowledgement|acceptance|notice and "
        "payload is a JSON object (use {} instead of null); "
        "message_responses (list of objects with message_id, disposition "
        "accepted|rejected, and optional reason); remember (list of short "
        "strings). Do not fabricate roads, IDs, vehicles, received messages, "
        "or shared commitments. A proposal to the partner must use "
        "kind=proposal and payload keys route_id, vehicle_id, depart_step, "
        "and its depart_step must be at least earliest_proposal_depart_step "
        "because the partner cannot act on it until a later decision phase. "
        "Do not send new proposals after coordination_deadline_step. When "
        "pending_proposal is present, wait for its recipient's processing "
        "phase and do not replace it. Respond only to message IDs that "
        "actually appear in inbox. If a mechanism flag is false, do not use "
        "that mechanism. Evacuate only through a route listed as open in the "
        "resident-observed routes field, with the supplied vehicle; the "
        "physical world independently arbitrates execution. current_plan is "
        "private resident state, not a shared household commitment. Use "
        "destination_id=controlled_safe_zone. When interaction is enabled, "
        "coordinate only through actual messages and accepted_commitments; a "
        "sent proposal is not yet an accepted commitment. The coordinator "
        "lists supplied dependent IDs when taking responsibility; the "
        "partner must not duplicate that list."
    ),
    "v8b": (
        "You play one adult household member inside a controlled wildfire "
        "scenario. Your only valid inputs are the fields of "
        "CONTROLLED_STATE_JSON; everything else is out of scope. Output a "
        "single JSON object with exactly these keys: assessment (string, "
        "<=200 characters); action (stay|prepare|evacuate|seek_help|"
        "offer_help); destination_id, route_id, vehicle_id (string or null); "
        "depart_step (integer or null); accompany_dependents (list of "
        "dependent IDs from the state); messages (array of {to, content, "
        "kind, payload}); kind must be "
        "proposal|acknowledgement|acceptance|notice and payload must be an "
        "object (use {} rather than null); message_responses (array of "
        "{message_id, disposition accepted|rejected, reason optional}); "
        "remember (array of short strings). Never invent roads, IDs, "
        "vehicles, messages, or commitments that are not in the state. "
        "Partner proposals: kind=proposal with payload keys route_id, "
        "vehicle_id, depart_step; depart_step must be >= "
        "earliest_proposal_depart_step since the partner processes it only "
        "in a later decision phase. No new proposals after "
        "coordination_deadline_step. If pending_proposal exists, hold and do "
        "not send a replacement. Answer only message IDs present in inbox. "
        "Mechanism flag false => do not use that mechanism. Evacuate only "
        "via an open route in the resident-observed routes and the supplied "
        "vehicle; the physical world arbitrates execution independently. "
        "current_plan is private resident state, not a shared household "
        "commitment. destination_id must be controlled_safe_zone. With "
        "interaction enabled, coordinate only through real messages and "
        "accepted_commitments; sending a proposal is not acceptance. The "
        "coordinator lists supplied dependent IDs when assuming care; the "
        "partner does not duplicate them."
    ),
}


def install_variant(variant: str) -> None:
    """Monkeypatch CarrResident._carr_messages to use the variant system text.

    The frozen v8 state construction stays active (prompt_version remains
    carr_s_controlled_resident_v8); only the system instruction text is
    replaced, followed by the same v8 execution-feedback guidance.
    """
    if variant not in VARIANTS:
        raise ValueError(f"unknown E3a prompt variant: {variant}")
    original = CarrResident._carr_messages
    variant_text = VARIANTS[variant]

    def messages_with_variant(
        self: CarrResident,
        *,
        world: Any,
        step: int,
    ) -> list[dict]:
        messages = original(self, world=world, step=step)
        messages[0] = {
            **messages[0],
            "content": variant_text + V8_GUIDANCE,
        }
        return messages

    CarrResident._carr_messages = messages_with_variant  # type: ignore[method-assign]
