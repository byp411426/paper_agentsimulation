"""Continuation safety gates: no paid replacement of already completed responses."""
import json
from pathlib import Path
import pytest
from ds.llm.cache import LLMCache
from scripts.comparison_cache_replay import CacheReplay


@pytest.fixture
def replay(tmp_path):
    context=CacheReplay.__new__(CacheReplay)
    context.previous=tmp_path/'old';context.previous.mkdir()
    context.run=tmp_path/'new';context.run.mkdir()
    for name in ('initial_state.json','input_events.jsonl','input_graph.json','selected_profiles.jsonl'):
        (context.previous/name).write_text('{}')
        (context.run/name).write_text('{}')
    context.completed=1;context.verified_steps=0;context.initial_verified=False
    context.expected=[{'step':1,'world':{'location':'home'}}]
    context.manifest={}
    return context


def test_prefix_cache_miss_is_rejected_before_any_backend_call(replay,tmp_path):
    cache=LLMCache(tmp_path/'cache.sqlite')
    request={'step':1,'model':'m','messages':[{'role':'user','content':'x'}],'seed':1,'temperature':0}
    with pytest.raises(ValueError,match='refuse a new paid call'):
        replay.before_call(request,cache)
    cache.put(LLMCache.make_key('m',request['messages'],1,0),'m','{}',4,2)
    replay.before_call(request,cache)
    with pytest.raises(ValueError,match='prefix must match'):
        replay.before_call({**request,'step':2},cache)
    logger=replay.logger_type()(tmp_path/'events')
    logger.dump_step(replay.expected[0]);logger.close()
    replay.before_call({**request,'step':2},cache)
    assert json.loads((replay.run/'cache_replay.json').read_text())['prefix_verified']
    cache.close()


def test_changed_replayed_state_stops_instead_of_splicing(replay,tmp_path):
    logger=replay.logger_type()(tmp_path/'events')
    with pytest.raises(ValueError,match='full state differs'):
        logger.dump_step({'step':1,'world':{'location':'safe'}})
    logger.close()
    assert replay.verified_steps==0
    assert not (tmp_path/'events/events.jsonl').read_text()


def test_changed_initial_input_is_rejected(replay):
    (replay.run/'input_graph.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='initial input differs'):
        replay.check_initial()
