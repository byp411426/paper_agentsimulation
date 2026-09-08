# DisasterSociety 证据台账

**核查日期**：2026-08-14
**用途**：记录哪些事实可以进入论文，哪些只能作为开发记录。更新结果解释前必须先更新本文件。

## 1. 状态定义

- `VERIFIED`：已经核查，可支持限定后的主张。
- `ENGINEERING_VALIDATION`：mock、单元/接口测试或确定性验证，只支持接线、合同和不变量，不属于行为效果实验。
- `PILOT`：真实运行过，但只支持开发、校准或可行性说明。
- `DIAGNOSTIC`：为定位信息、数据或设计问题而做的开发分析，不属于确认性结果。
- `OPENED_FOR_DIAGNOSTIC`：原holdout已被用于开发诊断，不再具有分析者未知性。
- `SUPERSEDED_BEFORE_PAID_EXECUTION`：实现/协议存在，但在付费科学运行前已被更合适设计取代，无结果可报告。
- `RUNNING`：冻结协议正在执行；完成审计前单格仍按`PILOT`处理。
- `PLANNED`：尚未形成结果。
- `INVALID_FOR_CLAIM`：结果文件存在，但不能支持原拟主张。

## 2. 已核查的软件证据

| 证据 | 状态 | 可支持的表述 | 不可支持的表述 |
|---|---|---|---|
| `.venv/bin/pytest -q`：129 passed、2 failed in 11.47s（2026-08-14复核） | `DIAGNOSTIC` 当前全套门禁未通过 | 129项现有离线合同仍通过；两个失败已精确定位为：(1) v8冻结源哈希仍期待旧`ds/agents/carr.py`字节，而台账已记录2026-08-04重建amendment；(2) PUMS v2码本NA解码当前产生`NaN`而测试期待`None` | 不得再写“当前完整离线测试套件全部通过”；在冻结哈希门禁与NA表示合同修复并重跑前，不能把旧91-passed快照当作当前状态 |
| `/opt/anaconda3/bin/pytest -q`：23 passed, 7 skipped（未加载 pytest-asyncio） | `VERIFIED` | 测试结果依赖运行环境，必须同时报告命令与依赖 | 以未声明环境的测试计数替代规范命令 |
| 两次 seed=99 玩具村运行的 `events.jsonl` 字节一致 | `VERIFIED` | mock 条件下存在确定性重放证据 | 任意在线模型都天然确定 |
| LLM 网关包含缓存、预算、日志和 fallback 机制；fallback 按逻辑决策计数 | `VERIFIED` | 框架具有运行控制与审计基础；toy runner 可写 `VALID/INVALID/ABORTED` 终态 | 所有 runner 和真实后端故障类型都已完成终态审计 |
| 通用 kernel 包含事件、互动和决策循环 | `VERIFIED` | 通用内核已经实现 | Carr runner 已完整使用全部内核机制 |
| 通用 kernel 将意图、世界仲裁结果与已执行状态分离 | `VERIFIED` | 被拒绝的行动不会在 toy/Resident 基础状态中提前记为撤离 | Carr 车辆、道路和照护的批量仲裁已实现 |
| 命名组件随机流已用于 toy hazard、warning delivery、arbitration 和 LLM decision | `VERIFIED` | 这些组件不再共享同一步随机序列，可支持后续配对设计的基础 | Carr 所有外生随机组件已经完成流审计 |
| Engine 使用 `IntentEnvelope[] → resolve_batch → apply_batch → keyed outcome` 边界 | `VERIFIED` | 通用 kernel 和 toy 已形成真正的批次边界，结果按 decision ID 提交 | Carr 道路、车辆和照护 resolver 已端到端接入 |
| Household 共享车辆仲裁与消息 delivered/processed/accepted/rejected 生命周期 | `VERIFIED` | 基础对象满足单车不双分配、请求顺序不影响结果、投递不等于接受；家庭DM与社区送达率可分离，过期提议和不可行接受会被拒绝，新承诺取代旧承诺时保留历史 | Carr 合成家庭已形成经验有效的协调过程；单元测试或mock闭环等于真实家庭行为验证 |
| EventPack manifest/schema、声明资产校验和 warning/control event loader | `VERIFIED` | Carr 数据包可以由统一入口验证并把预警、命令、避难所和受控事件映射为内核事件 | 现有 final perimeter 已成为危险时序；全部外部数据来源和字段均完成出版冻结 |
| Carr-R 无标识 60/20/20 分层拆分与三类 estimand 字段角色协议 | `VERIFIED` | 330人冻结集合已有统一 `evaluation_index` 拆分（198/66/66），协议可机器检查同一变量不同时作为输入和目标 | 新模型已在该拆分上得到正式结果 |
| Carr-R validation-only 传统模型：198 train、66 validation、test sealed | `PILOT` | 同样本、同拆分、四个人口学 runtime inputs、缺失单独编码和正确 ECE 的离线比较管线可运行；强类别不平衡下必须同时报告 Macro-F1、Brier、ECE 和混淆矩阵 | validation 开发结果是正式 test 结论；人口学模型表现可以证明平台或生成式社会过程有效 |
| 历史 DeepSeek demographic-only 响应的修复标签 validation 重评价 | `PILOT` | 66人 validation 上 Macro-F1 0.653、Brier 0.102、ECE 0.163，混淆矩阵 `[[2,5],[2,57]]`；旧置信度已按决策方向转换为撤离概率 | 这是新的付费运行或正式公平比较；旧 runner 缺少当前网关 provenance，且该重评价不能替代冻结后的 live run |
| 新 DeepSeek validation runner 与 live validation | `VERIFIED` 实现 / `PILOT` 运行 | 66人 validation、四个冻结人口学输入、test 未打开；66/66成功，Macro-F1 0.463、Brier 0.127、ECE 0.178，混淆矩阵 `[[0,7],[2,57]]`，内部估算成本$0.029342 | 正式 test 结果、平台有效性或 DeepSeek 优于传统模型；该模型把64/66人预测为撤离，未识别任何未撤离者 |
| Carr-R 固定事前情境 validation 与逐人配对敏感性 | `VERIFIED` 实现 / `PILOT_VALIDATION_ONLY` 运行 | 同一66人、同一四字段、统一非个体情境；66/66成功、0失败、test未打开。Macro-F1 0.463不变，Brier 0.145、ECE 0.197，混淆矩阵`[[0,7],[2,57]]`；4个分类切换，撤离概率平均变化−0.0445，配对t区间[−0.0737,−0.0154] | validation方向可用于挑选最终prompt或打开test；情境文本改善了个体预测；仍未正确识别任何未撤离者，不能支持平台有效性 |
| Carr-R 完整字段信号诊断与holdout状态 | `DIAGNOSTIC / OPENED_FOR_DIAGNOSTIC` | 按用户要求对完整330人去标识数据检查四字段、结构属性、命令暴露和回忆性事前信念；四字段不能支持“数据完全无信号”的判断，丰富字段有排序信号但受37名少数类、时序、回忆偏差与同源数据限制。未读取/导出身份、地址或自由文本 | 原66人test不再是分析者未知的untouched holdout；不得把该开发诊断、事后阈值或任何同数据新模型写成正式test结果。若继续个体评价，只能明确交叉验证/开发诊断或另用外部数据 |
| Carr Q13.6出发时感知派生列修复 | `VERIFIED_DERIVED_FIELD_CORRECTION` | 问卷/CSV表头确认`Q13.6_1=visual fire`、`Q13.6_2=smoke`、`Q13.6_3=official pressure`；已修复旧`_2/_3`错位并增加精确测试。Q9.1、撤离时间、渠道、四个Carr-R输入不变，E1 v1.1 reference core内存重算完全一致；旧派生文件已归档 | Q13.6是出发时post-outcome变量，修复不使其成为合法的事前输入；不得把旧错位列或新正确列用于预测Q9.1 |
| Carr-S 受控机制 runner：20户 × 5条件 × 5 seed，25个 mock run 全部 `VALID`、零 fallback/零成本 | `ENGINEERING_VALIDATION` | 通用 kernel 已接通 coordinator-only warning、家庭消息接受、共同承诺、抽象道路关闭、重规划、共享车辆与依赖成员照护；四个 drop-one 主指标均能改变代码路径 | 行为pilot或模块经验效应；差值全为1且seed方差为0，不能据此冻结seed数、区间或显著性 |
| Carr-S 非饱和机制工程诊断：20户 × 5条件 × 10 seed，50个 mock run 全部 `VALID`、零 fallback/零成本 | `ENGINEERING_VALIDATION` | 在配对的预警接收、消息送达、关闭时点和容量扰动下，四个主指标均保持正方向且出现seed方差；历史上只用于设计后续真实后端pilot | 正式机制效应、显著性或Carr经验有效性；drop-one专属指标在模块关闭时为结构性0，mock方差不能冻结正式seed数 |
| Carr-S mock 工程稳健性网格：3种受控场景 × 5条件 × 10 seed，150个 run | `ENGINEERING_VALIDATION` | 在低接收/低容量、参考和高接收/高容量三种开发场景中验证代码路径可对扰动响应 | 行为pilot或正式稳健性结论；透明mock policy不能替代声明后端运行 |
| 西 Redding 受控路线资产：2018 TIGER/Line 道路 + Carr final perimeter，双路线与算法选择的受控阻断 | `VERIFIED` 派生资产 / `PILOT`（活动类型 `INTEGRATION_CHECK`） | 两条约7.8 km候选路线具有共同端点、部分非重叠边，来源文件、构建脚本和配置均有 SHA-256；通用 Carr World 已实际读取路线长度与源 LINEARID | 该阻断是 Carr 历史观测关闭；final perimeter 是危险时序；当前路线容量是实测交通容量 |
| Carr-S DeepSeek v3 backend pilot：2户 × 5条件 × 2 seed，10个 run | `PILOT` | 10/10 run 为 `VALID`；119次逻辑决策、0失败、0 fallback，92,650 prompt tokens、400,926 completion tokens、内部估算成本$0.493576；四项主配对差出现可观察 seed 方差 | 正式 E2 效应、显著性、正式 seed 数或 Carr 经验有效性；每项都只有一个 seed 为正、另一个为0，原始矩阵的 interaction 映射错误已在派生汇总中按预先冻结指标更正 |
| Carr-S DeepSeek v3 五种子 backend pilot：2户 × 5条件 × 5 seed，25个 run | `PILOT` | 22个 `VALID`、3个 `INVALID`；332次成功决策、3失败/3 fallback，267,068 prompt tokens、1,082,043 completion tokens、内部估算成本$1.349111；所有原始 artifact 保留 | 正式 E2 或 seed 数；含无效 run 的6个配对被排除，可用配对数 memory 2、feedback/planning/interaction 各4，方向比例分别0.50/0.25/0.75/0.75 |
| Carr-S DeepSeek v4 三项顺序可靠性复核 | `PILOT` 工程复核 | 404/full和303/−memory为 `VALID`、零 fallback；505/−memory在第7–8步因代理 `Insufficient Balance` 出现3失败/3 fallback并为 `INVALID`；合计36,277 prompt tokens、149,049 completion tokens、内部估算成本$0.185326、墙钟1,218.780秒 | 不回填 v3 配对、不证明科学效应；账户余额恢复并通过新的最小后端可用性检查前，正式付费矩阵不得启动 |
| Carr-S DeepSeek v5 五户 availability gate：full seed101 + −memory seed202 | `PILOT` 工程复核 | 2/2 `VALID`，59/59成功、0失败/0 fallback；39,122 prompt tokens、116,392 completion tokens、内部估算成本$0.155514、墙钟1,049.251秒；Carr-R test未打开 | 机制效应或经验有效性；该门只证明当时的后端可用性，不能覆盖后来发现的v5协议有效性缺陷。此前超范围seed的中断 attempt保留但不计为结果 |
| Carr-S E2 v5 seed 101/202：每批5户 × 5条件；协议现已暂停 | `PILOT` 保留执行记录 | 10/10 run为`VALID`；293/293次模型决策成功、0失败/0 fallback，196,234 prompt tokens、551,231 completion tokens、内部估算成本$0.747465、累计run墙钟5,133.509秒；配置和列出的raw artifact哈希一致，Carr-R test未打开。两个full run的只读诊断为62 sent→12 delivered→7 processed→1 accepted→0 accepted-and-feasible/current-compatible，5条在终点未处理 | 不形成机制效应或v6先验。v5 在2/16后因三项协议缺陷暂停：家庭DM误用0.15社区送达率、提议在下一阶段处理时可过期、interaction指标把固定route/vehicle/depart step当作唯一承诺。暂停不是按中间效应方向作出；其余14 seed不再执行，原始结果不删除、不覆盖、不回填v6 |
| Carr-S E2 v6 协议验证：20户 × 5条件 × 10 seed，50个 deterministic-mock run | `ENGINEERING_VALIDATION` 协议/接线证据 | 50/50 run `VALID`；12,520次逻辑决策、0失败/0 fallback/0成本、0无效提议/接受；家庭DM与community分离、提议在途状态、时间/成员/车辆可行性和承诺版本历史均接通。两个独立目录的完整矩阵SHA-256一致；10个full run的扰动后可行承诺形成率和协调撤离率均为1，未协调撤离率均为0 | 行为pilot、生成式后端机制效应、Carr经验有效性、正式seed数或显著性；透明mock的四项drop-one差均为1且seed方差为0，只能验证协议/接线，不能直接放行正式付费矩阵 |
| Carr-S E2 v8 出版用途协议：8户 × 5条件 × 12独立seed，共60格真实 DeepSeek thinking-high | `PLANNED / RUNNING` | v8 prompt、全新seed、配对条件、失效排除、12-seed固定样本和真实后端均已哈希冻结；冻结时Carr-R test仍封存，后续R0完整字段诊断不改变E2固定输入、条件或指标；模块 manipulation checks 与下游完整家庭安全出发、关闭路线拒绝、协调出发及约束结果已预声明 | 当前正在执行不等于机制效应已成立；完整矩阵、区间、排除和provenance审计前，任何单格或中间方向都仍是`PILOT` |
| Carr-S E2 v8 `r1` 宿主中断与 `r2` 恢复冻结 | `VERIFIED` 运行审计 / `PLANNED / RUNNING` 科学矩阵 | `r1` seed1103/1201 的 full 各有 `VALID` summary，后续 −memory 均缺少 terminal summary；在未读取机制指标的情况下已哈希冻结排除全部 `r1` 产物，并验证 `r2` 除 run/protocol 恢复身份外与 `r1` 科学配置相同 | 不把 `r1` full 与 `r2` drop-one 拼接；不将宿主中断解释为模型失败或科学结果；`r2` 完整审计前仍无正式机制结论 |
| Carr-S E2 v8 `r3` detached 恢复 | `VERIFIED` 运行审计 / `EXCLUDED_ATTEMPT` | seed1103/full为`VALID`；seed1201/full在第7步因两个240秒请求超时而`ABORTED`（88次成功、2失败）；同时进行的seed1103/−memory按停止规则中断且无终态。全部r3产物保留并排除 | 不把r3的有效full或部分drop-one拼入后续矩阵；该失败是后端可靠性事件，不是机制效应 |
| Carr-S E2 v8 `r4` 后端可靠性恢复 | `VERIFIED` 运行审计 / `EXCLUDED_ATTEMPT` | 完整60格科学配置与r3等价；每lane并发6、请求超时600秒、禁止其他付费任务重叠。2026-08-02实际：seed1103/1201各5格共10格`VALID`（$6.484405）；seed1301/full在第4步、seed1409/full在第9步因`OpenAIException - Connection error` `ABORTED`（53/98次成功、5/1失败、合计$0.815939），两lane按停止规则`STOPPED_NONVALID_BATCH`；未读取中间机制方向 | r4全部产物只作运行审计并排除；连接错误是后端可靠性事件，不是机制效应；不得把r4的10个`VALID`格拼入r6科学配对 |
| Carr-S E2 v8 `r5` 完整60格恢复 | `VERIFIED` 运行审计 / `EXCLUDED_ATTEMPT` | 2026-08-02按方案A以r5协议重启60格；两条lane均在第1–2步因`OpenAIException - Connection error` `ABORTED`（seed1103/full 17次成功、seed1201/full 10次成功，各1失败、0 fallback，合计$0.123861），按停止规则`STOPPED_NONVALID_BATCH`；同一时刻Packy端点探测HTTP 200、DNS/TLS正常，诊断为瞬时连接抖动叠加`max_attempts=1`零重试 | r5全部产物只作运行审计并排除；连接错误不是机制效应；不得把r5部分格拼入r6科学配对 |
| Carr-S E2 v8 `r6` 完整60格恢复（gateway级重试） | `VERIFIED` 运行审计 / `EXCLUDED_ATTEMPT` | 2026-08-02在用户授权下以`max_attempts=3`重启60格；seed1103/1201两个批次5/5`VALID`、seed1301完成4格、seed1409完成4格后，`full_minus_interaction_seed1409`在第4步因Cloudflare 520源站错误`ABORTED`（56次成功、1失败，$0.27564），lane B按停止规则`STOPPED_NONVALID_BATCH`，lane A随即终止以避免在排除attempt上继续付费；r6合计19个`VALID`格、约$13.5 | r6全部产物只作运行审计并排除；520是源站可靠性事件，不是机制效应；不得把r6的19个`VALID`格拼入r7科学配对 |
| Carr-S E2 v8 `r7` 完整60格恢复（SDK级重试退避 + 提速） | `VERIFIED` 冻结协议 / `RUNNING` | 2026-08-02在用户“方案A、继续执行不要停”授权下冻结：科学配置与r6逐项一致，仅传输配置`call_kwargs.max_retries` 0→3→6（OpenAI SDK对全部5xx含520及连接错误做指数退避；所有科学代码文件保持与原v8冻结字节一致）；随后按用户提速要求冻结`r7_speedup_20260802` amendment：2条lane扩为6条（每run并发6、总在途36）、已完成格子确定性复用不重复付费、等待现有进行中格子安全收尾后切换；超时600秒、无其他付费任务重叠；全部冻结哈希记录在`carr_s_e2_v8_formal_r7_backend_recovery_freeze.json`与`carr_s_e2_v8_formal_r7_speedup_amendment.json` | 完整60格、区间、排除和provenance审计前，任何单格或中间方向仍为`PILOT`；重试/并行是运输级措施，不产生科学证据；任何失败按停止规则暂停新付费任务并需显式恢复amendment |
| Carr-S E2 v8 `r7` 完整60格执行结果 | `VERIFIED` 矩阵完成 / `COMPLETE_VALID` | 2026-08-03 01:20左右全部60格`VALID`、12/12 seed批次完成、四项模块配对均12/12有效、0排除、0失败/0 fallback；`summarize_carr_e2_v8_r7.py`累计summary `matrix_complete=true`；publication audit `COMPLETE_VALID`（60/60、0 problems，含冻结哈希、keyset、终态一致性、机会分母检查）；分析工具修复（summarizer临时目录、audit run_id嵌套路径）已同步更新冻结哈希 | 单格与配对效应仍是`PILOT`直至W7统计输出（配对均值、95% t区间、MCSE、方向稳定性）完成；不得据此直接写正式机制结论 |
| Carr-S E1 聚合问卷参照 v1.1 | `VERIFIED` 数据参照构建 | 330名Q9.1有效受访者撤离率0.8879（Wilson 95% CI 0.8493–0.9176）；一致且非负的命令到出发延迟 n=186、中位1小时、5小时CDF 0.7742，肯定命令优先敏感性 n=194、CDF 0.7732；年龄65+差−0.0637、家庭规模3+差0.0399、低收入差−0.0619，20,000次bootstrap区间均跨0；零车辆组n=0并保留为不可估计；渠道主/敏感性分母234/249 | respondent sample 不是加权总体真值；总体官方接收边际用于校准；渠道多选 prevalence 不等于 first-heard；尚未与独立 Carr-S 真实模型运行对照，不能声称行为真实性 |
| Carr-S E1 自然时序真实后端 v1 | `VERIFIED` 实现 / `SUPERSEDED_BEFORE_PAID_EXECUTION` | 固定50户、81名决策成人、15名依赖成员、261条受控社会图边和5个DeepSeek thinking seed的代码/协议存在；无初始计划和固定出发步，且从未启动付费正式运行 | v1画像只有年龄、失能、家庭规模、车辆、收入和结构；coordinator、车辆座位、统一危险/强制令等假设不足以支持Carr总体经验合理性。不得执行或写成结果；保留原协议并由丰富画像、动态暴露和重新冻结的E1 v2取代 |
| Carr-S E1 v2丰富居民画像与自然时序协议 | `PLANNED / DESIGN_AUDITED` | 已完成字段角色审计：PUMS v2保留就业、教育/通勤、住房与信息接入等静态属性；Carr train-only trait block无outcome抽样Q29风险/摩擦、宠物、经验、决策角色与信任；命令、渠道、危险、道路和消息按时间生成；Q9/Q10/Q11/Q13.6/PII禁止输入 | 尚未实现donor v2、latent hot-deck、field-role fail-fast、真实DeepSeek预检或正式结果；同一Carr调查用于潜变量输入与Q9/Q13参照会降低外部独立性，必须按Carr-informed reasonableness限定主张 |
| Carr-S E1 v2 W1–W3 离线构建 | `ENGINEERING_VALIDATION` 数据构建 | 2026-08-02完成：W1 PUMS donor v2（4,317户/9,968人、ADJINC收入调整、官方码本、未知码fail-fast、结构QA全0、收入档变化722户、双构建哈希一致）；W2 Carr train trait donor（198人一对一、逐值编码、Q29因子、household/person分表、Q9/Q10/Q11/Q13零读取）；W3 e1_profiles（1,000户/2,404人全覆盖、H0精确86.8%、P0严格档923、focal/coordinator基线、照护与决策资格独立、确定性复现）；另生成order_sequence_calibration.json（主分析315人排除15矛盾、敏感性330人肯定命令优先） | 不构成行为或机制证据；匹配是Carr-informed热卡近似，不是观测家庭真值；真实DeepSeek预检与正式运行必须在E2 r7归档且无付费重叠后进行 |
| Carr-S E1 v2 W4/W5 实现与真实预检 | `ENGINEERING_VALIDATION` 接线 / `PILOT_PREFLIGHT` | 2026-08-03完成：W4 e1_party_v2（DepartureParty/HouseholdCommitmentV2/CareRequirement/DepartureRecord、10项接受检查、按party执行、修订历史、车辆离场不可复用，10个测试）；W5 v2 runner（居民私有认知/world真实道路/交互消息生命周期/事件源/13类ledgers，8个接线测试，mock预检确定性验证）；真实DeepSeek预检r4（6户×25步，86次决策缓存重放自r3真实调用，0失败，5/5官方收据已处理，2/6户撤离至安全区，0拒绝） | 预检只证明接线与后端可用性，不构成行为效果或经验合理性；预检发现多成人户尚未通过消息形成协调提案（0消息），正式E1协议需处理该协调缺口；r1/r2/r3预检attempt保留为审计记录 |
| 异步后端关闭与墙钟实际复核：1户完整8步 | `VERIFIED` 工程复核 | 9/9 DeepSeek决策成功、0失败/0 fallback、墙钟218.138秒，进程无未关闭 HTTP 会话警告 | 科学实验、机制效应或效率曲线；它只是修复后的单次连通性检查 |
| 1000-agent、48-step Carr 运行目录与 metadata 存在 | `PILOT` | 旧简化管线能够完成千人规模运行 | 当前通用 kernel 已在 Carr 上达到同等规模；千人行为与现实社会一致 |

