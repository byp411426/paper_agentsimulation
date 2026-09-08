from types import SimpleNamespace as NS
import json
import pytest
from pydantic import ValidationError
from ds.agents.carr_empirical_v2 import CarrEmpiricalResidentV2
from ds.agents.e1_contracts import E1Decision,PartyProposal,ProtectivePlan
from ds.households.state import Household,VehicleResource,CareRequirement,HouseholdCommitmentV2,DepartureParty
from ds.world.carr_empirical_v2 import CarrEmpiricalWorldV2
from ds.interaction.carr_empirical_v2 import CarrEmpiricalInteractionV2
from ds.kernel.actions import IntentEnvelope,ExecutionOutcome
from ds.kernel.clock import Clock

def setup():
    residents={r:CarrEmpiricalResidentV2(agent_id=r,household_id='H',profile={'age':40,'decision_capable':True},vehicles={}) for r in ['a','b','c']}
    hh=Household(id='H',member_ids=('a','b','c','child'),decision_member_ids=('a','b','c'),dependent_ids=('child',),vehicles={'v':VehicleResource(id='v',location=('home','H'),capacity=4)})
    care={'child':CareRequirement(member_id='child',assistance_type='minor',caregiver_id=None)}
    world=CarrEmpiricalWorldV2(households={'H':hh},residents=residents,config={'primary_route_id':'primary','alternate_route_id':'alternate','closure_step':3,'safe_zone':'safe','care_requirements':care},run_seed=7)
    ix=CarrEmpiricalInteractionV2(run_seed=7,household_dm_probability=1,community_message_probability=1,social_graph=None,residents=residents,households={'H':hh},decision_capable={r:True for r in residents},care_requirements=care,world=world)
    return residents,hh,world,ix

def decision(**kw):return E1Decision(**{'action':'prepare',**kw})
def apply(world,residents,step,ds):
    clock=Clock(30,step);world.update(clock)
    env=[IntentEnvelope(decision_id=f'{step}:{r}',agent_id=r,agent=residents[r],decision=d) for r,d in ds.items()]
    before=json.dumps(world.snapshot(),sort_keys=True)
    resolved=world.resolve_batch(env,clock,7)
    assert json.dumps(world.snapshot(),sort_keys=True)==before, 'resolve phase changed shared state'
    outcomes=world.apply_batch(resolved,clock)
    for r,d in ds.items():residents[r].commit_execution(d,outcomes[f'{step}:{r}'],step=step)
    return outcomes

def propose(ix,rs,step,depart,route='primary'):
    p=PartyProposal(traveler_ids=['a','b','c'],accompanying_member_ids=['child'],caregiver_by_member={'child':'a'},vehicle_id='v',route_id=route,depart_step=depart,content='Travel together')
    d=rs['a']._normalize_proposal(decision(party_proposal=p),step=step)
    ix.emit(rs['a'],d,Clock(30,step));ix.deliver(Clock(30,step))
    return list(ix.messages)[-1]

def accept(ix,rs,r,mid,step):
    ix.process(rs[r],decision(message_responses=[{'message_id':mid,'disposition':'accepted'}]),Clock(30,step))

def test_complete_household_trip_after_closed_route_and_revised_agreement():
    rs,hh,w,ix=setup();mid=propose(ix,rs,1,5)
    assert not hh.v2_commitments and hh.vehicles['v'].reserved_by is None
    accept(ix,rs,'b',mid,2);assert not hh.v2_commitments
    accept(ix,rs,'c',mid,2);c=next(iter(hh.v2_commitments.values()))
    assert c.accepted_by==frozenset(rs) and c.created_step==2
    assert all(r.my_commitments for r in rs.values())
    ds={r:decision(action='evacuate',departure_mode='commitment',commitment_id=c.id,depart_step=5,vehicle_id='v',route_id='primary') for r in rs}
    outcomes=apply(w,rs,5,ds)
    assert all(o.reason=='route_closed' for o in outcomes.values())
    assert all(r.perceived_routes['primary']['open'] is False for r in rs.values())
    assert hh.vehicles['v'].location==('home','H')
    mid2=propose(ix,rs,6,8,'alternate');accept(ix,rs,'b',mid2,7);accept(ix,rs,'c',mid2,7)
    c2=hh.v2_commitments['commit:'+mid2]
    ds={r:decision(action='evacuate',departure_mode='commitment',commitment_id=c2.id,depart_step=8,vehicle_id='v',route_id='alternate') for r in rs}
    outcomes=apply(w,rs,8,ds)
    assert all(o.status=='executed' for o in outcomes.values())
    assert set(w.member_locations)==set(hh.member_ids)
    assert set(w.member_locations.values())=={'safe'}
    assert len([x for x in hh.departure_records if x.outcome=='executed'])==1
    assert all(not r.should_wake(events=[],world=w,step=9) for r in rs.values())

def test_current_postponed_intent_never_executes_old_due_commitment():
    rs,hh,w,ix=setup();mid=propose(ix,rs,1,4,'alternate');accept(ix,rs,'b',mid,2);accept(ix,rs,'c',mid,2)
    d=decision(action='evacuate',departure_mode='commitment',commitment_id='commit:'+mid,depart_step=5,vehicle_id='v',route_id='alternate')
    out=apply(w,rs,4,{'a':d})
    assert out['4:a'].reason=='departure_not_due' and not hh.departure_records
    assert w.member_locations['a']==('home','H')

