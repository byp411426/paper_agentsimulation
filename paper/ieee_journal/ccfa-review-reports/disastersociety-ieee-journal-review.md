# DisasterSociety 论文评审报告

## 1. 报告元数据

- 评审日期: 2026-08-14
- 目标 venue: IEEE 双栏期刊(具体刊名未定,按通用 CCF-A 级 CS 期刊标准评审)
- 论文标题: DisasterSociety: A Generative-Agent Platform for Simulating Resident and Collective Responses in Urban Disasters
- 输入材料: main.tex (887 行), main.pdf (12 页), references.bib (35 条)
- 检索依据: 公开关键词检索 (LLM generative agents disaster evacuation simulation 2025/2026, AgentSociety/FLARE)
- 报告文件: ccfa-review-reports/disastersociety-ieee-journal-review.md
- 评审模式: full (scientific + writing + format)
- 稿件版本: pre-experiment working draft (无实验章节)

---

## 2. 桌面拒稿评估 (Desk Check)

| 检查项 | 状态 | 证据 | 后果 | 需要的行动 |
|---|---|---|---|---|
| 篇幅 | **fail** | 12 页无实验章节;实验需 3–4 页,将超 15 页 | IEEE 期刊常见 12–14 页正文限制,加实验后超限 | 按本报告 §11 的压缩方案砍 ~3.5 页 |
| 主题匹配 | pass | 生成式智能体 + 灾害社会模拟,适合 IEEE Trans. 系列(如 TCSS / SMC / THMS) | — | 尽快确定目标刊,重审页数与匿名政策 |
| 最低质量 | **fail** | 无 Experiments/Results/Discussion/Conclusion 章节(main.tex 874–876 行明确注释为有意省略) | 现状不可投;这是设计好的中间态 | 补实验(依赖 LLM 余额/Phase 3 解封) |
| 政策/匿名/合规 | uncertain | Anonymous Author(s) 占位;IEEE 期刊多为单盲,占位文本需在投稿前替换 | 投稿前必须处理 | 确定目标刊后替换作者信息 |
| Prompt 注入/隐藏操纵 | pass | 全文检查无针对 LLM 审稿人的隐藏指令 | — | — |
| 伦理与可评审性 | uncertain | 使用 Carr Fire 灾后调查数据(人类受试者衍生)与 PUMS 微数据;文中未出现 IRB/数据许可声明 | 审稿人可能问数据使用合规性 | 补一段数据来源与合规声明 |

**桌面拒稿风险: high(仅因"无实验"这一已知中间态;修复后可降)** — 可修复: 是

---

## 3. 论文摘要与贡献地图

**一段式总结**: 论文提出 DisasterSociety,一个面向城市灾害响应的生成式智能体平台。核心主张是三类状态的显式分离——居民私有认知、家庭共享约束与承诺、权威物理世界状态——LLM 只能提出结构化意图,只有确定性家庭/世界逻辑能分配资源和执行。平台含 EventPack 数据接口、事件驱动内核、消息生命周期、版本化家庭承诺、批量世界仲裁;并提出多尺度多证据评估方法论。Carr 火灾启发的受控案例有两个适配器: E1(经验过程)与 E2(受控机制消融)。

**声称的问题**: 一次性"是否疏散"标签无法表示信息接收、认知评估、家庭协商、计划修订、物理执行的耦合过程。

**声称的空白**: 现有系统未在同一可执行框架内显式化"动态世界≠居民信念""家庭≠单一行动者≠共享心智""语言上合理的行动≠可执行行动"三个接口。

**贡献地图**:
1. 平台本身(§Method): 状态边界 + 事件驱动内核 —— 证据: 架构图 fig2、公式 eq:state/arbitration、trace 设计。**无运行证据**。
2. 居民社会过程模型(§3.3): 闭环多步循环 —— 证据: fig3、十步调度。**无运行证据**。
3. 评估方法论(§Evaluation Design): claim-evidence 映射 + 消融公式 —— 证据: 表 II、eq:ablation。**设计文档,非结果**。