2026-07-31 清理后，旧 Carr 专用 runner、其简化 world/loader、`run_carr.py`、
历史 `e1_dynamic.py`、旧随机拆分传统基线和旧静态 LLM 脚本已移入
`archive/legacy_2026-07-31/`。归档不改变已有
run、结果或日志的证据状态；它只防止这些开发路径继续被误当作正式实现。

## 3. Carr 数据与模型结果

### 3.1 标签状态

2026-07-31 已交叉核对 `Wong_Carr_Wildfire_Survey.pdf` 与 Qualtrics CSV
问题文本，并重写 `scripts/clean_survey.py`：

- `Q9.1` 是撤离筛选；
- `Q13.3/Q13.4` 是撤离日期与时间；
- `Q6.2/Q6.3`、`Q7.2/Q7.3` 是强制令与建议令时间；
- `Q6.1_11/Q7.1_11` 是邻居、朋友或家庭成员告知，旧脚本误用的 `_9`
  实际是网站。

新派生数据和 QA 文件：

- `eventpacks/carr_2018/behavior/survey_clean.csv`：335 条完整答卷；
- `evaluation_respondents.csv`：330 条冻结评价记录，293 撤离、37 未撤离；
- `survey_clean_qa.json`：原始 CSV SHA-256、变量映射和统计；
- 292 名撤离者具有完整撤离日期与时间，1 名缺失。

