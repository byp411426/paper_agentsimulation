#!/usr/bin/env python3
"""One-call diagnostic: why does the E1 v2 model emit zero messages?

Runs a single household x two adults x one step with the real backend,
prints the exact prompt, the raw model content, and the schema-validation
result so we can see whether messages are dropped by validation/repair or
never emitted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import yaml

from ds.agents.carr_empirical_v2 import OfficialInformationReceipt
from ds.agents.decide import E1ResidentDecision
from ds.llm.gateway import LLMGateway
from experiments.carr.empirical_v2_runner import build_e1_v2_components


PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--household", default="syn_t001_h0000002")
    parser.add_argument("--step", type=int, default=7)
    parser.add_argument("--deliver-message", action="store_true")
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    exp = cfg["experiment"]
    profiles_path = PROJECT_ROOT / exp["profiles_dir"] / exp["profiles_file"]
    models_cfg = yaml.safe_load(
        (PROJECT_ROOT / cfg["llm"]["models_config"]).read_text(
            encoding="utf-8"
        )
    )
    gateway = LLMGateway(
        run_id="carr_s_e1_v2_prompt_diagnostic",
        models_cfg=models_cfg,
        budget_usd=1.0,
        max_concurrency=2,
        log_dir=PROJECT_ROOT / "experiments/carr/runs/diagnostic_e1_prompt",
    )
    gateway.run_seed = 4201
    gateway.decision_model = cfg["llm"]["decision_model"]
    gateway.temperature = float(cfg["llm"]["temperature"])
    components = build_e1_v2_components(
        cfg=cfg,
        profiles_path=profiles_path,
        n_households=2,
        run_seed=4201,
        gateway=None,
    )
    households, residents, profiles, world, ix, event_source, agents = components
    household = households[args.household]

    # Deliver a mandatory order receipt to every decision adult (as step 7 does).
    for member_id in household.decision_member_ids:
        resident = residents[member_id]
        receipt = OfficialInformationReceipt(
            receipt_id=f"diag_receipt_{member_id}",
            resident_id=member_id,
            source_event_id="diag_order_m",
            severity="mandatory",
            channel="official_direct",
            issued_step=7,
            delivered_step=7,
            processed_step=None,
        )
        resident.deliver_receipt(receipt)

    if args.deliver_message:
        for member_id in household.decision_member_ids:
            resident = residents[member_id]
            resident.deliver_message(
                {
                    "message_id": f"m6:{household.decision_member_ids[0]}:0",
                    "sender_id": household.decision_member_ids[0],
                    "kind": "proposal",
                    "content": "Household evacuation proposal",
                    "channel": "household_dm",
                    "payload": {
                        "protocol_version": "e1_party_v2",
                        "traveler_ids": list(household.decision_member_ids),
                        "accompanying_member_ids": [],
                        "caregiver_by_member": {},
                        "vehicle_id": f"{household.id}:vehicle:1",
                        "route_id": "tiger_primary",
                        "depart_step": 8,
                    },
                }
            )

    print(f"household={args.household} members={household.member_ids}")
    for member_id in household.decision_member_ids:
        resident = residents[member_id]
        payload = resident._prompt_payload(world=world, step=args.step)
        system = (
            "You are a wildfire-zone resident in a shared household. "
            "Decide one action for this step: stay, prepare, evacuate, "
            "seek_help, or offer_help. When evacuating you MUST pick a "
            "route_id and vehicle_id from the provided household profile and "
            "a depart_step at or after the current step, and send a household "
            "proposal message with payload protocol_version e1_party_v2, "
            "traveler_ids, accompanying_member_ids, caregiver_by_member, "
            "vehicle_id, route_id, depart_step. When you receive a feasible "
            "proposal, respond accepted. Output ONLY the JSON schema. Treat "
            "'unverified' information without a source as rumor."
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
        print("\n" + "=" * 80)
        print(f"AGENT {member_id} step {args.step}")
        print("-" * 80)
        print("SYSTEM:", system)
        print("USER JSON (first 2400 chars):")
        print(json.dumps(payload, ensure_ascii=False, default=str)[:2400])

        # Full pipeline path: decide() embeds the JSON schema and normalizes
        # depart_step and proposal fields exactly as the runner will.
        decision = await resident.decide(
            events=[], world=world, gateway=gateway, step=args.step
        )
        print("-" * 80)
        print(
            "FINAL DECISION: action="
            + decision.action
            + f" n_messages={len(decision.messages)} "
            + f"n_responses={len(decision.message_responses)} "
            + f"route={decision.route_id} vehicle={decision.vehicle_id} "
            + f"depart={decision.depart_step}"
        )
        for message in decision.messages:
            print(
                "MESSAGE:",
                json.dumps(
                    message.model_dump(), ensure_ascii=False, default=str
                )[:600],
            )
        for response in decision.message_responses:
            print(
                "RESPONSE:",
                json.dumps(
                    response.model_dump(), ensure_ascii=False, default=str
                ),
            )

    gateway.flush()
    gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
