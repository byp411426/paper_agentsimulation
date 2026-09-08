"""One immutable E1 run, using the validated shared kernel and model contract."""
import argparse,json,os,sys,time,subprocess,shutil,hashlib,signal
from pathlib import Path
Q=Path(__file__).resolve().parent
sys.path.insert(0,str(Q/'frozen'))
import yaml
from ds.llm.backends import LiteLLMBackend,MockBackend
from ds.llm.gateway import LLMGateway
from ds.llm.cache import LLMCache
from ds.kernel.logger import RunLogger
import experiments.carr.empirical_v2_runner as runner

def atomic(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2,default=str));tmp.replace(path)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--households',type=int,required=True);parser.add_argument('--seed',type=int,required=True);parser.add_argument('--attempt',type=int,default=1);parser.add_argument('--backend',choices=['mock','real'],default='real');parser.add_argument('--resume-cache',type=Path)
    a=parser.parse_args();cfg=yaml.safe_load((Q/f'configs/{a.households}.yaml').read_text());name=f'{a.households}hh_seed{a.seed}';out=Q/('runs' if a.backend=='real' else 'offline')/name/f'attempt{a.attempt}';out.mkdir(parents=True,exist_ok=False);run=out/cfg['run']['run_id'];run.mkdir()
    manifest=json.loads((Q/'freeze.json').read_text())
    for f,h in manifest['files_sha256'].items():
        if hashlib.sha256((Q/f).read_bytes()).hexdigest()!=h:raise RuntimeError('Frozen input changed: '+f)
    if os.environ.get('PYTHONHASHSEED')!='0':raise RuntimeError('PYTHONHASHSEED=0 required')
    models=yaml.safe_load((Q/'configs/models.yaml').read_text())
    if a.backend=='real':
        key=subprocess.run(['security','find-generic-password','-s','PACKY_API_KEY','-w'],capture_output=True,text=True,timeout=15)
        if key.returncode or not key.stdout.strip():raise RuntimeError('Credential unavailable')
        os.environ['PACKY_API_KEY']=key.stdout.strip();del key
    if a.resume_cache:shutil.copy2(a.resume_cache,out/'cache.sqlite')
    cache=LLMCache(out/'cache.sqlite');started=time.monotonic()
    class Backend(LiteLLMBackend):
        calls=0
        async def acomplete(self,**kwargs):
            self.calls+=1;number=self.calls
            response=await super().acomplete(**kwargs)
            with (out/'raw_responses.jsonl').open('a') as f:f.write(json.dumps({'request':number,'content':response.content,'prompt_tokens':response.prompt_tokens,'completion_tokens':response.completion_tokens})+'\n')
            return response
    backend=Backend() if a.backend=='real' else MockBackend()
    gateway=LLMGateway(run_id=cfg['run']['run_id'],models_cfg=models,budget_usd=cfg['llm']['budget_usd'],max_concurrency=cfg['llm']['max_concurrency'],log_dir=out,cache=cache,backends={cfg['llm']['decision_model']:backend},abort_on_call_failure=True)
    class Progress(RunLogger):
        def dump_step(self,record):
            super().dump_step(record);self.flush();gateway.flush()
            value={'status':'RUNNING','households':a.households,'seed':a.seed,'attempt':a.attempt,'step':record['step'],'planned_steps':25,'awake':record['n_awake'],'elapsed_seconds':round(time.monotonic()-started,1),'gateway':gateway.stats(),'provider_requests':getattr(backend,'calls',0),'run_dir':str(run)}
            atomic(out/'progress.json',value);print(json.dumps(value),flush=True)
    runner.RunLogger=Progress
    components=runner.build_e1_v2_components(cfg=cfg,profiles_path=Q/'inputs/profiles.jsonl',n_households=a.households,run_seed=a.seed,gateway=gateway)
    atomic(run/'input_graph.json',{'edges':sorted([sorted(e) for e in components[4].graph.edges()])})
    del components
    atomic(run/'provenance.json',{'backend':a.backend,'seed':a.seed,'households':a.households,'freeze_sha256':hashlib.sha256((Q/'freeze.json').read_bytes()).hexdigest(),'resume_cache':str(a.resume_cache) if a.resume_cache else None,'model':cfg['llm']['decision_model'],'temperature':cfg['llm']['temperature'],'hash_seed':os.environ['PYTHONHASHSEED']})
    shutil.copy2(Q/f'configs/{a.households}.yaml',run/'execution_config.yaml')
    def deadline(*unused):raise TimeoutError('Per-attempt wall-clock limit reached')
    signal.signal(signal.SIGALRM,deadline);signal.alarm(10800)
    result={'status':'ABORTED'}
    try:
        result=runner.run_e1_v2(cfg=cfg,out_dir=out,gateway=gateway,run_seed=a.seed,n_households=a.households,profiles_path=Q/'inputs/profiles.jsonl')
    except BaseException as exc:
        result.update(status='ABORTED',exception_type=type(exc).__name__)
    finally:
        signal.alarm(0);gateway.flush();result.update(backend=a.backend,provider_requests=getattr(backend,'calls',0),elapsed_seconds=round(time.monotonic()-started,2),gateway=gateway.stats(),run_dir=str(run));atomic(out/'status.json',result);atomic(run/'execution_status.json',result);gateway.close();cache.close();os.environ.pop('PACKY_API_KEY',None)
    print(json.dumps({'status':result['status'],'completed_steps':result.get('completed_steps')}),flush=True)
    return 0 if result['status']=='VALID' else 2
if __name__=='__main__':raise SystemExit(main())
