#!/usr/bin/env python3
"""Two-call end-to-end loop diagnostic for E1 v2 coordination.

Verifies the full chain with the real backend: sender evacuates and emits a
household proposal -> recipient receives it -> recipient processes the inbox
and replies accepted with the exact message_id -> system forms a commitment.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import yaml

from ds.agents.carr_empirical_v2 import OfficialInformationReceipt
from ds.households.state import DepartureParty, HouseholdCommitmentV2
from ds.kernel.clock import Clock
from ds.llm.gateway import LLMGateway
from experiments.carr.empirical_v2_runner import build_e1_v2_components


PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    cfg = yaml.safe_load(
        (
            PROJECT_ROOT
            / "experiments/carr/configs/carr_s_e1_empirical_v2_formal.yaml"
        ).read_text(encoding="utf-8")
    )
    exp = cfg["experiment"]
    profiles_path = PROJECT_ROOT / exp["profiles_dir"] / exp["profiles_file"]
    models_cfg = yaml.safe_load(
        (PROJECT_ROOT / cfg["llm"]["models_config"]).read_text(
            encoding="utf-8"
        )
    )
    gateway = LLMGateway(
        run_id="carr_s_e1_v2_loop_diagnostic",
        models_cfg=models_cfg,
        budget_usd=1.0,
        max_concurrency=2,
        log_dir=PROJECT_ROOT / "experiments/carr/runs/diagnostic_e1_loop",
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
    household = households["syn_t001_h0000002"]
    r1, r2 = household.decision_member_ids
    clock = Clock(30)
    for _ in range(7):
        clock.tick()

    # Step 7: mandatory order reaches both adults.
    for member_id in household.decision_member_ids:
        residents[member_id].deliver_receipt(
            OfficialInformationReceipt(
                receipt_id=f"loop_receipt_{member_id}",
                resident_id=member_id,
                source_event_id="loop_order",
                severity="mandatory",
                channel="official_direct",
                issued_step=7,
                delivered_step=7,
                processed_step=None,
            )
        )

    # Call 1: sender decides (should evacuate + emit proposal).
    decision1 = await residents[r1].decide(
        events=[], world=world, gateway=gateway, step=7
    )
    print(f"[1] {r1}: action={decision1.action} n_msgs={len(decision1.messages)}")
    if not decision1.messages:
        raise SystemExit("sender did not emit a proposal")
    proposal = decision1.messages[0]
    ix.emit(residents[r1], decision1, clock)
    sent_id = next(reversed(ix.messages))

    # Deliver to recipient inbox (deterministic, household DM p=1).
    residents[r2].deliver_message(ix.messages[sent_id])
    print(f"[2] proposal {sent_id} delivered to {r2} inbox: {len(residents[r2].inbox)} item")

    # Recipient processes inbox and decides (should reply accepted with exact id).
    clock.tick()
    print(
        f"[3] recipient inbox before decide: "
        f"{[(i.get('message_id') or i.get('receipt_id'), i.get('kind'), i.get('message_kind')) for i in residents[r2].inbox]}"
    )
    decision2 = await residents[r2].decide(
        events=[], world=world, gateway=gateway, step=8
    )
    print(
        f"[4] {r2}: action={decision2.action} n_responses={len(decision2.message_responses)}"
    )
    for response in decision2.message_responses:
        print(
            f"    response message_id={response.message_id!r} "
            f"disposition={response.disposition} reason={response.reason!r}"
        )
    ix.process(residents[r2], decision2, clock)

    # Check the ledger reflects processed + accepted.
    message = ix.messages[sent_id]
    print(
        f"[5] ledger: status={message['status']} "
        f"processed={message['processed_step']} disposition={message['disposition']}"
    )
    print(f"    payload={json.dumps(message['payload'], default=str)[:400]}")
    print(f"    acceptance={message.get('acceptance')}")
    print(
        f"[6] recipient inbox cleared: {len(residents[r2].inbox) == 0} "
        f"({len(residents[r2].inbox)} remaining)"
    )
    active = household.active_v2_parties()
    print(f"[7] active commitments: {len(active)}")
    for commitment in active:
        print(
            f"    {commitment.id}: travelers={sorted(commitment.party.traveler_ids)} "
            f"depart={commitment.party.depart_step} route={commitment.party.route_id}"
        )
    gateway.flush()
    gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
