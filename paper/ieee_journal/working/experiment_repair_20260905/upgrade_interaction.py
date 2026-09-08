from pathlib import Path
p=Path('implementation/ds/interaction/carr_empirical_v2.py');s=p.read_text().replace('from typing import Any','from typing import Any\nfrom dataclasses import replace\nfrom ds.agents.e1_contracts import PartyProposal')
s=s.replace('        care_requirements: dict[str, CareRequirement],','        care_requirements: dict[str, CareRequirement],\n        world: Any = None,')
s=s.replace('        self.run_seed = run_seed','        self.world = world\n        self.run_seed = run_seed',1)
a=s.index('    # ---- emission');s=s[:a]+'''    def _notify(self, message, step, accepted, reason, commitment=None):
        recipients={message['sender_id']} | {
            r for r,v in message.get('recipient_states',{}).items() if v['processed_step'] is not None}
        for rid in sorted(recipients):
            if rid not in self.residents:continue
            notice={'message_id': f"protocol:{message['message_id']}:{step}:{rid}:{len(self.commitment_notifications)}",
                'kind':'notice','channel':'household_protocol','sender_id':'household_protocol',
                'source_message_id':message['message_id'],'recipient_id':rid,
                'issued_step':step,'delivered_step':step,
                'content': 'Party accepted' if accepted else 'Party not accepted: '+str(reason),
                'payload':{'accepted':accepted,'reason_code':reason,'commitment_id':commitment.id if commitment else None}}
            if commitment is not None:
                notice['payload'].update(depart_step=commitment.party.depart_step,
                    route_id=commitment.party.route_id,vehicle_id=commitment.party.vehicle_id,
                    traveler_ids=sorted(commitment.party.traveler_ids))
                if rid in commitment.accepted_by:
                    self.residents[rid].my_commitments.append({**notice['payload'],
                        'source_message_id':message['message_id'],'delivered_step':step})
            self.commitment_notifications.append(notice)
            self.residents[rid].deliver_message(notice)

    def emit(self, agent, decision, clock):
        for index,msg in enumerate(decision.messages):
            payload=dict(msg.payload or {}); proposal=msg.kind=='proposal'
            if msg.to in ('household','family'):
                channel='household_dm'
                recipients=[r for r in self.households[agent.household_id].decision_member_ids if r!=agent.id]
            else:
                channel='community'
                neighbors=list(self.graph.neighbors(agent.id)) if self.graph is not None and agent.id in self.graph else []
                recipients=neighbors if msg.to in ('community','neighbors') else [msg.to] if msg.to in neighbors else []
            if payload.get('forward_official') or payload.get('source_event_id'):
                owned=any(m.get('source_event_id')==payload.get('source_event_id') for m in agent.memories)
                if not owned:payload.update(verified=False,source_event_id=None,unverified_rumor=True)
            record={'message_id':f'm{clock.t}:{agent.id}:{index}', 'sender_id':agent.id,
                'recipient_ids':recipients,'kind':msg.kind,'content':msg.content,'channel':channel,
                'payload':payload,'issued_step':clock.t,'delivered_step':None,'processed_step':None,
                'status':'sent','disposition':None,
                'recipient_states':{r:{'delivered_step':None,'processed_step':None,'disposition':None,'response_step':None} for r in recipients}}
            self.messages[record['message_id']]=record
            if proposal:
                try:party=PartyProposal.model_validate({**payload,'content':msg.content})
                except Exception:
                    record['acceptance']={'accepted':False,'reason_code':'explicit_party_fields_required','commitment_id':None}
                    record['status']='rejected';self._notify(record,clock.t,False,'explicit_party_fields_required');continue
                hh=self.households[agent.household_id]
                reason=None
                if not set(party.traveler_ids)<=set(hh.decision_member_ids):reason='invalid_travelers'
                elif not set(party.accompanying_member_ids)<=set(hh.dependent_ids):reason='invalid_dependents'
                elif agent.id not in party.traveler_ids:reason='proposer_must_join_party'
                elif party.depart_step<clock.t+2:reason='insufficient_coordination_time'
                elif channel!='household_dm':reason='party_requires_household_channel'
                if reason:
                    record['acceptance']={'accepted':False,'reason_code':reason,'commitment_id':None}
                    record['status']='rejected';self._notify(record,clock.t,False,reason);continue
                record['recipient_ids']=[r for r in party.traveler_ids if r!=agent.id]
                record['recipient_states']={r:record['recipient_states'][r] for r in record['recipient_ids']}
                if not record['recipient_ids']:self._accept_party_proposal(agent,record,clock.t)

    def process(self, agent, decision, clock):
        processed=agent.process_inbox(step=clock.t)
        for item in processed:
            m=self.messages.get(item.get('message_id'))
            if m is not None and agent.id in m['recipient_states']:
                m['recipient_states'][agent.id]['processed_step']=clock.t
                m['processed_step']=m['processed_step'] or clock.t
        for cid in getattr(decision,'cancel_commitment_ids',[]):
            hh=self.households[agent.household_id];c=hh.v2_commitments.get(cid)
            if c is not None and c.status=='accepted' and agent.id in c.accepted_by:
                hh.v2_commitments[cid]=replace(c,status='cancelled')
                dummy={'message_id':'cancel:'+cid,'sender_id':agent.id,
                    'recipient_states':{m:{'processed_step':clock.t} for m in c.accepted_by}}
                self._notify(dummy,clock.t,False,'commitment_cancelled:'+cid)
        for response in decision.message_responses:
            m=self.messages.get(response.message_id)
            if m is None or m['kind']!='proposal' or m.get('acceptance',{}).get('accepted'):continue
            state=m['recipient_states'].get(agent.id)
            if state is None or state['processed_step'] is None:continue
            if m['status']=='rejected':continue
            state.update(disposition=response.disposition,response_step=clock.t)
            if response.disposition=='rejected':
                m['status']='rejected';m['acceptance']={'accepted':False,'reason_code':'participant_declined','commitment_id':None}
                self._notify(m,clock.t,False,'participant_declined')
            else:self._accept_party_proposal(agent,m,clock.t)

    def _accept_party_proposal(self,agent,message,step,**unused):
        if message.get('acceptance',{}).get('accepted'):return
        hh=self.households[agent.household_id];p=message['payload']
        accepted={message['sender_id']}|{r for r,s in message['recipient_states'].items() if s['disposition']=='accepted'}
        travelers=set(p['traveler_ids'])
        if not travelers<=accepted:return  # pending, not a rejected agreement
        party=DepartureParty(traveler_ids=frozenset(travelers),
            accompanying_member_ids=frozenset(p.get('accompanying_member_ids',[])),
            caregiver_by_member=tuple(sorted(p.get('caregiver_by_member',{}).items())),
            vehicle_id=p['vehicle_id'],route_id=p['route_id'],depart_step=p['depart_step'])
        c=HouseholdCommitmentV2(id='commit:'+message['message_id'],protocol_version='e1_party_v2',party=party,
            accepted_by=frozenset(accepted),created_step=step,supersedes_id=p.get('supersedes_id'))
        reason=None
        if self.world is not None:
            if any(self.world.member_locations.get(m)!=('home',hh.id) for m in party.member_ids):reason='party_member_not_at_origin'
            elif party.route_id not in self.world.route_state:reason='unknown_route'
        if reason is None:
            result=hh.try_accept_commitment_v2(commitment=c,decision_capable=self.decision_capable,
                care_requirements=self.care_requirements,earliest_depart_step=step+1,party_origin=('home',hh.id))
            reason=result.reason_code
            ok=result.accepted
        else:ok=False
        message['acceptance']={'accepted':ok,'commitment_id':c.id if ok else None,'reason_code':reason,'formed_step':step if ok else None}
        message['status']='accepted' if ok else 'rejected'
        self._notify(message,step,ok,reason,c if ok else None)

    def deliver(self,clock):
        for m in self.messages.values():
            if m['status']=='rejected':continue
            if m['channel']=='community' and clock.t<=m['issued_step']:continue
            for rid,state in m['recipient_states'].items():
                if state['delivered_step'] is not None or rid not in self.residents:continue
                probability=self.household_dm_probability if m['channel']=='household_dm' else self.community_message_probability
                rng=stream_rng(self.run_seed,'e1_message_delivery',entity_id=m['message_id']+':'+rid,step=clock.t)
                if rng.random()>=probability:continue
                state['delivered_step']=clock.t
                m['delivered_step']=m['delivered_step'] or clock.t
                self.residents[rid].deliver_message({**m,'delivered_step':clock.t})
                if m['status']=='sent':m['status']='delivered'

    def snapshot(self):
        receipts=[]
        for r in self.receipts:
            agent=self.residents.get(r.resident_id)
            receipts.append((agent._receipts.get(r.receipt_id,r) if agent else r).__dict__)
        return {'messages':self.messages,'receipts':receipts,'commitment_notifications':self.commitment_notifications}
''';p.write_text(s)
p=Path('implementation/experiments/carr/empirical_v2_runner.py');s=p.read_text();needle='''        decision_capable=decision_capable,
        care_requirements=care_requirements,
    )''';assert needle in s;s=s.replace(needle,'''        decision_capable=decision_capable,
        care_requirements=care_requirements,
        world=world,
    )''');p.write_text(s)
