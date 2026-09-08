"""Household shared-state and batch resource arbitration tests."""

from __future__ import annotations

from ds.agents.decide import Decision, MessageResponse, OutMsg
from ds.agents.state import Resident, StaticAttrs
from ds.households import Household, VehicleRequest, VehicleResource
from ds.interaction.engine import InteractionEngine
from ds.kernel.clock import Clock


def _household() -> Household:
    return Household(
        id="h1",
        member_ids=("a", "b", "child"),
        decision_member_ids=("a", "b"),
        dependent_ids=("child",),
        vehicles={
            "car1": VehicleResource(
                id="car1", location=(0, 0), capacity=4
            )
        },
    )


def test_single_vehicle_batch_has_one_order_independent_winner():
    requests = [
        VehicleRequest("d-a", "a", "car1", request_step=4),
        VehicleRequest("d-b", "b", "car1", request_step=4),
    ]
    household = _household()
    forward = household.resolve_vehicle_requests(
        requests, run_seed=9, step=4
    )
    reverse = household.resolve_vehicle_requests(
        list(reversed(requests)), run_seed=9, step=4
    )

    assert forward == reverse
    winners = [
        result for result in forward.values()
        if result.status == "allocated"
    ]
    assert len(winners) == 1
    household.commit_vehicle_allocations(forward)
    assert household.vehicles["car1"].reserved_by == winners[0].agent_id


def test_existing_vehicle_reservation_has_deterministic_priority():
    household = _household()
    household.vehicles["car1"].reserved_by = "b"
    allocations = household.resolve_vehicle_requests(
        [
            VehicleRequest("d-a", "a", "car1", request_step=4, priority=10),
            VehicleRequest("d-b", "b", "car1", request_step=4, priority=0),
        ],
        run_seed=9,
        step=4,
    )
    assert allocations["d-b"].status == "allocated"
    assert allocations["d-a"].status == "rejected"


def test_functional_limitation_does_not_cancel_decision_capability():
    static = StaticAttrs(
        decision_capable=True,
        decision_policy="generative",
        functional_limitations={"mobility": True, "hearing": True},
    )
    resident = Resident("adult", static=static)
    assert resident.static.decision_capable is True


def test_dependent_member_never_wakes_as_decision_agent():
    class NearFireWorld:
        @staticmethod
        def distance_to_fire(location):
            return 0

    resident = Resident(
        "child",
        static=StaticAttrs(
            age=10,
            decision_capable=False,
            decision_policy="dependent",
        ),
    )
    resident.inbox.append({"content": "Evacuate"})
    assert not resident.should_wake(events=[], world=NearFireWorld(), step=1)


def test_message_lifecycle_separates_delivery_processing_and_acceptance():
    household = _household()
    sender = Resident("a", static=StaticAttrs(household_id="h1"))
    recipient = Resident("b", static=StaticAttrs(household_id="h1"))
    interaction = InteractionEngine(
        {"a": sender, "b": recipient},
        households_by_id={"h1": household},
    )
    clock = Clock(step_minutes=30, t=4)
    outgoing = Decision(
        action="stay",
        messages=[
            OutMsg(
                to="b",
                kind="proposal",
                content="Let us leave together at the next checkpoint.",
                payload={
                    "route_id": "r1",
                    "vehicle_id": "car1",
                    "depart_step": 5,
                },
            )
        ],
    )
    interaction.emit(sender, outgoing, clock)
    interaction.deliver(clock)

    assert interaction.snapshot()["receipt_states"] == {"delivered": 1}
    message_id = recipient.inbox[0]["message_id"]
    response = Decision(
        action="prepare",
        message_responses=[
            MessageResponse(
                message_id=message_id,
                disposition="accepted",
            )
        ],
    )
    interaction.process(recipient, response, clock)

    assert interaction.snapshot()["receipt_states"] == {"accepted": 1}
    assert recipient.inbox == []
    assert recipient.memory.items[-1].kind == "message"


def test_channel_specific_delivery_keeps_household_dm_out_of_social_dropout():
    sender = Resident("a")
    recipient = Resident("b")
    interaction = InteractionEngine(
        {"a": sender, "b": recipient},
        run_seed=9,
        dm_delivery_probability=1.0,
        community_delivery_probability=0.0,
    )
    clock = Clock(step_minutes=30, t=4)
    interaction.emit(
        sender,
        Decision(
            action="stay",
            messages=[
                OutMsg(to="b", kind="notice", content="household notice"),
                OutMsg(to="community", kind="notice", content="public notice"),
            ],
        ),
        clock,
    )
    interaction.deliver(clock)
    assert interaction.snapshot()["delivered_by_channel"] == {"dm": 1}

    clock.t = 5
    interaction.deliver(clock)
    snapshot = interaction.snapshot()
    assert snapshot["sent_by_channel"] == {"community": 1, "dm": 1}
    assert snapshot["delivered_by_channel"] == {"dm": 1}
    assert snapshot["dropped_by_channel"] == {"community": 1}