**声称的局限(已声明)**: 不声称历史重建、不声称城市自动生成器、不声称人群级疏散预测;Carr-R 测试分区已开放不再是 untouched holdout;社会网络是建模假设非观测数据。

**未声明的局限**: LLM 后端依赖与成本;fallback 机制对行为有效性的影响;30 分钟步长的粒度合理性论证。

---

## 4. 检索与相关工作依据

- 检索词: "LLM generative agents disaster evacuation simulation household 2025 2026"; "AgentSociety OR FLARE wildfire evacuation LLM agent simulation arxiv 2025"
- 来源: WebSearch(公开)
- 最接近的工作(文中已引): AgentSociety, CitySim, FLARE, Dang et al. fire agents, Yang et al., RESPOND —— 覆盖良好
- 未验证的相关工作风险: ① HCI/CSCW 社区的 crisis informatics 工作(Palen, Hughes 等)未出现,灾害信息行为的实证文献对"居民信息处理"主张有直接相关性;② 经典疏散行为模型(belief-desire-intention 类、PED 类)覆盖偏薄,相关工作目前以 PADM 一条线为主
- 来源质量筛查: 通过(仅公开检索,未使用私有文本)

---

## 5. 预期评审结果

- **预期结果(现状投出): reject (overall 3/10)** — 致命原因: 无实验
- **预期结果(补实验 + 压缩后): borderline ~ weak accept (5–7/10)**,取决于 E1 经验合理性与 E2 消融结果的强度
- 主要接受信号: 状态分离架构的清晰性、诚实的评估方法论设计、双适配器估计量区分
- 主要拒稿信号: 全部三条贡献均无实证支撑;"平台论文"若没有运行结果,贡献 1/2 退化为系统设计描述
- 置信度: 4/5(全文可读,但缺实验、缺目标刊、缺附录)

---

## 6. 优点与缺点

### 优点
- **S1** 三层状态边界(认知/承诺/物理)是真正的架构主张,不是装饰;eq:state 与 eq:arbitration 把"LLM 不能改物理世界"落到了可检查的接口上
- **S2** 评估设计章节的四类证据区分(验证/合理性/机制/鲁棒性)在 LLM-agent 论文中少见,且明确写了"calibrated inputs are not independent confirmation"
- **S3** 双适配器(E1 经验/E2 机制)共享内核但估计量不同,避免了"一套系统两个故事"的混淆
- **S4** 措辞诚实: 多处显式限定(social graph 是建模假设、Carr 案例是受控场景、当前 summary label 不可用于 Results)

### 缺点

**W1 (fatal): 无任何实验证据。**
- 证据依据: main.tex 874–876 行;§Evaluation Design 全部是将来时("will be recomputed", "None is eligible for Results")
- 审稿人推论: 三条贡献(平台/过程模型/方法论)目前都是设计声明;IEEE 期刊审稿人无法区分"已实现的平台"与"设计文档"
- 需要的修复: E0 软件验证 + E1 经验合理性 + E2 机制消融至少跑出核心结果;fallback 率、成本、延迟必须有数字

**W2 (major): 方法章节严重过载,信息效率低。**
- 证据依据: §Method 占 ~4.5 页、7 个子节;11 个编号公式中至少 5 个(eq:intention, eq:interaction-transition, eq:message-lifecycle, eq:message-disposition, eq:fallback)是把一句话形式化
- 审稿人推论: "LLM 不能改世界"这一论点在引言、§3.1、§3.4、§3.5、§3.6 各重复一次;E1/E2 适配器细节(§3.7)与表 I 内容大量重叠
- 需要的修复: 压缩至 ~3 页(详见 §11 压缩方案);E1/E2 正文各留"目的 + 一句关键差异",细节全部交给表 I

**W3 (major): Related Work 过长且有三处与本研究主张重复。**
- 证据依据: ~1.7 页、3 个子节、35 条引用;"interface claim rather than priority claim"段(§2.2 末)与引言第 2 段、§2.1 末的区分声明三处重复
- 审稿人推论: 对 IEEE 双栏期刊,相关工作超过 1 页即被读为"动机未在引言讲清楚"
- 需要的修复: 砍至 ~1 页;合成人口段移入 §3.2;模拟评估段移入 §Evaluation Design 开头