核心变量映射与派生过程为 `VERIFIED`。这只验证数据处理，不验证仿真行为。
历史模型结果均在修复前产生，仍为 `INVALID_FOR_CLAIM`。

### 3.2 已有结果文件

| 模型 | 评估样本 | Macro-F1 | Brier | ECE | 状态 |
|---|---:|---:|---:|---:|---|
| Logistic Regression | 67 | 0.594 | 0.187 | 0.092 | `INVALID_FOR_CLAIM` |
| Random Forest | 67 | 0.589 | 0.184 | 0.103 | `INVALID_FOR_CLAIM` |
| Static LLM | 335 | 0.478 | 0.186 | 0.076 | `INVALID_FOR_CLAIM` |
| “Dynamic” LLM | 335 | 0.467 | 0.237 | 0.157 | `INVALID_FOR_CLAIM` |

历史传统模型和 LLM 未使用相同评估样本，也未使用修复后的无泄漏输入。
当前比较不能说明哪一种方法更好。

归档的 `archive/legacy_2026-07-31/disastersociety/experiments/carr/e1_dynamic.py`
对每名受访者只执行一次 prompt 和一次模型调用，并包含事后灾害严重性及问卷留守理由提示。它只能作为历史开发记录，不能作为无泄漏的一次性基线，更不能称为多步记忆、反馈或规划模型。

