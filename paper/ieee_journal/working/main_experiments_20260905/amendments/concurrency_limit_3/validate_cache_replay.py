"""Offline replay of successful responses; no credential or network access."""
import contextlib
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

Q = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Q))
import worker
from ds.llm.backends import BackendFatalError


class CacheMissStop:
    calls = 0

    async def acomplete(self, **kwargs):
        self.calls += 1
        raise BackendFatalError('OFFLINE_CACHE_MISS_NO_NETWORK')


def main():
    target = Q / 'amendments/concurrency_limit_3'
    old_attempt = Q / 'runs/100hh_seed101/attempt1'
    source_cache = old_attempt / 'cache.sqlite'
    original_hash = hashlib.sha256(source_cache.read_bytes()).hexdigest()
    worker.MockBackend = CacheMissStop
    sys.argv = ['worker.py', '--households', '100', '--seed', '101',
                '--attempt', '903', '--backend', 'mock',
                '--resume-cache', str(source_cache)]
    with (target / 'offline_console.log').open('w') as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            rc = worker.main()
    replay = Q / 'offline/100hh_seed101/attempt903'
    name = 'carr_s_e1_repaired_100_20260905'
    original_events = (old_attempt / name / 'events/events.jsonl').read_bytes()
    replay_events = (replay / name / 'events/events.jsonl').read_bytes()
    status = json.loads((replay / 'status.json').read_text())
    with sqlite3.connect(f'file:{source_cache}?mode=ro', uri=True) as db:
        cached_rows = db.execute('SELECT COUNT(*) FROM cache').fetchone()[0]
    result = {
        'passed': rc == 2 and original_events == replay_events
                  and len(original_events.splitlines()) == 9
                  and 'OFFLINE_CACHE_MISS_NO_NETWORK' in status.get('abort_reason', '')
                  and status['gateway']['n_ok'] == 0
                  and status['gateway']['n_cache'] == cached_rows
                  and hashlib.sha256(source_cache.read_bytes()).hexdigest() == original_hash,
        'mode': 'cache-only; backend refuses every missing response without network access',
        'prefix_complete_steps': len(replay_events.splitlines()),
        'prefix_events_byte_identical': original_events == replay_events,
        'cached_successful_responses': cached_rows,
        'cache_hits': status['gateway']['n_cache'],
        'new_successful_calls': status['gateway']['n_ok'],
        'expected_stop_reason': status.get('abort_reason'),
        'original_cache_sha256_before': original_hash,
        'original_cache_sha256_after': hashlib.sha256(source_cache.read_bytes()).hexdigest(),
        'freeze_sha256': hashlib.sha256((Q / 'freeze.json').read_bytes()).hexdigest(),
    }
    (target / 'offline_replay_check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
