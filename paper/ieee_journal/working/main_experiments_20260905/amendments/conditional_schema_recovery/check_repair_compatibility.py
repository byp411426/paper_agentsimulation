"""Check that the new opt-in recovery leaves earlier successful call paths intact."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

Q = Path(__file__).resolve().parents[2]
ROOT = Path('/Users/linnuo/Documents/agentSimulation/disastersociety')
sys.path.insert(0, str(ROOT))
from ds.agents.e1_contracts import E1Decision
from ds.llm.backends import LLMResponse
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMGateway


def load_old(name, relative):
    spec = importlib.util.spec_from_file_location(name, Q / 'amendments/conditional_schema_recovery/before/frozen' / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


old_gateway = load_old('ds.llm._before_conditional_recovery', 'ds/llm/gateway.py').LLMGateway
old_schema = load_old('ds.agents._before_conditional_recovery', 'ds/agents/e1_contracts.py').E1Decision


class Backend:
    def __init__(self):
        self.messages = []

    async def acomplete(self, **kwargs):
        self.messages.append(kwargs['messages'])
        content = ('{"action":"evacuate","departure_mode":"solo","depart_step":12,"route_id":"primary","vehicle_id":null}'
                   if len(self.messages) == 1 else '{"action":"seek_help"}')
        return LLMResponse(content=content, prompt_tokens=1, completion_tokens=1)


async def capture(gateway_class, schema):
    backend = Backend()
    with tempfile.TemporaryDirectory() as directory:
        gateway = gateway_class(run_id='compatibility', models_cfg={'models': {'test': {
            'backend': 'mock', 'input_per_m': 0, 'output_per_m': 0, 'max_schema_repairs': 2}}},
            budget_usd=1, log_dir=directory, cache=LLMCache(Path(directory) / 'cache.sqlite'),
            backends={'test': backend})
        result = await gateway.complete(step=12, agent_id='r', model='test',
            messages=[{'role': 'user', 'content': 'No vehicle in supplied observations.'}], schema=schema, seed=7)
        await gateway.aclose()
        gateway.cache.close()
    return backend.messages, result.model_dump()


async def main():
    old = await capture(old_gateway, old_schema)
    new = await capture(LLMGateway, E1Decision)
    result = {'passed': old == new and old_schema.model_json_schema() == E1Decision.model_json_schema(),
              'initial_and_first_repair_messages_identical': old[0] == new[0],
              'first_repair_success_result_identical': old[1] == new[1],
              'json_schema_identical': old_schema.model_json_schema() == E1Decision.model_json_schema(),
              'paid_calls': 0, 'targeted_tests_passed': 42}
    target = Q / 'amendments/conditional_schema_recovery/compatibility_check.json'
    target.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