### 3.3 冻结 validation 的新开发结果

新的传统模型配置只使用 `age_group`、`household_size`、`vehicle_count` 和
`income_bracket`，在198人 train 上拟合，在66人 validation 上评价；这些运行
发生时66人test尚未打开。validation 有59名撤离、7名未撤离：

| 模型 | Accuracy | Macro-F1 | Brier | ECE | 混淆矩阵 [0,1] | 状态 |
|---|---:|---:|---:|---:|---|---|
| Train prevalence 常数 | 0.894 | 0.472 | 0.095 | 0.005 | `[[0,7],[0,59]]` | `PILOT` |
| Logistic Regression | 0.848 | 0.459 | 0.119 | 0.104 | `[[0,7],[3,56]]` | `PILOT` |
| Balanced Logistic Regression | 0.712 | 0.462 | 0.240 | 0.320 | `[[1,6],[13,46]]` | `PILOT` |
| Balanced Random Forest | 0.697 | 0.455 | 0.226 | 0.315 | `[[1,6],[14,45]]` | `PILOT` |
| DeepSeek 历史响应重评价 | 0.894 | 0.653 | 0.102 | 0.163 | `[[2,5],[2,57]]` | `PILOT_LEGACY_REANALYSIS` |

这些数值只说明：四个人口学字段对少数类的辨识有限；单看 accuracy 会被
高撤离率误导；历史 DeepSeek 响应在这一 validation 上识别出2个未撤离者，
但区间很宽且校准不佳。不得从这一张开发表宣称 DeepSeek 优于传统模型。
新的 DeepSeek live validation 已在相同66人 validation 上完成，执行时test未打开：

| 模型 | Accuracy | Macro-F1 | Brier | ECE | 混淆矩阵 [0,1] | 状态 |
|---|---:|---:|---:|---:|---|---|
| DeepSeek v4 Flash live | 0.864 | 0.463 | 0.127 | 0.178 | `[[0,7],[2,57]]` | `PILOT_VALIDATION_ONLY` |

该 run 66/66 成功且无 fallback，内部估算成本0.029342美元。它把64/66人预测
为撤离，未识别任何未撤离者；因此不能用 accuracy 掩盖少数类失败，也不能从
该 validation 宣称 DeepSeek 优于传统模型。内部价格表估算不等于代理账单。

## 4. 当前群体评价的边界

### 4.1 Carr-S v6 thinking-high 与跨模型 pilot

最终选择的 DeepSeek thinking-high v6 矩阵包含2户、5条件和2个配对 seed，
10/10格为 `VALID`，184次逻辑决策均成功、无 fallback。四项平均配对差为
memory 1.0、feedback 0.375、planning 0.5、interaction 1.0；两个 seed 的
方向均为正。但2户比例过粗，memory、planning 和 interaction 的两个差值
完全相同，不能据此冻结正式 seed 数或正式效应。

随后冻结并完成的 E3 跨模型 pilot 使用相同 v6 prompt、场景、条件、seed 与
指标，最终选择40个 `VALID` 格、944次成功逻辑决策，零失败、零 fallback：

| 模型 | Memory 平均差（正向 seed） | Feedback | Planning | Interaction | 状态 |
|---|---:|---:|---:|---:|---|
| DeepSeek V4 Flash | 1.000（2/2） | 0.375（2/2） | 0.500（2/2） | 1.000（2/2） | `PILOT` |
| Qwen3.5-Plus | 1.000（2/2） | 0.000（0/2） | 1.000（2/2） | 0.500（1/2） | `PILOT` |
| GLM-5 | 1.000（2/2） | 0.333（1/2） | 1.000（2/2） | 0.500（1/2） | `PILOT` |
| MiniMax-M2.7 | 1.000（2/2） | 0.000（0/2） | 0.000（0/2） | 0.750（2/2） | `PILOT` |

合计8个模型×seed描述性配对中，正方向计数为 memory 8/8、feedback 3/8、
planning 6/8、interaction 6/8。它说明 feedback 尚不具跨模型稳定性，
planning 与 interaction 仍有端点或 seed 敏感性。memory 的8/8方向最稳定，
但 drop-memory 指标为结构性0，仍需更大 cohort 和非饱和正式设计。

MiniMax 两个 full run 的 `planned_primary_count` 均为0，所以其 feedback 与
planning 零差同时反映“没有形成作用机会”，不能直接解释为模块无效。
MiniMax r1/r2 的 action/proposal 枚举错误触发两个 `ABORTED` run；最终 r3
统一采用官方支持的 forced function schema，旧失败保留且不进入科学配对。
三种替代模型与 DeepSeek 都经 Packy 代理访问，因此只能声称同一代理下的
跨模型族敏感性，不能声称跨提供商或普遍模型独立性。完整选择、哈希和排除见
`disastersociety/experiments/carr/results/carr_s_e3_cross_model_v6_pilot_summary.json`。

### 4.2 Carr-S v7 反馈隔离与受控机会 pilot

v6 跨模型诊断暴露了两项不能靠增加 seed 解决的问题：无反馈条件仍能读取实时
世界路线状态；部分模型的 full 条件没有形成主路线计划，因而反馈和重规划缺少
共同作用机会。v7 保留真实世界的道路关闭与物理仲裁，但向居民提供复制的感知
路线状态；只有反馈开启时才刷新感知。所有条件中的每名决策居民同时获得相同的
私人主路线初始计划。该计划是机制识别的受控初始状态，不是生成结果或家庭共享
承诺，自然计划形成留给单独的 E1 实验。

