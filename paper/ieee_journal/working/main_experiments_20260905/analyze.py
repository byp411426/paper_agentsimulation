from pathlib import Path
import json,csv,collections,base64,html
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Patch
from matplotlib.colors import ListedColormap,BoundaryNorm
import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--run-dir',type=Path)
parser.add_argument('--output',type=Path)
parser.add_argument('--planned-steps',type=int,default=12)
args=parser.parse_args()
HERE=Path(__file__).resolve().parent
ATTEMPT='live_complete'
R=args.run_dir or HERE/ATTEMPT/'e1_repaired_4hh_seed7201'
P=args.output or HERE
P.mkdir(parents=True,exist_ok=True)
planned=args.planned_steps
profile_path=R/'selected_profiles.jsonl' if (R/'selected_profiles.jsonl').exists() else HERE/'profiles.jsonl'
status_path=R/'execution_status.json' if args.run_dir else HERE/ATTEMPT/'execution_status.json'
initial_path=R/'initial_state.json' if (R/'initial_state.json').exists() else HERE/ATTEMPT/'initial_state.json' 
def readlines(p):return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
events=readlines(R/'events/events.jsonl');profiles=readlines(profile_path)
if not events:raise SystemExit('No complete steps')
status=json.loads(status_path.read_text()) if status_path.exists() else {'status':'RUNNING'}
hids=[h['household_id'] for h in profiles];labels={h:f'H{i+1}' for i,h in enumerate(hids)}
member_h={m['resident_id']:h['household_id'] for h in profiles for m in h['member_profiles']}
deciders={m['resident_id'] for h in profiles for m in h['member_profiles'] if m['decision_capable']}
initial=json.loads(initial_path.read_text());oldloc=initial['world']['member_locations'];safe='controlled_safe_zone'
violations=[];first_depart={};aware=set();joint=set();joint_executed=set();metrics=[];allcommits={};rejects=[];action_counts=collections.Counter();trace=[]
for e in events:
 t=e['step'];loc=e['world']['member_locations'];commits={cid:(h,c) for h,cs in e['world']['household_commitments'].items() for cid,c in cs.items()};allcommits.update(commits)
 if set(loc)!=set(member_h):violations.append({'step':t,'issue':'member_roster_mismatch'})
 executed=set()
 before={a['id']:a for a in e['state_before_decisions']['agents']}
 after={a['id']:a for a in e['agents']}
 for d in e['decisions']:
  rid=d['agent'];a=d['decision'];o=d['outcome'];action_counts[a['action']]+=1
  trace.append({'step':t,'resident':rid,'household':labels[member_h[rid]],'action':a['action'],'outcome':o['status'],'reason':o.get('reason'),'assessment':a.get('assessment',''),'departure_mode':a.get('departure_mode'),'plan_update':a.get('plan_update')})
  if oldloc.get(rid)==safe:violations.append({'step':t,'issue':'decision_after_terminal','resident':rid})
  if o['status']=='rejected':rejects.append({'step':t,'resident':rid,'reason':o.get('reason')})
  if a['action']=='evacuate' and o['status']=='executed':
   if rid in first_depart:violations.append({'step':t,'issue':'repeat_departure','resident':rid})
   if a.get('depart_step')!=t:violations.append({'step':t,'issue':'intent_execution_time_mismatch','resident':rid})
   if loc.get(rid)!=safe:violations.append({'step':t,'issue':'executed_without_position_change','resident':rid})
   cid=o.get('state_delta',{}).get('commitment_id');entry=commits.get(cid)
   if not entry:violations.append({'step':t,'issue':'execution_without_commitment','resident':rid})
   elif entry[1]['party']['depart_step']!=t:violations.append({'step':t,'issue':'agreement_execution_time_mismatch','resident':rid})
   first_depart.setdefault(rid,t);executed.add(rid)
  pre=before[rid].get('current_plan');post=after[rid].get('current_plan')
  if pre and a.get('plan_update') is None:
   if not post or any(pre[k]!=post[k] for k in ['goal','steps','created_step']):violations.append({'step':t,'issue':'private_plan_lost_without_revision','resident':rid})
 new_safe={m for m in deciders if loc.get(m)==safe and oldloc.get(m)!=safe}
 if new_safe!=executed:violations.append({'step':t,'issue':'position_and_execution_set_mismatch'})
 for cid,(hid,c) in commits.items():
  travelers=set(c['party']['traveler_ids']);accepters=set(c['accepted_by'])
  if not travelers<=accepters:violations.append({'step':t,'issue':'missing_party_consent','commitment_id':cid})
  if len(travelers)>=2:
   joint.add(hid)
   if c['status']=='executed':joint_executed.add(hid)
   mid=cid.removeprefix('commit:');m=e['interaction']['messages'].get(mid)
   if not m:violations.append({'step':t,'issue':'joint_agreement_without_proposal','commitment_id':cid})
   else:
    for r in travelers-{m['sender_id']}:
     recipient=m['recipient_states'].get(r,{})
     if recipient.get('disposition')!='accepted' or recipient.get('processed_step') is None:violations.append({'step':t,'issue':'consent_without_processed_response','resident':r})
 aware.update(r['resident_id'] for r in e['interaction']['receipts'] if r['delivered_step']<=t)
 metrics.append({'step':t,'hours':e['sim_minutes']/60,'official_recipients':len(aware),'first_departures':len(first_depart),'joint_agreement_households':len(joint),'joint_execution_households':len(joint_executed),'active_private_plans':sum(bool(a.get('current_plan')) and a['current_plan']['status']=='active' for a in e['agents']),'all_safe_households':sum(all(loc.get(m['resident_id'])==safe for m in h['member_profiles']) for h in profiles)})
 oldloc=loc