**W4 (moderate): 评估设计章节混入"实现待办"。**
- 证据依据: §Evaluation Design 中 "Its present complete_safe_household_departure summary counts...", "the current runner does not separately compute..." 等内部实现状态描述
- 审稿人推论: 这是作者自己的工程备忘,不是论文内容;暴露未完成状态会损害可信度
- 需要的修复: 写实验时把这些转化为确定的指标定义;删除所有 "current/present/not eligible" 措辞

**W5 (moderate): 公式数量与真实信息不匹配。**
- 证据依据: eq:message-lifecycle / eq:message-disposition 表达的是"sent→delivered→processed"一句话;eq:fallback 是一个比率定义
- 需要的修复: 保留 eq:state, eq:arbitration, eq:wake-gate, eq:commitment-feasibility, eq:ablation 五个;其余转文字。这正是你觉得"公式有点少但其实不少"的原因——公式不少,但**承载信息的公式**少

**W6 (minor): Carr-R/Carr-S 人群区分在两处重复说明。**
- 证据依据: §Evaluation Design 第 2 段与 E1 段重复"survey field 预先分配"原则
- 需要的修复: 合并为一处

---

## 7. 可能缺失的相关工作

| 工作 | 状态 | 为何相关 | 需要的对比 |
|---|---|---|---|
| Crisis informatics 实证线 (Palen & Hughes, social media in disaster) | unverified | 居民灾害信息处理的 HCI 实证基础,支撑"信息暴露有界"主张 | 一句定位: 我们建模的是决策过程,他们观测的是信息行为 |
| BDI 类疏散行为模型 | unverified | 意图-信念-执行分离有更长学术谱系 | §2.1 加一句承认该谱系,区分点在 LLM 认知 + 家庭承诺对象 |
| GenSim/GenAgents 类 2025–2026 最新平台 | searched(浅) | 大规模 agent 社会模拟竞争加剧 | 投稿前做一次增量检索,确认无同时期撞车 |

---

## 8. 主张-证据审计

| 主张 | 位置 | 提供证据 | 强度 | 审稿人推论 | 需要的修复 |
|---|---|---|---|---|---|
| 三类状态可分离且必要 | 摘要, §1, §3.1 | 架构图 + 形式化 | adequate | 作为设计主张成立,但"必要性"需要反例(不分离会出错的演示) | E2 消融中展示边界破坏的失败案例 |
| LLM 只做意图不做执行 | §3.1, §3.4 | 接口设计 | adequate | 可检查的设计;需 trace 证明实际运行如此 | 实验章节给出 trace 审计数字 |
| 闭环多步过程 | §3.3 | fig3 | weak | 没有运行轨迹展示闭环真的闭合 | 至少一个 case trace 展示 观察→计划→拒绝→修订→执行 |
| 评估方法论可区分证据类型 | §Evaluation Design | 表 II | weak | 设计合理,但没有演示一次完整应用 | 实验章节按表 II 四行各给至少一个结果 |
| Carr 案例可操作化 | §3.2, §3.7 | 表 I | weak | 无人口拟合数字(如边际分布误差) | 补 IPF 拟合质量数字 |

---

## 9. 实验/基准/可复现审计

- **baselines**: 无。即使是平台论文,也需要至少一个"无状态分离"的对照配置来证明边界设计的价值
- **ablations**: E2 设计了 memory/feedback/planning/interaction 四开关消融(好),但无结果
- **数据集**: Carr-R 调查 + PUMS 微数据 + 受控场景;数据合规声明缺失
- **metrics**: 指标定义细致(safe arrival / any-party / complete departure / split departure 的分母区分是真正的优点),但全部未计算
- **统计严谨性**: eq:ablation 的配对种子设计正确;独立复制单位声明清晰(run 级而非 resident 级)
- **鲁棒性/失败案例**: fallback 率公式已定义,无数字
- **实现细节**: 内核十步调度清晰;wake gate 公式完整
- **工件与可复现性**: 指纹/溯源设计好;未见代码可用性声明
- **局限**: 局限声明诚实地存在,但散落在正文里,无独立 Limitations 小节