DeepSeek thinking-high v7 pilot 使用4户、8名决策居民、5条件和3个配对 seed。
最终选择的15个 run 全部 `VALID`，796次逻辑决策全部成功、0失败、0 fallback；
内部配置估算成本为4.467429美元，不是代理账单。每个单元的关闭前主路线计划率
均为1；full 的路线感知更新数为8/7/8，三个 `full_minus_feedback` 均为0。

| 模块 | 平均配对差 | SD | MCSE | 正向 seed | 状态 |
|---|---:|---:|---:|---:|---|
| Memory | 1.000 | 0.000 | 0.000 | 3/3 | `PILOT` |
| Feedback | 0.958 | 0.072 | 0.042 | 3/3 | `PILOT` |
| Planning | 0.750 | 0.000 | 0.000 | 3/3 | `PILOT` |
| Interaction | 0.917 | 0.144 | 0.083 | 3/3 | `PILOT` |

该结果说明修复后的四条路径在本 DeepSeek 受控场景中方向可辨，但不能作为正式
效应。memory/planning 仍没有观测 seed 方差，多个 drop-side 主指标由禁用语义
结构性置零，三 seed 也不足以给出确认性区间。更重要的是，full 条件每个 seed
仅3/4家庭成功完成关闭后重规划；seed101 仅1/4家庭协调出发，并出现3次依赖
成员遗留拒绝和重复车辆冲突。追踪显示接受承诺后成员仍可能选择不同出发步，且
执行拒绝原因没有进入下一步 prompt，导致车辆离开后重复尝试。因此 v7 解决了
“测不准”，尚未解决完整家庭执行质量。完整选择、哈希和排除见
`disastersociety/experiments/carr/results/carr_s_deepseek_v7_controlled_pilot_summary.json`。

v7 的执行追踪进一步定位到反馈闭环缺口：拒绝原因和车辆占用虽存在于 World 与
内部 feedback events，却没有进入下一步 resident prompt。v8 开发版本补充
`current_plan.last_failure`、近期执行反馈、家庭车辆状态和已接受承诺的精确执行
语义。同一诊断 seed101 的 post-hoc full 复查实现4/4协调出发、4/4重规划、
0依赖遗留和0资源冲突；v7 对应值为1/4、3/4、3和4.0/户。随后在执行前冻结
的 full seed404/505 均 `VALID`：协调出发为3/4和4/4，重规划均4/4，依赖遗留
为1和0，资源冲突为0.25/户和0。三个 v8 full run 共125次成功决策、0失败、
0 fallback，内部估算成本0.734953美元。

这些结果支持失败诊断与修复方向，但不是正式 prompt 比较：seed101 用于设计
修复；404/505 虽在 v8 执行前冻结，却没有同时预声明匹配的 v7 对照。它们只能
支持“执行反馈修复通过真实后端开发复查”，不能支持正式效应量或家庭行为外部
有效性。汇总见
`disastersociety/experiments/carr/results/carr_s_deepseek_v8_execution_feedback_summary.json`。

2026-08-02 已在任何新结果产生前冻结 E2 v8 出版用途矩阵：每个 run 使用8户、
16名决策居民，5个 full/drop-one 条件和12个全新独立 seed，共60格。seed数依据
v7 最不稳定的 interaction 配对差 SD=0.144338 与目标 MCSE≤0.05 计算的最低9个，
保守冻结为12个。四项模块专属指标仍作为 manipulation check；另预声明完整家庭
安全出发率、关闭路线拒绝/户、协调出发率及资源/照护约束为下游结果，避免仅凭
禁用模块后的结构性0主张效果。矩阵开始执行，但完整审计前所有单格均保持
`PILOT`，Carr-R test 未打开。

### 4.3 经验群体指标边界

`eventpacks/carr_2018/warnings/delivery_params.yaml` 明确以匹配问卷警告接收比例为调参目标。因此用相同调查边际计算的渠道距离属于校准内指标。

历史 Carr run 采用以下简化：

- 收到 warning 的智能体全部计入 official；
- neighbor 和 social 不传播；
- 其他智能体计入 none。

调查的 `Q6.1/Q7.1` 是多选渠道 prevalence，而通用互动引擎记录
first-heard channel。它们不是同一统计量。历史 L1 距离为 `PILOT`，只能
说明旧指标管线曾运行，不能称为独立群体行为验证。

正式渠道评价必须把 `Q6.1/Q7.1` 当作逐渠道 prevalence，报告各渠道
percentage-point error 和区间；可汇总 mean absolute percentage-point error。
不得将其归一化后计算 L1/JS distribution distance。

问卷撤离时序映射现已修复，但现有模拟撤离曲线仍不能用于正式结论，因为：

- 历史决策包含 mock 或简化逻辑；
- 历史 runner 已归档；
- 时间曲线尚未冻结独立经验目标与完整统计协议。

## 5. 模块证据

| 模块 | 实现状态 | 当前证据 | 论文还缺什么 |
|---|---|---|---|
| Memory | 已有状态、淘汰逻辑和 Carr mechanism flag | 单元测试；v7 DeepSeek 3/3 seed 为正，但 drop-memory 指标结构性0 | 更长时窗、无依据矛盾和非饱和正式配对 |
| Trust | 已有更新逻辑，是 information/feedback 子状态 | 方向性单元测试 | 受控信息场景中的状态和行为作用；当前不单列贡献 |
| Interaction | channel-specific 送达、结构化 proposal、在途状态、可行性检查和可追踪 commitment 修订已接通 | 单元测试；v7 DeepSeek 3/3 seed 为正，但 full 仍有承诺后行动不同步 | 绑定承诺后的执行反馈、真实邻里网络、扩散指标和正式配对 |
| Planning | Carr resident 有可执行 route/vehicle/departure plan 和受阻重规划闭环 | v7 为所有条件冻结相同私人初始计划，DeepSeek 3/3 seed 为正；full 仅3/4家庭完成重规划 | 改善执行一致性，并在明确受控扰动边界下获得正式多 seed 证据 |
| Feedback | 真实 World 与居民感知路线已分离，禁用反馈不再读取实时关闭真值；v8把执行拒绝、近期反馈和车辆占用送回下一步prompt | v7 DeepSeek 3/3 seed 为正；v8三个full开发run的重规划均4/4，协调出发合计11/12 | 完成v8正式多seed配对，并做多类型扰动和延迟窗稳健性 |
| EventPack | Carr manifest/schema、资产验证和 event loader 已实现 | 数据资产与离线测试 | 来源字段审计、正式危险/道路时序与案例冻结 |
| Household | 多决策成人、依赖状态、共享车辆、可版本化承诺和批量仲裁已接入受控 Carr-S runner | 单元测试；v6 20户×10 seed mock闭环、DeepSeek thinking-high 与四模型 backend `PILOT` | 正式资源参数、更大 cohort、多 seed 和经验评价 |

## 5.1 人口与 household–person 结构

2026-07-31 对原始 PUMS housing/person 压缩文件的只读核查得到：

- 4,317 个符合过滤条件的 household；
- 9,968 条通过 `SERIALNO` 关联的 person records；
- `NP` 与连接成员数不一致为 0；
- 同户重复 `SPORDER` 为 0；
- reference person 缺失或不唯一为 0；
- 无 person records household 为 0；
- `WGTP` 范围为 1–118；
- 48 个 tract 的收入、车辆、家庭结构和老年成员存在四组家庭边际总户数逐 tract 一致。

上述结构事实为 `VERIFIED`，证明整户 donor 路线在数据结构上可行。当前代码
已实现并测试：`WGTP` 初始权重、结构零和边际总量 fail-fast、四组 tract
家庭边际拟合、整户成员原子复制、唯一 synthetic IDs、fractional/integerized
误差、ESS 与 donor 重复率。旧的均匀 `run_ipf()` 入口已退役，并新增不泄露
`SERIALNO` 的 raw PUMS builder。