eligible_households=sum(sum(m['decision_capable'] for m in h['member_profiles'])>=2 for h in profiles)
for m in metrics:
 m['official_recipient_share']=m['official_recipients']/len(deciders) if deciders else None
 m['first_departure_share']=m['first_departures']/len(deciders) if deciders else None
 m['all_safe_household_share']=m['all_safe_households']/len(profiles)
 m['joint_agreement_household_share']=m['joint_agreement_households']/eligible_households if eligible_households else None
 m['joint_execution_household_share']=m['joint_execution_households']/eligible_households if eligible_households else None
rows=[]
for h in profiles:
 ms=h['member_profiles'];n=sum(oldloc.get(m['resident_id'])==safe for m in ms)
 rows.append({'label':labels[h['household_id']],'household_id':h['household_id'],'members':len(ms),'decision_members':sum(m['decision_capable'] for m in ms),'vehicles':h['shared_attributes']['vehicle_count'],'safe_members':n,'remaining_members':len(ms)-n,'state':'全员安全' if n==len(ms) else '部分安全' if n else '窗口内尚未出发'})
rejection_counts=dict(collections.Counter(r['reason'] for r in rejects));logs=readlines(R/'llm_calls.jsonl');calls=dict(collections.Counter(l['status'] for l in logs))
summary={'status':status.get('status'),'completed_steps':len(events),'planned_steps':planned,'households':rows,'metrics':metrics[-1],'contract_violations':violations,'rejection_counts':rejection_counts,'call_status_counts':calls,'gateway':status.get('gateway',{}),'provider_requests':status.get('provider_requests'),'wall_seconds':status.get('elapsed_seconds',status.get('wall_clock_seconds')),'action_counts':dict(action_counts),'private_plan_users':len({a['id'] for e in events for a in e['agents'] if a.get('current_plan')}),'number_of_joint_commitment_versions':sum(len(c['party']['traveler_ids'])>=2 for h,c in allcommits.values()),'number_of_solo_commitment_versions':sum(cid.startswith('auto_') for cid in allcommits),'all_commitment_final_statuses':dict(collections.Counter(c['status'] for h,c in allcommits.values()))}
summary['software_check_passed']=status.get('status')=='VALID' and len(events)==planned and not violations
summary['metric_denominators']={'decision_residents':len(deciders),'all_households':len(profiles),'multi_decision_households':eligible_households}
(P/'results.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False));(P/'household_trace.json').write_text(json.dumps(trace,indent=2,ensure_ascii=False))
with (P/'process_metrics.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(metrics[0]));w.writeheader();w.writerows(metrics)
font_manager.fontManager.addfont('/System/Library/Fonts/STHeiti Medium.ttc')
plt.rcParams.update({'font.family':font_manager.FontProperties(fname='/System/Library/Fonts/STHeiti Medium.ttc').get_name(),'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axs=plt.subplots(1,3,figsize=(15,4.4),layout='constrained');x=[0]+[m['step'] for m in metrics]
for key,title,color in [('official_recipients','已收到官方警告','#3274b7'),('first_departures','已实际首次出发','#269b7a')]:axs[0].step(x,[0]+[m[key] for m in metrics],where='post',lw=2,label=title,color=color)
axs[0].set(title='信息接收与实际行动',ylabel=f'决策成员人数（共 {len(deciders)} 人）',ylim=(-.1,len(deciders)+.7))
for key,title,color,ls in [('joint_agreement_households','已达成共同出发约定','#9368ad','-'),('joint_execution_households','已实际共同出发','#d68a2b','--')]:axs[1].step(x,[0]+[m[key] for m in metrics],where='post',lw=2,label=title,color=color,ls=ls)
axs[1].set(title='家庭协商与执行',ylabel='家庭数',ylim=(-.1,sum(sum(m['decision_capable'] for m in h['member_profiles'])>=2 for h in profiles)+.5))
for ax in axs[:2]:
 ax.set(xlim=(0,planned),xlabel='时间步（每步 30 分钟）');ax.set_xticks(range(0,planned+1,2));ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True));ax.grid(axis='y',alpha=.17);ax.legend(loc='upper left',fontsize=8,frameon=False)
 for tick,label in [(3,'建议撤离'),(7,'强制命令'),(9,'主路封闭')]:
  ax.axvline(tick,color='#aaa',ls=':',lw=.9);ax.text(tick+.08,ax.get_ylim()[1]*.63,label,rotation=90,va='top',fontsize=8,color='#777')
 if len(events)<planned:ax.axvspan(len(events),planned,color='#eee',zorder=-1)
if len(rows)<=12:
 ys=range(len(rows));axs[2].barh(ys,[r['safe_members'] for r in rows],color='#269b7a',label='已到安全区');axs[2].barh(ys,[r['remaining_members'] for r in rows],left=[r['safe_members'] for r in rows],color='#dce2e7',label='尚未到安全区');axs[2].set_yticks(ys,[r['label'] for r in rows]);axs[2].invert_yaxis();axs[2].set(title=f'第 {len(events)} 步家庭状态',xlabel='家庭成员人数（含依赖成员）');axs[2].legend(frameon=False,fontsize=8)
else:
 counts=collections.Counter(r['state'] for r in rows)
 states=['全员安全','部分安全','窗口内尚未出发']
 axs[2].barh(states,[counts[k] for k in states],color=['#269b7a','#f1ce63','#dce2e7'])
 axs[2].invert_yaxis();axs[2].set(title=f'第 {len(events)} 步家庭状态',xlabel='家庭数')

fig.suptitle(f'E1 修复后过程预览｜{len(profiles)} 户 / {len(member_h)} 人｜实际日志',fontsize=14)
fig.savefig(P/'main_preview.png',dpi=170,bbox_inches='tight');plt.close(fig)
# Small, legible actual-action raster.
ids=sorted(deciders)[:12];palette=['#edf0f3','#a9c8e7','#f1ce63','#269b7a','#d86c63','#a28fca','#68b9b8'];codes={'stay':1,'prepare':2,'seek_help':5,'offer_help':6}
arr=[[0]*len(events) for r in ids]
for j,e in enumerate(events):
 for d in e['decisions']:
  if d['agent'] not in ids:continue
  a=d['decision']['action'];arr[ids.index(d['agent'])][j]=3 if a=='evacuate' and d['outcome']['status']=='executed' else 4 if a=='evacuate' else codes[a]
fig,ax=plt.subplots(figsize=(13,4.2),layout='constrained');ax.imshow(arr,aspect='auto',cmap=ListedColormap(palette),norm=BoundaryNorm([v-.5 for v in range(8)],7),interpolation='nearest');ax.set_xticks(range(len(events)),[e['step'] for e in events]);ax.set_yticks(range(len(ids)),[labels[member_h[r]]+' / '+r.rsplit('_',1)[-1] for r in ids]);ax.set(title='逐人行动与实际执行结果' + ('（按 ID 顺序展示前 12 人）' if len(deciders)>12 else ''),xlabel='时间步');ax.legend(handles=[Patch(facecolor=c,label=t) for c,t in zip(palette,['本步未唤醒','留守 / 监测','准备','已执行出发','出发被拒绝','求助','提供帮助'])],loc='upper center',bbox_to_anchor=(.5,-.17),ncol=4,frameon=False,fontsize=8);fig.savefig(P/'actions_preview.png',dpi=160,bbox_inches='tight');plt.close(fig)
print(json.dumps(summary,ensure_ascii=False,indent=2))