---

## 10. 多 Reviewer Panel

**Reviewer: 方法/严谨性**
- 评分倾向: 4/5(设计),2/5(验证)
- 置信度: 4
- 主要正面信号: 状态所有权分离是真架构贡献;wake gate 与承诺可行性公式精确
- 主要负面信号: 内核十步调度没有讨论计算复杂度/可扩展性上限;"并发决策而物理世界不可变"的竞争条件只提了一次
- 改分条件: 给出规模上限实验(N residents 时的 wall-clock)

**Reviewer: 证据/实验**
- 评分倾向: 1/5
- 置信度: 5
- 主要负面信号: 零实验。所有指标是定义不是数字
- 改分条件: E0+E1+E2 出结果,含 fallback 率与成本;此项单独可 +2~3 overall

**Reviewer: 新颖性/定位**
- 评分倾向: 3/5
- 置信度: 4
- 主要正面信号: "接口声明非首创声明"定位诚实且可辩护
- 主要负面信号: 与 AgentSociety/RESPOND 的差异是抽象层级差异,审稿人可能读为"工程整合";crisis informatics 与 BDI 谱系缺失让"社会过程"主张显得根基薄
- 改分条件: 补两条谱系的定位句;用 E2 消融证明边界是**功能必要**而非仅设计偏好

**Reviewer: 写作/清晰度**
- 评分倾向: 3/5
- 置信度: 4
- 主要正面信号: 术语稳定(commitment/intention/receipt 用法一致)
- 主要负面信号: §Method 重复论点五次;§Evaluation Design 混入实现待办;阅读负担高
- 改分条件: 按压缩方案执行后可达 4

**Reviewer: 领域应用**
- 评分倾向: 3/5
- 置信度: 3
- 主要负面信号: 灾害管理实践者会质疑 30 分钟步长、单终点 perimeter、双路线抽象的现实性;这些目前只有限定声明没有敏感性论证
- 改分条件: 敏感性分析或对抽象层级的明确辩护段

**Reviewer: 可复现性**
- 评分倾向: 3/5
- 置信度: 3
- 主要正面信号: 指纹/种子/网关记录设计完整
- 主要负面信号: 无代码可用性声明;LLM 后端依赖(余额问题)直接威胁复现
- 改分条件: 明确 artifact 计划;报告模型 alias 与版本

**Reviewer: 新手可读性**
- 评分倾向: 2/5
- 置信度: 4
- 主要负面信号: running example(fig1)好,但正文读完引言后立刻进入公式密度最高的 §3.1;没有 roadmap 段;E1/E2 的区分要到 §3.7 才完全清楚
- 改分条件: 引言末加一句各章节指引;§3.1 开头先用 running example 复述一遍状态分离

**AC/Meta-Reviewer 综合**:
- 共识: 架构设计清晰、评估方法论严谨;无实验是致命项
- 分歧: 状态分离是"贡献"还是"良好工程实践"——取决于 E2 消融是否证明功能必要性
- 决定性接受轴: E2 消融若显示去掉任一机制导致可测的行为退化 + E1 显示 Carr 合理性 → weak accept
- 决定性拒绝轴: 现状(无实验)直接拒;补实验后若消融无效应(所有 Δ≈0),贡献退化为平台描述,仍偏拒
- 未解决证据: LLM 余额/Phase 3 状态决定实验能否产出

---

## 11. 关注项总表(按严重性)

