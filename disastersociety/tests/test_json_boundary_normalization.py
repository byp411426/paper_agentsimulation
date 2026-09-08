import json
import pytest
from ds.llm.gateway import _normalize_model_json
from ds.llm.backends import LLMResponse
from ds.agents.e1_contracts import E1Decision
from tests.conftest import make_gateway

def test_extra_brace_preserves_entire_object_and_strings():
    data={'action':'seek_help','assessment':'Literal } inside text','plan_update':None}
    raw=json.dumps(data)
    fixed,kind=_normalize_model_json(raw+'}')
    assert json.loads(fixed)==data and kind=='one_extra_closing_brace'

@pytest.mark.parametrize('raw',['{"action":"stay"}{"action":"evacuate"}','{"action":"stay"} explanation','{"action":"stay"','{"action":"stay"}}}'])
def test_ambiguous_or_truncated_content_is_not_silently_selected(raw):
    fixed,kind=_normalize_model_json(raw)
    assert fixed==raw and kind is None
    with pytest.raises(ValueError):E1Decision.model_validate_json(fixed)

async def test_narrow_format_normalization_is_logged_without_second_model_call(tmp_path):
    class Backend:
        calls=0
        async def acomplete(self,**kw):
            self.calls+=1
            return LLMResponse(content='{"action":"seek_help"}}',prompt_tokens=3,completion_tokens=2)
    b=Backend();g=make_gateway(tmp_path,backends={'mock':b})
    d=await g.complete(step=18,agent_id='r',model='mock',messages=[{'role':'user','content':'No vehicle'}],schema=E1Decision,seed=1)
    g.flush();rows=[json.loads(l) for l in g.log_path.read_text().splitlines()]
    assert d.action=='seek_help' and b.calls==1 and g.n_failed==0 and g.n_fallback==0
    assert rows[-1]['format_normalizations']==[{'phase':'initial','kind':'one_extra_closing_brace'}]
    await g.aclose()