def test_ambiguous_proposal_and_implicit_solo_are_not_accepted():
    with pytest.raises(ValidationError):PartyProposal(vehicle_id='v',route_id='primary',depart_step=5,content='go')
    with pytest.raises(ValidationError):decision(action='evacuate',vehicle_id='v',route_id='primary',depart_step=2)
    p=PartyProposal(traveler_ids=['a','b'],vehicle_id='v',route_id='primary',depart_step=5,content='go')
    with pytest.raises(ValidationError):decision(action='evacuate',departure_mode='solo',vehicle_id='v',route_id='primary',depart_step=2,party_proposal=p)

def test_undelivered_response_and_decline_do_not_make_joint_agreement():
    rs,hh,w,ix=setup();mid=propose(ix,rs,1,5)
    ix.messages[mid]['recipient_states']['c']['processed_step']=None
    rs['c'].inbox=[];accept(ix,rs,'c',mid,2);accept(ix,rs,'b',mid,2)
    assert not hh.v2_commitments
    rs['c'].deliver_message(ix.messages[mid]);ix.process(rs['c'],decision(message_responses=[{'message_id':mid,'disposition':'rejected'}]),Clock(30,3))
    assert not hh.v2_commitments and ix.messages[mid]['acceptance']['reason_code']=='participant_declined'
    assert any('participant_declined' in n['content'] for n in ix.commitment_notifications)

def test_timing_rejection_is_returned_to_sender_and_no_vehicle_reserved():
    rs,hh,w,ix=setup();mid=propose(ix,rs,1,2)
    assert ix.messages[mid]['acceptance']['reason_code']=='insufficient_coordination_time'
    assert any(x.get('payload',{}).get('reason_code')=='insufficient_coordination_time' for x in rs['a'].inbox)
    assert not hh.v2_commitments

def test_private_plan_persists_and_execution_feedback_updates_it():
    rs,hh,w,ix=setup();a=rs['a']
    plan=ProtectivePlan(goal='Keep household safe',steps=[{'action':'coordinate','due_step':3,'description':'Discuss transport'}],reason='warning received')
    out=ExecutionOutcome(decision_id='1:a',agent_id='a',status='executed',executed_action='prepare')
    a.commit_execution(decision(plan_update=plan),out,step=1)
    a.commit_execution(decision(),out,step=2)
    assert a.current_plan['created_step']==1
    assert rs['b'].current_plan is None
    payload=a._prompt_payload(world=w,step=3)
    assert payload['private_process']['current_plan']['goal']=='Keep household safe'
    rejected=ExecutionOutcome(decision_id='3:a',agent_id='a',status='rejected',executed_action='evacuate',reason='vehicle_not_at_origin')
    a.commit_execution(decision(),rejected,step=3)
    assert a.current_plan['last_failure']['reason']=='vehicle_not_at_origin'

def test_cancel_releases_agreement_and_notifies_participants():
    rs,hh,w,ix=setup();mid=propose(ix,rs,1,5);accept(ix,rs,'b',mid,2);accept(ix,rs,'c',mid,2)
    cid='commit:'+mid;ix.process(rs['a'],decision(cancel_commitment_ids=[cid]),Clock(30,3))
    assert hh.v2_commitments[cid].status=='cancelled' and not hh.active_v2_parties()
    assert any('commitment_cancelled' in n['content'] for n in ix.commitment_notifications)

def test_solo_has_explicit_companions_and_no_duplicate_departure():
    rs,hh,w,ix=setup();d=decision(action='evacuate',departure_mode='solo',route_id='primary',vehicle_id='v',depart_step=2,accompany_dependents=['child'])
    out=apply(w,rs,2,{'a':d});assert out['2:a'].status=='executed'
    assert w.member_locations['child']=='safe' and w.member_locations['b']==('home','H')
    d=d.model_copy(update={'depart_step':3,'route_id':'alternate'})
    out=apply(w,rs,3,{'a':d});assert out['3:a'].reason=='resident_not_at_origin'
    assert len(hh.departure_records)==1

def test_long_explanation_does_not_abort_or_change_action_fields():
    p=ProtectivePlan(goal='g'*400,steps=[{'action':'coordinate','due_step':4,'description':'d'*400}],reason='r'*500)
    d=decision(plan_update=p)
    assert d.action=='prepare' and d.plan_update.steps[0].due_step==4
    assert len(d.plan_update.reason)==240 and len(d.plan_update.goal)==180

def test_received_proposal_is_not_treated_as_new_proposal():
    rs,hh,w,ix=setup();mid=propose(ix,rs,1,3,'alternate')
    payload=rs['b']._prompt_payload(world=w,step=2)
    assert payload['received_proposal_earliest_depart_step']==3
    assert payload['new_proposal_earliest_depart_step']==4
    accept(ix,rs,'b',mid,2);accept(ix,rs,'c',mid,2)
    assert hh.v2_commitments['commit:'+mid].party.depart_step==3
