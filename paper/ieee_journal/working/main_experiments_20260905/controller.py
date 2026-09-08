"""Sequential execution: first full seed must be reviewed before remaining seeds."""
from pathlib import Path
import argparse,json,subprocess,os,sys,hashlib,time
Q=Path(__file__).resolve().parent
JOBS=[(24,7201),(24,8301),(24,9401),(100,101),(100,202)]
def atomic(path,value):
    t=path.with_suffix('.tmp');t.write_text(json.dumps(value,indent=2));t.replace(path)
def analyze(n,seed,attempt):
    base=Q/'runs'/f'{n}hh_seed{seed}'/f'attempt{attempt}';run=base/f'carr_s_e1_repaired_{n}_20260905';dest=base/'analysis';dest.mkdir(exist_ok=True)
    with (base/'analysis_console.log').open('w') as f:
        result=subprocess.run([sys.executable,str(Q/'analyze.py'),'--run-dir',str(run),'--output',str(dest),'--planned-steps','25'],stdout=f,stderr=subprocess.STDOUT)
    if result.returncode:return False
    from gate import check
    result=check(run,dest,n,seed)
    if result['passed']:atomic(Q/'runs'/f'{n}hh_seed{seed}'/'accepted.json',{'attempt':attempt,'analysis':str(dest),'run_dir':str(run),'accepted_at':time.time()})
    return result['passed']
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--start-index',type=int,default=0);a=parser.parse_args()
    env={**os.environ,'PYTHONHASHSEED':'0','PYTHONUNBUFFERED':'1'}
    if a.start_index:
        review=json.loads((Q/'first_seed_review.json').read_text())
        assert review['passed'] and review['freeze_sha256']==hashlib.sha256((Q/'freeze.json').read_bytes()).hexdigest()
        for n,s in JOBS[:a.start_index]:assert (Q/'runs'/f'{n}hh_seed{s}'/'accepted.json').exists()
    for index,(n,seed) in enumerate(JOBS[a.start_index:],start=a.start_index):
        home=Q/'runs'/f'{n}hh_seed{seed}'
        if (home/'accepted.json').exists():continue
        if home.exists() and list(home.glob('attempt*')):
            atomic(Q/'batch_status.json',{'status':'NEEDS_REPAIR','index':index,'households':n,'seed':seed,'reason':'Existing unsuccessful attempt requires diagnosis; not blindly retried'});return 2
        home.mkdir(parents=True,exist_ok=True)
        atomic(Q/'batch_status.json',{'status':'RUNNING','index':index,'households':n,'seed':seed,'attempt':1,'stage':'FIRST_FULL_SEED' if index==0 else 'REMAINING_RUNS','started_at':time.time()})
        with (home/'attempt1_console.log').open('w') as f:
            result=subprocess.run([sys.executable,str(Q/'worker.py'),'--households',str(n),'--seed',str(seed)],cwd=Q,env=env,stdout=f,stderr=subprocess.STDOUT)
        if result.returncode or not analyze(n,seed,1):
            atomic(Q/'batch_status.json',{'status':'NEEDS_REPAIR','index':index,'households':n,'seed':seed,'attempt':1,'worker_returncode':result.returncode});return 2
        if index==0:
            atomic(Q/'batch_status.json',{'status':'FIRST_SEED_AWAITING_AGENT_REVIEW','households':n,'seed':seed,'attempt':1});return 0
    atomic(Q/'batch_status.json',{'status':'ALL_RUNS_ACCEPTED','completed':len(JOBS),'finished_at':time.time()});return 0
if __name__=='__main__':raise SystemExit(main())
