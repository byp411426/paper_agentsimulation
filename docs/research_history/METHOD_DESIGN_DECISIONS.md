# DisasterSociety 方法设计与决策依据

状态：`ACTIVE`

最后核对：2026-08-02

本文件冻结首篇论文的方法架构，记录设计选择、替代方案、证据边界与当前实现状态。它不替代代码事实、证据台账或正式实验协议：

- 当前代码与数据事实见 `docs/EVIDENCE_LEDGER.md`；
- 论文定位见 `docs/PAPER_STRATEGY.md`；
- 正式实验设计见 `disastersociety/experiments/analysis_plan.md`。

状态标签：

- `DECIDED`：方法选择已经确认，但不表示代码已完成；
- `IMPLEMENTED`：当前代码已接通，仍需结合测试范围理解；
- `VERIFIED`：代码、数据和重复结果已核查；
- `ENGINEERING_VALIDATION`：只核验接线、接口和不变量，不评价行为效果；
- `PILOT`：真实后端开发运行，不能直接作为正式论文结论；
- `RUNNING`：冻结实验正在执行，完整审计前没有正式结果；
- `SUPERSEDED_BEFORE_PAID_EXECUTION`：旧实现/协议保留，但在付费科学运行前已被取代；
- `PLANNED`：尚未实现或尚未执行；
- `DEFERRED`：不作为首篇论文前置条件。

## 1. 论文对象与基本本体

### R1. Carr-R 与 Carr-S 分轨 — `DECIDED`

Carr 案例分成两个不强行一一对应的评价轨道：

| 轨道 | 评价对象 | 主要用途 | 不允许的推断 |
|---|---|---|---|
| Carr-R | 去标识的真实问卷受访者 | respondent-conditioned 信息充分性辅助诊断；在共同样本、信息集和排除规则下报告 F1、Brier、ECE 等 | 不代表合成家庭过程；不把个体指标恢复为论文主线；不得再称原 test 为 untouched holdout |
| Carr-S | 合成居民、家庭与社会网络 | 家庭协调、互动、约束、群体过程、稳健性与系统评价 | 不把合成居民映射为某个 Carr 真实受访者 |

Carr 调查分布只有在抽样设计、权重、目标总体和 estimand 对齐后，才能作为 Carr-S 的外部经验目标；否则只称 respondent sample 的描述性参照。

同一个 Carr-R 变量在同一实验中不得既作为运行输入又作为评价目标。所有调查字段必须预先标记为：

`runtime input / calibration / evaluation-only / excluded`。

四字段 Carr-R validation 的 DeepSeek live 与统一事前情境敏感性均未识别
7名未撤离者；它们只表明年龄段、家庭规模、车辆和收入这四个粗字段不足。
2026-08-02 的完整字段信号诊断按用户要求检查了全部330人的候选特征—结果
关系，因此原66人test已改为`OPENED_FOR_DIAGNOSTIC`。此前validation运行时
test确实封存，但此后不能把同数据的新结果称为正式holdout；若继续个体任务，
只能明确使用开发交叉验证、重新声明的外部数据或新的前瞻样本。

### R2. Resident、Household、World 与 Interaction — `DECIDED`

- `Resident` 是生成式认知与决策单位，拥有私有 inbox、memory、判断、计划、意图和消息处理状态。
- `Household` 是共享资源、成员关系、照护责任、共同承诺和协调约束对象，不是取代成员的统一 LLM。
- `World` 保存物理状态、道路、资源与危险，并对行动意图实施统一仲裁。
- `Interaction` 负责信息实际发送、投递、处理和接受，不允许 prompt 假装通信已经发生。

首篇论文承诺支持受控的多决策成员家庭，但不承诺所有家庭成员、所有时间步都调用 LLM。正式家庭机制实验优先使用恰有两名成年成员的 donor household；更大家庭进入敏感性或系统实验。

当前状态：

