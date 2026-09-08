# DisasterSociety 论文诊断评估

> 评估者：论小舟（论文写作导师） ｜ 评估日期：2026-08-30 ｜ 依据：main.tex 全文 + 编译日志 + 参考文献与图表核验

## 一、评估范围与材料

- **对象**：`DisasterSociety: Generative Agent-Based Simulation of Resident and Household Responses to Dynamic Urban Disasters`（main.pdf，12 页，IEEE journal 格式）
- **材料**：LaTeX 源码 main.tex（全文通读）、main.log（编译日志）、main.blg（BibTeX 日志）、references.bib、figures/ 目录
- **本轮任务**：全文诊断评价（先诊断后修改路线）
- **未覆盖**：未代为检索数据库验证文献真伪（诚信边界）；未实查图表视觉质量；未运行外部查重

## 二、编译与材料完整性核验（已核验）

| 检查项 | 结果 | 状态 |
|---|---|---|
| LaTeX 编译 | 无 error，无 undefined reference/citation | VERIFIED_DONE |
| BibTeX 处理 | 29 条被引文献，`warning$ = 0` | VERIFIED_DONE |
| 引用-文献匹配 | \cite 唯一键 29 = bibtex 处理 29，全匹配 | VERIFIED_DONE |
| 图表文件 | fig1–fig5 五张 PDF 齐全 | VERIFIED_DONE |
| Overfull/Underfull box | 共 10 处（排版微瑕，非致命） | TODO_FORMAT |
| bib 冗余 | 106 条中 77 条未引用 | TODO_CLEANUP |

**结论**：技术层面"能编译、能出图、引用闭合"，处于可投稿的技术就绪状态。

## 三、整体判断（一句话）

这是一篇**结构完整、论证清晰、诚信度高、实验设计精巧**的成熟 IEEE 期刊稿，核心贡献（三状态边界 + 机制功能 vs 下游必要性的 dissociation）站得住；距离投稿主要差**作者元信息补全、统计推断补强、样本量/场景外部效度的事先声明与审稿预案**，而非内容重写。

## 四、论文优点（写得好的地方）

1. **框架贡献明确**：resident-private cognition / household-shared commitments / authoritative world state 三状态边界，是清晰可辩的理论贡献，不是工程堆砌。
2. **实验设计精巧**：两个 adapter（empirical-process / controlled-mechanism）分离 estimand；"机制功能（manipulation check）vs 下游必要性（downstream effect）"的区分是本文最具学术价值的发现，直接回应了生成式智能体评估的方法论缺口。
3. **证据诚实**：反复明确 "Carr-informed rather than historical reconstruction"、"directional consistency rather than behavioral validation"、"computational artifacts rather than representations of real persons"——边界声明克制且到位。
4. **鲁棒性检查充分**：E3 跨 7 个模型 + 提示词复现，覆盖了生成式智能体最易被攻击的"单模型artifact"质疑。
5. **规则参考臂**：PADM-style 确定性策略作为 policy-class ceiling，解释了生成式 full-condition 的 0.812 短板源于决策过程退化而非场景难度——这是很漂亮的对照设计。
6. **写作质量高**：英文学术表达规范，术语一致，图表引用闭环，章节契约清晰。

## 五、问题清单（按 P0/P1/P2 排序）

### P0（可能影响提交资格或核心诚信——本轮无致命项）

- **P0-1 作者/资助/通讯作者信息为占位符**（main.tex L36-38 `Anonymous Author(s)` + PENDING 注释）。属有意为之的 working state，但**投稿前必须补全**；若目标 IEEE 期刊非双盲，需确认其匿名政策。
  - 状态：`TODO_AUTHOR_CONFIRM` ｜ 风险：提交即被编辑部退回（metadata 不全）
- **P0-2 较新引用的身份与可获取性**（如 zhou2026gasim、yang2026whenagents、sultimov2026respond、mendoza2026hierarchical、rende2025crowd、guo2026embodied、bail2024generativeai 等）。BibTeX 格式合规，但**投稿前需自行核验这些较新/可能为预印本的来源是否已正式发表、卷期页码是否更新**。我不代为检索数据库，仅提示核验义务。
  - 状态：`TODO_AUTHOR_CONFIRM` ｜ 风险：审稿人或编辑核查引用可获取性

### P1（结论成立，但论证/报告/复现可能被审稿质疑）

- **P1-1 小样本统计功效**：E2 消融仅 8 户×12 seeds；E3 跨模型每模型仅 4 seeds。论文已诚实声明 boundary，但审稿人极可能要求**扩展 seed 数或给出功效说明**。当前 paired-$t$ 区间仅用于"descriptive visualization"，未做正式假设检验。
  - 建议：投稿前补充效应量与（哪怕非参数的）方向性检验说明；或在 limitations 中预先写明 seed 数选择依据。
