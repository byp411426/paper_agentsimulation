from ds.agents.e1_contracts import E1Decision
from ds.llm.backends import LLMResponse
from tests.conftest import make_gateway
import json
import pytest
from ds.llm.backends import BackendFatalError
from ds.llm.gateway import BudgetExceeded, LLMBackendUnavailable, LLMCallFailed

INVALID_WALK = '{"action":"evacuate","departure_mode":"solo","depart_step":12,"route_id":"primary","vehicle_id":null}'


def recovery_models(*, repairs=2, priced=False):
    return {'models': {'mock': {'backend': 'mock', 'max_schema_repairs': repairs,
                               'input_per_m': 1000000.0 if priced else 0.0,
                               'output_per_m': 0.0}}}


class RepeatedWalkBackend:
    def __init__(self, final='{"action":"seek_help"}'):
        self.calls = 0
        self.final = final
        self.messages = []

    async def acomplete(self, **kw):
        self.calls += 1
        self.messages.append(kw['messages'])
        if self.calls < 3:
            content = INVALID_WALK
        elif isinstance(self.final, Exception):
            raise self.final
        else:
            content = self.final
        return LLMResponse(content=content, prompt_tokens=1, completion_tokens=1)


async def test_additional_repair_explains_null_vehicle_without_inventing_resources(tmp_path):
    backend = RepeatedWalkBackend()
    gateway = make_gateway(tmp_path, backends={'mock': backend}, model_cfg=recovery_models())
    messages = [{'role': 'user', 'content': 'There are no household vehicles.'}]
    args = dict(step=12, agent_id='r', model='mock', messages=messages,
                schema=E1Decision, seed=7)
    try:
        result = await gateway.complete(**args)
        assert result.action == 'seek_help' and result.vehicle_id is None
        assert 'final allowed' not in backend.messages[1][-1]['content']
        assert 'on-foot evacuation is not implemented' in backend.messages[2][-1]['content']
        assert 'Do not invent vehicles' in backend.messages[2][-1]['content']
        assert backend.calls == 3 and gateway.n_ok == 1
        assert gateway.n_failed == gateway.n_fallback == 0
        assert gateway.live_prompt_tokens == gateway.live_completion_tokens == 3
        cached = await gateway.complete(**args)
        assert cached == result and backend.calls == 3 and gateway.n_cache == 1
        records = [json.loads(line) for line in gateway.log_path.read_text().splitlines()]
        assert records[0]['schema_repairs'] == 2
        assert messages == [{'role': 'user', 'content': 'There are no household vehicles.'}]
    finally:
        await gateway.aclose()
        gateway.cache.close()


@pytest.mark.parametrize('repairs, expected_calls', [(1, 2), (2, 3)])
async def test_schema_recovery_remains_bounded_and_invalid_actions_are_not_cached(tmp_path, repairs, expected_calls):
    backend = RepeatedWalkBackend(final=INVALID_WALK)
    gateway = make_gateway(tmp_path, backends={'mock': backend}, model_cfg=recovery_models(repairs=repairs))
    try:
        with pytest.raises(LLMCallFailed):
            await gateway.complete(step=12, agent_id='r', model='mock', messages=[], schema=E1Decision, seed=7)
        assert backend.calls == expected_calls and gateway.n_failed == 1
        assert gateway.n_ok == gateway.n_fallback == 0
        assert gateway.cache.db.execute('SELECT COUNT(*) FROM cache').fetchone()[0] == 0
    finally:
        await gateway.aclose()
        gateway.cache.close()


async def test_additional_schema_repair_preserves_fatal_provider_stop(tmp_path):
    backend = RepeatedWalkBackend(final=BackendFatalError('credential unavailable'))
    gateway = make_gateway(tmp_path, backends={'mock': backend}, model_cfg=recovery_models())
    try:
        with pytest.raises(LLMBackendUnavailable):
            await gateway.complete(step=12, agent_id='r', model='mock', messages=[], schema=E1Decision, seed=7)
        assert backend.calls == 3 and gateway.n_failed == 1
        assert gateway.n_ok == gateway.n_fallback == 0
    finally:
        await gateway.aclose()
        gateway.cache.close()


async def test_budget_stops_before_additional_schema_call(tmp_path):
    backend = RepeatedWalkBackend()
    gateway = make_gateway(tmp_path, backends={'mock': backend}, budget=2, model_cfg=recovery_models(priced=True))
    try:
        with pytest.raises(BudgetExceeded):
            await gateway.complete(step=12, agent_id='r', model='mock', messages=[], schema=E1Decision, seed=7)
        assert backend.calls == 2 and gateway.spent == 2
        assert gateway.n_ok == gateway.n_fallback == 0
    finally:
        await gateway.aclose()
        gateway.cache.close()

async def test_schema_repair_reports_conditional_resource_requirement(tmp_path):
    class Backend:
        calls=0
        async def acomplete(self, **kw):
            self.calls+=1
            if self.calls==1:
                return LLMResponse(content='{"action":"evacuate","departure_mode":"solo","depart_step":7,"route_id":"primary","vehicle_id":null}',prompt_tokens=1,completion_tokens=1)
            repair=kw['messages'][-1]['content']
            assert 'evacuate requires explicit departure_mode, depart_step, route_id and vehicle_id' in repair
            assert 'inventing resources' in repair
            return LLMResponse(content='{"action":"seek_help"}',prompt_tokens=1,completion_tokens=1)
    b=Backend();g=make_gateway(tmp_path,backends={'mock':b})
    result=await g.complete(step=7,agent_id='r',model='mock',messages=[{'role':'user','content':'No vehicle available.'}],schema=E1Decision,seed=7)
    assert result.action=='seek_help' and b.calls==2 and g.n_failed==0 and g.n_fallback==0
    await g.aclose()
