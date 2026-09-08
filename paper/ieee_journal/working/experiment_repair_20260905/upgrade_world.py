from pathlib import Path
p=Path('implementation/ds/world/carr_empirical_v2.py');s=p.read_text().replace('from typing import Any','from typing import Any\nfrom dataclasses import replace')
s=s.replace('        self._step = clock.t\n','''        self._step = clock.t
        for household in self.households.values():
            for c in household.active_v2_parties():
                if c.party.depart_step < clock.t:
                    household.v2_commitments[c.id] = replace(c, status='cancelled')
''',1)
a=s.index('    # ---- arbitration');b=s.index('    def snapshot(',a)
s=s[:a]+'''    def commitment_statuses_for(self, resident_id: str) -> list[dict]:
        household = self.households[self.residents[resident_id].household_id]
        return [{'commitment_id': c.id, 'status': c.status,
                 'depart_step': c.party.depart_step, 'route_id': c.party.route_id,
                 'vehicle_id': c.party.vehicle_id, 'traveler_ids': sorted(c.party.traveler_ids)}
                for c in household.v2_commitments.values() if resident_id in c.accepted_by]

    def resolve_batch(self, envelopes, clock, run_seed):
        """Read-only proposal validation; all resource changes occur at commit."""
        resolved = []
        for e in envelopes:
            d=e.decision; hh=self.households[e.agent.household_id]
            if d.action != 'evacuate':
                action=('noop',d.action)
            elif self.member_locations.get(e.agent_id) != ('home',hh.id):
                action=('rejected','resident_not_at_origin')
            elif d.depart_step != clock.t:
                action=('rejected','departure_not_due')
            elif getattr(d,'departure_mode',None)=='commitment':
                c=hh.v2_commitments.get(d.commitment_id)
                if c is None or c.status!='accepted':
                    action=('rejected','commitment_not_active')
                elif e.agent_id not in c.party.traveler_ids:
                    action=('rejected','not_a_traveler')
                elif (c.party.depart_step,c.party.route_id,c.party.vehicle_id)!=(d.depart_step,d.route_id,d.vehicle_id):
                    action=('rejected','current_intent_commitment_mismatch')
                else:
                    action=('party',c.id)
            elif getattr(d,'departure_mode',None)=='solo':
                companions=frozenset(d.accompany_dependents)
                if not companions <= set(hh.dependent_ids):
                    action=('rejected','invalid_accompanying_members')
                elif any(self.member_locations.get(m)!=('home',hh.id) for m in companions):
                    action=('rejected','party_member_not_at_origin')
                else:
                    action=('solo',None)
            else:
                action=('rejected','explicit_departure_mode_required')
            resolved.append(ResolvedIntent(decision_id=e.decision_id,agent_id=e.agent_id,
                agent=e.agent,decision=d,action=action))
        return resolved

    def apply_batch(self, resolved, clock):
        outcomes={}; groups={}
        def finish(intent,status,reason=None,commitment=None):
            outcomes[intent.decision_id]=ExecutionOutcome(
                decision_id=intent.decision_id,agent_id=intent.agent_id,status=status,
                executed_action=intent.decision.action,reason=reason,
                state_delta={'commitment_id':commitment} if commitment else {})
        ordered=sorted(resolved,key=lambda x:x.agent_id)
        stream_rng(self.run_seed,'e1_world_commit',step=clock.t).shuffle(ordered)
        for intent in ordered:
            kind,cid=intent.action;hh=self.households[intent.agent.household_id]
            if kind=='rejected':
                finish(intent,'rejected',cid);continue
            if kind=='noop':
                finish(intent,'executed');continue
            if kind=='solo':
                d=intent.decision;companions=frozenset(d.accompany_dependents)
                cid='auto_'+intent.decision_id
                c=HouseholdCommitmentV2(id=cid,protocol_version='e1_party_v2',
                    party=DepartureParty(traveler_ids=frozenset({intent.agent_id}),
                        accompanying_member_ids=companions,
                        caregiver_by_member=tuple((m,intent.agent_id) for m in sorted(companions)),
                        vehicle_id=d.vehicle_id,route_id=d.route_id,depart_step=clock.t),
                    accepted_by=frozenset({intent.agent_id}),created_step=clock.t)
                accepted=hh.try_accept_commitment_v2(commitment=c,
                    decision_capable={m:True for m in hh.decision_member_ids},
                    care_requirements=self._care_requirements,earliest_depart_step=clock.t,
                    party_origin=('home',hh.id))
                if not accepted.accepted:
                    finish(intent,'rejected',accepted.reason_code);continue
            groups.setdefault((hh.id,cid),[]).append(intent)
        for (hid,cid),intents in groups.items():
            hh=self.households[hid];c=hh.v2_commitments[cid];party=c.party
            reason=None
            if c.status!='accepted':reason='party_not_active'
            elif party.depart_step!=clock.t:reason='party_not_due'
            elif any(self.member_locations.get(m)!=('home',hid) for m in party.member_ids):reason='party_member_not_at_origin'
            elif party.route_id not in self.route_state:reason='unknown_route'
            elif not self.route_state[party.route_id]['open']:reason='route_closed'
            elif self.route_usage.get(party.route_id,0)>=self.route_state[party.route_id]['capacity_per_step']:reason='route_capacity_exhausted'
            if reason:
                hh.v2_commitments[cid]=replace(c,status='rejected')
                for intent in intents:finish(intent,'rejected',reason,cid)
                continue
            record=hh.execute_v2_party(commitment=c,step=clock.t,
                traveler_intents={i.agent_id for i in intents},origin=('home',hid),destination=self.safe_zone)
            for intent in intents:finish(intent,record.outcome,record.reason_code,cid)
            if record.outcome=='executed':
                self.route_usage[party.route_id]=self.route_usage.get(party.route_id,0)+1
                for m in party.member_ids:self.member_locations[m]=self.safe_zone
        return outcomes

'''+s[b:];p.write_text(s)
# Preserve causal direction of revisions and avoid partially cancelling on failed acceptance.
p=Path('implementation/ds/households/state.py');s=p.read_text();a=s.index('        supersedes_id = commitment.supersedes_id',s.index('    def try_accept_commitment_v2'));b=s.index('        accepted = replace(',a)
s=s[:a]+'''        supersedes_id = commitment.supersedes_id
        overlaps=[active for active in self.active_v2_parties() if active.id!=commitment.id
            and (active.party.vehicle_id==party.vehicle_id or bool(active.party.member_ids & all_party_members))]
        if any(active.id!=supersedes_id for active in overlaps):
            return CommitmentAcceptanceResult(False,None,'active_party_conflict')
        if supersedes_id is not None:
            previous=self.v2_commitments.get(supersedes_id)
            if previous is None:
                return CommitmentAcceptanceResult(False,None,'unknown_superseded_commitment')
        for active in overlaps:
            self.v2_commitments[active.id]=replace(active,status='cancelled')
'''+s[b:];p.write_text(s)