| ID | 严重性 | 关注项 | 证据依据 | 影响维度 | 修复类型 | 需要的行动 | Owner skill | 改分条件 |
|---|---|---|---|---|---|---|---|---|
| C1 | fatal | 无实验章节 | main.tex 874–876 | Evidence | experiment | 解封 LLM 余额→跑 E0/E1/E2→写 3.5 页实验 | ccf-experiment-designer + ccf-paper-writer | +3 overall |
| C2 | major | Method 4.5 页过载 | §3 七子节、论点重复 5 次 | Clarity | compression | 压至 3 页:公式 11→5,E1/E2 细节入表 I | ccf-paper-writer | +0.5~1 clarity |
| C3 | major | Related Work 1.7 页过长 | §2 三子节 35 引 | Clarity/Positioning | compression | 压至 1 页:3 子节→2,合成人口移 §3.2,评估段移 §4 | ccf-paper-writer | +0.5 clarity |
| C4 | major | Evaluation Design 混入实现待办 | "current runner does not..." 等 | Soundness(观感) | writing | 实验落地时转为确定定义,删将来时 | ccf-paper-writer | +0.5 soundness |
| C5 | moderate | 低信息公式过多 | eq:message-lifecycle 等 5 个 | Clarity | compression | 保留 5 个核心公式,其余转文字 | ccf-paper-writer | 并入 C2 |
| C6 | moderate | 缺 crisis informatics / BDI 定位 | §2 未出现 | Positioning | related-work | 各加一句定位 | ccf-literature-searcher | +0.5 positioning |
| C7 | moderate | 无 baseline 配置 | 全文 | Evidence | experiment | 至少一个"无状态分离"对照或论证为何不可行 | ccf-experiment-designer | 并入 C1 |
| C8 | moderate | 数据合规/IRB 声明缺失 | Carr-R + PUMS 使用 | Ethics | ethics | 加数据来源与许可段 | ccf-paper-writer | 消除审稿疑问 |
| C9 | minor | 规模上限/复杂度未讨论 | §3.3 | Soundness | experiment | E0 或鲁棒性实验给 N-scale 数字 | ccf-experiment-designer | 并入 C1 |
| C10 | minor | 代码可用性未声明 | 全文 | Reproducibility | reproducibility | 加 artifact 声明 | ccf-submission-checker | 消除审稿疑问 |

**页数预算(压缩方案汇总)**: 引言 1.7(不动) + RW 1.0(−0.7) + Method 3.0(−1.5) + EvalDesign 1.0(−2.0) + 实验 3.5(新) + Discussion/Conclusion 0.7(新) + 参考文献 ~1.5 ≈ **12.5–13.5 页** ✓

---

## 12. AC / Meta-Review

- **Reviewer 共识**: 所有评审视角一致认为"状态分离架构"是论文最强的点、"零实验"是最弱的点。写作过载是第二弱点。
- **Reviewer 分歧**: 新颖性评审认为贡献是"抽象层级整合",方法评审认为是"真架构贡献"。该分歧只能由 E2 消融结果裁决——如果去掉边界/机制没有可测后果,新颖性评审的读法成立。
- **决定性接受轴**: E2 消融效应显著 + E1 Carr 合理性好 + 压缩到位 → 7/10 weak accept
- **决定性拒绝轴**: 现状(3/10);或消融全无效(4/10)
- **AC 立场**: 当前稿件是高质量的"实验前工作稿",不是可投稿件。修改路径清晰且全部可执行。
- **讨论风险**: 若审稿轮中 LLM 后端问题导致 fallback 率过高,行为有效性主张会被质疑;必须在实验章节如实报告 fallback 率并分析其影响。

---

## 13. 量化评分

| Dimension | Score (1-5) | Confidence (1-5) | Evidence basis | Deduction / score-change condition |
|:---|:---:|:---:|:---|:---|
| Novelty | 3 | 4 | §1, §2.2 定位声明 | 抽象层级整合 vs 真贡献未定;E2 消融证功能必要 → 4 |
| Soundness | 3 | 4 | §3 设计严谨但 §Evaluation Design 混入实现待办 | 删将来时 + 跑通验证 → 4 |
| Evidence | 1 | 5 | 无实验(main.tex 874–876) | E0+E1+E2 出结果 → 3~4 |
| Significance | 4 | 3 | 灾害响应 + LLM agent 交叉是活跃区 | 取决于实验 |
| Clarity | 3 | 4 | §Method 过载, §RW 过长 | 压缩方案执行 → 4 |
| Reproducibility | 3 | 3 | 指纹/种子设计好;无代码声明;LLM 依赖风险 | artifact 声明 + 模型版本固定 → 4 |
| Ethics / Limitations | 3 | 3 | 局限声明诚实但散落;数据合规未声明 | 补合规段 + 独立 Limitations 小节 → 4 |

