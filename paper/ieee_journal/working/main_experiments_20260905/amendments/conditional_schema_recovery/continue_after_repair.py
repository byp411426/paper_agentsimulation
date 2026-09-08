"""Resume the diagnosed original job, then finish the original seed list."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

Q = Path(__file__).resolve().parents[2]


def main():
    with (Q / 'batch_execution.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        review = json.loads((Q / 'first_seed_review.json').read_text())
        replay = json.loads((Q / 'amendments/conditional_schema_recovery/replay_checks.json').read_text())
        current_hash = hashlib.sha256((Q / 'freeze.json').read_bytes()).hexdigest()
        assert review['passed'] and review['freeze_sha256'] == current_hash
        assert replay['passed'] and replay['freeze_sha256'] == current_hash
        for seed in [7201, 8301, 9401]:
            assert (Q / f'runs/24hh_seed{seed}/accepted.json').exists()
        env = {**os.environ, 'PYTHONHASHSEED': '0', 'PYTHONUNBUFFERED': '1'}
        if not (Q / 'runs/100hh_seed101/accepted.json').exists():
            assert not (Q / 'runs/100hh_seed101/attempt3').exists(), 'Do not restart an existing attempt'
            command = [sys.executable, str(Q / 'recover_job.py'), '--index', '3',
                       '--attempt', '3', '--resume-cache',
                       str(Q / 'runs/100hh_seed101/attempt2/cache.sqlite')]
            result = subprocess.run(command, cwd=Q, env=env)
            if result.returncode:
                return result.returncode
        result = subprocess.run([sys.executable, str(Q / 'controller.py'),
                                 '--start-index', '4'], cwd=Q, env=env)
        if result.returncode:
            return result.returncode
        result = subprocess.run([sys.executable, str(Q / 'aggregate.py')], cwd=Q, env=env)
        print(json.dumps({'stage': 'ORIGINAL_BATCH_AGGREGATION',
                          'returncode': result.returncode}), flush=True)
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
