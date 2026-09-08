"""Replay the three accepted jobs and interrupted 100hh prefix without a network."""
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


class CacheOnly:
    calls = 0

    async def acomplete(self, **kwargs):
        self.calls += 1
        raise BackendFatalError('OFFLINE_CACHE_MISS_NO_NETWORK')


def main():
    worker.MockBackend = CacheOnly
    target = Q / 'amendments/provider_credit_stop'
    checks = []
    for households, seed, attempt in [(100, 101, 3)]:
        source = Q / f'runs/{households}hh_seed{seed}/attempt{attempt}'
        cache = source / 'cache.sqlite'
        original_hash = hashlib.sha256(cache.read_bytes()).hexdigest()
        sys.argv = ['worker.py', '--households', str(households), '--seed', str(seed),
                    '--attempt', '905', '--backend', 'mock', '--resume-cache', str(cache)]
        with (target / f'offline_{households}hh_seed{seed}.log').open('w') as log:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                rc = worker.main()
        replay = Q / f'offline/{households}hh_seed{seed}/attempt905'
        run_name = f'carr_s_e1_repaired_{households}_20260905'
        old_events = (source / run_name / 'events/events.jsonl').read_bytes()
        new_events = (replay / run_name / 'events/events.jsonl').read_bytes()
        status = json.loads((replay / 'status.json').read_text())
        with sqlite3.connect(f'file:{cache}?mode=ro', uri=True) as db:
            rows = db.execute('SELECT COUNT(*) FROM cache').fetchone()[0]
        correct_end = (rc == 0 and status['status'] == 'VALID' if households == 24 else
                       rc == 2 and 'OFFLINE_CACHE_MISS_NO_NETWORK' in status.get('abort_reason', ''))
        check = {'households': households, 'seed': seed, 'original_attempt': attempt,
                 'complete_steps': len(new_events.splitlines()),
                 'events_byte_identical': old_events == new_events,
                 'cached_rows': rows, 'cache_hits': status['gateway']['n_cache'],
                 'new_successful_calls': status['gateway']['n_ok'],
                 'source_cache_unchanged': hashlib.sha256(cache.read_bytes()).hexdigest() == original_hash,
                 'correct_terminal_state': correct_end}
        check['passed'] = (correct_end and check['events_byte_identical'] and check['source_cache_unchanged']
                           and check['cache_hits'] == rows and check['new_successful_calls'] == 0)
        checks.append(check)
        print(json.dumps(check), flush=True)
    result = {'passed': all(c['passed'] for c in checks), 'mode': 'offline cache-only',
              'freeze_sha256': hashlib.sha256((Q / 'freeze.json').read_bytes()).hexdigest(), 'checks': checks}
    (target / 'replay_checks.json').write_text(json.dumps(result, indent=2) + '\n')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