- toy `Resident` 与基础 World/Interaction：`IMPLEMENTED`；
- Carr-S 受控两成人家庭、依赖状态、共享车辆、消息承诺和道路
  resolver：`IMPLEMENTED / PILOT`；
- 2018 TIGER 双路线派生资产与通用 World 接线：`VERIFIED` 派生资产 /
  `INTEGRATION_CHECK` 运行；
- 声明 DeepSeek 后端、凭据门、并发、缓存、预算和 provenance：
  `IMPLEMENTED`，2户 × 5条件 × 2 seed 的实际 backend pilot 为 `PILOT`；
- 权威危险/道路关闭时序和经验目标下的正式运行：`PLANNED`。

### R3. 决策资格、策略与唤醒分离 — `DECIDED`

成员状态必须区分：

- `decision_capable`：稳定的独立决策资格；
- `decision_policy`：`generative | rule | dependent`；
- `awake`：本时间步是否因新信息、风险变化、计划失败或检查点而被唤醒。

成年人默认 `decision_capable` 是透明的基线假设，不是心理或法律事实。PUMS 的 `DIS`、`DEAR`、`DEYE`、`DREM`、`DPHY`、`DOUT`、`DRAT` 应保留为分项约束；失能首先影响信息接收、移动、照护与执行条件，不能由聚合 `DIS` 自动推断为缺乏决策能力。

依赖成员不必调用 LLM，但至少保存位置、安全、照护者、移动能力、交通资源和执行状态。

## 2. 人口合成协议

### R4. 家庭级拟合与整户 donor 重采样 — `DECIDED / IMPLEMENTED-FOUNDATION`

首篇论文采用：

> `WGTP` 基础权重 + tract 家庭级边际调整 + 整户 donor household 重采样。

固定拟合四组家庭级边际：

1. 收入；
2. 车辆；
3. 家庭结构；
4. 家庭中是否存在老年成员。

抽中 donor household 时：

1. 通过 `SERIALNO` 连接 housing 与全部 person records；
2. 整体复制其成员，保留年龄、亲属关系、成员数量和分项失能结构；
3. 生成新的 synthetic household ID 与 resident ID；
4. 原始 `SERIALNO` 仅进入受限 provenance，不作为模拟身份。

必须分别报告：

- IPF 分数权重的家庭边际误差；
- integerization/加权抽样后的家庭边际误差；
- effective sample size；
- donor 重复率和极端权重；
- person-level 描述性 QA。

年龄是“未参与直接拟合的 person-level diagnostic margin”，不是独立 holdout；65+ 年龄与已拟合的 older-adult-presence 部分耦合。家庭规模只有在加入有明确来源和 provenance 的 ACS 目标后，才能成为拟合边际。

不声称 person-level 联合边际已经拟合，不声称 PUMA donor 是 tract 或 Carr 中的真实家庭。完整 household–person IPU 为 `DEFERRED`。

数据结构审计已 `VERIFIED`：

- 4,317 个过滤后 household；
- 9,968 条关联 person records；
- `NP` 不一致为 0；
- 同户重复 `SPORDER` 为 0；
- reference person 缺失或不唯一为 0；
- 无 person household 为 0；
- `WGTP` 范围 1–118；
- 48 个 tract 的四组家庭边际总户数逐 tract 一致。

旧的均匀 `run_ipf()` 入口已退役。当前代码已实现带 `WGTP` 的 IPF 结果对象、
结构零和总量检查、tract 分配与四边际拟合、整户成员原子复制、唯一 synthetic
IDs、两层误差、ESS、donor 重复 QA、两成人 cohort 和 raw PUMS builder，并
由离线单元测试覆盖。规范 Carr raw build 已生成并核验 4,317 户/9,968 人
donor 表；1000 户/48 tract 产物为 `PILOT`，fractional fit 收敛但未拟合年龄
诊断存在明显 tract 偏差。正式 base population 规模、实验子样本策略和
person-level 敏感性规则仍为 `PLANNED`。

