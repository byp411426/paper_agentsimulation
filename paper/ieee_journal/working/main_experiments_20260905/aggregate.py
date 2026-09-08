"""Render only accepted, complete runs; keep per-seed values visible."""
from pathlib import Path
import csv,json,statistics
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
Q=Path(__file__).resolve().parent;out=Q/'results';out.mkdir(exist_ok=True)
entries=[];curves={}
for n,seed in [(24,7201),(24,8301),(24,9401),(100,101),(100,202)]:
    marker=Q/'runs'/f'{n}hh_seed{seed}'/'accepted.json'
    if not marker.exists():continue
    location=json.loads(marker.read_text());folder=Path(location['analysis']);r=json.loads((folder/'results.json').read_text());gate=json.loads((folder/'acceptance.json').read_text());assert gate['passed']
    row={'households':n,'seed':seed,'attempt':location['attempt'],'decision_residents':r['metric_denominators']['decision_residents'],'eligible_joint_households':r['metric_denominators']['multi_decision_households'],**r['metrics'],'private_plan_users':r['private_plan_users'],'logical_decisions':gate['logical_decisions'],'fallback':r['gateway']['n_fallback'],'failed_calls':r['gateway']['n_failed'],'live_prompt_tokens':r['gateway']['live_prompt_tokens'],'live_completion_tokens':r['gateway']['live_completion_tokens'],'internal_estimated_cost':r['gateway']['spent'],'wall_seconds':r['wall_seconds']}
    attempts=[json.loads(f.read_text()) for f in (Q/'runs'/f'{n}hh_seed{seed}').glob('attempt*/status.json')]
    row.update(cache_hits=r['gateway']['n_cache'],logical_prompt_tokens=r['gateway']['logical_prompt_tokens'],logical_completion_tokens=r['gateway']['logical_completion_tokens'],retained_run_uses_cache_replay=bool(r['gateway']['n_cache']),all_attempts_elapsed_seconds=sum(a.get('elapsed_seconds',0) for a in attempts),all_attempts_internal_estimated_cost=sum(a.get('gateway',{}).get('spent',0) for a in attempts))
    entries.append(row)
    with (folder/'process_metrics.csv').open() as f:curves[n,seed]=list(csv.DictReader(f))
if not entries:raise SystemExit('No accepted complete runs')
with (out/'main_results.csv').open('w') as f:
    w=csv.DictWriter(f,fieldnames=list(entries[0]));w.writeheader();w.writerows(entries)
keys=['first_departure_share','all_safe_household_share','joint_agreement_household_share','joint_execution_household_share']
grouped=[]
for n in [24,100]:
    group=[r for r in entries if r['households']==n]
    if not group:continue
    for key in keys:
        vals=[r[key] for r in group if r[key] is not None]
        grouped.append({'households':n,'metric':key,'n_seeds':len(vals),'mean':statistics.mean(vals) if vals else None,'min':min(vals) if vals else None,'max':max(vals) if vals else None})
(out/'summary_by_scale.json').write_text(json.dumps(grouped,indent=2))
font='/System/Library/Fonts/STHeiti Medium.ttc';font_manager.fontManager.addfont(font);plt.rcParams.update({'font.family':font_manager.FontProperties(fname=font).get_name(),'axes.spines.top':False,'axes.spines.right':False,'font.size':10})
scales=sorted({r['households'] for r in entries});fig,axs=plt.subplots(len(scales),3,figsize=(14,4*len(scales)),squeeze=False,layout='constrained')
for index,n in enumerate(scales):
    for j,(key,title) in enumerate([('first_departure_share','首次实际出发比例'),('all_safe_household_share','全员到安全区家庭比例'),('joint_execution_household_share','多人共同出发家庭比例')]):
        ax=axs[index,j]
        for (size,seed),rows in curves.items():
            if size!=n:continue
            ax.step([0]+[int(r['step']) for r in rows],[0]+[float(r[key]) for r in rows],where='post',lw=1.7,label=f'seed {seed}')
        ax.set(title=f'{n} 户｜{title}',xlabel='时间步（每步 30 分钟）',ylabel='比例',ylim=(-.02,1.02),xlim=(0,25));ax.grid(axis='y',alpha=.16);ax.legend(frameon=False,fontsize=8)
        for t in [3,7,9]:ax.axvline(t,color='#888',ls=':',lw=.7,alpha=.6)
fig.suptitle('修复后主实验｜逐 seed 实际轨迹（虚线：建议令、强制令、封路）',fontsize=14)
fig.savefig(out/'main_curves.png',dpi=180,bbox_inches='tight');fig.savefig(out/'main_curves.pdf',bbox_inches='tight');plt.close(fig)
rows='\n'.join(f"| {r['households']} | {r['seed']} | {r['first_departures']}/{r['decision_residents']} | {r['all_safe_households']}/{r['households']} | {r['joint_agreement_households']}/{r['eligible_joint_households']} | {r['joint_execution_households']}/{r['eligible_joint_households']} |" for r in entries)
text=f'''# 修复后主实验结果

已完成并通过逐次检查：{len(entries)}/5。表内只含完整运行，未完成项不填零。

| 户数 | seed | 首次实际出发成员 | 全员到安全区家庭 | 多人约定家庭 | 多人实际出发家庭 |
|---|---:|---:|---:|---:|---:|
{rows}

![逐 seed 过程曲线]({out/'main_curves.png'})

所有运行都是原定 DeepSeek 模型、25 步、每步 30 分钟。第 3 步建议令、第 7 步强制令、第 9 步主路关闭。分母及验收定义见 [指标与执行顺序]({Q/'指标与执行顺序.md'})。

曲线展示每个独立 seed；24 户和 100 户分开分析。均值与范围见 [按规模汇总]({out/'summary_by_scale.json'})，它们不是置信区间。此处不计算显著性，不把家庭或居民视作独立重复。

留守或未共同出发的结果完整保留。请求帮助不等于实际接送完成。合法性通过只说明执行和统计通过检查，不能自动推出行为真实性或机制优越性。

[逐次指标与运行消耗 CSV]({out/'main_results.csv'})；消耗中的 cost 为内部预算估价，并非核实账单。恢复运行可能复用成功缓存：CSV 同时报告缓存命中、保留轨迹的逻辑 tokens、当前尝试实际消耗和包含失败尝试的开发总消耗。缓存恢复的墙钟不能与全新调用的墙钟直接作效率比较。已有消融和跨模型结果未被覆盖，也没有混入本表。
'''
(out/'主实验结果.md').write_text(text)
print(json.dumps({'accepted_runs':len(entries),'report':str(out/'主实验结果.md')},ensure_ascii=False))
