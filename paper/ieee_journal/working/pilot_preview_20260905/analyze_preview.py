from pathlib import Path
import json,csv,collections,html
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Patch
from matplotlib import font_manager

P=Path(__file__).resolve().parent
import os
ATTEMPT=os.environ.get('PILOT_ATTEMPT','real')
R=P/ATTEMPT/'e1_preview_4hh_seed7201'
def jl(p):return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
profiles=jl(P/'profiles.jsonl'); events=jl(R/'events/events.jsonl')
if not events:raise SystemExit('No completed real steps to analyze')
status=json.loads((P/ATTEMPT/'execution_status.json').read_text()) if (P/ATTEMPT/'execution_status.json').exists() else {'status':'RUNNING'}
if ATTEMPT=='real_r2' and (P/'inspection_stop.json').exists():
 status['raw_engine_status']=json.loads((R/'events/summary.json').read_text()).get('status')
 status['status']='STOPPED_FOR_IMPLEMENTATION_REVIEW'
hhids=[h['household_id'] for h in profiles]; labels={h:f'H{i+1}' for i,h in enumerate(hhids)}
members={m['resident_id']:(h['household_id'],m) for h in profiles for m in h['member_profiles']}
decision_ids=[m for m,(_,x) in members.items() if x['decision_capable']]
safe='controlled_safe_zone'; metrics=[];ever_informed=set();first_depart={};ever_joint=set();violations=[];failures=[]
oldlocations=json.loads((P/ATTEMPT/'initial_state.json').read_text())['world']['member_locations']
allcommitments={}; by_household={h:[] for h in hhids}; counts=collections.Counter()
for e in events:
 step=e['step'];world=e['world'];locations=world['member_locations']
 ever_informed.update(r['resident_id'] for r in e['interaction']['receipts'] if r.get('delivered_step') is not None and r['delivered_step']<=step)
 transitions={m for m,loc in locations.items() if loc==safe and oldlocations.get(m)!=safe}
 executed_members=set()
 for d in e['decisions']:
  aid=d['agent'];a=d['decision']['action'];outcome=d['outcome'];ok=outcome['status']=='executed'
  counts[a]+=1
  by_household[members[aid][0]].append({'step':step,'resident':aid,'action':a,'outcome':outcome['status'],'reason':outcome.get('reason'),'assessment':d['decision'].get('assessment','')})
  if a=='evacuate' and ok:
   executed_members.add(aid)
   requested=d['decision'].get('depart_step')
   if isinstance(requested,int) and requested>step:violations.append({'step':step,'issue':'execution_before_current_requested_departure','member':aid,'requested_step':requested})
   if aid in first_depart:violations.append({'step':step,'issue':'repeat_departure','member':aid})
   first_depart.setdefault(aid,step)
   if locations.get(aid)!=safe:violations.append({'step':step,'issue':'execution_position_mismatch','member':aid})
  if outcome['status']=='rejected':failures.append({'step':step,'resident':aid,'action':a,'reason':outcome.get('reason')})
  if oldlocations.get(aid)==safe:violations.append({'step':step,'issue':'decision_after_terminal','member':aid})
 for m in transitions & set(decision_ids):
  if m not in executed_members:violations.append({'step':step,'issue':'position_change_without_own_execution','member':m})
 for h,cs in world.get('household_commitments',{}).items():
  for cid,c in cs.items():
   allcommitments[cid]=(h,c)
   travelers=set(c['party']['traveler_ids'])
   if len(travelers)>=2 and travelers<=set(c['accepted_by']):ever_joint.add(h)
 all_safe=sum(all(locations.get(m['resident_id'])==safe for m in h['member_profiles']) for h in profiles)
 metrics.append({'step':step,'hours':e['sim_minutes']/60,'official_recipients':len(ever_informed),'decision_departed':len(first_depart),'multi_member_agreement_households':len(ever_joint),'all_safe_households':all_safe,'unknown_members':len(set(members)-set(locations))})
 oldlocations=locations
