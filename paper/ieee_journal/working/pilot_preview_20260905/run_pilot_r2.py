"""Bounded diagnostic through the existing E1 runner; never prints credentials."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

SOURCE = Path('/Users/linnuo/Documents/agentSimulation/disastersociety')
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "implementation"))
os.chdir(SOURCE)
import yaml
from ds.llm.backends import MockBackend, LiteLLMBackend, BackendFatalError
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMGateway
from ds.kernel.logger import RunLogger
import experiments.carr.empirical_v2_runner as runner


class ProgressLogger(RunLogger):
    def dump_step(self, record):
        super().dump_step(record)
        self.flush()
        print(json.dumps({'step': record['step'], 'awake': record['n_awake']}), flush=True)


class BoundedBackend(LiteLLMBackend):
    def __init__(self):
        super().__init__()
        self.request_count = 0

    async def acomplete(self, **kwargs):
        if self.request_count >= 92:
            raise BackendFatalError('diagnostic provider request cap reached')
        self.request_count += 1
        print(json.dumps({'provider_request_started': self.request_count}), flush=True)
        return await super().acomplete(**kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backend', choices=['mock', 'real'], required=True)
    args = parser.parse_args()
    cfg = yaml.safe_load((HERE / 'pilot.yaml').read_text())
    models = yaml.safe_load((HERE / 'models.yaml').read_text())
    models["models"][cfg["llm"]["decision_model"]]["request_timeout_seconds"] = 300
    out = HERE / ("real_r2" if args.backend == "real" else "mock_r2")
    out.mkdir(exist_ok=False)
    if args.backend == 'real':
        key = subprocess.run(['security', 'find-generic-password', '-s', 'PACKY_API_KEY', '-w'],
                             capture_output=True, text=True, timeout=15)
        if key.returncode or not key.stdout.strip():
            raise RuntimeError('Credential unavailable; no provider request sent')
        os.environ['PACKY_API_KEY'] = key.stdout.strip()
        del key
    backend = BoundedBackend() if args.backend == 'real' else MockBackend()
    import shutil
    shutil.copy2(HERE / "real/cache.sqlite", out / "cache.sqlite")
    cache = LLMCache(out / 'cache.sqlite')
    gateway = LLMGateway(run_id=cfg['run']['run_id'], models_cfg=models,
                         budget_usd=cfg['llm']['budget_usd'], max_concurrency=2,
                         log_dir=out, cache=cache,
                         backends={cfg['llm']['decision_model']: backend},
                         abort_on_call_failure=True)
    runner.RunLogger = ProgressLogger  # flushing/progress only, no decision changes
    components = runner.build_e1_v2_components(cfg=cfg, profiles_path=HERE / 'profiles.jsonl',
                                               n_households=4, run_seed=7201, gateway=gateway)
    initial = {'world': components[3].snapshot(),
               'agents': [a.snapshot() for a in components[-1]],
               'event_schedule': {str(k): [vars(e) for e in v]
                                  for k, v in components[5].by_step.items()}}
    (out / 'initial_state.json').write_text(json.dumps(initial, indent=2, default=str))
    def deadline(signum, frame):
        raise TimeoutError('bounded recovery wall-clock limit reached')
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(1000)
    started = time.monotonic()
    status = {'backend': args.backend, 'evidence_status': 'DIAGNOSTIC_PILOT'}
    try:
        result = runner.run_e1_v2(cfg=cfg, out_dir=out, gateway=gateway, run_seed=7201,
                                 n_households=4, profiles_path=HERE / 'profiles.jsonl')
        status.update(result)
    except Exception as exc:
        status.update(status='ABORTED', exception_type=type(exc).__name__)
    finally:
        signal.alarm(0)
        gateway.flush()
        status['gateway'] = gateway.stats()
        status['provider_requests'] = getattr(backend, 'request_count', 0)
        status['elapsed_seconds'] = round(time.monotonic() - started, 2)
        gateway.close()
        cache.close()
        os.environ.pop('PACKY_API_KEY', None)
        (out / 'execution_status.json').write_text(json.dumps(status, indent=2, default=str))
        print(json.dumps({k: status.get(k) for k in ['status', 'completed_steps', 'provider_requests', 'elapsed_seconds']}), flush=True)


if __name__ == '__main__':
    main()