## 3. 信息、计划与行动因果协议

### R5. 部分可观测与协调状态 — `DECIDED`

必须区分三类状态：

- 私有认知：inbox、memory、风险判断、私人计划；
- 可观察物理状态：位置、车辆占用、是否已离开；
- 已接受协调状态：经显式沟通并被接受的共同承诺和资源预约。

共同在场不自动同步私有认知。家庭消息的最小状态机为：

`sent → delivered → processed → accepted/rejected`

只有论文确实分析确认过程时才增加 `acknowledged`。消息到达不等于计划接受。

2026-08-01 的 v6 协议在结构化 proposal payload 基础上进一步冻结：家庭DM与
community 使用不同送达率；proposal 的 depart step 不得早于收件人处理阶段；
发送方在收件人处理窗口内把提议标为在途，不重复覆盖；recipient 明确返回
`accepted` 后，Interaction 还必须检查双方家庭决策成员身份、家庭车辆和时间
可行性。新承诺可取代旧承诺，但旧记录改为 `cancelled` 而不删除。该闭环已有
单元测试、50-run mock验证和确定性重放证据，但尚未形成外部经验有效性证据。

### R6. 同快照意图收集与集中仲裁 — `DECIDED / IMPLEMENTED-FOUNDATION`

每步顺序固定为：

1. World 和外生事件推进；
2. 信息投递与居民唤醒；
3. 所有醒来居民在同一不可变世界阶段上产生意图；
4. World 集中检查位置、资源、照护与时间约束；
5. 先使用确定性优先规则，只对仍无法区分的冲突使用 seeded tie-break；
6. 返回 executed/rejected/partial 结果；
7. 只有执行结果可以提交物理状态；
8. 结果进入反馈并触发后续重规划。

意图、仲裁动作、执行结果与拒绝原因必须分别记录。决策/意图不得在仲裁前写入 `evacuating`、`evac_step` 或其他已执行状态。

2026-07-31 已在通用 kernel 和 toy world 中实现
`IntentEnvelope[] → resolve_batch → apply_batch → keyed outcome → commit`
闭环，并添加拒绝意图和输入顺序回归测试；Household 已有共享车辆的批量
冲突仲裁基础。受控 Carr-S adapter 已把抽象路线关闭、共享车辆、依赖成员
照护和家庭共同移动接入该批量边界并通过离线测试。2018 TIGER 路网已经派生
出两条可追踪路线并进入同一 Carr World；其中道路阻断仍是算法选择的受控
扰动，不是历史观测关闭。权威关闭时序和正式资源容量仍为 `PLANNED`。

### R7. 机制操作化 — `DECIDED / IMPLEMENTED-PILOT`

每个模块只冻结一个主要指标族：

- memory：受控相关事件的跨时保留，以及证据不变时的无依据矛盾；
- feedback：预声明扰动后在规定时间窗内发生方向正确的状态/行动更新；
- planning：原计划受阻后，新计划通过确定性可行检查并进入执行；
- interaction：受控扰动后，消息 delivered 且 processed，并形成通过成员、车辆与时间检查的可行承诺；出发时间不硬编码为唯一固定步。

家庭成员 departure-time gap 是描述性结果，不预设越小或越大越好。Trust 保持为 information/feedback 的子状态，不单列论文贡献。

首轮零成本机制接线工程验证已运行20户、5条件、5个配对 seed。四个主指标均
按预期区分 full 与 drop-one，但差值全部为1、跨 seed 方差为0。该结果仅为
`ENGINEERING_VALIDATION`，证明开关改变了目标代码路径；由于场景和 deterministic mock policy
过于饱和，不能用于 seed 数、区间或正式行为效应推断。

