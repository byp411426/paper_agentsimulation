#!/usr/bin/env python3
"""Probe gpt-5.6-luna and claude-sonnet-5 on one E1 decision call each."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from ds.agents.decide import E1ResidentDecision


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _profile_payload() -> dict:
    profiles = [
        json.loads(line)
        for line in (
            PROJECT_ROOT
            / "eventpacks/carr_2018/population/e1_profiles_v2_seed4201/e1_profiles_seed4201.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    p = profiles[1]
    member = p["member_profiles"][0]
    return {
        "resident_profile": {
            "static": member.get("pums_static", {}),
            "functional_limitations": member.get("functional_limitations", {}),
            "needs_execution_assistance": member.get(
                "needs_execution_assistance", False
            ),
            "latent_traits": member.get("latent_traits", {}),
        },
        "household_profile": {
            "members": [
                {
                    "resident_id": m.get("resident_id"),
                    "age": m.get("age"),
                    "relationship": m.get("relationship"),
                }
                for m in p["member_profiles"]
            ],
            "vehicles": [
                {
                    "id": f"{p['household_id']}:vehicle:1",
                    "capacity": 5,
                    "location": ["home", p["household_id"]],
                }
            ],
            "housing": p.get("shared_attributes", {}),
            "pets": p.get("shared_attributes", {}).get("pet_owned", False),
            "livestock": p.get("shared_attributes", {}).get(
                "livestock_owned", False
            ),
        },
        "observed_now": {
            "inbox": [
                {
                    "kind": "official_receipt",
                    "message_id": None,
                    "severity": "mandatory",
                    "content": None,
                    "source_event_id": "order_m_1",
                    "source_message_id": None,
                    "channel": "official_direct",
                }
            ],
            "hazard_distance_m": 7134,
            "perceived_routes": {
                "tiger_primary": {"open": True},
                "tiger_alternate": {"open": True},
            },
            "shared_resource_reservations": [
                {
                    "vehicle_id": f"{p['household_id']}:vehicle:1",
                    "reserved_by": None,
                    "location": ["home", p["household_id"]],
                    "occupied": 0,
                    "capacity": 5,
                }
            ],
        },
        "private_process": {
            "memories": [],
            "current_plan": None,
            "my_accepted_commitments": [],
            "recent_execution_feedback": [],
        },
    }


async def probe(model: str, key_env: str, base_url: str) -> None:
    import os

    import litellm

    payload = _profile_payload()
    system = (
        "You are a wildfire-zone resident in a shared household. Decide one "
        "action: stay, prepare, evacuate, seek_help, or offer_help. When "
        "evacuating pick route_id/vehicle_id from the household profile, "
        "depart_step at or after the current step (current step is 7), and "
        "send a household proposal via the messages array "
        "(kind=proposal, to=household). If you receive a proposal, respond "
        "accepted with its exact message_id. Output ONLY valid JSON matching "
        "this schema:\n"
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
            "content": json.dumps(payload, ensure_ascii=False, default=str),
        },
    ]
    print(f"\n===== {model} =====")
    try:
        resp = await litellm.acompletion(
            model=f"openai/{model}",
            messages=messages,
            temperature=0.0,
            api_key=os.environ[key_env],
            api_base=base_url,
            max_tokens=2048,
            timeout=300,
        )
        raw = resp.choices[0].message.content or ""
        print("RAW (first 1400):", raw[:1400])
        try:
            parsed = E1ResidentDecision.model_validate_json(raw)
            print(
                "VALID: action="
                + parsed.action
                + f" n_messages={len(parsed.messages)} "
                + f"n_responses={len(parsed.message_responses)} "
                + f"route={parsed.route_id} vehicle={parsed.vehicle_id} "
                + f"depart={parsed.depart_step}"
            )
            for m in parsed.messages:
                print("MSG:", json.dumps(m.model_dump(), default=str)[:300])
            for r in parsed.message_responses:
                print(
                    "RESP:",
                    json.dumps(r.model_dump(), default=str)[:200],
                )
        except Exception as exc:
            print("VALIDATION FAILED:", type(exc).__name__, str(exc)[:300])
    except Exception as exc:
        print("CALL FAILED:", type(exc).__name__, str(exc)[:300])


async def main() -> None:
    await probe("gpt-5.6-luna", "PACKY_LUNA_API_KEY", "https://www.packyapi.com/v1")
    await probe(
        "claude-sonnet-5", "PACKY_CLAUDE_API_KEY", "https://www.packyapi.com/v1"
    )


if __name__ == "__main__":
    asyncio.run(main())