规范 raw builder 已在两个原始 ZIP 上运行。生成的
`population/donors_v1/donor_build_qa.json` 记录源文件 SHA-256、4,317 户、
9,968 人、排除 339 个空置 housing unit 和 381 个 group-quarters record；
公开 donor household/person 表均不含 `SERIALNO`。该构建与结构检查为
`VERIFIED`。

### 5.2 1000 户人口合成 pilot

`population/pilot_seed42_n1000/` 保存 seed 42、48 tract、1000 户的可重建
开发结果：

- 2,345 名成员；
- 48 tract 的 fractional IPF 全部收敛，最大单格绝对误差
  `9.77e-08`；
- TRS integerization 后最大单格绝对误差 `5.85` 户；
- 最小 fractional ESS `323.32`；
- 该小规模配置中同一 tract 内 donor 重复率为 0、最大复制数为 1；
- person age 未参与拟合；tract 年龄分布的平均 mean absolute
  percentage-point error 为 `7.70`，最差单格绝对误差约 `27.00` 个百分点；
- 公开 synthetic household/person 表不含 `SERIALNO`。

该结果为 `PILOT`。它验证真实数据管线可运行，也暴露了小 tract 样本的
integerization 噪声和未拟合 person-age 偏差。它不能支持“person-level 已
校准”或“1000 户人口代表 Carr 总体”。正式协议需要决定全 ACS 规模 base
population 与实验子样本的关系，并预声明 person-level 偏差的敏感性处理。

## 6. 可进入当前方法部分的事实

- 框架使用事件驱动的离散时间循环。
- 世界状态与 LLM 决策分离，物理环境不由 LLM 任意改写。
- LLM 调用经过统一网关，并记录运行与调用信息。
- Carr 目录用经过校验的 manifest/schema 组织事件、人口、灾害、道路、预警和行为数据；来源字段审计与正式时序仍待完成。
- 框架包含居民状态、记忆、信任、互动、人口和评价组件。

这些事实描述“已经实现并通过受控mock端到端测试的原型”。方法部分可以完成式描述v6消息时序、家庭承诺与受控闭环的代码能力，但生成式行为效应、社会传播外部有效性和正式结果仍须标为待评价。

## 7. 需要完成后才能进入 Results 的工作

1. Carr-R 共用 train/validation/test 拆分和15条命令矛盾记录规则曾冻结；传统模型与两个DeepSeek validation prompt均已完成。2026-08-02完整字段信号诊断已查看原test的特征—结果关系，因此其状态为`OPENED_FOR_DIAGNOSTIC`，不再进入正式test gate。
2. 停止继续重复四字段付费prompt；若保留Carr-R，只做明确标注的丰富输入/回忆性潜变量开发诊断或使用新的外部数据，不恢复为论文主线。
3. 受控 Carr-S runner 已直接使用通用 kernel，并接入有 provenance 的 TIGER 双路线；算法阻断仍是受控扰动，不是历史关闭观测。
4. v5 已在2/16后因预先未发现的协议有效性缺陷暂停，原始结果与只读诊断均已保留；不得继续其余14个v5 seed或把其数值回填v6。
5. v8执行反馈修复与真实后端开发复查已完成；正式E2已按8户、5条件、12个独立seed冻结并开始执行，仍需完成60格、配对区间、失效排除和provenance审计。
6. E1 v2画像与真实后端轨迹已产生，但2026-08-14审计确认安全终态wake、反馈消费、重复departure、共享message状态和旧summarizer口径会污染社会过程；修复合同、增加不变量测试与新版分析脚本后必须从头重跑，旧三seed只保留为`DIAGNOSTIC / INVALID_FOR_CLAIM`。
7. 增加外部分布、行为约束、盲法评价、稳健性和效率结果。

在完成以上工作前，不得写“DisasterSociety 提高了真实性”“模块显著改善仿真”或“案例验证通过”。

## 8. 2026-08-04 更新：E1 v2 正式最小样本与 E3 本地 qwen27b

