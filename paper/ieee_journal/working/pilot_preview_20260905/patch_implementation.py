from pathlib import Path
D=Path(__file__).parent/'implementation'
def edit(rel, old, new):
 p=D/rel;s=p.read_text();assert s.count(old)==1,(rel,s.count(old),old[:80]);p.write_text(s.replace(old,new))
edit('ds/world/carr_empirical_v2.py','''            resident_id: ("home", resident.household_id)
            for resident_id, resident in residents.items()''','''            member_id: ("home", household.id)
            for household in households.values()
            for member_id in household.member_ids''')
edit('ds/world/carr_empirical_v2.py','''    def _matching_party(self, household: Household, decision: Any) -> Any | None:''','''    def _matching_party(self, household: Household, decision: Any, agent_id: str) -> Any | None:''')
edit('ds/world/carr_empirical_v2.py','''                party.depart_step == self._step
                and party.route_id''','''                party.depart_step == self._step
                and agent_id in party.traveler_ids
                and party.route_id''')
edit('ds/world/carr_empirical_v2.py','''            party = self._matching_party(household, decision)''','''            if self.member_locations.get(envelope.agent_id) != ("home", household.id):
                resolved.append(ResolvedIntent(decision_id=envelope.decision_id,
                    agent_id=envelope.agent_id, agent=envelope.agent, decision=decision,
                    action=("rejected", "resident_not_at_origin")))
                continue
            party = self._matching_party(household, decision, envelope.agent_id)''')
edit('ds/world/carr_empirical_v2.py','''                        if member_id in self._care_requirements
''','''                        if member_id in self._care_requirements
                        and self.member_locations.get(member_id) == ("home", household.id)
''')
edit('ds/world/carr_empirical_v2.py','''            route_id = commitment.party.route_id
            if (''','''            if commitment.party.depart_step != clock.t:
                for intent in intents:
                    outcomes[intent.decision_id] = ExecutionOutcome(
                        decision_id=intent.decision_id, agent_id=intent.agent_id,
                        status="rejected", executed_action="evacuate", reason="party_not_due")
                continue
            if any(self.member_locations.get(m) != ("home", household_id)
                   for m in commitment.party.member_ids):
                for intent in intents:
                    outcomes[intent.decision_id] = ExecutionOutcome(
                        decision_id=intent.decision_id, agent_id=intent.agent_id,
                        status="rejected", executed_action="evacuate", reason="party_member_not_at_origin")
                continue
            route_id = commitment.party.route_id
            if route_id not in self.route_state:
                for intent in intents:
                    outcomes[intent.decision_id] = ExecutionOutcome(
                        decision_id=intent.decision_id, agent_id=intent.agent_id,
                        status="rejected", executed_action="evacuate", reason="unknown_route")
                continue
            if (''')
edit('ds/world/carr_empirical_v2.py','''            self.route_usage[route_id] = self.route_usage.get(route_id, 0) + 1
            executed = record.outcome == "executed"''','''            executed = record.outcome == "executed"
            if executed:
                self.route_usage[route_id] = self.route_usage.get(route_id, 0) + 1''')
edit('ds/world/carr_empirical_v2.py','''            "hazard_offsets": self.hazard_offsets,
''','''            "hazard_offsets": self.hazard_offsets,
            "household_commitments": {
                hh.id: {c.id: {"id": c.id, "created_step": c.created_step,
                    "status": c.status, "supersedes_id": c.supersedes_id,
                    "accepted_by": sorted(c.accepted_by),
                    "party": {"traveler_ids": sorted(c.party.traveler_ids),
                        "accompanying_member_ids": sorted(c.party.accompanying_member_ids),
                        "route_id": c.party.route_id, "vehicle_id": c.party.vehicle_id,
                        "depart_step": c.party.depart_step}}
                    for c in hh.v2_commitments.values()} for hh in self.households.values()},
''')
edit('ds/agents/carr_empirical_v2.py','''        if not self.static.decision_capable:
''','''        if self.state.evacuating or world.member_locations.get(self.id) == world.safe_zone:
            return False
        if not self.static.decision_capable:
''')
edit('ds/agents/carr_empirical_v2.py','''        return {
            "resident_profile": {''','''        return {
            "current_step": step,
            "resident_id": self.id,
            "household_id": self.household_id,
            "current_location": world.member_locations.get(self.id),
            "resident_profile": {''')
edit('ds/agents/carr_empirical_v2.py','''            depart_step = max(int(depart_step), step + 1)''','''            depart_step = max(int(depart_step), step)''')
edit('ds/agents/carr_empirical_v2.py','''            "id": self.id,
            "household_id": self.household_id,
            "inbox":''','''            "id": self.id,
            "household_id": self.household_id,
            "evacuating": self.state.evacuating,
            "evac_step": self.state.evac_step,
            "inbox":''')