第二轮非饱和 mock 工程诊断加入配对 seed 控制的预警接收、家庭消息送达、
道路关闭时点和路线容量；20户、5条件、10 seed 共50个 run 全部 `VALID`、
零 fallback、零成本。memory、feedback、planning 和 interaction 的平均配对差
分别为0.580、0.975、0.455和0.480，跨 seed SD 分别为0.170、0.079、0.249
和0.220。该方差可用于设计下一轮声明后端 pilot，但禁用模块时对应专属指标
仍为结构性0，且决策策略仍为 deterministic mock，因此正式 seed 数尚未冻结。

第三轮 mock 工程网格在低接收/低容量、参考、高接收/高容量三种场景下
执行150个 mock run。四项配对主差值在每种场景中均保持正方向并具有 seed
方差；该结果仅用于检查接线、场景扰动和后端 pilot 设计，状态为
`ENGINEERING_VALIDATION`，不得作为正式稳健性或生成式模型行为证据。

声明后端 v3 pilot 使用 `packy-deepseek-v4-flash`、2户、5个 full/drop-one
条件和2个配对 seed，共10个 run。119次逻辑决策全部成功，10个 run 均为
`VALID`，无失败和 fallback；内部价格表估算成本为0.493576美元。按预先冻结
的主指标重新核对后，memory、feedback、planning 和 interaction 的平均配对
差为0.25、0.083、0.50和0.25，但四项均只有一个 seed 为正、另一个为0。
该结果证明实际后端管线可执行并暴露高 seed 方差，不足以冻结正式 seed 数或
支持机制效应。原始矩阵曾把 interaction 错映射到下游 coordinated departure；
派生汇总已按既有 R7 定义更正为 compatible commitment，并保留原始矩阵不覆盖。

预声明 v3 扩展随后完整运行 seed 303/404/505。与原两 seed 合计25个 run：
22个 `VALID`、3个 `INVALID`，332次成功决策、3失败/3 fallback，内部估算
成本1.349111美元。含无效 run 的配对严格排除，因此 memory 只有2个有效对，
其余模块各4对；方向比例分别为0.50、0.25、0.75、0.75。这些不完整且混合的
对比不能冻结正式 seed 数。

v4 使用新 prompt/run ID 顺序复核三项失败。404/full的长度边界和303/−memory
均零 fallback 通过；505/−memory在第7–8步因代理返回 `Insufficient Balance`
产生3次 fallback并为 `INVALID`。该复核只属于工程可靠性证据，不回填 v3
配对。余额恢复前停止新的付费矩阵。

2026-08-01 新凭据恢复后，代理暴露只接受31位有符号 seed。模型注册表现声明
`provider_seed_max=2147483647`，网关保留32位逻辑 seed 作为缓存/共同随机流
身份，并确定性映射、同时记录 provider seed。新 run ID 的5户 full 与5户
−memory availability gate 均为 `VALID`，59次决策零失败/零 fallback。该结果
只证明当时的付费后端可用性，不是机制效应。

v5 seed 101/202 的10个run均为`VALID`且保留，但只读漏斗核查发现：两个full
run合计62条消息仅12条送达、7条处理、1条接受，且该接受在处理时已过期，最终
没有可执行/当前相容承诺。原因是家庭DM错误复用0.15社区送达率、提议与下一阶段
处理的时间合同不一致，以及interaction指标硬编码固定出发步。v5因此在2/16后
按协议有效性暂停，不是按中间效应方向停止；剩余seed不执行，旧数值不回填v6。

v6 已冻结上述消息、时间、接受和承诺修订合同，并把interaction主要指标改为
`post_closure_feasible_commitment_rate`。20户、5条件、10 seed 的透明mock验证
50/50 `VALID`，12,520次逻辑决策零失败/零fallback/零成本、无无效提议或接受；
两个独立输出目录的矩阵哈希一致，10个full run均完成扰动后承诺和协调撤离。
四个drop-one差仍饱和为1、seed方差为0，所以这里冻结的是可执行v6协议和工程
接线，不是
正式效应或seed数；下一步必须先做预声明的小型声明后端pilot。

