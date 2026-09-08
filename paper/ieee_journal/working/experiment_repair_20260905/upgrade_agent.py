from pathlib import Path
p=Path('implementation/ds/agents/carr_empirical_v2.py');s=p.read_text()
s=s.replace('from ds.agents.decide import E1ResidentDecision, OutMsg, ResidentDecision','from ds.agents.decide import OutMsg, ResidentDecision\nfrom ds.agents.e1_contracts import E1Decision as E1ResidentDecision')
s=s.replace('        self.my_commitments: list[dict[str, Any]] = []','        self.current_plan: dict[str, Any] | None = None\n        self.plan_history: list[dict[str, Any]] = []\n        self.my_commitments: list[dict[str, Any]] = []')
s=s.replace('        if self.inbox or self.recent_execution_feedback:', '''        if self.current_plan and self.current_plan['status'] == 'active':
            if any(x['due_step'] <= step for x in self.current_plan['steps']):
                return True
        if self.inbox or self.recent_execution_feedback:''')
s=s.replace('            "current_location": world.member_locations.get(self.id),','''            "current_location": world.member_locations.get(self.id),
            "earliest_group_depart_step": step + 2,
            "own_commitment_statuses": world.commitment_statuses_for(self.id),''')
s=s.replace('                        "relationship": member.get("relationship"),','                        "relationship": member.get("relationship"),\n                        "location": member.get("location"),')
s=s.replace('"current_plan": None','"current_plan": self.current_plan')
a=s.index('        system = (',s.index('    async def decide('));b=s.index('        messages = [',a)
s=s[:a]+'''        system = (
            "You are one resident making protective-action decisions with private memory and a persistent plan. "
            "Use only the supplied observations. Give a short assessment and JSON; do not invent roads or resources. "
            "You may stay, prepare, seek_help, offer_help, or evacuate. Staying is allowed. "
            "Set plan_update only to create or revise a 1-3 step plan; null preserves the existing plan. "
            "To coordinate, use party_proposal with explicit traveler IDs, dependents, caregivers, route and vehicle. "
            "Propose departure at earliest_group_depart_step or later, allowing delivery, consent and confirmation. "
            "While negotiating choose prepare or another non-departure action. Proposals do not reserve vehicles. "
            "Respond to received proposals through message_responses; accept only if you agree to that exact party. "
            "For a confirmed trip, evacuate at its due step using departure_mode=commitment and its commitment_id. "
            "For an explicitly independent trip, use departure_mode=solo; accompany_dependents lists exactly whom you take. "
            "Evacuate means leave NOW: depart_step must equal current_step. Future intentions belong in the plan. "
            "To postpone or change a confirmed group trip, cancel_commitment_ids and propose a new version; do not silently change it. "
            "Only physically executed actions change locations. seek_help/offer_help express requests/offers and do not themselves move anyone. "
            "Information messages use messages with kind=notice. Output JSON matching this schema:\\n"
            + json.dumps(E1ResidentDecision.model_json_schema(), ensure_ascii=False)
        )
''' + s[b:]
a=s.index('        """Normalize depart steps',s.index('    def _normalize_proposal'));b=s.index('    def rule_fallback',a)
s=s[:a]+'''        """Serialize an explicit typed proposal; never invent travelers or shift times."""
        proposal = decision.party_proposal
        messages = list(decision.messages)
        if proposal is not None:
            payload = proposal.model_dump(exclude={'content'})
            payload['protocol_version'] = 'e1_party_v2'
            messages.append(OutMsg(to='household', kind='proposal',
                content=proposal.content, payload=payload))
        return decision.model_copy(update={'messages': messages})

''' + s[b:]
a=s.index('        mandatory = any(',s.index('    def rule_fallback'));b=s.index('    # ---- execution feedback',a)
s=s[:a]+'''        return E1ResidentDecision(assessment='backend unavailable; no generative decision', action='stay')

'''+s[b:]
s=s.replace('        status = getattr(outcome, "status", "unknown")','''        from copy import deepcopy
        update = getattr(decision, 'plan_update', None)
        if update is not None:
            if self.current_plan is not None:
                self.plan_history.append({**deepcopy(self.current_plan), 'ended_step': step, 'end_reason': 'revised'})
            self.current_plan = {**update.model_dump(), 'created_step': step, 'status': 'active'}
        status = getattr(outcome, "status", "unknown")''')
s=s.replace('        self.recent_execution_feedback.append(','        self.memories.append({"kind": "execution", "step": step, "status": status, "action": executed, "reason": reason})\n        self.recent_execution_feedback.append(')
s=s.replace('            self.state.evac_step = step','''            self.state.evac_step = step
            if self.current_plan:
                self.current_plan['status'] = 'completed'
                self.current_plan['completed_step'] = step''')
s=s.replace('        if status == "rejected" and reason:', '''        if self.current_plan and status == 'rejected':
            self.current_plan['last_failure'] = {'step': step, 'reason': reason}
        if status == "rejected" and reason:''')
s=s.replace('            "my_commitments": self.my_commitments,','            "my_commitments": self.my_commitments,\n            "current_plan": self.current_plan,\n            "plan_history": self.plan_history,')
p.write_text(s)