- **P1-2 GPT-5.4-mini 交互效应未复现（1/4 seeds）**：已诚实报告并解释为 floor-limited（full-condition 仅 0.031）。这是**审稿人最可能的攻击点**，需准备回复：要么补跑排除该模型的敏感性说明，要么强化"floor-limited estimand"的论证（如报告其 full-condition 已接近 0，无 headroom）。
- **P1-3 Carr-R 参考偏离大**：模拟个体疏散率 0.375 vs 调查 0.888；延迟 CDF 压缩（0.570 立即疏散 vs 调查 0.446）。论文已声明为 "reasonableness rather than validation"，但**差距幅度大**，审稿人可能质疑"既然差这么远，Carr-R 参考的价值是什么"。需在 Discussion 强化"为何这种偏离是可预期的结构性差异"（如 25 步窗口、半小时决策粒度、未警告家庭不自疏散），而非仅声明边界。
- **P1-4 缺少正式统计推断**：全文以 direction shares（如 12/12、4/4）+ descriptive paired-$t$ interval 呈现，无 p 值/效应量/置信区间的正式假设检验。IEEE 审稿人可能要求至少给主要 contrast 的效应量与区间。论文已主动声明区间仅用于可视化，但可补一句方法学立场说明（为何偏好 direction-share 胜过 p 值，参考模拟方法学文献）。
- **P1-5 无 baseline 平台横向对比**：论文解释合理（"Existing platforms do not expose matched mechanism controls"），但审稿人可能仍想要至少一个外部基线。可用规则参考臂 + 同平台内对照的组合论证回应，但需在投稿信中预先说明这一设计理由。
- **P1-6 单一场景 archetype**：仅一个 Carr-informed 受控场景、一条灾害轨迹、一次道路封闭。论文已声明不外推，但这是**外部效度的根本限制**，投稿前考虑在 limitations 加一句"未来工作扩展 hazard archetypes"的具体计划（Conclusion 已提，Discussion 可再强化）。

### P2（清晰度/格式，不影响核心结论）

- **P2-1 bib 冗余**：references.bib 106 条，实际引用 29 条，77 条未引用。不影响 PDF（IEEEtran.bst 只处理被引），但投稿前**清理 bib** 可减少编辑困惑与潜在误引。
- **P2-2 摘要数字精度过高**：摘要 "6.542 per household" 三位小数，正文 Table 也是 6.542。建议摘要改为 "approximately 6.5 per household" 或 "by 6.5"，正文保留精确值。过度精确的小数会显得样本量比实际大。
- **P2-3 排版微瑕**：10 处 overfull/underfull box，非致命但影响版面整洁，终投前微调。
- **P2-4 表格信息密度高**：Table adapter-contracts、e2-levels、e3-cross-model 信息密度大，审稿人阅读负担重。可考虑在 caption 增加一句"读表指引"。
- **P2-5 标题 vs 场景**：标题 "Dynamic Urban Disasters"（复数、泛化），实验仅 Carr Fire（野火-城市边缘）。已声明不外推，但标题的 generalization claim 与单一场景存在张力，可在 Introduction 末尾点明"本文以 Carr 为案例，generalization 留待未来"。

## 六、各章节就绪度

| 章节 | 就绪度 | 主要缺口 |
|---|---|---|
| Title/Abstract | 接近就绪 | 数字精度；标题泛化张力 |
| Introduction | 就绪 | — |
| Related Work | 就绪 | 较新引用需核验 |
| Method | 就绪 | 数学符号与文字衔接良好 |
| Experiments (E1) | 接近就绪 | Carr-R 偏离需更强解释 |
| Experiments (E2) | 接近就绪 | 样本量声明 + GPT-5.4-mini 预案 |
| Experiments (E3) | 接近就绪 | 同上 |
| Discussion | 就绪 | 可强化 limitations 与未来计划 |
| Conclusion | 就绪 | — |
| References | 格式就绪，内容待核验 | 77 条冗余清理 + 较新引用核验 |
| 整体 | `draft_with_placeholders`（因作者占位）→ 接近 `ready_to_submit` | 见 P0/P1 |

## 七、整体就绪度与投稿建议

- **整体状态**：`draft_with_placeholders`（作者元信息占位）→ 内容上接近 `ready_to_submit`
- **能投吗**：技术上能编译、能出图、引用闭合，**补全作者信息并清理 P0 后即可投**；P1 是"投了之后大概率被审稿人追问"的点，建议投稿前尽量预先加固（尤其 P1-2 GPT-5.4-mini 预案与 P1-3 Carr-R 偏离解释），可减少返修轮次。
- **目标期刊匹配**：本评估不替你拍板目标期刊。论文定位为"生成式智能体 + 灾害社会模拟 + 方法论评估"，候选可考虑 IEEE T-SG/AI/SMC/CIS 类或 AGI 相关期刊；**建议你基于官方 Aims & Scope 与近期发表的相关工作确认 fit**，我可在此后基于官方要求做期刊匹配矩阵。

## 八、下一步（低负担，按优先级）

1. **（P0，必做）** 补全作者/资助/通讯作者信息，确认目标期刊匿名政策。
2. **（P0，必做）** 自行核验较新引用是否已正式发表、卷期页码是否更新（我不代检索）。
3. **（P1-2，强烈建议）** 为 GPT-5.4-mini 交互效应未复现写一段 1–2 句的"floor-limited"预案，放 Discussion 或留作 reviewer response 储备。
4. **（P1-3，建议）** 在 E1 分布对比段补 1–2 句解释"偏离为何结构性可预期"。
5. **（P2-1，建议）** 清理 references.bib 未引用条目。
6. **（P2-2，建议）** 摘要数字精度降一位。
7. **（可选）** 确定目标期刊后，我可基于官方要求做引用格式逐项核对与投稿包就绪度检查。

---

*本诊断为基于可见材料的全文评估，不承诺录用概率、审稿周期或查重结果。涉及外部数据库检索、文献真伪判断、投稿操作均由你完成。*