v7 随后把居民感知路线与真实 World 分离，并为所有条件设置相同的私人主路线
初始计划；v8 再把执行拒绝、近期反馈、车辆占用和已接受承诺的精确执行语义送回
下一步 prompt。v8 出版用途 E2 于2026-08-02冻结为8户、5条件、12个全新独立
seed，共60个真实 DeepSeek thinking-high run。正式报告把四个模块专属过程指标
作为 manipulation checks，同时预声明非结构性下游结果：完整家庭安全出发、
关闭路线拒绝、协调出发和资源/照护约束。这样既保留模块构念的直接测量，也不把
禁用模块后的结构性0作为唯一效应证据。矩阵完成审计前仍为 `PILOT`。

首次 `r1` 运行因 Codex 宿主任务中断，只留下两个 terminal full 和两个无终态
−memory 目录。恢复选择在读取机制指标前按运行完整性作出：全部 `r1` 仅保留为
审计产物，`r2` 对12个 seed 的五条件完整重跑；科学配置逐字段等价，禁止跨版本
拼接配对。

`r2` 也因任务切换在两个 full 形成终态前被宿主终止。第二份恢复修订在未读取
科学指标前冻结 `r3`：继续使用完全相同的60格科学配置，仅把执行传输改成两个
detached lane；每 lane 对首个异常 fail-closed，不自动重试。

`r3` 中 seed1103/full 完成且为 `VALID`，但 seed1201/full 在第7步出现两个
240秒后端超时并以 `ABORTED` 终止；并行的 seed1103/−memory 随即按停止规则
中断。`r4` 因此排除全部 r3 产物并完整重跑60格。其科学设计不变，只把每lane
并发从12降至6、单请求超时从240秒延长至600秒，并要求不与其他付费实验重叠。
这些是运行运输修复，不能被解释为机制设计变化或选择性重跑。

Carr-S E1 的外部参照采用 respondent-sample 聚合量：Q9.1 撤离比例、首次报告
命令到出发的非负延迟、多选渠道 prevalence 和预声明群体差异。主延迟分析排除
命令矛盾，敏感性采用肯定命令优先；渠道总体接收率标为 calibration。零车辆组
在冻结后预检查发现 n=0，因此保持不可估计且不新增替代对比。

E1 自然时序v1的50户固定cohort和五个真实DeepSeek seed协议已经冻结，但在
任何付费执行前即被字段审计否决，状态为`SUPERSEDED_BEFORE_PAID_EXECUTION`。
原因是它只有年龄、失能、家庭规模、车辆、收入和家庭结构等薄画像；首名成人
自动作为coordinator、车辆容量至少容纳全家，且全部家庭共享同一危险轨迹与
step-1强制命令。该设计虽然能运行，却不能代表Carr总体中不同命令暴露、家庭
角色、风险担忧、工作/财产责任和撤离摩擦，不得为了复用已写代码而继续执行。

E1 v2 的方法决定为`DECIDED / PLANNED`：

1. 从PUMS housing/person原始文件重建whole-household donor v2，保留预声明的
   就业、教育/通勤、住房/产权、信息接入、家庭关系和分项失能等灾前静态字段；
2. 只从Carr train抽取不含结果的完整trait block，并只用共同的非结果静态字段
   粗匹配；不按Q9.1分层抽样，不拟合`P(trait | outcome)`；
3. Q29只作为带回忆偏差标记的事前信念潜变量，并在看Q9结果前冻结为危险担忧、
   撤离摩擦、生命/住房威胁、基础设施/救援、财产安全和工作义务等理论因子；
4. 命令、渠道、危险、道路、家庭和网络消息都按时间进入inbox；居民没收到或
   没处理的信息不能出现在prompt；