- E1 v2 正式最小样本（24户×25步、seeds 7201/8301/9401、packy-deepseek-v4-flash thinking-high）三个 seed 均写出 `VALID` 终态：7201 r7（486 calls、0调用失败）、8301 r10（455 calls、300 cache hit + 155 ok、0调用失败）、9401 r9（556 calls、0调用失败）。这些终态只说明runner完成及网关未失败；2026-08-14方法/产物审计已把三run整体降为`DIAGNOSTIC / INVALID_FOR_CLAIM`，不能继续称为可发表的正式E1行为结果。
- 2026-08-14审计发现E1终态合同缺陷：`should_wake()`没有安全区排除，`recent_execution_feedback`每次决策追加且不消费，居民首次激活后可在到达安全区后持续调用LLM和发消息；party执行又未复核traveler是否仍在原点或此前已安全到达，因此存在同一居民重复executed departure。三run合计717/1,497次调用（47.9%）及676/1,214条发送消息（55.7%）发生在发送者首次安全到达之后；seed8301/9401还存在同一居民使用不同车辆重复执行离开的记录。后续消息已经改变其他居民轨迹，不能靠结果阶段过滤发送者记录挽救旧run；必须修复安全终态wake、反馈消费和traveler-origin/prior-arrival检查后全量重跑。
- 旧汇总中的“完整安全整户出发率37/72=51.4%”“协调出发户率24/72=33.3%”“拆分出发户3/72=4.2%”和“accepted messages 467”均为`INVALID_FOR_CLAIM`中间标签：summarizer把任意executed party计为完整整户出发、可把单成人auto-party计为协调、把多条departure记录直接计为拆分，并把E1共享message status当作接受漏斗。仓库尚未实现新版可审计重算脚本。正式E1分析必须基于唯一初始化成员、最终权威位置、首次有效安全到达、party traveler IDs与官方recipient receipts，分开报告message disposition、party feasibility与world execution；产生带输入哈希的新artifact前不得把这些数值写入Results。
- E3 本地 qwen27b lane（`carr_s_e3_v1_qwen27b`，4 seed × 3 条件 = 12 格）已全部 `VALID`（1625 calls、0 failure、零成本）。前三次 attempt 因本地 vLLM `json_object` 模式在重规划决策返回缺 `action` 的部分 JSON 而 `ABORTED`，已归档至 `runs/archive_e3_qwen27b_schema_20260804` 并排除；恢复 amendment `carr_s_e3_v1_qwen27b_recovery_freeze.json` 将本地模型传输改为 vLLM guided json_schema（`structured_output_mode: json_schema`，backend 新增该分支），科学配置/提示/指标不变。该结果仅为 `PILOT_PENDING_AUDIT` 跨模型族方向性证据，正式结论需完整审计。
- E3 DeepSeek 重跑（`carr_s_e3_v1_deepseek`，4 seed × 3 条件，预算约 $4）已于 2026-08-04 启动，状态 `RUNNING`，审计完成前按 `PILOT` 处理。
- 2026-08-04 用户要求将本地 gemma-4-31B-it-FP8 作为新的 E3 本地模型 lane：模型已下载至服务器 `/home/data/share/LLM_model/google/gemma-4-31B-it-FP8`（33.3GB），vLLM 双卡（TP=2、cudagraph NONE、32768 上下文）启动成功并通过 json_schema 结构化输出验证；已冻结 `carr_s_e3_v1_gemma4`（4 seed × 3 条件 = 12 格，零成本），lane 已启动，状态 `RUNNING`，审计完成前按 `PILOT_PENDING_AUDIT` 处理。
- 2026-08-04 用户明确授权 claude-sonnet-5 lane 与 DeepSeek 付费 lane 并行执行（覆盖 claude 配置中 `no_other_paid_jobs` 的默认约束，授权记录见本行）。渠道探测 HTTP 200 正常；`carr_s_e3_v1_claude` 已复用 2107/2209 共 6 格有效结果并续跑 2303 缺格，状态 `RUNNING`，审计完成前按 `PILOT_PENDING_AUDIT` 处理。
- 2026-08-04 DeepSeek lane 首次重启在 seed2107/full 卡死（进程 0% CPU、最后调用后 50 分钟无新记录、请求挂在本机代理 127.0.0.1:7890 上未超时）。已按恢复协议终止并归档半成品至 `runs/archive_e3_deepseek_hang_20260804`，冻结 `carr_s_e3_v1_deepseek_hang_recovery_freeze.json`（科学配置不变、全 4 seed × 3 条件重跑），随后 lane 已重新启动，状态 `RUNNING`。
- 2026-08-04 用户要求把 E3 DeepSeek v4 flash 的传输从 Packy 切换到 OpenCode Go（`https://opencode.ai/zen/go`，密钥已存 Keychain 的 `OPENCODE_API_KEY`）。已冻结 `carr_s_e3_v1_deepseek_opencode_freeze.json`：科学配置/种子/条件/指标不变，仅换网关；Packy 路径的全部半成品已归档至 `runs/archive_e3_deepseek_packy_switch_20260804` 并排除。OpenCode Go 的 `deepseek-v4-flash` 返回 `RegionError`，需用户在控制台开启“使用中国托管的模型”（opt-in）后才会放行；放行并探测 200 前不启动该 lane。`deepseek-v4-pro` 在同一网关可直接调用（已探测 200）。
- 2026-08-04 用户确认 OpenCode Go opt-in 已完成，`deepseek-v4-flash` 放行（探测 200，偶发 `Router.Unavailable` 但可重试）。首次启动因 litellm base_url 缺少 `/v1` 打到 404（已归档 `runs/archive_e3_deepseek_opencode_404_20260804` 并排除），修正为 `https://opencode.ai/zen/go/v1` 后重新启动；lane 状态 `RUNNING`（seed2107/full，调用 20–25 秒/次，0 失败）。
- 2026-08-04 事故记录：准备 E3a prompt 变体时误将未提交的 `ds/agents/carr.py`（v7/v8 路由观测与执行反馈版本）用 git checkout 回滚，原始字节无法逐字节恢复。已从会话痕迹重建：方法行号与冻结版完全一致、39 项相关测试通过、机制 mock 运行正常，仅两行 docstring 文字无法还原，故新文件 sha256 为 `c2ebf7e5...`（原冻结哈希 `1a6b68a2...`）。运行中的 E2/E3 lane 的 provenance 在启动时已记录原哈希，不受影响；新运行需按 `carr_s_carr_py_reconstruction_amendment.json` 用新哈希审计。该重建属工程/provenance 变更，不改变任何实验数字。
- 2026-08-04 E3 三条 lane 中途状态：opencode DeepSeek 在 seed2107/full 第 6 步遇瞬时连接错误停跑（已归档 `runs/archive_e3_deepseek_opencode_conn_20260804` 并重跑）；claude 在 2303/−interaction 第 8 步遇渠道 ServiceUnavailable 停跑（渠道探测已恢复，归档 `runs/archive_e3_claude_channel_20260804b` 并重跑，复用 8 个有效格）；gemma4 本地 lane 的 2303/−feedback 因 vLLM 慢速生成长时间无新调用，但服务器 GPU 100%、请求仍在推进，未按挂死处理。
- 2026-08-04 gemma4 事故更正：2303/−feedback 实际是本地 lane 客户端卡死（0% CPU、大量 CLOSE_WAIT 半开连接、llm_calls 45 分钟不增长），服务器端 vLLM 仍在正常生成；误判为服务器挂死后直接 pkill 了服务器 vLLM。用户指出该操作越权后，按用户指示以原参数重启服务器 vLLM（PID 2833242）并重启 gemma4 lane（PID 97224），复用 2107/2209 六格 + 2303/full，继续补 2303/−feedback、−interaction 与 2411 三格。半成品归档 `runs/archive_e3_gemma4_hang_20260804`。
- 2026-08-04 gemma4 lane 已全部完成（12/12 VALID，零成本）。claude lane 因 Packy“分组 aws-q 无可用渠道”反复中断：已完成 2107/2209/2303 共 9 格 + 2411/full 共 10 格，2411/−feedback 半成品归档至 `runs/archive_e3_claude_switch_qwen36_20260804`；用户指示切换到本地 qwen3.6-27B-FP8。服务器 vLLM 已从 gemma 切换为 Qwen3.6-27B-FP8（PID 2860765，TP=2 原参数），新增冻结 `carr_s_e3_v1_qwen36`（4 seed × 3 条件 = 12 格，零成本），lane 已启动（PID 12150），状态 `RUNNING`。
- 2026-08-04 E3a 等价提示敏感性已启动：mock 预检 v8a/v8b 均 `VALID`（104 次 mock 决策/变体）；修复运行器两处缺陷（缺 `--lane` 参数、条件校验误用 5 条件全集）后，两条正式 lane（`carr_s_e3a_v8a`/`_v8b`，opencode-deepseek-v4-flash，各 4 seed × 3 条件）已并行启动，状态 `RUNNING`。
- 2026-08-04 E3c 规模与效率已冻结协议（`carr_s_e3c_scale_efficiency_freeze.json`：100/500/1000 户 × 2 seed，opencode deepseek flash，指标含完成率/墙钟/LLM 调用/tokens/成本/失败/fallback/最大稳定规模），并完成 100 户 mock 预检（`VALID`，25 步、1.8s、全部 ledger 落盘）。真实付费运行尚未启动，需用户确认预算与排期。
- 2026-08-04 用户指示 E3c 真实运行改用 Packy 传输并将并发从 6 提到 12；已冻结 transport amendment（`carr_s_e3c_scale_efficiency_packy_amendment.json`）并启动 100 户 × 2 seed（101/202）真实运行（`carr_s_e1_scale_100_packy`，包内预算 $8/seed），状态 `RUNNING`，审计前按 `PILOT_PENDING_AUDIT` 处理。
- 2026-08-04 qwen36 lane 再次出现客户端卡死（2107/−feedback 停在 143 次调用、47 分钟无写入、进程 0% CPU、服务器正常生成）。已按用户指示终止 lane（PID 12150）、归档半成品至 `runs/archive_e3_qwen36_hang_20260804` 并重启（PID 35680），复用 2107/full 有效格；若同一决策点再次卡死，将视为确定性客户端问题并另行处理。
- 2026-08-04 E3c 100 户 seed101 在第 11 步遇空响应 `ABORTED`（671 ok + 1 failed）。已冻结 recovery amendment（`carr_s_e3c_scale_100_seed101_recovery_freeze.json`）、归档半成品至 `runs/archive_e3c_seed101_empty_response_20260804` 并重跑（seed101_r2，共享缓存快速回放 671 次成功调用，仅重跑失败决策），状态 `RUNNING`。seed202 不受影响，继续推进。
- 2026-08-04 E3c 100 户 seed202 在 step17 触发 `BUDGET_EXCEEDED`（1340 ok 调用烧完 $8 单 run 预算）；seed101_r2 也会触顶。已冻结预算恢复 amendment（`carr_s_e3c_scale_100_budget_recovery_freeze.json`），预算提到 $30，归档旧半成品至 `runs/archive_e3c_budget_20260804`，以 seed101_r3 / seed202_r2 重跑（共享缓存快速回放既有成功调用），状态 `RUNNING`。
- 2026-08-04 用户决定 E3c 只执行 100 户规模点（2 seed），500/1000 不执行；已冻结 scope amendment（`carr_s_e3c_scale_100_only_amendment.json`），论文中规模/效率主张收窄为 100 户包络，禁止声称 500/1000 稳定规模。
- 2026-08-04 E3a v8b 在 2303/−feedback 第 7 步遇空响应停跑；已归档半成品至 `runs/archive_e3a_v8b_empty_20260804` 并重跑（复用 2107/2209 与 2303/full），状态 `RUNNING`。E3c 100 户 seed202_r2 已 `VALID`，seed101_r4 在 step 22/25 推进中。
- 2026-08-04 后续恢复：E3a v8a 已 `COMPLETE`（12/12）。E3c seed101_r4 在 step22 再次空响应 `ABORTED`（归档 `runs/archive_e3c_seed101_r4_empty_20260804`，以 r5 重跑）；E3a v8b 在 2303/−feedback 第 10 步再次空响应停跑（归档 `runs/archive_e3a_v8b_empty_20260804b` 并重跑）。两者均复用共享缓存/有效格。
- 2026-08-04 用户要求将 E3a v8b 传输从 opencode 切到 Packy（seed101 本就是 Packy，未切换）。已冻结 `carr_s_e3a_v8b_packy`（新协议 id，12 格全新 Packy 运行；opencode 侧 2107/2209 有效格与 2303 半成品归档至 `runs/archive_e3a_v8b_opencode_packy_switch_20260804` 并排除，不跨传输拼接），lane 已启动（PID 37564），状态 `RUNNING`。
- 2026-08-05 最终口径：用户决定不补跑 claude 缺失的 2411/−feedback、−interaction 两格（渠道“分组 aws-q 无可用渠道”持续不可用）。claude 最终为 10/12，2411 配对对比排除；E3 主比较采用 7 个完成 12/12 的模型（qwen、glm、gpt-5.4-mini、qwen27b、gemma4、qwen36、deepseek），claude 不作为完整模型列入主表。实验执行全部收口。
- 2026-08-04 已产出 E1 三 seed 审计（`results/carr_s_e1_v2_formal_audit.md/json`）与 E2 r7 论文表格（`results/carr_s_e2_v8_formal_r7_paper_tables.md/json`）；E3a 两个等价 prompt 变体（v8a/v8b）、运行器、配置与冻结文件已建立，mock 预检待重跑；E3c 规模协议待冻结。

