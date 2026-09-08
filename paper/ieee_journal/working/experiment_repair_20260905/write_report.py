from pathlib import Path
import json

p=Path(__file__).resolve().parent
r=json.loads((p/'results.json').read_text())
audit=json.loads((p/'old_run_audit.json').read_text())
metric=r['metrics'];g=r['gateway']
rows='\n'.join(f"| {h['label']} | {h['members']} | {h['decision_members']} | {h['vehicles']} | {h['safe_members']} | {h['state']} |" for h in r['households'])
old='\n'.join(f"| {h['n_households']} | {h['seed']} | {h['repeated_members']} | {h['premature_execution_count']} | {h['members_missing_final']} |" for h in audit)
report=f'''# 主实验修复与真实短运行结果

本次完成的是现有 E1 主实验的代码修复和小样本核验。24 户、100 户实验设计保留，已有消融和跨模型结果保留。全量补跑尚未启动。

## 已交付

- 修复已接回实际项目 `/Users/linnuo/Documents/agentSimulation/disastersociety`，不是仅存在于工作副本。
- 重复出发、缺失成员状态、约定时间与当前意图冲突、协商回应、私有计划持续和执行反馈均有对应修复与回归检查。
- 真实模型运行完成 {r['completed_steps']}/12 步，状态 `{r['status']}`。逐步软件约束检查发现 {len(r['contract_violations'])} 项违规。
- 针对修复的 61 项测试通过；共享内核、机制与 Carr 入口的另外 28 项检查通过。共 89 项，不代表运行了仓库全部测试。
- 正式入口的 4 户 × 12 步离线接线检查通过；离线结果未作为行为结果使用。
- 五个受影响主实验任务已准备，见 [待补跑任务](prepared_main_runs.json)。这些任务还没有启动。

## 真实运行看到了什么

模型为原有 `packy-deepseek-v4-flash`，对应 `deepseek-v4-flash`，温度 0，保留 thinking enabled。样本为原画像中的第 1、2、5、7 户，共 12 人、7 名决策成员；这组样本用于覆盖家庭结构，不用于总体估计。seed=7201，每步 30 分钟，第 3 步建议撤离、第 7 步强制命令、第 9 步主路关闭。12 步是短窗口，原正式主实验仍为 25 步。

| 观察量 | 本次实际记录 |
|---|---:|
| 收到官方信息的决策成员 | {metric['official_recipients']} / 7 |
| 实际首次出发的决策成员 | {metric['first_departures']} / 7 |
| 全员到达安全区的家庭 | {metric['all_safe_households']} / 4 |
| 形成多人共同出发约定的家庭 | {metric['joint_agreement_households']} / 3 |
| 实际执行多人共同出发的家庭 | {metric['joint_execution_households']} / 3 |
| 曾生成持续计划的决策成员 | {r['private_plan_users']} / 7 |
| 重复出发、状态缺失及其他逐步约束违规 | {len(r['contract_violations'])} |

“到达安全区”只统计世界实际执行的状态变化。窗口内未出发保留为未出发，不自动算作错误，也不伪造出发时刻。多人协商的分母是具有至少两名决策成员的三户家庭，独居家庭不放进这个分母。

![信息、协商和出发的实际变化](main_preview.png)

![逐人决策及实际执行](actions_preview.png)

| 家庭 | 全部成员 | 决策成员 | 车辆 | 到达安全区人数 | 窗口末状态 |
|---|---:|---:|---:|---:|---|
{rows}

出发被拒绝的原因及次数：`{json.dumps(r['rejection_counts'],ensure_ascii=False)}`。这张表同时保留成功与失败的尝试，不能通过删除失败日志得到好看的比例。

本次运行{'没有出现多人共同出发，因此不能声称真实小样本已验证多人协商的效果。多人接受、封路失败、重新约定与共同执行的完整链条另有自动化回归测试；其证据性质是软件检查。' if metric['joint_execution_households']==0 else '出现了多人共同执行，具体约定、参与者、回应与执行时刻可在原始日志中逐条连接。'}这次运行证明的是修复后入口和统计能工作，不能用四户的数值提前替代正式消融结论。

## 哪些旧数据可以保留，哪些需要补跑

五条旧主实验记录已核查：

| 户数 | seed | 重复出发成员数 | 早于约定执行的出发组数 | 末态缺失成员数 |
|---|---:|---:|---:|---:|
{old}

原家庭画像、外部事件配置、随机种子、原始日志继续保留。成员名册缺失可以在明确假设下重建一部分统计，但提前执行和重复出发已经改变后续模拟，不能靠删重恢复正确过程。因此，这五条主实验的新过程结果需要使用修复代码补跑。补跑仍然是原来的 24 户三次和 100 户两次，不是重新设计整套论文实验。

已有消融和跨模型实验使用的 Carr 适配器没有被改成这套 E1 决策协议。共享代码的变动是增加决策前快照，以及可配置的暂时性请求重试；旧配置默认行为参数保留。历史结果不能直接与修复后的 E1 数值拼成配对比较；若未来把新指标用于消融，须在相同代码版本下配对运行。

## 运行记录与检查范围

本次最终运行的逻辑调用：新响应 {g.get('n_ok',0)}，精确缓存复用 {g.get('n_cache',0)}，失败 {g.get('n_failed',0)}，fallback {g.get('n_fallback',0)}。供应商请求数 {r['provider_requests']}，墙钟 {r['wall_seconds']} 秒。缓存只复用先前相同模型输入的成功响应；整次事件历史从初态重新生成，不拼接半次状态。

先前开发运行依次暴露了说明文字过长、提议与接受时间混淆、输出截断和 HTTP 520。修复依据及这些运行全部留档。当前输出上限 32768、请求超时 600 秒，暂时性服务错误最多尝试 3 次，等待 60/120 秒；鉴权与余额错误不重试。内部价格仅用于预算熔断，不作为已核实账单。

额外检查发现旧 E2 冻结测试错误地要求今天的源代码等于历史版本，且本轮之前已有多个文件不相等。已让该测试使用同文件现有的历史记录检查函数；历史哈希和数据配置都未改。源代码实际行为仍由运行测试检查。详见 [历史版本核查](historical_freeze_check.json)。

软件检查通过不等于保证所有模型会完成协商，也不等于保证论文效果。接下来正式实验要测的就是这些真实差异；不能在小样本里强迫模型产生有利结果。

## 文件

- [修复后的源文件及哈希](promoted_files.json)
- [代码差异](source_changes.diff)
- [旧主实验核查](old_run_audit.json)
- [逐步指标 CSV](process_metrics.csv)
- [逐人决策记录](household_trace.json)
- [完整结果 JSON](results.json)
- [真实事件日志](live_complete/e1_repaired_4hh_seed7201/events/events.jsonl)
- [实验设置和指标正文草稿](实验正文修订草稿.md)

论文正文和旧结果表没有被四户试跑数值覆盖。
'''
(p/'完成情况与结果.md').write_text(report,encoding='utf-8')
print(p/'完成情况与结果.md')