# Save the actual bounded observation and private state before every decision.
edit('ds/agents/carr_empirical_v2.py','''        seed = stream_seed(
''','''        audit_path = gateway.log_path.parent / "decision_inputs.jsonl"
        with audit_path.open("a") as handle:
            handle.write(json.dumps({"step": step, "resident_id": self.id,
                "payload": payload}, ensure_ascii=False, default=str) + "\\n")
        seed = stream_seed(
''')
# Per-recipient lifecycle; a response counts only after actual delivery.
edit('ds/interaction/carr_empirical_v2.py','''        self._step = 0
''','''        self._step = 0
        self.commitment_notifications: list[dict] = []
''')
edit('ds/interaction/carr_empirical_v2.py','''                "disposition": None,
''','''                "disposition": None,
                "recipient_states": {r: {"delivered_step": None,
                    "processed_step": None, "disposition": None, "response_step": None}
                    for r in recipients},
''')
edit('ds/interaction/carr_empirical_v2.py','''                self.messages[message_id]["status"] = "processed"
''','''                self.messages[message_id]["status"] = "processed"
                delivery = self.messages[message_id]["recipient_states"].get(agent.id)
                if delivery is not None:
                    delivery["processed_step"] = clock.t
''')
edit('ds/interaction/carr_empirical_v2.py','''            if message is None:
                continue
            message["disposition"]''','''            if message is None:
                continue
            delivery = message.get("recipient_states", {}).get(agent.id)
            if delivery is None or delivery["processed_step"] is None:
                continue
            delivery.update(disposition=response.disposition, response_step=clock.t)
            message["disposition"]''')
edit('ds/interaction/carr_empirical_v2.py','''        household = self.households[agent.household_id]
        payload = message["payload"]''','''        household = self.households[agent.household_id]
        if message.get("acceptance", {}).get("accepted"):
            return
        payload = message["payload"]''')
edit('ds/interaction/carr_empirical_v2.py','''            accepted_by=frozenset({message["sender_id"]})
            | (frozenset(message["recipient_ids"]) if not self_accept else frozenset()),''','''            accepted_by=frozenset({message["sender_id"]}) | frozenset(
                member for member, state in message.get("recipient_states", {}).items()
                if state["disposition"] == "accepted" and state["processed_step"] is not None),''')
edit('ds/interaction/carr_empirical_v2.py','''            agent.my_commitments.append(
                {
                    "commitment_id": commitment.id,
                    "depart_step": party.depart_step,
                    "route_id": party.route_id,
                    "vehicle_id": party.vehicle_id,
                    "traveler_ids": sorted(party.traveler_ids),
                }
            )''','''            # Explicit protocol acknowledgement, only to the consenting travelers.
            for member_id in sorted(party.traveler_ids & commitment.accepted_by):
                notice = {"commitment_id": commitment.id,
                    "source_message_id": message["message_id"],
                    "recipient_id": member_id, "delivered_step": step,
                    "depart_step": party.depart_step, "route_id": party.route_id,
                    "vehicle_id": party.vehicle_id,
                    "traveler_ids": sorted(party.traveler_ids)}
                self.residents[member_id].my_commitments.append(dict(notice))
                self.commitment_notifications.append(notice)''')
edit('ds/interaction/carr_empirical_v2.py','''            if message["status"] != "sent":
                continue
            for recipient_id in message["recipient_ids"]:
                recipient = self.residents.get(recipient_id)''','''            for recipient_id in message["recipient_ids"]:
                recipient_state = message["recipient_states"][recipient_id]
                if recipient_state["delivered_step"] is not None:
                    continue
                recipient = self.residents.get(recipient_id)''')
edit('ds/interaction/carr_empirical_v2.py','''                recipient.deliver_message(message)
                message["delivered_step"] = clock.t''','''                recipient_state["delivered_step"] = clock.t
                recipient.deliver_message({**message, "delivered_step": clock.t})
                message["delivered_step"] = message["delivered_step"] or clock.t''')
edit('ds/interaction/carr_empirical_v2.py','''            "receipts": current_receipts,
''','''            "receipts": current_receipts,
            "commitment_notifications": self.commitment_notifications,
''')
edit('experiments/carr/empirical_v2_runner.py','''                        "status": value.status,
                        "supersedes_id":''','''                        "status": value.status,
                        "created_step": value.created_step,
                        "accepted_by": sorted(value.accepted_by),
                        "household_id": household_id,
                        "supersedes_id":''')
# Shared kernel extra fields contain only logging snapshots, not inputs to decisions.
edit('ds/kernel/engine.py','''                # ⑤ collect intentions while the world is immutable for this phase
''','''                import copy
                self._audit_before = {"world": copy.deepcopy(self.world.snapshot()),
                    "agents": copy.deepcopy([a.snapshot() for a in self.agents])}
                # ⑤ collect intentions while the world is immutable for this phase
''')
edit('ds/kernel/engine.py','''            "n_awake": len(awake),
''','''            "n_awake": len(awake),
            "state_before_decisions": self._audit_before,
''')
p=Path(__file__).parent/'run_pilot.py';s=p.read_text();s=s.replace('sys.path.insert(0, str(SOURCE))','sys.path.insert(0, str(HERE / "implementation"))');p.write_text(s)
print('Patched isolated E1 implementation; original source unchanged')
