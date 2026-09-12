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
    for method in METHODS:
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
        rows.append({'method':method,'behavior_mean':behavior['scores'][method]['mean'],
            'scored_households':behavior['scores'][method]['scored'],'households':len(profiles),
            'independent_worlds':1,'decisions':len(decisions),'successful_gateway_calls':gw['n_ok'],
            'schema_repairs':sum(r.get('schema_repairs',0) for r in calls if r['status']=='ok'),
            'provider_retries':sum(r['status']=='provider_retry' for r in calls),
            'input_tokens':gw['live_prompt_tokens'],'output_tokens':gw['live_completion_tokens'],
            'estimated_cost_usd':gw['spent'],'minutes':status['wall_clock_seconds']/60,
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
    text=['# DisasterSociety 三方法小规模配对实验结果','',
        '本报告使用三种方法各自完整的真实模型运行和独立 Codex 评审。每组 8 户、25 步、同一随机种子。它是可报告的比较预实验，尚不能替代多次独立运行的正式主实验。','',
        '比较对象是共享灾害环境中的居民认知架构。两种外部方法是明确记录过领域改动的适配版本；不能称为完整原平台的直接复现。共享家庭承诺处理程序的优势不由这张表验证。','',
        '| 方法 | 行为合理性 /5 | 可评分/总户数 | 模型输入/输出 token | 耗时（分钟） |',
        '|---|---:|---:|---:|---:|']
    for r in rows:
        score='N/A' if r['behavior_mean'] is None else f"{r['behavior_mean']:.3f}"
        text.append(f"| {names[r['method']]} | {score} | {r['scored_households']}/{r['households']} | {r['input_tokens']:,}/{r['output_tokens']:,} | {r['minutes']:.2f} |")
    text+=['','绝对评分每户一次。反向会话对预先指定的两户做重复评分，只用于检查分歧，不替换主评分。家庭之间可能互动，因此 8 户不是 8 次独立仿真实验。','',
        '| 相对比较 | 我们的偏好胜率（平局计 0.5） | 双向均可判断/配对户数 | 正反顺序判断不一致 |','|---|---:|---:|---:|']
    for m,p in behavior['pairwise'].items():
        value='N/A' if p['ours_win_rate_with_half_ties'] is None else f"{p['ours_win_rate_with_half_ties']:.1%}"
        text.append(f"| DisasterSociety vs {names[m]} | {value} | {p['judgeable_in_both_orders']}/{p['paired_households']} | {p['order_disagreements']} |")
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
    for m in METHODS:
        text+=['### '+names[m],'']
        for score in behavior['scores'][m]['scores']:
            text.append(f"- {score['household_id']}：{score['score']}/5。{score['rationale_zh']}")
        text.append('')
    text+=['## 论文可怎样写','',
        '本轮可以写成“在同一灾害环境下，与两个已发表居民架构的灾害适配版本进行小规模配对比较，采用固定量表和匿名顺序评审报告行为合理性、计算代价及过程证据”。结果表可以作为初步比较结果，但单个种子不能支持“显著优于”或对真实人群的泛化结论。','',
        '还需要在正式结果之前固定独立重复的运行方案，并按实际差异和变异决定所需证据。Humanoid Agents、正式消融及独立场景测试集不在本轮完成名单中。','',
        '独立评审使用 Codex 会话，具体底层模型快照未知，不把 GPT 6 Astra 写成可调用的评审 API。行为文本可能暴露间接架构线索，匿名化不保证完美盲法。程序核验了结果格式、证据坐标及哈希，没有自动证明评审的语义结论。','',
        '成本按输入、输出各 USD 1/M token 的内部口径估计，实际 Packy 账单未核验。开发阶段失败和中止的调用另列在 development_attempt_register.json，不纳入完整运行的行为均分，也不隐去其消耗。','']
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