5. Q9.1、Q10/Q11结果分支、Q13撤离/出发时字段、事后行为、身份、地址和自由
   文本永久排除出runtime input；
6. 离线lineage/leakage QA后，先运行约20户×2新seed的真实DeepSeek预检，再按
   run-level方差重新冻结正式户数和seed；E1正式实验只跑full自然过程，不复用
   E2的drop-one矩阵。

Carr同一调查既提供部分潜变量初始化又提供Q9/Q13聚合参照，会降低证据独立性。
首篇论文只能称`Carr-informed empirical reasonableness`，不能称独立外部验证。

## 4. 实验与推断协议

### R8. Full + drop-one 消融 — `DECIDED / E2-V8-RUNNING`

条件固定为：

- static one-shot（辅助参照，不作为模块消融）；
- full；
- full − memory；
- full − feedback；
- full − planning；
- full − interaction；
- 可选 full − household coordination。

每个 drop-one 估计的是“其余模块存在时移除该模块”的条件效应，不声称识别模块的普遍独立效应或模块交互。首篇论文不把完整 factorial 设为前置条件。

### R9. 组件隔离共同随机流 — `DECIDED / IMPLEMENTED-FOUNDATION`

随机数由以下键派生：

`derive(run_seed, stream_name, entity_id, step, draw_index)`

至少使用：

`population / hazard_spread / warning_delivery / network_delivery / arbitration / llm_decision`

实验条件名不得进入共同外生随机流。full 与 drop-one 保留的相同组件使用相同随机输入；移除模块只停止使用该模块自己的流。LLM prompt 或历史改变后，生成轨迹可以自然分化，共同随机数只控制可配对的外生随机性。

2026-07-31 已实现命名随机流，并将 toy hazard、warning delivery、Carr
network delivery、arbitration 和 LLM decision 分流；Carr 正式 runner 的
全流审计仍为 `PLANNED`。

### R10. 统计重复单位 — `DECIDED`

`seed × condition` 的独立 run 是正式重复单位。resident、household 和 resident-step 都是同一共享世界中的嵌套、相关观测，不能直接当独立重复。

正式分析：

1. 每个 seed 内分别形成 full 与 drop-one 的 run-level 指标；
2. 计算同 seed 配对差值；
3. 跨独立 seed 报告差值、区间和方向稳定性；
4. 使用个体明细时采用含 run/household 结构的聚类或分层模型。

正式 seed 数在 pilot 后依据关键配对差值的方差、Monte Carlo 标准误
`s_D / sqrt(R)` 或目标区间半宽冻结，不能事先凭惯例写死。

## 5. 运行有效性与失败处理

### A1. fallback 率和终态 — `DECIDED / IMPLEMENTED-FOUNDATION`

逻辑决策 fallback 率固定为：

`n_fallback / (n_ok + n_cache + n_fallback)`

`n_failed` 仅作后端可靠性诊断，因为一次 backend failure 后接 rule fallback 仍是一条逻辑决策。失败与 fallback 日志共享 decision ID。

运行终态：

- `VALID`：完整完成并通过最终工程门槛；
- `INVALID`：完整完成但未通过最终门槛；
- `ABORTED`：预算、认证、全局后端故障或灾难性异常导致未完成。

所有终态都必须写 summary、已完成步数、停止原因、gateway 统计与成本。普通早期 fallback 不因暂时比例高而立即中止。最终 fallback >1% 是本项目预声明的工程门槛，不是普遍科学标准；付费运行的提前停止规则需在 Gate D 另行冻结。

不能按条件事后只筛选零 fallback run。`INVALID` 与 `ABORTED` artifact 保留；修复后重跑使用新 run ID，不覆盖历史运行。

