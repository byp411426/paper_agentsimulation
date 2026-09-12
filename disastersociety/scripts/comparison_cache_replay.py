"""Exact cache replay after an operational budget stop; never splice event logs."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from ds.kernel.logger import RunLogger
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMGateway


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class CacheReplay:
    def __init__(self, previous, current_root, method, registry, profiles, total_budget, config):
        self.previous = Path(previous).resolve()
        if (self.previous/'cache_replay.json').exists():
            raise ValueError('Nested continuations require explicit cumulative accounting')
        self.status = read(self.previous/'execution_status.json')
        if self.status['status'] != 'ABORTED' or self.status.get('reason_code') != 'BUDGET_EXCEEDED':
            raise ValueError('Replay is only for a documented budget stop')
        provenance = read(self.previous/'provenance.json')
        import yaml
        from copy import deepcopy
        prior_config=yaml.safe_load((self.previous/'execution_config.yaml').read_text())
        normalized=deepcopy(config)
        normalized['llm']['budget_usd']=prior_config['llm']['budget_usd']
        if normalized != prior_config or provenance['python_hash_seed'] != os.environ.get('PYTHONHASHSEED'):
            raise ValueError('Scenario, seed, or hash seed changed')
        if provenance['method'] != method or provenance['kind'] != 'paired_single_seed_real_model_comparison':
            raise ValueError('Wrong method or non-real source')
        if provenance['model_registry_sha256'] != digest(registry) or provenance['profiles_sha256'] != digest(profiles):
            raise ValueError('Model settings or population changed')
        for relative, expected in provenance['code_sha256'].items():
            # Only the launching script gains this optional replay path. All
            # cognitive, schema, world, gateway and engine code must be exact.
            if relative != 'scripts/run_published_comparison.py' and digest(current_root/relative) != expected:
                raise ValueError('Runtime changed: '+relative)
        self.expected = [json.loads(l) for l in (self.previous/'events/events.jsonl').read_text().splitlines()]
        self.completed = self.status['completed_steps']
        if [e['step'] for e in self.expected] != list(range(1, self.completed+1)):
            raise ValueError('Source has an incomplete event prefix')
        self.prior_cost = self.status['gateway']['spent']
        if total_budget <= self.prior_cost:
            raise ValueError('Total operational allowance must cover prior usage')
        self.remaining_budget = total_budget-self.prior_cost
        self.verified_steps = 0
        self.initial_verified = False
        self.run = None
        self.manifest = {
            'kind':'same_trajectory_cache_replay_after_budget_stop',
            'previous_run':str(self.previous), 'previous_completed_steps':self.completed,
            'previous_status_sha256':digest(self.previous/'execution_status.json'),
            'previous_cache_sha256':digest(self.previous/'llm_cache.sqlite'),
            'previous_gateway':self.status['gateway'],
            'previous_wall_clock_seconds':self.status['wall_clock_seconds'],
            'previous_config_sha256':digest(self.previous/'execution_config.yaml'),
            'previous_operational_budget_usd':prior_config['llm']['budget_usd'],
            'total_operational_budget_usd':total_budget,
            'additional_operational_budget_usd':self.remaining_budget,
            'reason':'Complete the fixed 25-step task; budget is not exposed to agents or a performance target',
            'prefix_verified':False,
        }

    def install(self, run):
        self.run = Path(run)
        with sqlite3.connect('file:'+str(self.previous/'llm_cache.sqlite')+'?mode=ro',uri=True) as source:
            with sqlite3.connect(self.run/'llm_cache.sqlite') as destination:
                source.backup(destination)
        self.save()

    def save(self):
        self.manifest.update(verified_steps=self.verified_steps,
            prefix_verified=self.initial_verified and self.verified_steps==self.completed)
        (self.run/'cache_replay.json').write_text(json.dumps(self.manifest,indent=2))

    def check_initial(self):
        if not self.initial_verified:
            for name in ('initial_state.json','input_events.jsonl','input_graph.json','selected_profiles.jsonl'):
                if digest(self.previous/name) != digest(self.run/name):
                    raise ValueError('Replay initial input differs: '+name)
            self.initial_verified = True

    def before_call(self, kwargs, cache):
        self.check_initial()
        key = LLMCache.make_key(kwargs['model'],kwargs['messages'],kwargs['seed'],kwargs.get('temperature',.7))
        if kwargs['step'] <= self.completed and cache.get(key) is None:
            raise ValueError('Replay cache miss inside completed prefix; refuse a new paid call')
        if kwargs['step'] > self.completed and self.verified_steps != self.completed:
            raise ValueError('Replay prefix must match before continuation')

    def logger_type(self):
        context = self
        class VerifiedReplayLogger(RunLogger):
            def dump_step(self, record):
                context.check_initial()
                # Normalize the same tuple/set serialization used by the logger.
                from ds.kernel.logger import _json_default
                normalized = json.loads(json.dumps(record,default=_json_default))
                if record['step'] <= context.completed:
                    if normalized != context.expected[record['step']-1]:
                        raise ValueError('Replayed full state differs at step '+str(record['step']))
                    context.verified_steps = record['step']
                super().dump_step(record)
                context.save()
        return VerifiedReplayLogger


class ReplayGateway(LLMGateway):
    def __init__(self, *, replay, **kwargs):
        self.replay = replay
        super().__init__(**kwargs)

    async def complete(self, **kwargs):
        self.replay.before_call(kwargs,self.cache)
        return await super().complete(**kwargs)
