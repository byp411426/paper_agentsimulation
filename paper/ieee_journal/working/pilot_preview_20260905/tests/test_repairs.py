from types import SimpleNamespace as NS
from ds.agents.carr_empirical_v2 import CarrEmpiricalResidentV2
from ds.agents.decide import ResidentDecision
from ds.households.state import Household, VehicleResource
from ds.interaction.carr_empirical_v2 import CarrEmpiricalInteractionV2
from ds.world.carr_empirical_v2 import CarrEmpiricalWorldV2
from ds.kernel.actions import IntentEnvelope
from ds.kernel.clock import Clock

def parts():
    people={p:CarrEmpiricalResidentV2(agent_id=p,household_id='H',profile={'age':40,'decision_capable':True},vehicles={}) for p in ['a','b','c']}
    hh=Household(id='H',member_ids=('a','b','c','child'),decision_member_ids=('a','b','c'),dependent_ids=('child',),vehicles={'v':VehicleResource(id='v',location=('home','H'),capacity=5)})
    w=CarrEmpiricalWorldV2(households={'H':hh},residents=people,config={'safe_zone':'safe','primary_route_id':'primary','alternate_route_id':'alternate'},run_seed=7)
    ix=CarrEmpiricalInteractionV2(run_seed=7,household_dm_probability=1,community_message_probability=0.15,social_graph=None,residents=people,households={'H':hh},decision_capable={**{x:True for x in people},'child':False},care_requirements={})
    return people,hh,w,ix

def envelope(agent, step, depart):
    d=ResidentDecision(action='evacuate',route_id='primary',vehicle_id='v',depart_step=depart)
    return IntentEnvelope(decision_id=f'{step}:{agent.id}',agent_id=agent.id,agent=agent,decision=d)

def test_all_members_have_initial_locations():
    people,hh,w,ix=parts()
    assert set(w.member_locations)==set(hh.member_ids)

def test_terminal_agent_cannot_wake_or_depart_again():
    people,hh,w,ix=parts();a=people['a'];w.member_locations['a']='safe'
    a.recent_execution_feedback.append({'step':1});a.inbox.append({'kind':'unrelated'})
    assert not a.should_wake(events=[],world=w,step=2)
    clock=Clock(30,2);w.update(clock)
    rs=w.resolve_batch([envelope(a,2,2)],clock,7)
    result=w.apply_batch(rs,clock)
    assert result['2:a'].reason=='resident_not_at_origin'
    assert not hh.departure_records

def test_future_party_waits_then_executes_once():
    people,hh,w,ix=parts();a=people['a'];clock=Clock(30,2);w.update(clock)
    result=w.apply_batch(w.resolve_batch([envelope(a,2,3)],clock,7),clock)
    assert result['2:a'].reason=='party_not_due'
    assert w.member_locations['a']==('home','H') and not hh.departure_records
    clock.tick();w.update(clock)
    result=w.apply_batch(w.resolve_batch([envelope(a,3,3)],clock,7),clock)
    assert result['3:a'].status=='executed' and len(hh.departure_records)==1
    assert hh.departure_records[0].step==3

def test_response_requires_delivery_and_all_travelers_accept():
    people,hh,w,ix=parts()
    msg=NS(to='household',kind='proposal',content='Travel together',payload={'protocol_version':'e1_party_v2','traveler_ids':['a','b','c'],'vehicle_id':'v','route_id':'primary','depart_step':5})
    ix.emit(people['a'],NS(messages=[msg]),Clock(30,1));mid=next(iter(ix.messages))
    response=NS(message_responses=[NS(message_id=mid,disposition='accepted')])
    ix.process(people['b'],response,Clock(30,1))
    assert not hh.v2_commitments
    ix.deliver(Clock(30,1))
    assert all(s['delivered_step']==1 for s in ix.messages[mid]['recipient_states'].values())
    ix.process(people['b'],response,Clock(30,2))
    assert not hh.v2_commitments
    ix.process(people['c'],response,Clock(30,2))
    assert len(hh.v2_commitments)==1
    c=next(iter(hh.v2_commitments.values()))
    assert c.accepted_by==frozenset({'a','b','c'}) and c.created_step==2
    assert {n['recipient_id'] for n in ix.commitment_notifications}=={'a','b','c'}
    assert all(n['source_message_id']==mid for n in ix.commitment_notifications)

def test_closed_route_rejection_does_not_leak_before_execution():
    people,hh,w,ix=parts();a=people['a'];clock=Clock(30,9);w.update(clock)
    assert a.perceived_routes['primary']['open']
    env=envelope(a,9,9);result=w.apply_batch(w.resolve_batch([env],clock,7),clock)
    assert result['9:a'].reason=='route_closed'
    a.commit_execution(env.decision,result['9:a'],step=9)
    assert not a.perceived_routes['primary']['open']
    assert not hh.departure_records

def test_current_time_identity_present_without_future_route_truth():
    people,hh,w,ix=parts();payload=people['a']._prompt_payload(world=w,step=2)
    assert payload['current_step']==2 and payload['resident_id']=='a'
    assert 'route_state' not in payload['observed_now']
    assert payload['current_location']==('home','H')