2026-07-31 已实现上述 fallback 分母、三类终态、预算中止 summary 与基础回归
测试。Carr runner 已支持声明模型注册表、凭据前置门、同快照并发决策、逐 run
缓存和凭据不落盘 provenance。v3 pilot 核查了实际代理认证和零 fallback
终态；退出时暴露 LiteLLM 异步 HTTP 会话未关闭警告，现已增加同事件循环
关闭与墙钟计时。修复后的实际连通性复核以9/9成功决策、零 fallback、
218.138秒墙钟完成，进程无未关闭会话警告。全局后端故障 reason code 仍待
专门故障注入核查。v4 余额耗尽后，网关已增加 billing/auth 非重试分类并让
引擎以 `BACKEND_UNAVAILABLE` 终止为 `ABORTED`；离线回归已覆盖，仍需余额
恢复后的最小 live check 已以2/2 `VALID` 通过，不能用该检查或旧 `INVALID`
artifact 反向改写机制结果。

### A2. Carr 渠道指标 — `DECIDED`

Carr `Q6.1/Q7.1` 是多选渠道 prevalence，不是互斥概率分布，也不是 first-heard share。因此：

- 逐渠道报告 percentage-point error 与区间；
- 可汇总 mean absolute percentage-point error；
- 不对归一化后的渠道值计算 L1/JS distribution distance；
- first-heard 只能作为模拟内部过程指标，除非找到同 estimand 的外部目标。

### A3. Carr 情景边界 — `DECIDED`

当前案例统一称：

> Carr-informed controlled case/scenario

现有官方 final perimeter 不是时间序列，当前又缺少权威道路关闭时序。因此案例可以使用 Carr 的地理、人口与调查约束构建受控情景，但不能声称历史重建或真实时间线复现。只有接入有 provenance 的权威时序 hazard/closure 后，才重新评估表述。

## 6. 证据与写作边界

1. 方法架构已 `DECIDED` 不等于功能已 `IMPLEMENTED`，更不等于结果已 `VERIFIED`。
2. Carr `Q9.1` 只评价焦点受访者是否撤离，不能验证家庭协商、车辆分配或成员信息过程。
3. 家庭过程当前可由可执行约束、配对消融、受控扰动和盲法人工/专家评价支持；无 Carr 外部真值的部分不得声称经验验证。
4. 历史模型、运行和结果 artifact 不删除；其证据状态按台账保留。
5. 主文只保留研究对象、实体边界、核心循环、算法、estimand 与证据边界；完整 ODD、状态与调度细节进入补充材料。
6. 题目仍是候选，待 Carr runner、家庭机制和正式证据完成度明确后再冻结。

## 7. 近期 Gate

### Gate B：实现基础

- [x] 完成 household–person donor 构建、WGTP 初始化和四组家庭边际拟合；
- [x] 实现 `Household`、分项成员状态、车辆/照护约束和批量仲裁；
- [x] 实现家庭消息状态机与 network delivery；
- [x] 完成 Carr-R/Carr-S runner 分轨；
- [x] 对当前正式路径使用的随机组件和终态进行回归测试。

Gate B只证明实现基础；1000户人口仍为`PILOT`且person-level未校准，不能由此
推断经验真实性。

### Gate C：离线受控机制实验

- [x] 使用恰有两名成年成员的受控 donor household；
- [x] 以mock完成工程接线和不变量验证，但不把mock当作行为效果证据；
- [x] 以真实DeepSeek完成小型full + drop-one开发pilot；
- [x] 验证模块主要指标和作用机会，并以v7真实后端方差冻结v8 E2 seed数。

### Gate D：正式协议冻结

- [x] 冻结E2 v8 cohort、条件、12 seed、区间方法、fallback/abort与恢复规则；
- [ ] 完成E2 r4 60格并进行完整终态、hash、配对、MCSE和方向审计；
- [ ] 实现并重新冻结E1 v2数据、真实后端预检、正式户数/seed和停止规则；
- [ ] 冻结并执行真实人工/专家盲评协议；
- [ ] 冻结等价提示、有限跨模型和100/500/1000规模实验。
