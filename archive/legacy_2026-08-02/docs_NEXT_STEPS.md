# DisasterSociety 下一阶段执行路线（历史快照）

> `SUPERSEDED 2026-08-02`：本文件保留用于审计2026-08-01时的计划状态，
> 不再是活跃执行依据。当前唯一实验总账见
> `docs/EXPERIMENT_MASTER_PLAN.md`，事实状态见`docs/EVIDENCE_LEDGER.md`。

**更新日期**：2026-08-01
**目标**：在不更换论文方向、不扩展第二城市的前提下，把 Carr Fire 从历史
简化 pilot 推进为可审查的 Carr-informed controlled case。

## 1. 当前实现缺口

| 区域 | 已有基础 | 关键缺口 | 当前状态 |
|---|---|---|---|
| 通用 kernel | batch 意图/执行边界、组件随机流、日志、网关、三类终态；v6 channel-specific消息与可行承诺；受控 Carr-S adapter | v6声明后端 pilot 与正式协议运行 | `VERIFIED` 基础 / `PILOT` 集成 |
| EventPack | Carr manifest、正式 schema、声明资产校验和 warning/control loader | 来源字段审计、案例冻结和正式危险/道路时序 | `VERIFIED` 基础 / `PLANNED` 冻结 |
| 人口 | 规范 raw donor build 已核验；1000 户/48 tract pilot 已保存 | 冻结 full ACS base 与实验子样本关系；处理 person-age 诊断偏差 | `VERIFIED` 构建 / `PILOT` 人口 |
| 环境 | toy world、队列模型；2018 TIGER 双路线已进入 Carr World | 权威危险/关闭时序或冻结的受控扰动协议、正式资源参数 | 路线适配 `VERIFIED` / 动态时序 `PLANNED` |
| 居民 | 状态、记忆、信任、结构化意图、执行后提交；可执行计划；v6 proposal时间与在途合同 | v6 DeepSeek backend pilot 后冻结正式seed数，补充正式行动后果范围 | 部分实现 |
| 互动 | 分离的家庭DM/community送达、消息生命周期、结构化proposal、系统可行性检查、可版本化家庭commitment | 真实邻里网络路由、帮助过程与声明后端协调结果 | 受控实现 / mock已验证 |
| Carr 行为数据 | 核心映射、330人评价集合、198/66/66 split、字段角色和矛盾规则已冻结 | 公平基线重跑与最终 prompt 泄漏审计 | Gate A 协议已关闭 |
| 评价 | 指标函数、分析计划 | 独立经验目标、家庭/网络指标、预注册消融 | `PLANNED` |

## 2. 必须按顺序通过的门

### Gate A：Carr 数据修复（核心部分已于 2026-07-31 完成）

核心标签、时间、渠道字段、评价 respondent、共用 split 和矛盾规则已冻结。
在最终 prompt/feature 泄漏审计前，不启动付费的出版用途 LLM 运行。

交付物：

已完成：

1. 问卷与 Qualtrics 字段审计表；
2. 撤离筛选、离开时间、预警时间和多选渠道映射；
3. outcome 缺失与排除原因；
4. 新版清洗数据及机器可读 QA；
5. 330 人 respondent evaluation set；
6. 从基线输入中删除 Q13.6 post-outcome 感知。

已关闭：

1. 所有模型共用的 `evaluation_index` train/validation/test split：
   198/66/66；
2. 15条命令回答矛盾记录：渠道主分析排除，敏感性分析采用肯定命令回答优先，
   不因该矛盾删除有效 Q9.1 outcome。

通过条件：

- `evacuated` 不再由 `warned_official` 派生（已通过）；
- 观测撤离时间均不早于点火时间（已通过）；
- 每一行 outcome 排除都有机器可读原因（已通过）；
- 清洗脚本在相同原始输入上可确定性重建输出（已通过）；
- 证据台账同步更新（已通过）。

### Gate B：Carr 最小端到端内核

不恢复旧 Carr 专用引擎，直接扩展通用协议。

最小实现：

1. EventPack schema 与 loader；
2. 冻结 full ACS base population 与机制/规模实验子样本的关系；
3. 预声明 person-age diagnostic 偏差的限制与敏感性规则；
4. 将非智能体 `Household` 基础对象接入 Carr：成员、车辆、资源预约、物理状态和已接受承诺；
5. resident adapter：decision capability/policy、受限信息、行动状态和后果；
6. Carr batch world resolver：同快照 intents、道路/车辆/照护集中仲裁、execution outcomes；
7. network-aware interaction：家庭、邻里、公共渠道与消息生命周期；
8. 可执行计划对象和机制开关；
9. 标准日志：意图、执行结果、消息、计划、拒绝、终态和 provenance。

通过条件：

- mock 后端的 Carr 小场景可重复；
- 未送达信息不会进入 resident prompt；
- 非法道路、车辆、家庭和资源行动由 world 拒绝并记录；
- 同一步共享车辆请求不双重分配，结果不依赖 agent 输入顺序；
- donor household 的 person rows 原子复制且模拟 ID 唯一，原始 `SERIALNO` 不泄露；
- 每个机制开关确实改变代码路径；
- 测试覆盖家庭协调、网络延迟、受阻重规划和 fallback。

### Gate C：小规模机制 pilot

先用恰有两名成年决策成员的受控 donor household、20–50 个家庭和配对
seed 检查 full + drop-one 指标与效应方向：

- memory：重要事件保持与跨时矛盾；
- feedback：新信息后的响应方向和延迟；
- planning：可行性、完成、受阻与重规划；
- interaction：消息覆盖、延迟、求助响应与家庭协调；
- system：完成率、fallback、时间、tokens 和成本。

