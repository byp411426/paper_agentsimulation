# Carr 问卷变量审计

**审计日期**：2026-08-02

**状态**：核心标签、时间和 Q13.6 派生映射已核验；Carr-R 原 test 已用于完整字段诊断

**来源**：

- `disastersociety/Wong_Carr_Wildfire_Survey.pdf`
- `disastersociety/Wong_Carr_Wildfire_Dataset.csv`
- Qualtrics CSV 第二行问题文本

## 1. 核心映射

| 论文变量 | 问卷字段 | PDF 位置 | 处理 |
|---|---|---|---|
| 是否撤离 | `Q9.1` | 第 18 页 | Yes=1，No=0，缺失不插补 |
| 实际撤离日期 | `Q13.3` | 第 27 页 | 与 `Q13.4` 合并为 2018 时间戳 |
| 实际撤离时间 | `Q13.4` | 第 27 页 | 与 `Q13.3` 合并 |
| 收到的命令类型 | `Q5.2_1..4` | 第 9 页 | 强制令、建议令、就地避难、无官方命令分别保留 |
| 强制令时间 | `Q6.2`、`Q6.3` | 第 11 页 | 日期和小时合并 |
| 建议令时间 | `Q7.2`、`Q7.3` | 第 13 页 | 日期和小时合并 |
| 强制令渠道 | `Q6.1_1..13` | 第 10 页 | 多选布尔字段 |
| 建议令渠道 | `Q7.1_1..13` | 第 13 页 | 多选布尔字段 |
| 撤离时可见火势/烟雾 | `Q13.6_1`、`Q13.6_2` | 第 27–28 页 | `_1=visual fire`、`_2=smoke`；只作过程/结果变量，禁止作为预测输入 |
| 撤离时官方压力 | `Q13.6_3` | 第 28 页 | post-outcome 过程/结果变量，禁止作为预测输入 |

## 2. 已纠正的旧错误

1. 旧脚本先正确读取 `Q9.1`，随后又把 `evacuated` 覆盖为
   `warned_official`；覆盖逻辑已经删除。
2. 旧脚本把 `Q6.1_9` 当作邻居渠道。CSV 问题文本和 PDF 均表明：
   `Q6.1_9` 是网站，`Q6.1_11` 才是邻居、朋友或家庭成员告知。
3. 旧脚本把 `Q6.3` 当作整数编码，但导出的值是 `7:00 PM` 一类文本；
   现在与日期字段一起解析。
4. 旧脚本用 `warned_hour` 代替撤离时间；现在使用 `Q13.3/Q13.4`。
5. 旧 `risk_perception` 来自撤离时的 `Q13.6`，属于 post-outcome
   信息；现在改名为 departure perception，并从基线输入中删除。
6. 旧脚本把多选渠道压成单一 `heard_from`，且按固定优先级取第一个。
   问卷没有“first heard”题，因此现在保留 13 个多选渠道指示变量。
7. 旧脚本曾把 `departure_fire_perception` 和
   `departure_smoke_perception` 错映射为 `Q13.6_2/Q13.6_3`；问卷和
   Qualtrics 表头确认正确映射为 `Q13.6_1/Q13.6_2`。2026-08-02 已修复、
   重建派生文件并增加精确回归测试。Q9.1、撤离时间、渠道、Carr-R 四字段输入
   和 E1 v1.1 聚合参照核心均不受影响；修复前派生文件保留在归档目录。

## 3. 冻结后的样本事实

由 `scripts/clean_survey.py` 从同一原始文件确定性生成：

| 项目 | 数量 |
|---|---:|
| 原始答卷（不含 Qualtrics ImportId 行） | 647 |
| `Finished=TRUE` | 335 |
| `Q9.1` 有效、进入个体评价集合 | 330 |
| 撤离 | 293 |
| 未撤离 | 37 |
| `Q9.1` 缺失、排除 | 5 |
| 撤离者中日期和时间完整 | 292 |
| 撤离者中时间不完整 | 1 |
| 至少一个撤离命令时间完整 | 246 |

冻结文件：

- `eventpacks/carr_2018/behavior/survey_clean.csv`
- `eventpacks/carr_2018/behavior/evaluation_respondents.csv`
- `eventpacks/carr_2018/behavior/survey_clean_qa.json`

QA 文件记录原始 CSV 的 SHA-256、字段映射、样本统计和渠道选择计数。

## 4. 分析边界

- 个体撤离评价使用 330 人冻结集合。
- 撤离时间分布使用 292 名具有完整 `Q13.3/Q13.4` 的撤离者。
- 36 名受访者报告的撤离命令时间晚于撤离时间。这可能表示先自主撤离、
  后收到命令，不能自动标为时间错误；应作为可解释过程类别单列。
- 15 名完整答卷同时报告收到强制/建议令和“无官方命令”。原始回答保留，
  `order_response_inconsistent=True`，正式渠道分析需预先声明处理方式。
- 渠道题是多选 prevalence，不是互斥份额，也不是 first-heard 变量。
  不得将其与模拟 first-heard shares 直接计算总变差距离。
- Carr-R 的统一 `evaluation_index` 拆分为198 train、66 validation、66
  former-test，并按Q9.1分层。2026-08-02的完整字段信号诊断检查了全部330人
  的候选特征—结果关系，因此原test状态为`OPENED_FOR_DIAGNOSTIC`，以后不得
  称untouched holdout。跟踪文件不导出respondent ID。
- 15条命令矛盾记录在渠道 prevalence 主分析中排除；敏感性分析采用肯定
  mandatory/voluntary order 回答及其所选渠道优先。该矛盾不单独排除有效
  Q9.1 outcome。

## 5. 仍待完成

1. ~~决定15条命令响应矛盾记录的主分析与敏感性处理~~；
2. ~~冻结传统模型与 LLM 共用的数据拆分~~；
3. ~~为渠道评价改用多选 prevalence 指标~~；若研究 first-heard，另找同
   estimand 外部数据；
4. E1 v2 仅从Carr train构建不按outcome条件抽样的潜在trait block，并完成
   字段级来源、时序和泄漏fail-fast；
5. Carr-R如继续，只能使用明确的开发交叉验证或新外部holdout；历史无效模型
   结果继续标记为`INVALID_FOR_CLAIM`。
