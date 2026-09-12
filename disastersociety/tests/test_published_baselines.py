"""Host-boundary regressions; scripted checks are never behavioral results."""
import json
from types import SimpleNamespace

import pytest
from ds.baselines.as_support import FormatPrompt, Memory, Environment
from ds.baselines.residents import AgentSocietyResident, NativeStepDecision
from ds.agents.e1_contracts import E1Decision
from ds.agents.e1_contracts import E1ActionRequest


async def test_prompt_formatting_preserves_nested_incident_and_literal_placeholders():
    p = FormatPrompt('Literal {{"a":1}} {incident} ${profile.thought}',
                     Memory({'thought': '{incident}'}, Environment()))
    incident = json.dumps({'nested': {'literal': '{incident}'}})
    await p.format(incident=incident)
    assert p.text == 'Literal {"a":1} ' + incident + ' {incident}'


@pytest.mark.parametrize('executed,step_complete,expected', [
    (True, False, (0, False, False)),
    (True, True, (1, False, False)),
    (False, True, (0, False, True)),
])
def test_native_plan_requires_execution_and_explicit_step_completion(executed, step_complete, expected):
    resident = AgentSocietyResident(agent_id='r', household_id='h',
        profile={'age': 30, 'pums_static': {'sex': 'Female', 'employment': 'Employed'}}, vehicles={})
    plan = {'target': 'Coordinate before departing', 'index': 0, 'completed': False,
        'failed': False, 'steps': [{'intention': 'Reach agreement'}, {'intention': 'Depart'}]}
    resident.native_memory.status.data['current_plan'] = plan
    decision = NativeStepDecision(action='prepare', cognitive_step_complete=step_complete,
                                  cognitive_step_reason='Fixture assertion, not behavior')
    outcome = SimpleNamespace(status='executed' if executed else 'rejected',
                              executed_action='prepare' if executed else None, reason=None)
    resident.commit_execution(decision, outcome, step=1)
    assert (plan['index'], plan['completed'], plan['failed']) == expected
    assert resident.native_memory.status.data['gender'] == 'Female'


def test_empty_plan_is_rejected_instead_of_silently_rewritten():
    with pytest.raises(ValueError):
        E1Decision(action='stay', plan_update={'goal': 'Wait', 'steps': [], 'reason': 'No change'})
    assert E1Decision(action='stay', plan_update=None).plan_update is None


def test_incomplete_intention_is_rejected_by_world_without_becoming_fake_execution():
    from scripts.run_household_process_suite import Scene
    scene=Scene()
    before=scene.world.physical_snapshot()
    request=E1ActionRequest(action='evacuate',departure_mode='solo')
    result=scene.apply(1,{'a':request})['1:a']
    assert result.status=='rejected' and result.reason=='incomplete_departure_request'
    assert result.executed_action is None
    assert scene.world.physical_snapshot()==before
    assert scene.residents['a'].recent_execution_feedback[-1]['status']=='rejected'


def test_reference_resolution_never_overrides_choices_or_creates_consent(tmp_path):
    from scripts.run_household_process_suite import Scene
    scene=Scene();resident=scene.residents['a']
    gateway=SimpleNamespace(log_path=tmp_path/'llm_calls.jsonl')
    source={'commitment_id':'c','status':'accepted','vehicle_id':'v','route_id':'alternate','depart_step':5}
    payload={'own_commitment_statuses':[source]}
    request=E1ActionRequest(action='evacuate',departure_mode='commitment',commitment_id='c',route_id='primary')
    resolved=resident._resolve_departure_reference(request,payload=payload,gateway=gateway,step=5)
    assert (resolved.vehicle_id,resolved.route_id,resolved.depart_step)==('v','primary',5)
    assert request.vehicle_id is None  # preserve original model output
    assert not scene.hh.v2_commitments  # resolution cannot form an agreement
    record=json.loads((tmp_path/'decision_reference_resolutions.jsonl').read_text())
    assert record['resolved_fields']=={'vehicle_id':'v','depart_step':5}
    unknown=request.model_copy(update={'commitment_id':'unknown'})
    assert resident._resolve_departure_reference(unknown,payload=payload,gateway=gateway,step=5) is unknown
    source['status']='cancelled'
    assert resident._resolve_departure_reference(request,payload=payload,gateway=gateway,step=5) is request


def test_nullable_wire_syntax_does_not_change_action_or_text():
    from ds.llm.gateway import _normalize_for_schema
    text=json.dumps({'action':'prepare','assessment':'null','departure_mode':'null','route_id':'nulltown'})
    fixed,kind=_normalize_for_schema(text,E1ActionRequest)
    assert json.loads(fixed)=={'action':'prepare','assessment':'null','departure_mode':None,'route_id':'nulltown'}
    assert kind=='nullable_string_null:departure_mode'