若模块没有改变其目标指标，先检查实现；仍无作用则缩小 C2，不改指标救结论。

首轮机制接线开发期 pilot、非饱和50-run pilot 和三场景150-run稳健性
pilot 均已完成。mock 结果表明开关路径可辨识，并为四项指标提供 seed 方差；
但它们不是生成式后端行为证据。五种子 DeepSeek backend pilot 已完成，结果为
22个 `VALID`、3个 `INVALID` run；可用配对方向不稳定且 memory 仅剩2对。
5户 v5 后端可用性门曾2/2 `VALID`、零 fallback，但v5在2/16后因家庭DM暴露、
提议时序和interaction指标口径缺陷暂停，原始结果全部保留。修复后的v6已用
20户、5条件、10 seed完成50-run零成本验证并冻结协议合同；Gate C 下一道门是
小型v6声明后端pilot，而不是继续v5或直接启动正式矩阵。

### Gate D：冻结评价协议

在正式运行前冻结：

- 每项主张的分析尺度和证据类型；
- 主要/次要指标与方向性预测；
- 条件矩阵、配对 seed、模型、prompt 和样本量；
- Carr-R 字段的 input/calibration/evaluation-only/excluded 角色；
- run-level 配对 estimand、MCSE/区间精度与正式 seed 数；
- component-isolated common random streams；
- 校准目标与独立评价目标；
- 排除、失败、重跑和多重比较规则；
- 人工/专家评价 rubric 与评审者一致性方法。

E2 v5 的历史冻结与2个已完成seed均保留，但协议因有效性缺陷暂停，不能继续。
E2 v6 已冻结消息/承诺合同、五条件和四项主要指标，并通过确定性mock验证；
正式模型、seed数、MCSE/区间目标须在预声明的小型v6声明后端pilot后冻结。
E1经验目标、盲评和完整E3协议仍待冻结，不能用E2局部冻结冒充整个Gate D已关闭。

### Gate E：正式运行与写作

执行顺序：

1. E0 系统验证；
2. E1 经验与行为有效性；
3. E2 配对机制消融；
4. E3 稳健性与效率；
5. 最后填写摘要结果、Results 和贡献完成式。

只有 `VERIFIED` 结果进入摘要和结论。Carr 仍作为 Carr-informed controlled case，不据此声称跨灾种
普遍性。

## 3. 最近一轮最小任务包

当前已建立独立工作分支并完成 kernel 因果、随机流和终态基础修复。接下来：

1. 审查可跟踪文件范围，继续排除原始答卷、respondent ID 派生表和预测 CSV；
2. 根据已保存 pilot 冻结 base population、子样本和 person QA 协议；
3. ~~将 `Household` 与 batch API 接入受控 Carr 路线、车辆和照护约束~~；
4. ~~生成 Carr-R 共用 split，并固化15条矛盾记录的规则和字段角色~~；
5. ~~定义 EventPack/Carr adapter 的最小接口~~；
6. ~~实现 mock 后端的受控两成人家庭场景与 full + drop-one 测试~~；
7. ~~把抽象路线 resolver 接到实际 Carr 道路图的受控子图，不冒充历史关闭~~；
8. ~~为机制 pilot 加入非饱和扰动，并确认四项配对差值均有 seed 方差~~；
9. ~~完成 Carr-R 四个人口学输入的公平传统模型 validation pilot，并保持 test 封存~~；
10. ~~执行新 DeepSeek 的1条连通性检查和66条 validation，并保持 test 封存~~；下一步运行无事后信息的情境一次性基线并决定正式 test 门槛。
11. ~~实现并运行同一 Carr runner 的 DeepSeek v3 backend pilot~~；2户 × 5条件 × 2 seed 共10个 run 全部 `VALID`、零失败/零 fallback。四项主差均为一个 seed 正、一个为零；先核验关闭修复和互动指标更正，再扩展预声明 seed，不能直接冻结正式数量。
12. ~~扩展 backend pilot 已按预先固定的 seed 303/404/505、2户、5条件、同一 v3 prompt 全部执行~~；新增15个 run 中12个 `VALID`、3个 `INVALID`，与原 pilot 合计22/25 `VALID`，没有按中间方向停止。
13. ~~恢复账户并完成新 run ID 的 v5 五户可用性门~~；首个 attempt 暴露 provider seed 范围并中断保留，31位映射修复后 full/−memory 2/2 `VALID`、59/59成功、零 fallback。
14. ~~暂停E2 v5并保留全部artifact~~；已建立机器可读暂停标记和只读漏斗诊断，剩余14个seed不再执行，停止依据是协议有效性而非中间方向。
15. ~~修复并冻结E2 v6协议合同~~；家庭DM/community分离、未来时点proposal、在途抑制、可行acceptance、承诺修订历史与四项主要指标已冻结；20户×5条件×10 seed的50-run mock验证和独立重放已通过。
16. 预声明并运行小型v6声明后端pilot；用有效配对差方差、MCSE或目标区间半宽冻结正式seed数。只有该pilot通过artifact、fallback、成本和协议审计后，才另行放行正式付费矩阵。

付费运行已获用户授权，但必须保留凭据门、调用数上限、缓存和 test 封存。
实际后端关闭、seed范围和历史五户可用性门已通过；当前直接任务是设计并执行
小型v6声明后端pilot，同时冻结E1经验评价和其余Gate D协议。Carr-R test继续封存。

## 4. 当前不做

- 不增加第二座城市或第二灾种；
- 不追求自动生成完整城市；
- 不把个体 F1 设为项目成败标准；
- 不继续运行旧 `e1_dynamic.py` 或旧 Carr runner；
- 不在家庭、道路和计划尚未成为可执行状态前宣称这些机制已实现；
- 不把同一调查边际同时用于参数校准和独立验证。
