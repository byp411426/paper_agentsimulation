"""One paired 8-household comparison: actual upstream cognitive modules, no fake scores.

Default is an offline integration check. --run requires a key in the environment
or a hidden terminal prompt. Each attempt uses a new directory and preserves logs.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import getpass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import yaml

from ds.llm.backends import LLMResponse, MockBackend
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMGateway
from experiments.carr.empirical_v2_runner import run_e1_v2

ROOT=Path(__file__).resolve().parents[1]
METHODS=("generative_agents","agentsociety","disastersociety")

class IntegrationBackend:
    """Scripted module values for wiring tests only; never report as behavior data."""
    async def acomplete(self, *, messages, schema, **kwargs):
        prompt="\n".join(m["content"] for m in messages)
        name=schema.__name__
        if name=="Importance":
            memories=json.loads(messages[-1]["content"].split("\n")[-1])
            data={"scores":[5]*len(memories)}
        elif name=="FocalQuestions":
            data={"questions":["What has this resident learned about the disaster?"]}
        elif name=="Reflection":
            memories=json.loads(messages[-1]["content"].split("\n")[-1])
            data={"insights":[{"thought":"Information may differ between residents.","evidence_ids":[memories[0]["id"]]}]}
        elif name=="Reaction":
            data={"revise":False,"reason":"Offline wiring check"}
        elif name=="Schedule":
            data={"goal":"Observe current information","activities":[{"due_step":25,"activity":"Wait and observe"}],"reason":"Offline wiring check"}
        elif name in ("E1Decision","NativeStepDecision"):
            data={"action":"stay","assessment":"Offline wiring check; not an experimental behavior", "cognitive_step_complete":False,"cognitive_step_reason":"Continue waiting"}
        elif "satisfaction initialization" in prompt:
            data={"current_satisfaction":{"hunger_satisfaction":.8,"energy_satisfaction":.8,"safety_satisfaction":.7,"social_satisfaction":.8}}
        elif "rebuild the satisfaction" in prompt or "Please evaluate and adjust" in prompt:
            data={"hunger_satisfaction":.8,"energy_satisfaction":.8,"safety_satisfaction":.7,"social_satisfaction":.8}
        elif "selected_option" in prompt:
            data={"selected_option":"Wait and observe","evaluation":{"attitude":.5,"subjective_norm":.5,"perceived_control":.5,"reasoning":"Offline wiring check"}}
        elif "specific execution steps" in prompt:
            data={"plan":{"target":"Observe","steps":[{"intention":"Wait and observe","type":"other"}]}}
        elif "emotion intensities" in prompt:
            data={"sadness":5,"joy":5,"fear":5,"disgust":5,"anger":5,"surprise":5,"conclusion":"Observing.","word":"Hope"}
        elif "thought" in prompt:
            data={"thought":"Observing the current circumstances"}
        else:
            raise ValueError("Unrecognized offline architecture stage")
        return LLMResponse(content=json.dumps(data),prompt_tokens=0,completion_tokens=0,response_model="scripted_integration_only")
    async def aclose(self):
        pass

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def one(method, output, real):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Prior attempt protected; use a new output directory")
    output.mkdir(parents=True,exist_ok=True)
    cfg=yaml.safe_load((ROOT/'experiments/carr/configs/evaluation_pilot_8hh_20260910.yaml').read_text())
    cfg['run']['run_id']=method
    cfg['experiment']['agent_method']=method
    cfg['experiment']['evidence_status']='PAIRED_SINGLE_SEED_DEVELOPMENT_COMPARISON'
    cfg['experiment']['claim_scope']='resident_architectures_with_shared_world_and_household_protocol'
    cfg['experiment']['order_calibration']=str((ROOT/cfg['experiment']['order_calibration']).resolve())
    cfg['llm']['models_config']='configs/models_published_comparison_20260912.yaml'
    cfg['llm']['max_concurrency']=3
    cfg['llm']['budget_usd']=5.0
    models_path=ROOT/cfg['llm']['models_config']
    models=yaml.safe_load(models_path.read_text())
    profiles=ROOT/'experiments/carr/inputs/evaluation_repair_20260909/profiles.jsonl'
    run=output/method
    run.mkdir()
    (run/'execution_config.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False))
    sources=list((ROOT/'ds/baselines').rglob('*.py'))+[
        ROOT/x for x in ['ds/agents/e1_contracts.py','ds/agents/carr_empirical_v2.py',
        'ds/world/carr_empirical_v2.py','ds/interaction/carr_empirical_v2.py','ds/households/state.py',
        'ds/kernel/engine.py','ds/kernel/actions.py','ds/kernel/rng.py','ds/population/profile_validation.py',
        'ds/llm/gateway.py','ds/llm/backends.py','ds/llm/cache.py','ds/agents/decide.py',
        'ds/population/networks.py','experiments/carr/empirical_v2_runner.py','scripts/run_published_comparison.py']]
    provenance={'kind':'paired_single_seed_real_model_comparison' if real else 'scripted_software_check',
        'backend':'real' if real else 'mock','method':method,'seed':7201,'n_households':8,
        'python_hash_seed':os.environ.get('PYTHONHASHSEED'),'log_schema_version':'e1_evaluation_v1',
        'code_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(sources)},
        'model_registry_sha256':sha(models_path),'profiles_sha256':sha(profiles),
        'upstream':json.loads((ROOT/'ds/baselines/vendor/UPSTREAM.json').read_text()),
        'scope':'All three arms share world, household protocol, wake scheduling and action contract; cognitive architecture comparison only.'}
    embedding_dir=Path(os.environ.get('DS_EMBEDDING_CACHE','/nonexistent'))
    provenance['embedding_artifacts_sha256']={str(p.relative_to(embedding_dir)):sha(p)
        for p in embedding_dir.rglob('*') if p.is_file() and p.suffix in ('.onnx','.json')}
    (run/'provenance.json').write_text(json.dumps(provenance,indent=2))
    cache=LLMCache(run/'llm_cache.sqlite')
    gateway=LLMGateway(run_id=method,models_cfg=models,budget_usd=5,max_concurrency=3,log_dir=output,
        cache=cache,backends=None if real else {key:IntegrationBackend() for key in models['models']},abort_on_call_failure=True)
    started=time.time()
    try:
        result=run_e1_v2(cfg=cfg,out_dir=output,gateway=gateway,run_seed=7201,n_households=8,profiles_path=profiles)
        if result['status']=='VALID':
            recorded_steps=[json.loads(line)['step'] for line in (run/'events/events.jsonl').read_text().splitlines()]
            if recorded_steps!=list(range(1,cfg['run']['total_steps']+1)):
                raise ValueError('Complete status without a complete event log; this attempt is not evaluable')
        print(json.dumps({'method':method,'status':result['status'],'elapsed_s':round(time.time()-started,2),
                          'gateway':gateway.stats()},ensure_ascii=False),flush=True)
    finally:
        gateway.close()
        cache.close()
    return 0 if result['status']=='VALID' else 2

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',action='store_true')
    ap.add_argument('--method',choices=METHODS)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if args.run and not os.environ.get('PACKY_API_KEY'):
        os.environ['PACKY_API_KEY']=getpass.getpass('Packy API key (hidden): ').strip()
        if not os.environ['PACKY_API_KEY']:
            raise ValueError('No credential supplied')
    if args.method:
        raise SystemExit(one(args.method,args.output,args.run))
    if args.output.exists() and any(args.output.iterdir()):
        raise FileExistsError('Use a new comparison output directory')
    args.output.mkdir(parents=True,exist_ok=True)
    protocol={'methods':METHODS,'households':8,'seed':7201,'steps':25,'step_minutes':30,
        'real_model':args.run,'model':'deepseek-v4-flash','thinking':'enabled','temperature':0,
        'max_output_tokens_per_call':16384,'estimated_budget_per_method_usd':5,
        'max_schema_repairs':2,'empty_optional_plan_guidance':'null, never steps:[]',
        'structured_output_mode':'tool',
        'native_agentsociety_modules':'same model and sampling, native JSON-object response format',
        'shared_services':['world physics','household commitment protocol','wake gate','action schema'],
        'exclusions':['no human prediction labels','no rule-generated results counted as model outputs'],
        'behavior_rubric':'scripts/export_behavior_review.py:RUBRIC; frozen before judging'}
    (args.output/'comparison_protocol.json').write_text(json.dumps(protocol,indent=2))
    processes=[]
    for method in METHODS:
        log=(args.output/(method+'.console.log')).open('w')
        cmd=[sys.executable,'-u','-m','scripts.run_published_comparison','--method',method,
             '--output',str(args.output/(method+'_attempt1'))]
        if args.run:
            cmd.append('--run')
        child=subprocess.Popen(cmd,cwd=ROOT,env=dict(os.environ),stdout=log,stderr=subprocess.STDOUT)
        processes.append((method,child,log))
    results=[]
    while processes:
        for entry in list(processes):
            method,child,log=entry
            if child.poll() is not None:
                log.close()
                results.append({'method':method,'exit_code':child.returncode})
                processes.remove(entry)
                print(json.dumps(results[-1]),flush=True)
        if processes:
            time.sleep(2)
    (args.output/'completion.json').write_text(json.dumps(results,indent=2))
    raise SystemExit(0 if all(r['exit_code']==0 for r in results) else 2)

if __name__=='__main__':
    main()