with (P/'process_metrics.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(metrics[0]));w.writeheader();w.writerows(metrics)
last=events[-1];household_rows=[]
for h in profiles:
 hid=h['household_id'];ms=h['member_profiles'];n_safe=sum(last['world']['member_locations'].get(m['resident_id'])==safe for m in ms);unknown=sum(m['resident_id'] not in last['world']['member_locations'] for m in ms)
 state='未知' if unknown else '全员安全' if n_safe==len(ms) else '部分安全' if n_safe else '尚无人到达安全区'
 household_rows.append({'household':labels[hid],'household_id':hid,'members':len(ms),'decision_residents':sum(m['decision_capable'] for m in ms),'vehicles':h['shared_attributes']['vehicle_count'],'safe_members':n_safe,'unknown_members':unknown,'state':state})
# These are task completion/record checks only, never a social-realism score.
commit_counts=collections.Counter(c['status'] for h,c in allcommitments.values())
call_logs=jl(R/'llm_calls.jsonl'); real_ok=sum(l['status']=='ok' for l in call_logs)
summary={'run_status':status.get('status'),'raw_engine_status':status.get('raw_engine_status'),'completed_steps':len(events),'households':household_rows,'last_metrics':metrics[-1],'action_counts':dict(counts),'commitment_states':dict(commit_counts),'automatic_commitments':sum(cid.startswith('auto_') for cid in allcommitments),'message_commitments':sum(not cid.startswith('auto_') for cid in allcommitments),'real_successful_decisions':real_ok,'cached_decisions':sum(l['status']=='cache_hit' for l in call_logs),'committed_decisions':sum(len(e['decisions']) for e in events),'call_status_counts':dict(collections.Counter(l['status'] for l in call_logs)),'violations':violations,'rejections':failures,'gateway':status.get('gateway',{}),'elapsed_seconds':status.get('elapsed_seconds'),'provider_requests':status.get('provider_requests')}
(P/'preview_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False))
# Plot is rendered in English for portable scientific font support; Chinese explanation below.
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(13,4.5),layout='constrained')
x=[0]+[m['step'] for m in metrics]
for key,label,color in [('official_recipients','Official warning received (of 7)','#3066BE'),('decision_departed','Executed first departure (of 7)','#159478')]:
 axes[0].step(x,[0]+[m[key] for m in metrics],where='post',label=label,color=color,lw=2.3)
axes[0].set(ylim=(-.15,7.5),xlim=(0,12),xlabel='Simulation step (30 min each)',ylabel='Decision residents',title='Information and executed departure')
for key,label,color in [('multi_member_agreement_households','Ever formed a joint agreement (of 3 eligible)','#9268B4'),('all_safe_households','All members safe (of 4)','#D08C24')]:
 axes[1].step(x,[0]+[m[key] for m in metrics],where='post',label=label,color=color,lw=2.3)
axes[1].set(ylim=(-.15,4.6),xlim=(0,12),xlabel='Simulation step (30 min each)',ylabel='Households',title='Household agreements and final-state progression')
for ax in axes:
 if len(events)<12:
  ax.axvspan(events[-1]['step'],12,color='#eeeeee',alpha=.65,zorder=-1)
  ax.text((events[-1]['step']+12)/2,ax.get_ylim()[1]*.55,'Not completed',ha='center',color='#888888')
 for step,label in [(3,'Voluntary'),(7,'Mandatory'),(9,'Closure')]:
  ax.axvline(step,color='#9aa3ad',ls=':',lw=1);ax.text(step+.08,ax.get_ylim()[1]-.25,label,rotation=90,va='top',fontsize=8,color='#626b73')
 ax.set_xticks(range(0,13,2));ax.grid(axis='y',alpha=.15);ax.legend(loc='lower center',bbox_to_anchor=(.5,-.34),frameon=False,fontsize=8)
fig.suptitle(f'4-household diagnostic pilot | {len(events)}/12 steps | not a population estimate',fontsize=13)
fig.savefig(P/'process_preview.png',dpi=160,bbox_inches='tight');plt.close(fig)
# Action raster: explicitly represents decisions, not latent psychological states.
colors=['#edf0f3','#aec7e8','#f1ce63','#36a585','#d86c63','#a28fca','#67bbba','#d7e4c0']
categories=['No decision','Stay','Prepare','Departure executed','Departure rejected','Seek help','Offer help','Other execution rejection']
array=[[0]*len(events) for _ in decision_ids]
for j,e in enumerate(events):
 for d in e['decisions']:
  a=d['decision']['action'];code={'stay':1,'prepare':2,'seek_help':5,'offer_help':6}.get(a,0)
  if a=='evacuate':code=3 if d['outcome']['status']=='executed' else 4
  elif d['outcome']['status']=='rejected':code=7
  array[decision_ids.index(d['agent'])][j]=code
fig,ax=plt.subplots(figsize=(12,4.2),layout='constrained')
ax.imshow(array,aspect='auto',interpolation='nearest',cmap=ListedColormap(colors),norm=BoundaryNorm([i-.5 for i in range(9)],8))
short={m:f'{labels[members[m][0]]} / R{sum(1 for a in decision_ids[:i+1] if members[a][0]==members[m][0])}' for i,m in enumerate(decision_ids)}
for v in violations:
 if v['issue']=='execution_before_current_requested_departure':ax.scatter(v['step']-1,decision_ids.index(v['member']),marker='x',s=150,color='#202020',linewidths=2.5)
ax.set_yticks(range(len(decision_ids)),[short[m] for m in decision_ids]);ax.set_xticks(range(len(events)),[e['step'] for e in events]);ax.set(xlabel='Simulation step',title=f'Actual actions, steps 1–{len(events)} | X = intention / execution time mismatch')
ax.legend(handles=[Patch(facecolor=c,label=l) for c,l in zip(colors,categories)],loc='upper center',bbox_to_anchor=(.5,-.18),ncol=4,frameon=False,fontsize=8)
fig.savefig(P/'resident_actions.png',dpi=160,bbox_inches='tight');plt.close(fig)
# Human-readable audit preview; conclusions remain conditional on actual observed opportunities.
old=json.loads((P/'old_run_audit.json').read_text())
lines=['# 主实验试跑预览与代码核查','',f'这次使用修改后的代码运行真实 DeepSeek-V4-Flash。完成 {len(events)}/12 步，运行状态为 {status.get("status")}。这是四户诊断试跑，不是正式主实验，也不是方法优势或真实性验证。','','## 先回答旧代码能不能直接用','','不能直接用于改造后的正式实验。本次修改的是单独的源码副本，具体差异见 implementation_changes.patch；没有覆盖旧代码或旧结果。', '', '旧主实验正式目录核查如下。提前执行指执行记录的 step 小于关联约定的 depart_step。', '', '| 规模 / 种子 | 成功出发记录 | 提前执行记录 | 重复出发成员 | 终态位置表缺失成员 |','|---|---:|---:|---:|---:|']
for r in old:lines.append(f'| {r["n_households"]} 户 / {r["seed"]} | {r["executed_party_records"]} | {r["premature_execution_count"]} | {r["repeated_members"]} | {r["members_missing_final"]} |')
lines+=['','位置缺失都发生在非决策成员上：依据初始化代码的默认家庭位置与执行日志，可补出部分状态统计；但提前执行和重复出发会改变后续行为，不能通过删除记录或重算百分比恢复原本应该发生的过程。五次主实验运行均受提前执行影响；用于修改后过程主张时需补跑。消融和跨模型使用另一套居民/世界适配器，本次没有证明它们受到同一问题影响，也没有启动重跑。','','## 本次具体设置','','四户取自原画像第 1、2、5、7 户，分别覆盖独居、双人、有照护成员、无车家庭；共有 12 名成员、7 名决策居民。沿用原事件时刻（第 3/7/9 步）和模型设置，缩短到 12 步。网络按四户重建，本次网络密度与 24/100 户不具有可比性。详细配置和停止规则见《试跑设置与修改说明》。','','## 已完成步骤的记录（不能作为正式效果结果）','','| 家庭 | 总人数 / 决策人数 | 车辆 | 已到安全区 | 终态 |','|---|---:|---:|---:|---|']
for r in household_rows:lines.append(f'| {r["household"]} | {r["members"]} / {r["decision_residents"]} | {r["vehicles"]} | {r["safe_members"]} | {r["state"]} |')
lines+=['',f'本轮 {real_ok} 次新请求成功，另有 {summary['cached_decisions']} 次来自真实模型响应缓存；完成的时间步中共提交 {summary['committed_decisions']} 次决策。累计 {metrics[-1]["official_recipients"]}/7 人收到官方信息，{metrics[-1]["decision_departed"]}/7 人有核实后的首次实际出发。明确多人约定涉及 {len(ever_joint)}/3 个具备多人决策机会的家庭；自动单人约定 {summary["automatic_commitments"]} 个，消息形成约定 {summary["message_commitments"]} 个。', '',f'本次检出的重复出发、终态后决策或位置/执行不一致及当前出发意图时间不一致共 {len(violations)} 项；终态未知成员 {metrics[-1]["unknown_members"]} 人。该检查不等于所有实现问题均已排除。','','![群体过程预览](process_preview.png)','','第一幅图分别画居民人数和家庭数，不把二者合成转化漏斗。线没有变化就保留水平线，不制造上升趋势。','','![居民行动预览](resident_actions.png)','','第二幅图显示每位居民每一步实际提出/执行的行动。黑色叉号标出实际执行与当下出发意图不一致的记录，这不是成功行为证据。灰色表示没有决策，不等于选择留守。求助或帮助只有动作记录时，不能解读为已经获得交通或完成救助。','','## 试跑暴露的问题和下一版需要改什么','','- 本轮在第 7 步后主动停止：第 5 步 H2/R1 的当前意图是第 6 步出发，执行器却匹配旧的第 5 步约定并执行。原始引擎记为 ABORTED / UNHANDLED_EXCEPTION（SIGINT），本报告另行注明人工检查停止原因，不改写原始终态。',
'- 首轮 real 在第 5 步接口超时、完成 4 步；real_r2 从初态重走并复用 3 次已成功真实响应，不拼接状态日志。本轮提交 9 次决策。停止时仍有在途请求，已记录 token 成本不能当最终账单。',
'- 【必须修：执行匹配】约定到期与当前意图时间都要符合；不同意当前出发或明确改期时，不能因为路线和车辆相同就执行旧约定。还要记录修订和需要重新同意的过程。',
'- 【必须修：提议对象】模型漏填同行者时不能静默补成单人并自动占用车。提议必须明确同行成员；只有明确选择单独行动，才允许自动单人出发组。不能反过来强迫所有家庭一起撤离。',
'- 【必须修：协商时序】第 t 步发送、下一步处理的提议要留出协商和确认时间；双方不能因正常的一步消息处理延迟就收到 depart_step_too_early。拒绝原因必须回到相关居民的下一次输入中。',
'- 【必须核实：持续计划】E1 的 private_process.current_plan 仍为 None。论文若要由这个主实验证明持续规划，就要把计划状态、更新和执行接入 E1；不能用 E2 有规划代替 E1 的实现。',
'- 原有输入、模型、场景和内核可以保留；下一版需要修改的是上述明确接口与状态规则，不能仅换汇总脚本。','- 只有确实出现多人同意的约定，才能检验约定形成到执行的统计；若数量为零，该面板目前不能承担“协调有效”的证明。','- 只有封路后发生了决策或拒绝，才能观察反馈后的调整。全部行动早于封路或没人接触封路时，这个原场景不足以展示适应过程。','- 修复版仍沿用原 E1 的行动集：seek_help/offer_help 不会自动实现跨家庭接送；private_process.current_plan 仍为 None，不能宣称本试跑验证了持续私有计划机制。','- 是否扩大运行要先依据这些具体缺口判断，不依据撤离率是否好看；本次不会自动转入全量。','','## 逐户记录（全部家庭，不挑成功案例）','']
translation={'stay':'留在原处','prepare':'准备','evacuate':'提出撤离','seek_help':'求助','offer_help':'提出帮助'}
for h,ds in by_household.items():
 lines+=['### '+labels[h], '','| 步 | 居民 | 行动 | 执行结果 / 原因 |','|---:|---|---|---|']
 for d in ds:lines.append(f'| {d["step"]} | {short[d["resident"]]} | {translation[d["action"]]} | {d["outcome"]} / {d["reason"] or "—"} |')
 if not ds:lines.append('| — | — | 本次窗口内无决策记录 | 不解释为主动留守 |')
 lines+=['']
(P/'试跑结果与后续修改.md').write_text('\n'.join(lines))
print(json.dumps({k:v for k,v in summary.items() if k not in ['gateway','rejections']},ensure_ascii=False,indent=2))