def test_stale_proposal_is_rejected_before_delivery():
    sender = Resident("a")
    recipient = Resident("b")
    interaction = InteractionEngine({"a": sender, "b": recipient})
    clock = Clock(step_minutes=30, t=4)
    interaction.emit(
        sender,
        Decision(
            action="prepare",
            messages=[
                OutMsg(
                    to="b",
                    kind="proposal",
                    content="Leave now.",
                    payload={
                        "route_id": "r1",
                        "vehicle_id": "car1",
                        "depart_step": 4,
                    },
                )
            ],
        ),
        clock,
    )
    snapshot = interaction.snapshot()
    assert snapshot["msg_count"] == 0
    assert snapshot["invalid_proposal_attempts"] == 1
    assert snapshot["invalid_proposal_reasons"] == {
        "proposal depart_step is no longer feasible": 1
    }


def test_proposal_that_expires_before_processing_cannot_form_commitment():
    household = _household()
    sender = Resident("a", static=StaticAttrs(household_id="h1"))
    recipient = Resident("b", static=StaticAttrs(household_id="h1"))
    interaction = InteractionEngine(
        {"a": sender, "b": recipient},
        households_by_id={"h1": household},
    )
    clock = Clock(step_minutes=30, t=4)
    interaction.emit(
        sender,
        Decision(
            action="prepare",
            messages=[
                OutMsg(
                    to="b",
                    kind="proposal",
                    content="Use route r1 and car1 at step 5.",
                    payload={
                        "route_id": "r1",
                        "vehicle_id": "car1",
                        "depart_step": 5,
                    },
                )
            ],
        ),
        clock,
    )
    interaction.deliver(clock)
    message_id = recipient.inbox[0]["message_id"]
    clock.t = 6
    interaction.process(
        recipient,
        Decision(
            action="prepare",
            message_responses=[
                MessageResponse(message_id=message_id, disposition="accepted")
            ],
        ),
        clock,
    )
    receipt = next(iter(interaction.receipts.values()))
    assert receipt.status == "rejected"
    assert receipt.disposition_reason == (
        "proposal depart_step is no longer feasible"
    )
    assert household.commitments == {}


def test_accepted_proposal_becomes_structured_household_commitment():
    household = _household()
    sender = Resident("a", static=StaticAttrs(household_id="h1"))
    recipient = Resident("b", static=StaticAttrs(household_id="h1"))
    interaction = InteractionEngine(
        {"a": sender, "b": recipient},
        households_by_id={"h1": household},
    )
    clock = Clock(step_minutes=30, t=4)
    interaction.emit(
        sender,
        Decision(
            action="prepare",
            messages=[
                OutMsg(
                    to="b",
                    kind="proposal",
                    content="Use route r1 and car1 at step 5.",
                    payload={
                        "route_id": "r1",
                        "vehicle_id": "car1",
                        "depart_step": 5,
                    },
                )
            ],
        ),
        clock,
    )
    interaction.deliver(clock)
    message_id = recipient.inbox[0]["message_id"]
    interaction.process(
        recipient,
        Decision(
            action="prepare",
            message_responses=[
                MessageResponse(
                    message_id=message_id,
                    disposition="accepted",
                )
            ],
        ),
        clock,
    )

    commitment = household.compatible_commitment(
        route_id="r1",
        vehicle_id="car1",
        depart_step=5,
    )
    assert commitment is not None
    assert commitment.accepted_by == frozenset({"a", "b"})


def test_new_feasible_commitment_supersedes_without_erasing_history():
    household = _household()
    sender = Resident("a", static=StaticAttrs(household_id="h1"))
    recipient = Resident("b", static=StaticAttrs(household_id="h1"))
    interaction = InteractionEngine(
        {"a": sender, "b": recipient},
        households_by_id={"h1": household},
    )
    for depart_step in (5, 6):
        clock = Clock(step_minutes=30, t=4)
        interaction.emit(
            sender,
            Decision(
                action="prepare",
                messages=[
                    OutMsg(
                        to="b",
                        kind="proposal",
                        content=f"Leave at {depart_step}.",
                        payload={
                            "route_id": "r1",
                            "vehicle_id": "car1",
                            "depart_step": depart_step,
                        },
                    )
                ],
            ),
            clock,
        )
        interaction.deliver(clock)
        message_id = recipient.inbox[0]["message_id"]
        interaction.process(
            recipient,
            Decision(
                action="prepare",
                message_responses=[
                    MessageResponse(
                        message_id=message_id,
                        disposition="accepted",
                    )
                ],
            ),
            clock,
        )

    commitments = sorted(
        household.commitments.values(),
        key=lambda commitment: commitment.depart_step or -1,
    )
    assert [item.status for item in commitments] == ["cancelled", "accepted"]
    assert commitments[1].supersedes_id == commitments[0].id
    assert household.has_feasible_commitment_formation()


def test_reserved_vehicle_cannot_be_reused_by_member_left_at_home():
    household = _household()
    household.vehicles["car1"].reserved_by = "a"
    allocations = household.resolve_vehicle_requests(
        [VehicleRequest("d-b", "b", "car1", request_step=5)],
        run_seed=9,
        step=5,
    )
    assert allocations["d-b"].status == "rejected"
    assert allocations["d-b"].reason == "vehicle reserved by a"
