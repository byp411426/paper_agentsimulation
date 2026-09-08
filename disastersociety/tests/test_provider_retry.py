import json
import pytest
from ds.llm.backends import BackendError, LLMResponse
from tests.conftest import make_gateway, XSchema

@pytest.mark.parametrize('during_repair', [False, True])
async def test_transient_error_has_bounded_logged_backoff(tmp_path, monkeypatch, during_repair):
    pauses=[]
    async def sleep(seconds): pauses.append(seconds)
    monkeypatch.setattr('ds.llm.gateway.asyncio.sleep', sleep)
    class Backend:
        calls=0
        async def acomplete(self, **kwargs):
            self.calls+=1
            if during_repair and self.calls==1:
                return LLMResponse(content='invalid json',prompt_tokens=1,completion_tokens=1)
            if self.calls==(2 if during_repair else 1):raise BackendError('HTTP 520 temporary')
            return LLMResponse(content='{"x": 9}',prompt_tokens=1,completion_tokens=1)
    backend=Backend()
    gateway=make_gateway(tmp_path,backends={'mock':backend},model_cfg={'models':{'mock':{
        'backend':'mock','input_per_m':0,'output_per_m':0,'max_attempts':3,'retry_backoff_seconds':60}}})
    result=await gateway.complete(step=1,agent_id='a',model='mock',messages=[{'role':'user','content':'x'}],schema=XSchema,seed=1)
    gateway.flush()
    records=[json.loads(line) for line in gateway.log_path.read_text().splitlines()]
    assert result.x==9 and gateway.n_failed==0 and gateway.n_fallback==0
    assert pauses==[60] and backend.calls==(3 if during_repair else 2)
    assert len([r for r in records if r['status']=='provider_retry'])==1
    await gateway.aclose()
