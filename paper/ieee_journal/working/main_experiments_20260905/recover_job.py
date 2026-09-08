"""Run a diagnosed replacement attempt, preserving all earlier artifacts."""
import argparse,subprocess,sys,os
from controller import Q,JOBS,atomic,analyze
def main():
    p=argparse.ArgumentParser();p.add_argument('--index',type=int,required=True);p.add_argument('--attempt',type=int,required=True);p.add_argument('--resume-cache');a=p.parse_args();n,seed=JOBS[a.index]
    atomic(Q/'batch_status.json',{'status':'RUNNING','index':a.index,'households':n,'seed':seed,'attempt':a.attempt,'stage':'DIAGNOSED_REPLACEMENT','fresh_cache':not bool(a.resume_cache)})
    cmd=[sys.executable,str(Q/'worker.py'),'--households',str(n),'--seed',str(seed),'--attempt',str(a.attempt)]
    if a.resume_cache:cmd+=['--resume-cache',a.resume_cache]
    with (Q/'runs'/f'{n}hh_seed{seed}'/f'attempt{a.attempt}_console.log').open('w') as f:r=subprocess.run(cmd,cwd=Q,env={**os.environ,'PYTHONHASHSEED':'0'},stdout=f,stderr=subprocess.STDOUT)
    good=r.returncode==0 and analyze(n,seed,a.attempt)
    atomic(Q/'batch_status.json',{'status':('FIRST_SEED_AWAITING_AGENT_REVIEW' if a.index==0 else 'REPLACEMENT_ACCEPTED') if good else 'NEEDS_REPAIR','index':a.index,'households':n,'seed':seed,'attempt':a.attempt,'worker_returncode':r.returncode})
    return 0 if good else 2
if __name__=='__main__':raise SystemExit(main())