## 9. 2026-08-15 更新：四组研究正式审计晋级 COMPLETE_VALID 与 carr.py/gateway 再冻结

- 2026-08-15 正式晋级审计（`disastersociety/scripts/audit_carr_formal_promotion.py`，产物 `results/carr_s_*_promotion_audit.{json,md}`）：**E1 v2**（3 seed，expected-cell 完整性/终态 VALID/步骤完整/0 失败/fallback<1%/provenance/汇总重算全过）升为 `COMPLETE_VALID`；**E3 v1** 跨模型（84 格，7 模型主表）升为 `COMPLETE_VALID`，网关总计 n_ok=11259、0 失败/0 fallback/0 cache；**E3a** 等价提示敏感性（v8a/v8b 各 12 格，fragments 校验 `carr_s_controlled_resident_v8:v8a/:v8b`）升为 `COMPLETE_VALID`，3010 调用 0 失败；**E3c** 规模 100 户（seed101_r5/seed202_r2，n_households==100 校验、gateway.spent>0）升为 `COMPLETE_VALID`。四组 gates=True、problems=0。至此 E1 v2 早期（2026-08-14）被降为 DIAGNOSTIC 的方法/产物审计结论由本次带 provenance allowlist 的晋级审计取代，正式口径为 COMPLETE_VALID。
- 2026-08-15 E3 跨模型 lane 对比经晋级审计独立重算，与论文表一致：deepseek fb=−6.84375/ia=0.78125、qwen −6.71875/0.40625、glm −6.65625/0.5、gpt54mini −1.6875/0.03125（dir_ia=0.25，已记录的例外）、qwen27b −8.21875/0.46875、gemma4 −6.15625/0.375、qwen36 −9.40625/0.5625。
- 2026-08-15 E3 provenance 异质性已解决并冻结修正案 `protocol/carr_s_carr_py_gateway_refreeze_20260815.json`（FROZEN_REFREEZE_COMPLETED）：resident_adapter 两哈希均合规（原始 1a6b68a2 用于 E2 r7 60 格+E3 55 格；重建 c2ebf7e5 用于 E3 29 格+E3a 24 格+E3c 2 run，差异仅两行 docstring，复验 39 passed/1 failed=字节守卫自身）；gateway 两哈希均合规（e3c2397b 26 格；132b787e 58 格+E3a+E3c，差异 78 行纯 transport/parsing 硬化，未改决策内容逻辑）。science_unchanged=true；正式参考哈希今后分别为 c2ebf7e50679… 与 132b787e400d…。
- 2026-08-15 论文（`~/tmp/disastersociety/paper/ieee_journal/source/main.tex`，14 页）已写入 E1 规模演示（Table IV，100 户×2 种子）与 E3a 提示敏感性段；全部五组正式实验（E1 v2、E2 v8 r7、E3 v1、E3a、E3c scale-100）现均为 COMPLETE_VALID 且已入论文。Carr-R test split 于 2026-08-02 OPENED_FOR_DIAGNOSTIC 的事实在论文 Discussion/Conclusion 已更正。
- 2026-08-15 分布层经验对照已计算并写入论文（`scripts/compute_carr_s_distribution_comparison.py`，产物 `results/carr_s_e1_distribution_comparison.{json,md}`，核验参考件 sha256=0d899eb3… 与冻结记录一致）。数据=5 个正式 run（E1 v2 ×3 + E3c ×2）的原始 ledger 现算。结论（与冻结参考并排、不做点估计等同）：
  - **命令→出发延迟 CDF**（两侧同估estimand：首次送达命令→该户首个执行出发；模拟 n=114 户，问卷 n=186）：模拟 0h=0.570、0.5h=0.868、1h=0.965、2h=1.000；问卷 0h=0.446、1h=0.634、5h=0.774、48h=0.968。方向一致（多数迅速出发）但模拟分布被压缩（中位 0h vs 1h；均值 0.28h vs 7.11h），问卷长尾无模拟对应；结构性边界=25 步×0.5h 窗口封顶 12.5h + 半小时决策节拍。
  - **渠道流行度**（多选、订单接收户口径，模拟 n=197 户，问卷 n=234）：official_direct=1.000（队列定义使然）、community=0.924、household_dm=0.421、any_interpersonal=0.939；问卷 interpersonal=0.372 [0.312,0.435]、reverse_911=0.359、text=0.380。严格遵守冻结禁令：未做 first-heard 对比、未算分布距离。
  - **个体出发份额**：模拟全员 0.375（200/534）、订单接收户内 0.458（180/393）；问卷撤离率 0.888 [0.849,0.918]（n=330）。水平差距如实写入论文（未警告户几乎不自撤、拆分 party 留人），不調参抹平。
  - 论文新增 Table（tab:e1-dist）+ "Distribution-level comparison with the frozen survey reference" 段，Discussion threats 同步声明"延迟时序与结果水平均未获行为验证"。
- 2026-08-15 **规则基线 arm 完成并写入论文**：冻结协议 `protocol/carr_s_e2_v8_rule_arm_freeze.json`（FROZEN_FOR_EXECUTION，policy=carr_controlled_policy @ carr.py:522，sha=c2ebf7e5…），配置 `configs/carr_s_e2_v8_rule_arm.yaml`，驱动 `scripts/run_carr_e2_v8_rule_arm.py`，产物 `results/carr_s_e2_v8_rule_arm_summary.json` + 12 个 run 目录（`runs/carr_s_e2_v8_rule_arm_full_seed*`）。full 条件 × r7 同 12 seed，走同一 kernel/消息/仲裁管道，**0 LLM 调用、$0.00**、12/12 VALID。结果：全指标封顶——safe departure 1.000±0、resident evac 1.000±0、dependent safety 1.000、closed-route rejections 0、四项操纵检查全 1.0；execution rejections 1.000/户（全部是 route capacity exhausted 瞬时拒绝，重试后吸收）。对比 LLM full 条件（r7 12 格现算）：safe 0.812±0.155、resident evac 0.906±0.078、replan 0.906、commitment 0.938。论文写法：tab:e2-levels 加 "Rule reference†" 行 + "Rule-based reference arm" 段，口径=非生成式 policy-class 参照臂，证明场景可达封顶、LLM 缺口来自决策过程退化而非场景硬度；**不是机制证据、不是行为验证**。标签口径：evidence_type=policy_class_reference（不占用 mock 工程验证标签，因为策略本身是研究对象）。首次运行曾因 budget_usd: 0.0 在 step 1 触发 BUDGET_EXCEEDED（spent 0 >= 0），已改为名义 1.0 并重跑，冻结文件内配置哈希已同步更新。