**Overall: 3/10(现状) | Scholarly Confidence: 4/5**

**Recommendation:** reject(现状) — 但这是设计好的中间态,非真实投稿
**Verdict:** 补实验(+3) + 压缩(+1) + 定位补充(+0.5) → 可达 7/10 weak accept 区间

---

## 14. 给作者的问题

1. E2 消融中,如果去掉 feedback 机制,居民在道路封闭后的行为退化具体表现为什么?有预期方向吗?(决定消融是否能支撑新颖性主张)
2. fallback 到规则决策的意图是否仍参与世界仲裁?(文中 §3.6 说是——实验章节需要给出 fallback 率,以及 fallback 意图与 LLM 意图的行为差异)
3. 目标期刊是哪一家?TCSS / SMC / THMS 的页数与评审口味差异会改变压缩策略。
4. 30 分钟步长与双路线抽象是否有 Carr 实证依据,还是纯受控设计选择?

---

## 15. 分数修订标准

**提分需要**:
- 跑出 E0/E1/E2 核心结果(含 fallback 率、成本、延迟)——最大杠杆,Evidence 1→3~4,overall +3
- 按 §11 压缩方案砍 3.5 页——Clarity +1
- 补 crisis informatics / BDI 两句定位——Positioning +0.5

**降分触发**:
- 消融实验全部 Δ≈0(机制无功能必要性)
- fallback 率 >30% 且无分析
- 发现同期撞车工作(2025–2026 LLM 灾害模拟平台爆发)

**投稿前不太可能改变的**:
- 无真实 Carr 社会网络观测(已诚实声明)
- 单场景(Carr)泛化性——需要一个第二场景或明确单案例定位

---

## 16. 行动计划与 CCFA 交接

| 优先级 | 行动 | Owner skill | 需要的输入 | 预期输出 | 需交接 |
|---|---|---|---|---|---|
| P0 | 解封 LLM 余额/确认实验可跑 | (用户操作) | PACKY 账户状态 | 实验可运行 | no |
| P0 | 冻结实验设计:E0/E1/E2 指标表结构 | ccf-experiment-designer | §Evaluation Design 指标定义 | 结果表 schema | yes |
| P1 | 压缩 Related Work 至 1 页 | ccf-paper-writer | 本报告 §6 W3 | 修订后 §2 | yes |
| P1 | 压缩 Method 至 3 页(公式 11→5) | ccf-paper-writer | 本报告 §6 W2/W5 | 修订后 §3 | yes |
| P1 | 补 crisis informatics / BDI 定位检索 | ccf-literature-searcher | 公开检索 | 2–3 条引用候选 + 定位句 | yes |
| P2 | 写实验章节(3.5 页) | ccf-paper-writer | 实验结果 + 指标表 | §Experiments/Results | yes |
| P2 | 确定目标刊 + 投稿合规检查 | ccf-submission-checker | 目标刊名 | 合规清单 | yes |
| P3 | 结果图表绘制 | ccf-visual-composer | 实验数字 | 出版级图表 | yes |

**Checks run**: 页数、引用数(35)、公式数(11)、章节字数分布、图片尺寸(1672×941, ~1.5MB/张)、公开检索(浅)、隐藏注入扫描
**Checks skipped**: 逐条引用真实性核验(属 ccf-integrity-auditor 范围,建议实验写完后跑)、目标刊官方政策核验(目标刊未定)
**Unresolved risks**: LLM 余额;目标刊未定;消融结果未知
