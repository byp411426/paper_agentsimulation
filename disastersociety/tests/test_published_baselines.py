"""Host-boundary regressions; scripted checks are never behavioral results."""
import json
from types import SimpleNamespace

import pytest
from ds.baselines.as_support import FormatPrompt, Memory, Environment
from ds.baselines.residents import AgentSocietyResident, NativeStepDecision
from ds.agents.e1_contracts import E1Decision


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

