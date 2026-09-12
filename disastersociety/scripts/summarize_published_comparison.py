"""Summarize complete real comparison artifacts without making evaluator judgments."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path

from scripts.audit_archived_run import read_json, read_jsonl, dump, commitments, digest
from scripts.evaluate_published_comparison import METHODS


def summarize(runs: Path, evaluation: Path, output: Path, process_suite: Path):
    behavior=read_json(evaluation/'behavior_comparison.json')
    manifest=read_json(evaluation/'manifest.json')
    if behavior['kind']!='single_seed_paired_development_comparison' or manifest['kind']!='paired_single_seed_real_model_comparison':
        raise ValueError('A real result report requires real complete runs and independent judgments')
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Existing reports are protected')
    output.mkdir(parents=True,exist_ok=True)
    rows=[]
    audits=read_json(evaluation/'implementation_audits.json')
    methods=manifest.get('methods',METHODS)
    for method in methods:
        run=runs/(method+'_attempt1')/method
        status=read_json(run/'execution_status.json')
        events=read_jsonl(run/'events/events.jsonl')
        if status['status']!='VALID' or [e['step'] for e in events]!=list(range(1,26)):
            raise ValueError('Incomplete arm')
        decisions=[d for e in events for d in e['decisions']]
        calls=read_jsonl(run/'llm_calls.jsonl')
        action_counts=Counter(d['decision']['action'] for d in decisions)
        rejected=Counter(d['outcome'].get('reason') for d in decisions if d['outcome']['status']=='rejected')
        final=events[-1]['world']
        import yaml
        config=yaml.safe_load((run/'execution_config.yaml').read_text())
        safe=config['experiment']['safe_zone']
        locations=final['member_locations']
        profiles=read_jsonl(run/'selected_profiles.jsonl')
        fully_evacuated=sum(all(locations[m['resident_id']]==safe for m in p['member_profiles']) for p in profiles)
        joint={cid: (hid,c) for e in events for cid,(hid,c) in commitments(e['world']).items()
               if len(c['party']['traveler_ids'])>=2}
        gw=status['gateway']
        replay=read_json(run/'cache_replay.json') if (run/'cache_replay.json').exists() else None
        prior=replay['previous_gateway'] if replay else {}
        previous_calls=read_jsonl(Path(replay['previous_run'])/'llm_calls.jsonl') if replay else []
        billed_calls=previous_calls+[c for c in calls if c['status']!='cache_hit']
        rows.append({'method':method,'behavior_mean':behavior['scores'][method]['mean'],
            'scored_households':behavior['scores'][method]['scored'],'households':len(profiles),
            'independent_worlds':1,'decisions':len(decisions),'successful_gateway_calls':gw['n_ok']+prior.get('n_ok',0),
            'cache_replay_hits':gw['n_cache'],'cache_replay':replay,
            'schema_repairs':sum(r.get('schema_repairs',0) for r in billed_calls if r['status']=='ok'),
            'provider_retries':sum(r['status']=='provider_retry' for r in billed_calls),
            'input_tokens':gw['live_prompt_tokens']+prior.get('live_prompt_tokens',0),
            'output_tokens':gw['live_completion_tokens']+prior.get('live_completion_tokens',0),
            'estimated_cost_usd':gw['spent']+prior.get('spent',0),
            'minutes':(status['wall_clock_seconds']+(replay['previous_wall_clock_seconds'] if replay else 0))/60,
            'action_counts':dict(action_counts),'execution_rejections':dict(rejected),
            'evacuated_residents':sum(x==safe for x in locations.values()),'total_residents':len(locations),
            'fully_evacuated_households':fully_evacuated,'joint_commitments':len(joint),
            'households_with_joint_commitments':len({v[0] for v in joint.values()}),
            'information':audits[method]['metrics']['information'],
            'consensus':audits[method]['metrics']['consensus'],
            'execution':audits[method]['metrics']['execution'],
            'consensus_opportunities':audits[method]['additional_checks']['consensus_formation_opportunities']})
    result={'kind':'paired_single_seed_pilot_report','rows':rows,'behavior':behavior,
        'run_protocol':read_json(runs/'comparison_protocol.json'),
        'implementation_scenario_suite':read_json(process_suite),
        'source_hashes':{'behavior':digest(evaluation/'behavior_comparison.json'),'manifest':digest(evaluation/'manifest.json')},
        'not_established':['population behavioral accuracy','between-run uncertainty','whole-platform superiority','publication readiness']}
    dump(output/'comparison_results.json',result)
    names={'generative_agents':'Generative Agents（灾害适配）','agentsociety':'AgentSociety（原城市架构灾害适配）','disastersociety':'DisasterSociety'}
    text=[f'# DisasterSociety {len(methods)} 方法小规模配对实验结果','',
        f'本报告使用 {len(methods)} 种方法各自完整的真实模型运行和独立 Codex 评审。每组 8 户、25 步、同一随机种子。它是可报告的比较预实验，尚不能替代多次独立运行的正式主实验。','',
        '比较对象是共享灾害环境中的居民认知架构。外部方法是明确记录过领域改动的适配版本；不能称为完整原平台的直接复现。共享家庭承诺处理程序的优势不由这张表验证。','',
        '| 方法 | 行为合理性 /5 | 可评分/总户数 | 模型输入/输出 token | 耗时（分钟） |',
        '|---|---:|---:|---:|---:|']
    for r in rows:
        score='N/A' if r['behavior_mean'] is None else f"{r['behavior_mean']:.3f}"
        text.append(f"| {names[r['method']]} | {score} | {r['scored_households']}/{r['households']} | {r['input_tokens']:,}/{r['output_tokens']:,} | {r['minutes']:.2f} |")
    text+=['','绝对评分每户一次。反向会话对预先指定的两户做重复评分，只用于检查分歧，不替换主评分。家庭之间可能互动，因此 8 户不是 8 次独立仿真实验。',
        '耗时包含实际运行与缓存重放时间，受并行负载和服务端延迟影响，不单独据此排名。若触及初始费用上限，只在验证已完成轨迹逐步完全相同后用缓存继续；表中 token 和费用计入中断前后的全部已记录真实调用，缓存读取不重复计费。该实验比较固定任务，不是固定费用预算下的性能。','',
        '| 相对比较 | 我们的偏好胜率（平局计 0.5） | 双向均可判断/配对户数 | 正反顺序判断不一致 |','|---|---:|---:|---:|']
    for m,p in behavior['pairwise'].items():
        value='N/A' if p['ours_win_rate_with_half_ties'] is None else f"{p['ours_win_rate_with_half_ties']:.1%}"
        text.append(f"| DisasterSociety vs {names[m]} | {value} | {p['judgeable_in_both_orders']}/{p['paired_households']} | {p['order_disagreements']} |")
    repeats=[r for r in behavior['repeat_scores'] if r['first'] is not None and r['repeat'] is not None]
    exact=sum(r['first']==r['repeat'] for r in repeats)
    text+=['',f"预先指定的重复绝对评分有 {len(repeats)} 对可核对，其中 {exact} 对完全一致。逐项初评与复评保留在 JSON 中；这只是小样本分歧检查，不是经过校准的评审可靠性结论。"]
    text+=['','胜率是同一个行为合理性标准的相对展示，不是另一项独立的真实性证据。每对轨迹有两个顺序判断，不能把它们当成两次仿真。','',
        '## 程序记录验证','',
        '下表均为错误数/实际检查数。N/A 表示没有对应检查机会，不能换成 0%。共享程序产生的零错误不构成方法间的性能优势。','',
        '| 方法 | 观察/接收记录 | 家庭共识状态 | 意图与执行混淆 |','|---|---:|---:|---:|']
    for r in rows:
        def cell(k):
            v=r[k];return f"{v['errors']}/{v['checked']}" if v['checked'] else 'N/A（无检查机会）'
        text.append(f"| {names[r['method']]} | {cell('information')} | {cell('consensus')} | {cell('execution')} |")
    suite=result['implementation_scenario_suite']
    text+=['',f"固定过程案例实际通过 {suite['passed']}/{suite['total']}。共识形成的正例、反例机会及逐条证据另见 comparison_results.json 和 audit 检查记录。这套固定案例用于开发修复，不能改称独立测试集上的方法优越性。",'',
        '## 社会过程（描述性统计，没有越高越好的方向）','',
        '| 方法 | 完整撤离家庭 | 撤离居民 | 联合承诺数 | 产生联合承诺的家庭 |','|---|---:|---:|---:|---:|']
    for r in rows:
        text.append(f"| {names[r['method']]} | {r['fully_evacuated_households']}/{r['households']} | {r['evacuated_residents']}/{r['total_residents']} | {r['joint_commitments']} | {r['households_with_joint_commitments']} |")
    text+=['','求助、提供帮助和同意声明都不自动等于实际接送或共同出发。没有被唤醒的时段也不计作主动等待。动作和执行拒绝的原始计数见 JSON。','',
        '## 逐户评分与依据','']
    for m in methods:
        text+=['### '+names[m],'']
        for score in behavior['scores'][m]['scores']:
            text.append(f"- {score['household_id']}：{score['score']}/5。{score['rationale_zh']}")
        text.append('')
    text+=['## 论文可怎样写','',
        '本轮可以写成“在同一灾害环境下，与已发表居民架构的灾害适配版本进行小规模配对比较，采用固定量表和匿名顺序评审报告行为合理性、计算代价及过程证据”。结果表可以作为初步比较结果，但单个种子不能支持“显著优于”或对真实人群的泛化结论。','',
        '还需要在正式结果之前固定独立重复的运行方案，并按实际差异和变异决定所需证据。Humanoid Agents、正式消融及独立场景测试集不在本轮完成名单中。','',
        '独立评审使用 Codex 会话，具体底层模型快照未知，不把 GPT 6 Astra 写成可调用的评审 API。行为文本可能暴露间接架构线索，匿名化不保证完美盲法。程序核验了结果格式、证据坐标及哈希，没有自动证明评审的语义结论。','',
        '成本按输入、输出各 USD 1/M token 的内部口径估计，实际 Packy 账单未核验。开发阶段失败和中止的调用另列在 development_attempt_register.json，不纳入完整运行的行为均分，也不隐去其消耗。','']
    formatted={r['method']:('N/A' if r['behavior_mean'] is None else f"{r['behavior_mean']:.3f}") for r in rows}
    baseline_names='、'.join(names[m] for m in methods if m!='disastersociety')
    score_sentence='；'.join(names[m]+' '+formatted[m] for m in methods)
    text += ['## 可直接改写入论文的结果段落','',
        f'我们在 Carr-informed controlled scenario 中开展了一个小规模配对比较实验。{baseline_names}采用明确记录的灾害领域适配，并与 DisasterSociety 共用灾害环境、家庭承诺协议、唤醒规则和行动接口。每种方法使用同一批 8 个合成家庭、同一外生事件与随机种子，运行 25 个时间步；所有生成调用采用提供商标识为 deepseek-v4-flash 的同一模型配置。比较对象为该共享环境中的居民认知架构，不能据此归因于共享协议本身。','',
        f"独立 Codex 会话按评分前固定的 1—5 分量表评价匿名完整家庭轨迹。各方法的平均行为合理性得分为：{score_sentence}。表中同时报告可评分家庭数、交换呈现顺序的配对偏好以及模型调用资源。等待、拒绝或撤离本身不被视为好坏标签；判断以居民当时实际获得的信息、家庭处境和后续行为是否连贯为依据。该结果来自每种方法的一次社会世界运行，仅作为初步比较证据，不提供独立重复运行的方差或显著性结论。",'',
        '三项状态记录错误率和固定过程案例另用于实现核验，不与行为得分加权成一个“总体真实性”数值。合成人群没有对应的真人逐户行为标签，因此本实验不报告真人行为预测准确率，也不将观察到的撤离比例最大化视为模拟质量目标。','',
        '## 指标计算口径','',
        r'行为均分：$S_m=\frac{1}{|H_m|}\sum_{h\in H_m}s_{mh}$，其中 $s_{mh}\in\{1,2,3,4,5\}$，$H_m$ 仅包含有足够证据的可评分家庭；同时报告 $|H_m|/8$。', '',
        r'配对偏好：$P_{m,b}=\frac{1}{|J|}\sum_{h\in J}\frac{u_{h,\mathrm{forward}}+u_{h,\mathrm{reverse}}}{2}$。胜、平、负分别记为 $1,0.5,0$；$J$ 仅包含两个顺序均可判断的家庭，同时报告缺失与顺序分歧。', '',
        r'三项记录错误率分别计算为 $E_k=n_{k,\mathrm{error}}/n_{k,\mathrm{checked}}$。每项分母对应其明确限定的检查事件，三类分母不混合；分母为零记为 N/A，证据不足另列，不按零错误处理。', '',
        r'固定过程案例通过率为 $T=n_{\mathrm{passed}}/n_{\mathrm{cases}}$，本轮 20 个案例是开发核验案例。以上量并不合成一个能证明真实人群有效性的总分。','']
    (output/'DisasterSociety_comparison_results_20260912.md').write_text('\n'.join(text))
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for field in ('runs','evaluation','output','process-suite'):
        ap.add_argument('--'+field,type=Path,required=True)
    a=ap.parse_args();r=summarize(a.runs,a.evaluation,a.output,a.process_suite)
    print([{k:v for k,v in x.items() if k in ('method','behavior_mean','decisions','input_tokens','output_tokens')} for x in r['rows']])

if __name__=='__main__':
    main()
