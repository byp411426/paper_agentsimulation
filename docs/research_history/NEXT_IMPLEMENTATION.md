# DisasterSociety 下一步实施路线与实验合同

**状态**：`ACTIVE_IMPLEMENTATION_CONTRACT`

**版本**：E1 v2 / E2 v8 r7 / H1 v1 / E3 v1

**更新日期**：2026-08-02

**适用范围**：首篇 DisasterSociety 框架论文的剩余工程、实验与论文取证

本文档是接手者实际施工的唯一入口。接手者不需要从旧对话重新推断方法，也不得
在工作包内部自行改变研究对象、数据角色、实验 estimand、样本或停止规则。

事实与方法优先级仍为：

1. `AGENTS.md`
2. `docs/PAPER_STRATEGY.md`
3. `docs/EVIDENCE_LEDGER.md`
4. `docs/METHOD_DESIGN_DECISIONS.md`
5. `disastersociety/experiments/analysis_plan.md`
6. 本文档

如果当前代码不能满足本文合同，先补实现和测试，再运行真实模型；不得通过删指标、
改主张或把异常样本静默排除来让实验“能够完成”。

---

## 1. 最终要交付什么

下一阶段要完成一条可追踪的 Carr-S 实验流水线：

```text
2014–2018 ACS/PUMS whole-household donors
    → household-level fitted synthetic population
    → Carr train-only household/person trait donors
    → complete household/member empirical profiles
    → Resident + Household + World + Interaction
    → time-stamped orders, hazard, messages and execution feedback
    → common Engine + real DeepSeek backend
    → E1 empirical/process results
    → E2 paired mechanism results
    → H1 independent human ratings
    → E3 prompt/model/scale results
```

完成后必须能够从持久化 artifact 直接回答四个问题：

| 问题 | 直接证据文件 | 回答边界 |
|---|---|---|
| 一个合成家庭由哪些成员和属性构成？ | `household_profiles.jsonl`、`member_profiles.jsonl`、公开 codebook、受限 linkage、人口 QA | 回答 PUMS whole-household 静态结构和 Carr-informed 插补 trait；不声称是 Carr 真实家庭 |
| 每名决策成员有哪些私有信息、记忆、计划和行动？ | `resident_state_timeline.jsonl`、`decision_records.jsonl`、`commitment_ledger.jsonl` | 回答每个 Resident 的私有过程；不输出隐藏 chain-of-thought |
| 命令、危险、消息和执行失败如何按时间改变行动？ | `official_receipts.jsonl`、`message_ledger.jsonl`、`perception_updates.jsonl`、`execution_ledger.jsonl` | E1 描述时间链；E2 的同 seed drop-one 才用于模块条件移除效应 |
| 结果与 Carr 参照、家庭约束、机制消融和成本差多少？ | E1/E2/H1/E3 冻结 summary 与图表 | 只称 Carr-informed controlled empirical reasonableness，不称历史重建或逐户验证 |

### 1.1 固定的实体与角色

- `Resident` 是生成式认知与决策单位。
- `Household` 是共享成员、资源、照护责任、承诺和冲突约束对象，不是 household LLM。
- `World` 保存真实物理状态并仲裁行动；居民不能直接读取未观测的 World 真值。
- `Interaction` 负责 `sent → delivered → processed → accepted/rejected`。
- `focal_resident_id` 用于 Carr respondent-sample 的聚合比较。
- `coordinator_id` 用于家庭协调。两个字段概念上分离，即使基线中经常指向同一参考人。
- `decision_capable`、`decision_policy`、`awake` 和 `needs_execution_assistance` 是四个不同字段。
- 成年人的功能限制不会自动把其降为非决策成员；需要执行帮助的成年人仍可以是生成式 Resident。

### 1.2 固定的 Carr 双轨

- Carr-R 只保留为 respondent-conditioned 开发诊断，不再有 untouched test 主张。
- Carr-S 是本文正式的合成家庭与社会过程实验。
- Carr-S 与 Carr respondent 不逐人映射。
- Carr 的 Q9/Q10/Q11/Q13、身份、地址和自由文本永不进入 Carr-S runtime prompt。
- Carr train-only trait 与 Carr 聚合参照来自同一调查，因此正式表述固定为
  `Carr-informed empirical reasonableness`，不是独立外部验证。

---

## 2. 执行总顺序与当前门槛

**用户 2026-08-02 确认的“两天冲刺”优先级**：E2 r7 跑完后立即进入 W4/W5 编码；
E1 v2 预检通过后按统计目标冻结**最小满足样本量**的正式 cohort；E3 保持多模型
（按合同上限 2 个替代模型 × 5 paired seed 做有限预声明复核，不做全矩阵多模型）；
W10 规模实验（100/500/1000）挂起为可选后续；H1 与 E1 并行安排评分者；论文
Results 集中在最后一天。该优先级不改变任何冻结的科学参数、指标或排除规则。

| 顺序 | 工作包 | 当前可做 | 结束标志 |
|---:|---|---|---|
| 0 | 保护并完成 E2 r7 | 正在执行 | 60 格终态与 publication audit 完成 |
| 1 | W1 PUMS donor v2 | 可以 | donor/population v2、官方码本与两层 QA 完成 |
| 2 | W2 Carr trait donor | 可以 | 198 名 train donor、逐值编码、field lineage 与 QA 完成 |
| 3 | W3 complete profiles | 可以 | 全体成员画像、focal/coordinator、trait 匹配与 QA 完成 |
| 4 | W4 Household/World v2 | E2 r7 归档后 | departure-party、车辆、照护和 movement ledger 测试完成 |
| 5 | W5 E1 v2 runner | W1–W4 后 | 信息隔离、动态场景、真实模型前的端到端测试完成 |
| 6 | W6 E1 预检、sizing、正式运行 | W5 后且不与付费任务重叠 | freeze、真实 run、联合不确定性 summary 完成 |
| 7 | W7 E2 正式分析 | r7 完整后 | keyset/hash/终态/配对/作用机会审计和图表完成 |
| 8 | W8 H1 人工评价 | E1 正式轨迹完成后 | 两名独立评分者完成全部正式 packet |
| 9 | W9 prompt/模型稳健性 | E1/E2 正式结果后 | 同 seed 配对敏感性结果完成 |
| 10 | W10 100/500/1000 规模 | 无其他付费任务时 | 三个规模各 3 个系统 seed 完成 |

### W0：E2 r7 保护规则

E2 r7 使用已冻结的 8 户、5 条件、12 seed、DeepSeek thinking-high 协议；
r7 是 r4–r6 因连接/源站错误停止后的完整60格恢复（传输层启用SDK级重试退避，
并按用户提速要求以6-lane并行执行、已完成格确定性复用），
r1–r6 全部只作运行审计并排除。

在 r7 归档前：

- W1–W3 可以新增文件和纯数据测试；
- W4 不修改 `HouseholdCommitment`、`InteractionEngine`、`CarrWorld`、
  `CarrResident` 或 E2 proposal 语义；
- 不启动 E1、H1、prompt、跨模型或规模付费任务；
- 不从 r1/r2/r3/r4/r5/r6 与 r7 拼接任何科学配对。

r7 完成后先保存：配置、代码、prompt、模型注册、数据、60 格原始 summary 和
publication audit 的 SHA-256。W4 采用版本化 v2 接口，E2 历史 artifact 仍由其
冻结 hash 解释。

---

## 3. W1：PUMS whole-household donor v2

### 3.1 修改文件

- 修改 `disastersociety/scripts/build_pums_donors.py`
- 新增 `disastersociety/eventpacks/carr_2018/population/pums_2018_v2_codebook.yaml`
- 修改 `disastersociety/tests/test_datalayer.py`

### 3.2 固定输入字段

`build_pums_donors.py` 增加版本化 schema：

```python
PUMS_SCHEMAS = {
    "v1": {"housing": [...], "person": [...]},
    "v2": {"housing": [...], "person": [...]},
}
```

v2 housing 字段：

```text
SERIALNO PUMA TYPE NP WGTP HINCP ADJINC VEH HHT TEN BLD ACCESS HISPEED
SMARTPHONE NOC NRC HUPAC HUPAOC HUPARC WIF BDSP RMSP
```

v2 person 字段：

```text
SERIALNO SPORDER RELP AGEP PWGTP SEX SCHL ESR WKW WKHP JWTR JWMNP
DIS DEAR DEYE DREM DPHY DOUT DDRS DRAT
```

功能限制的语义固定为：

```text
DEAR hearing difficulty
DEYE vision difficulty
DREM cognitive difficulty
DPHY ambulatory difficulty
DOUT independent-living difficulty
DDRS self-care difficulty
DIS  aggregate disability recode
DRAT veteran service-connected disability rating
```

`DRAT` 单独进入 `veteran_service_connected_rating`，不得参与普通功能限制或
care recipient 的确定。

### 3.3 收入处理

所有 IPF 收入边际、matching band 和 prompt 收入段统一使用：

```python
adjusted_household_income_2018 = HINCP * ADJINC / 1_000_000
```

规则：

- `HINCP` 或 `ADJINC` 缺失时，调整收入为 `null`，不得填 0；
- 负收入保留原值，在最终细分中进入 `<25k`，同时设置 `negative_income=true`；
- 原 `HINCP`、`ADJINC` 和派生公式进入 provenance；
- v1 产物不覆盖，v2 使用新目录。

### 3.4 官方码本

数字代码不得由接手者凭字段名猜测。固定来源为 Census 的
`2014–2018 ACS 5-year PUMS Data Dictionary`：

```text
https://www.census.gov/programs-surveys/acs/microdata/documentation.2018.html
https://www2.census.gov/programs-surveys/acs/tech_docs/pums/data_dict/PUMS_Data_Dictionary_2018.txt
```

实现步骤：

1. 把原始 txt 保存到受控 provenance 目录并记录 SHA-256；
2. 从该字典生成 `pums_2018_v2_codebook.yaml`；
3. codebook 至少覆盖 `TEN/BLD/RELP/SCHL/ESR/WKW/JWTR` 以及所有布尔/失能字段；
4. 明确区分有效类别、`not in universe`、`not applicable` 和缺失；
5. 未知代码直接 fail-fast；
6. `JWTR/JWMNP/WKHP/WKW` 对非就业者保持 `null/not_in_universe`，不得变成不开车、
   通勤 0 分钟或工作 0 小时；
7. `WIF` 解码为 household workers in past 12 months，不得写成互联网字段。

### 3.5 donor 构建与 QA

复用现有 `build_donor_tables()` 和 `prepare_carr_donor_features()`：

1. 用 `SERIALNO` 连接 housing 与全部 person records；
2. 保留 whole-household 成员原子性；
3. 公共表删除 `SERIALNO`；
4. 受限 linkage 保存 donor ID 与原始 `SERIALNO`；
5. 增加逐字段 dtype、缺失和未知代码检查。

`donor_build_qa.json` 至少包含：

```json
{
  "schema_version": "v2",
  "n_households": 4317,
  "n_persons": 9968,
  "np_mismatch_count": 0,
  "duplicate_sporder_count": 0,
  "invalid_reference_person_count": 0,
  "households_without_persons": 0,
  "adjusted_income_changed_fine_bin_count": 0,
  "unknown_code_counts": {},
  "input_sha256": {},
  "codebook_sha256": "",
  "output_sha256": {}
}
```

`adjusted_income_changed_fine_bin_count` 用于审计旧/新收入处理差异，不设置为 0 门槛；
当前只读核查为 722/4,317，正式构建应复现并记录实际值。

### 3.6 运行命令

```bash
cd /Users/linnuo/Documents/agentSimulation/disastersociety
.venv/bin/python scripts/build_pums_donors.py \
  --schema-version v2 \
  --housing-zip eventpacks/carr_2018/raw/census_pums_2018_5yr_ca_housing.csv.zip \
  --person-zip eventpacks/carr_2018/raw/census_pums_2018_5yr_ca_person.csv.zip \
  --puma 8900 \
  --public-dir eventpacks/carr_2018/population/donors_v2 \
  --restricted-dir eventpacks/carr_2018/restricted/pums_linkage_v2

.venv/bin/python scripts/synthesize_carr_population.py \
  --donor-households eventpacks/carr_2018/population/donors_v2/donor_households.csv \
  --donor-persons eventpacks/carr_2018/population/donors_v2/donor_persons.csv \
  --restricted-linkage eventpacks/carr_2018/restricted/pums_linkage_v2/donor_serialno_linkage.csv \
  --acs-marginals eventpacks/carr_2018/population/acs_marginals.csv \
  --target-n 1000 \
  --seed 42 \
  --public-dir eventpacks/carr_2018/population/pilot_seed42_n1000_v2 \
  --restricted-dir eventpacks/carr_2018/restricted/pilot_seed42_n1000_v2
```

### 3.7 完成门槛

- 4,317 户、9,968 人结构数字复现；
- `NP`、`SPORDER`、参考人和 whole-household 连接检查通过；
- 公共输出不含 `SERIALNO`；
- `ADJINC` 和 `DDRS` 存在，`DRAT` 未进入普通功能限制；
- IPF 使用 adjusted income；
- decoder 对全部已出现代码有明确输出，无未知代码；
- 固定 seed 两次构建的规范化 CSV/JSON SHA-256 一致；
- 1000 户人口仍只标记为 `PILOT`，person-level 年龄仍只作未拟合 QA。

---

## 4. W2：Carr train-only household/person trait donors

### 4.1 新增文件

- `disastersociety/scripts/build_carr_e1_trait_donors.py`
- `disastersociety/experiments/carr/protocol/carr_s_e1_v2_field_roles.yaml`
- `disastersociety/experiments/carr/protocol/carr_s_e1_v2_trait_codebook.yaml`
- `disastersociety/tests/test_carr_e1_traits.py`

固定输入路径：

```text
disastersociety/Wong_Carr_Wildfire_Dataset.csv
disastersociety/eventpacks/carr_2018/behavior/evaluation_respondents.csv
disastersociety/experiments/carr/protocol/carr_r_split.csv
```

### 4.2 输入连接

固定连接顺序：

1. `scripts.clean_survey.load_qualtrics()` 读取 Qualtrics 两行表头；
2. `evaluation_respondents.csv` 提供 `evaluation_index ↔ respondent_id`；
3. `carr_r_split.csv` 提供 `evaluation_index ↔ split`；
4. 只选择 `split == train` 的 198 人；
5. `respondent_id ↔ ResponseId` 一对一连接；
6. 建立稳定 `trait_donor_id`，随后从公开输出删除原连接 ID。

连接必须断言：198 行、198 个唯一 evaluation index、198 个唯一 respondent、无未匹配。

### 4.3 raw 字段角色合同

YAML 必须列出展开后的字段名，禁止使用 `Q29.3_1..9` 这类不会自动展开的字符串。

```yaml
raw_matching_inputs:
  - Q32.2
  - Q32.8_1
  - Q32.11
  - Q32.13

raw_household_trait_inputs:
  - Q32.9
  - Q32.10

raw_person_trait_inputs:
  - Q29.3_1
  - Q29.3_2
  - Q29.3_3
  - Q29.3_4
  - Q29.3_5
  - Q29.3_6
  - Q29.3_7
  - Q29.3_8
  - Q29.3_9
  - Q29.4_1
  - Q29.4_2
  - Q29.4_3
  - Q29.4_4
  - Q29.4_5
  - Q29.4_6
  - Q29.4_7
  - Q29.4_8
  - Q29.4_9
  - Q34.2
  - Q34.4
  - Q35.3_1
  - Q35.3_2
  - Q35.3_3
  - Q35.3_4
  - Q35.3_5
  - Q35.3_6
  - Q35.3_7
  - Q35.3_8
  - Q35.3_9
  - Q35.3_10
  - Q35.3_11
  - Q35.3_12
  - Q35.4
  - Q35.6_1
  - Q35.6_2
  - Q35.6_3
  - Q35.6_4
  - Q35.6_5

raw_evaluation_only_prefixes:
  - Q9
  - Q10
  - Q11
  - Q13

raw_forbidden_classes:
  - identity
  - address
  - geolocation_free_text
  - open_response_text
```

构建器记录每个派生字段的 raw lineage，并断言实际读取列只来自三个 allowlist。
只扫描最终列名不算 leakage 检查。

### 4.4 固定逐值编码

缺失、空白和 `Prefer not to answer` 一律编码为 `null`，不得中位数填补。

```yaml
Q29.3_worry:
  Not at all worried: 0.00
  Slightly worried: 0.25
  Moderately worried: 0.50
  Very worried: 0.75
  Extremely worried: 1.00

Q29.4_likelihood:
  Extremely unlikely: 0.00
  Somewhat unlikely: 0.25
  Neither likely nor unlikely: 0.50
  Somewhat likely: 0.75
  Extremely likely: 1.00

Q32.9_Q32.10:
  No: false
  Yes: true

Q35.3_trustworthiness:
  Almost never trustworthy: 0.00
  Not usually trustworthy: 0.25
  Sometimes trustworthy: 0.50
  Generally trustworthy: 0.75
  Almost always trustworthy: 1.00

Q35.4_general_trust:
  "We can never be too cautious in our dealings with other people.": 0.00
  "It is possible to trust most people.": 1.00

Q35.6_helping:
  "1 (not at all true)": 0.00
  "2": 0.25
  "3": 0.50
  "4": 0.75
  "5 (very true)": 1.00
```

`Q34.2` 同时输出：

```text
prior_evacuation_count_capped: 0,1,2,3,4,5,6
prior_evacuation_count_topcoded: true only for "More than 5"
```

`Q34.4` 输出 `decision_participation_propensity`：

```text
Another person is the sole decision maker                                  0.00
I provide input into the decisions, but I am not the primary decision maker 0.25
I share equally in making decisions with another household member(s)        0.50
I am the primary decision maker with input from another household member    0.75
I am the sole decision maker                                                 1.00
Prefer not to answer                                                         null
```

该值只影响居民参与协调的倾向，不用于选择合成家庭 coordinator。

### 4.5 Q29 理论因子

因子方向保持现有方法决定，按有效题等权平均：

```text
hazard_worry          = Q29.3_1, Q29.3_2                     minimum valid 1
evacuation_friction   = Q29.3_3 ... Q29.3_9                 minimum valid 4
home_person_threat    = Q29.4_1, Q29.4_2, Q29.4_4, Q29.4_5 minimum valid 2
infrastructure_rescue = Q29.4_3, Q29.4_7, Q29.4_8           minimum valid 2
property_security     = Q29.4_6                              minimum valid 1
work_obligation       = Q29.4_9                              minimum valid 1
```

低于 minimum valid 时整个因子为 `null`。Q29 是火灾后回忆的灾前信念，codebook
和论文必须保留 `retrospective_pre_event_report` 来源标签。

Q35.3 的 12 个对象特定 trust item 保留逐项值和题目文本映射；没有题目文本映射的
item 不得凭序号命名为 family/neighbor/government。`helping_tendency` 只在 Q35.6
至少 3/5 项有效时计算均值。

### 4.6 输出拆成家庭与个人两类 donor

```text
restricted/e1_traits/carr_household_trait_donors_v1.csv
restricted/e1_traits/carr_person_trait_donors_v1.csv
behavior/carr_e1_trait_codebook_v1.json
behavior/carr_e1_trait_qa_v1.json
```

- household donor 只含 Q32.9/Q32.10 共享属性及 household matching bands；
- person donor 只含 Q29、Q34.2、Q34.4、Q35.3、Q35.4、Q35.6 和 person matching bands；
- 两个受限表可以共享同一 198 人来源，但使用不同 `trait_donor_id` 命名空间；
- 公共 codebook/QA 不含 respondent ID。

QA 至少报告：每个原始类别计数、编码后分布、缺失率、每个因子有效题数、
raw-lineage hash、train split hash 和输出 hash。

运行命令：

```bash
cd /Users/linnuo/Documents/agentSimulation/disastersociety
.venv/bin/python scripts/build_carr_e1_trait_donors.py \
  --raw-survey Wong_Carr_Wildfire_Dataset.csv \
  --evaluation eventpacks/carr_2018/behavior/evaluation_respondents.csv \
  --split experiments/carr/protocol/carr_r_split.csv \
  --field-roles experiments/carr/protocol/carr_s_e1_v2_field_roles.yaml \
  --trait-codebook experiments/carr/protocol/carr_s_e1_v2_trait_codebook.yaml \
  --restricted-dir eventpacks/carr_2018/restricted/e1_traits \
  --public-dir eventpacks/carr_2018/behavior

.venv/bin/pytest -q tests/test_carr_e1_traits.py
```

### 4.7 完成门槛

- 198 名 train respondents 一对一连接；
- 上述所有 literal value 有测试；未知字面值 fail-fast；
- Q9/Q10/Q11/Q13、身份、地址和自由文本没有被读取；
- household/private trait 分开输出；
- Q34.4 未被用作 coordinator 真值；
- 固定输入和 seed 两次输出逐字节一致。

---

## 5. W3：完整 household/member empirical profiles

### 5.1 新增文件

- `disastersociety/ds/population/e1_profiles.py`
- `disastersociety/scripts/build_carr_e1_profiles.py`
- `disastersociety/tests/test_e1_profiles.py`

### 5.2 数据对象

```python
@dataclass(frozen=True)
class MemberEmpiricalProfile:
    resident_id: str
    household_id: str
    age: int
    relationship: str
    pums_static: dict[str, Any]
    functional_limitations: dict[str, bool | None]
    veteran_service_connected_rating: int | None
    decision_capable: bool
    decision_policy: Literal["generative", "rule", "dependent"]
    needs_execution_assistance: bool
    latent_traits: dict[str, float | bool | int | None]
    source_by_field: dict[str, str]

@dataclass(frozen=True)
class HouseholdEmpiricalProfile:
    household_id: str
    shared_attributes: dict[str, Any]
    member_profiles: tuple[MemberEmpiricalProfile, ...]
    decision_resident_ids: tuple[str, ...]
    nondecision_member_ids: tuple[str, ...]
    care_recipient_ids: tuple[str, ...]
    focal_resident_id: str
    coordinator_id: str
    source_by_field: dict[str, str]

@dataclass(frozen=True)
class ProfileAssemblyResult:
    households: tuple[HouseholdEmpiricalProfile, ...]
    qa: dict[str, Any]
    restricted_linkage: pd.DataFrame
```

`member_profiles` 必须包括 PUMS whole-household 中的全部成员，不只包括调用 LLM
的成年人。

### 5.3 成员角色算法

```text
adult := AGEP >= 18
child/non-adult := AGEP < 18
decision_capable := adult by transparent baseline
decision_policy := generative for every adult in the formal 1–2 adult E1 cohort
non-adult decision_policy := dependent
awake := runtime field, profile 中不预先固定
```

`needs_execution_assistance` 与 `decision_capable` 独立：

- 非成年人默认需要同行照护；
- `DPHY/DDRS/DOUT` 为真时标记为执行帮助候选；
- 成人即使需要执行帮助仍保留 generative Resident；
- `DREM` 不自动取消决策资格，只进入敏感性与人工评价说明；
- `DRAT` 不触发执行帮助。

运行时使用独立 `CareRequirement` 对象引用任何成员，不再要求“决策成员”和“需要
帮助成员”两个集合互斥。

### 5.4 focal 与 coordinator

基线规则固定为：

1. `coordinator_id`：成年 `RELP == 0` reference person；如 reference person 非成年或
   缺失，选择成年成员中最小 `SPORDER`；再并列按 resident ID。
2. `focal_resident_id`：同样从成年 reference person 开始，用于代表 household 中
   接受 Carr-style respondent exposure 的焦点居民。
3. 两个字段分别写入 artifact，任何代码不得用 `role == coordinator` 隐式替代 focal。
4. `Q34.4` 只进入 `decision_participation_propensity`，不改变上述基线。
5. 预声明敏感性可以使用 `oldest adult focal`，但不得按结果选择 focal。

### 5.5 household 与 person trait 匹配

粗匹配段由 W1/W2 共用同一函数 `to_e1_matching_bands()`：

```text
age_band:       18-24 / 25-34 / 35-44 / 45-54 / 55-64 / 65-74 / 75-84 / 85+
household_band: 1 / 2 / 3-4 / 5+
vehicle_band:   0 / 1 / 2 / 3+
income_band:    <25k / 25-49k / 50-99k / 100k+ / missing
```

household trait donor 层级：

```text
H0 household + vehicle + income
H1 household + vehicle
H2 household
H3 all train household donors
```

person trait donor 层级：

```text
P0 age + household + vehicle + income
P1 age + household + vehicle
P2 age + household
P3 age
P4 all train person donors
```

候选先按 trait donor ID 排序，再使用：

```python
stream_seed(profile_seed, "e1_household_trait_match", entity_id=household_id)
stream_seed(profile_seed, "e1_person_trait_match", entity_id=resident_id)
```

同户多名成人在候选足够时无放回抽取 person trait donor；候选不足时才允许重复，
并在 QA 记录原因。不要把不同 respondent donor 误写成现实中共同观察到的家庭成员。

### 5.6 逐字段 provenance

每个公开字段使用下列来源之一：

```text
pums_household_observed
pums_person_observed
carr_train_household_hotdeck_retrospective
carr_train_person_hotdeck_retrospective
derived
scenario_control
runtime_observation
```

受限 linkage 分别保存：

```text
household_id → PUMS donor_id → household_trait_donor_id → match_level
resident_id  → PUMS person donor_id → person_trait_donor_id → match_level
```

公开 profile 和 prompt 不含任何原始 `SERIALNO`、respondent ID 或 trait donor ID。

### 5.7 完成门槛

- 每户 profile 覆盖全部 PUMS 成员；
- 每户恰有一个 focal 和一个 coordinator；
- 每个成年决策成员有独立 inbox/memory 的初始化身份和独立 person trait；
- 共享宠物/牲畜来自 household trait donor，不来自 coordinator 的 private donor；
- decision capability 与 execution assistance 可同时为真；
- QA 报告 H0–H3、P0–P4、同户 donor 重复、donor 使用集中度、字段缺失和 provenance；
- 固定 seed 的规范化 JSONL 两次 SHA-256 一致；
- 正确方法名称固定为：
  `PUMS whole-household static structure + Carr-informed independently imputed household/person traits`。

运行命令：

```bash
cd /Users/linnuo/Documents/agentSimulation/disastersociety
.venv/bin/python scripts/build_carr_e1_profiles.py \
  --households eventpacks/carr_2018/population/pilot_seed42_n1000_v2/synthetic_households.csv \
  --persons eventpacks/carr_2018/population/pilot_seed42_n1000_v2/synthetic_persons.csv \
  --household-traits eventpacks/carr_2018/restricted/e1_traits/carr_household_trait_donors_v1.csv \
  --person-traits eventpacks/carr_2018/restricted/e1_traits/carr_person_trait_donors_v1.csv \
  --profile-seed 4201 \
  --public-dir eventpacks/carr_2018/population/e1_profiles_v2_seed4201 \
  --restricted-dir eventpacks/carr_2018/restricted/e1_profiles_v2_seed4201

.venv/bin/pytest -q tests/test_e1_profiles.py
```

---

## 6. W4：版本化家庭执行与 departure-party 合同

W4 修改共享核心，必须在 E2 r7 完整归档后开始。E1 v2 使用版本化接口，不能通过
修改旧空字段含义破坏 E2。

### 6.1 修改文件

- `disastersociety/ds/households/state.py`
- `disastersociety/ds/interaction/engine.py`
- `disastersociety/ds/world/carr.py`
- `disastersociety/ds/agents/decide.py`
- 修改 `disastersociety/tests/test_households.py`
- 新增 `disastersociety/tests/test_carr_interaction_v2.py`
- 新增 `disastersociety/tests/test_carr_world_v2.py`
- 修改 `disastersociety/tests/test_carr_pilot.py` 保留 E2 regression

### 6.2 新对象

```python
@dataclass(frozen=True)
class DepartureParty:
    traveler_ids: frozenset[str]
    accompanying_member_ids: frozenset[str]
    caregiver_by_member: tuple[tuple[str, str], ...]
    vehicle_id: str
    route_id: str
    depart_step: int

@dataclass(frozen=True)
class HouseholdCommitmentV2:
    id: str
    protocol_version: Literal["e1_party_v2"]
    party: DepartureParty
    accepted_by: frozenset[str]
    created_step: int
    status: Literal["accepted", "cancelled", "executed", "rejected"]
    supersedes_id: str | None

@dataclass(frozen=True)
class CommitmentAcceptanceResult:
    accepted: bool
    commitment_id: str | None
    reason_code: str | None

@dataclass(frozen=True)
class CareRequirement:
    member_id: str
    assistance_type: Literal["minor", "mobility", "self_care", "independent_living"]
    caregiver_id: str | None

@dataclass(frozen=True)
class HouseholdDepartureRecord:
    household_id: str
    party_id: str
    commitment_id: str | None
    step: int
    traveler_ids: tuple[str, ...]
    accompanying_member_ids: tuple[str, ...]
    caregiver_by_member: tuple[tuple[str, str], ...]
    vehicle_id: str
    route_id: str
    coordinated: bool
    outcome: Literal["executed", "rejected"]
    reason_code: str | None
```

旧 `HouseholdCommitment` 继续服务冻结的 E2 语义；E1 proposal 必须带
`protocol_version: e1_party_v2` 才进入严格 party 合同。不得用默认空集合同时表示
“legacy 未指定”和“明确没有同行成员”。

### 6.3 proposal 与接受检查

E1 proposal payload：

```json
{
  "protocol_version": "e1_party_v2",
  "route_id": "route_primary",
  "vehicle_id": "household_1_vehicle_1",
  "depart_step": 7,
  "traveler_ids": ["adult_1"],
  "accompanying_member_ids": ["child_1"],
  "caregiver_by_member": {"child_1": "adult_1"}
}
```

`try_accept_commitment()` 返回结构化接受/拒绝，普通资源冲突不得抛成 run-level
异常。接受时按顺序检查：

1. sender、recipient、traveler、accompanying member 都属于同户；
2. `traveler_ids` 非空；
3. party 中所有 decision-capable traveler 都在 `accepted_by`；
4. 每个需要帮助的同行成员恰有一个 caregiver；
5. caregiver 属于 traveler；
6. 车辆属于该户、当前位置与 party 相同、容量足够；
7. route 非空，depart step 不早于 recipient 的下一处理阶段；
8. 同一成员不能在时间重叠的两个 active party 中；
9. 在未实现车辆返程前，一辆车只能属于一个尚未完成的 departure party；
10. 修订保留 cancelled/supersedes 历史。

拒绝必须写 receipt、reason code 和下一步 execution/coordination feedback。

### 6.4 World 执行语义

Engine 主循环保持“所有醒来居民先产生 intent，World 再集中仲裁”。E1 v2 固定：

- 到期 party 的所有 decision-capable traveler 在同一 tick 被唤醒；
- 每名 traveler 必须独立提交与 commitment 完全一致的执行 intent；
- 缺少任一 traveler intent 时整个 party 拒绝或延期，World 不偷偷移动未决策成员；
- 同户同一步可执行多个成员、车辆互不重叠的 party；
- 每个输入 `IntentEnvelope` 恰好获得一个 keyed outcome；
- dependent/nondecision member 不产生 LLM intent，但由已验证 party 移动；
- 执行后统一更新 Resident、care recipient 和 Vehicle 的 location；
- 车辆到达 `controlled_safe_zone` 后不能被 home 中后续 party 复用；
- 每次成功或拒绝写 `HouseholdDepartureRecord`。

### 6.5 不在 E1 v2 中假装实现的能力

E1 v2 不实现跨家庭车辆搭载。零车辆家庭可以发送帮助请求并记录响应，但没有结构化
external transport/ride-share commitment 时，World 不执行邻居车辆搭载。

因此：

- 零车辆家庭进入 raw ACS-cohort 过程结果；
- Carr-standardized 主比较因 Carr 零车辆组 n=0 而不对其外推；
- 求助、响应和未满足帮助可报告；
- 不声称邻里搭载机制已经完成。

### 6.6 家庭指标

从 household departure ledger 计算：

```text
complete_safe_household_departure_rate
coordinated_household_rate
split_departure_household_rate
member_departure_time_gap
care_recipient_left_behind_count
vehicle_conflict_count
capacity_rejection_count
caregiver_violation_count
```

`coordinated_household_rate` 的分子是满足整户协调定义的 household 数，不是 movement
数，因此不得超过 1。

### 6.7 必须通过的端到端测试

1. 两成人、一名儿童、一辆五座车共同出发；
2. 两成人、四名同行成员、一辆五座车因容量不足拒绝；
3. 两辆车、两个 party 同一步成功执行；
4. 两辆车分批出发后整户安全；
5. 同一 care recipient 被两个 party 重复认领时拒绝；
6. caregiver 不在 party 中时拒绝；
7. party 缺一名决策 traveler 的 intent 时不移动；
8. 车辆离开后不能被留守成员复用；
9. 每个 envelope 恰有一个 outcome；
10. 分批家庭协调比例不超过 1；
11. 普通冲突产生 rejected receipt，不使 run `ABORTED`；
12. legacy E2 两成人、一辆车、共同承诺的原测试和指标保持不变。

测试命令：

```bash
cd /Users/linnuo/Documents/agentSimulation/disastersociety
.venv/bin/pytest -q \
  tests/test_households.py \
  tests/test_carr_interaction_v2.py \
  tests/test_carr_world_v2.py \
  tests/test_carr_pilot.py
```

---

## 7. W5：E1 v2 私有认知、动态事件与 runner

### 7.1 新增文件

- `disastersociety/ds/agents/carr_empirical_v2.py`
- `disastersociety/ds/interaction/carr_empirical_v2.py`
- `disastersociety/ds/world/carr_empirical_v2.py`
- `disastersociety/experiments/carr/empirical_v2_runner.py`
- `disastersociety/experiments/carr/configs/carr_s_e1_empirical_v2_preflight.yaml`
- `disastersociety/scripts/run_carr_e1_v2_preflight.py`
- `disastersociety/scripts/summarize_carr_e1_v2.py`
- `disastersociety/tests/test_carr_e1_v2.py`

### 7.2 runner 构建顺序

```text
load v2 synthetic whole-household population
→ select whole households without splitting members
→ assemble complete profiles
→ build Household/Vehicle/CareRequirement
→ build one Resident per decision adult
→ build controlled social graph
→ assign focal/coordinator and scenario
→ build private perceived route states
→ build CarrEmpiricalWorldV2
→ build CarrEmpiricalInteractionEngineV2
→ build timed EventSource
→ run common Engine
→ persist all ledgers and summary
```

### 7.3 官方信息 receipt

```python
@dataclass(frozen=True)
class OfficialInformationReceipt:
    receipt_id: str
    resident_id: str
    source_event_id: str
    severity: Literal["voluntary", "mandatory"]
    channel: str
    issued_step: int
    delivered_step: int
    processed_step: int | None
```

warning delivery 必须先按居民过滤：

```python
covered = [event for event in warning_events if event.recipient_covers(agent)]
```

只能从 `covered` 构建该居民的 inbox。每条 receipt 保留 event ID、severity、issued、
delivered、processed、channel 和 provenance。

社会转发官方信息时，payload 必须引用居民已经拥有的 `source_event_id` 或
`source_message_id`。没有可验证来源的“已经强制撤离”只能标为 unverified rumor，
不能计作官方 receipt。`order-to-departure` 主指标只使用直接官方 receipt。

### 7.3.1 Household、vehicle 与初始照护构建

- 每户按 PUMS `VEH` 创建对应数量的私家车；`VEH == 0` 不创建车辆；
- PUMS 最高类别按其公开 codebook 的最低可执行数量创建，并保留 top-code 标签；
- 首篇论文所有私家车容量固定为 5，属于 scenario control，不再使用
  `max(5, household_size)`；
- 车辆 ID 为 `{household_id}:vehicle:{1-based-index}`，初始位置为
  `home:{household_id}`；
- 每个 care recipient 的初始 caregiver 优先为 coordinator，但 caregiver 不能是
  recipient 自己；如 coordinator 不可用，按成年 decision resident 的 `SPORDER`
  选择第一名其他成员；没有可用 caregiver 时为 `null` 并记录 unmet care；
- 初始 caregiver 是明确的模拟基线，不是 PUMS 或 Carr 观测真值，可在真实消息与
  v2 commitment 中转移。

### 7.4 私有认知与可见性

真实 World 和居民认知分离：

```text
World.route_state                 true physical state
Resident.perceived_routes         private belief state
Resident.inbox                    only delivered items
Resident.memory                   only processed/retained items
Household.shared_reservations     observable accepted resource reservations
Resident.my_commitments           commitments accepted by or involving self
```

居民只能在以下事件后更新 `perceived_routes`：

- 收到并处理有来源的道路信息；
- 自己的路线执行请求被 World 拒绝；
- 受控的本地观察事件被投递。

prompt 不得读取 `world.route_snapshot()`。非 party 成员看不到其他成员的私有计划或
完整 commitment；只能看到共享资源已被预约这一可观察结果，或者通过真实消息得知。

### 7.5 固定 prompt schema

```json
{
  "resident_profile": {
    "static": {},
    "functional_limitations": {},
    "needs_execution_assistance": false,
    "latent_traits": {}
  },
  "household_profile": {
    "members": [],
    "vehicles": [],
    "housing": {},
    "pets": false,
    "livestock": false
  },
  "observed_now": {
    "inbox": [],
    "hazard_distance_m": 0,
    "perceived_routes": {},
    "shared_resource_reservations": []
  },
  "private_process": {
    "memories": [],
    "current_plan": null,
    "my_accepted_commitments": [],
    "recent_execution_feedback": []
  }
}
```

静态画像可以每次重复传入。动态区只来自本人的 receipt、inbox、memory、plan、
commitment、observable reservation 和 execution feedback。

### 7.6 动态命令情境

不再只用 mandatory/voluntary/none 三类。正式情境支持：

```python
OrderSequence = Literal[
    "none",
    "voluntary_only",
    "mandatory_only",
    "voluntary_then_mandatory",
]
```

构建 `order_sequence_calibration.json`：

- 从 330 名 Q9.1 eligible respondent 构建；
- 主分析在 order calibration 中排除 15 条命令矛盾记录；
- 敏感性采用肯定命令优先；
- 只使用 Q5/Q6/Q7 的命令类型与时间信息，不按 Q9.1 outcome 条件分配；
- 这是 calibration，不再作为独立渠道验证。

受控 schedule 固定为：

```text
none                         no official event
voluntary_only               voluntary at step 3
mandatory_only               mandatory at step 7
voluntary_then_mandatory     voluntary at step 3, mandatory at step 7
```

每步 30 分钟，共 25 步，因此最晚命令后仍有 9 小时观察窗。每个正式 cohort 使用
Hamilton largest-remainder 按 calibration proportion 分配固定配额，再按命名随机流
`e1_order_assignment` 对 household 排序。assignment 不依赖 trait、计划或结果。

每户直接官方 order 投递给 `focal_resident_id`，投递概率为 1，因为 calibration
对象是 respondent 报告的实际 receipt；其他家庭成员只有通过家庭/网络消息才能得知。

### 7.7 hazard 与道路情境

首个正式 E1 不把 final perimeter 写成危险时序。所有家庭使用相同受控 hazard 形状，
只加入明确的 household offset：

```python
u = named_uniform(run_seed, "e1_hazard_offset", entity_id=household_id)
hazard_offset_m = -250.0 + 500.0 * u
distance(step, household) = max(
    0.0,
    initial_distance_m + hazard_offset_m - approach_per_step_m * step,
)
```

`initial_distance_m`、`approach_per_step_m`、`[-250, 250]` 范围和 stream name 写入
config/freeze/provenance。offset 与 order assignment 使用不同随机流。该 offset 是
受控异质性，不称 tract 历史危险。

首个 formal config 固定：

```text
initial_distance_m = 9000
approach_per_step_m = 250
primary route = tiger_primary
alternate route = tiger_alternate
primary route controlled closure step = 9
alternate route remains open
route capacity = 10 vehicles per step per route
```

step-9 closure 是所有家庭共享的受控扰动，不是 Carr 历史道路关闭。

每个 household 的 member、care recipient 和 vehicle 初始位置统一为
`home:{household_id}`。World 中的真实道路在所有条件照常关闭；Resident 只通过
第 7.4 节的观察路径更新私有认知。

### 7.8 social graph

- household 关系是强边，但仍走真实消息生命周期；
- 复用 `ds.population.networks.build_social_graph()`；
- 固定参数为 `radius_m=1500`、`k_neighbors=6`、`k_friends=4`、
  `rewire_p=0.1`，seed 使用 seed tuple 的 `network_delivery_seed`；
- realized mean degree 是输出，不把参数 `k_neighbors=6` 误写成实际平均度恰为 6；
- graph 只依赖 synthetic geography/household，不依赖 Carr outcome 或 latent trait；
- graph manifest 保存节点数、边数、度分布、连通分量、算法参数和 hash；
- 第一版可以记录求助和响应，但不执行跨家庭 ride sharing。

### 7.9 必须持久化的 ledgers

每个 run 至少输出：

```text
run_summary.json
household_profiles.jsonl
member_profiles.jsonl
resident_state_timeline.jsonl
official_receipts.jsonl
message_ledger.jsonl
perception_updates.jsonl
commitment_ledger.jsonl
execution_ledger.jsonl
household_departure_ledger.jsonl
decision_records.jsonl
gateway_calls.jsonl
provenance.json
```

所有 ledgers 使用 stable IDs 互相连接；不得依靠自由文本反推事件关系。

### 7.10 必须通过的 E1 v2 测试

1. 同一步 A 户 mandatory、B 户 voluntary，消息不串户；
2. `none` 户没有 official receipt；
3. A 户 warning 不进入 B 户 inbox/memory；
4. 未送达/未尝试前，道路关闭不进入 resident perception；
5. 执行拒绝后 perception/last failure 在下一步可见；
6. 非 party 成员看不到其他成员私有 commitment；
7. household DM 和 community 使用不同送达参数；
8. 转发官方信息必须有有效 source lineage；
9. focal 与 coordinator 分别写入 summary；
10. 所有 profile/ledger 公开输出无 respondent/trait donor/`SERIALNO`；
11. 同 seed 两次离线接线的规范化 ledger hash 一致；
12. legacy E2 回归测试全部通过。

---

## 8. W6：E1 真实 DeepSeek 预检、sizing 与正式实验

### 8.1 E1 的两个报告总体

E1 同时保留两个结果层，不能混为一个总体：

1. **Raw ACS/PUMS cohort process results**：描述合成家庭的资源、协调和群体过程；
2. **Carr-standardized focal results**：只用于 Carr respondent-sample 经验参照。

Carr-standardized 分析对模拟 focal residents 按以下四组边际 raking：

```text
age_band
household_band
vehicle_band
income_band
```

目标边际来自 330 名 Q9.1 eligible Carr respondent。算法：

- 只使用 Carr 和模拟共同支持的类别；
- Carr 中目标比例为 0 的类别在 standardized 分析中权重为 0，但保留 raw 结果；
- 每次 formal cohort 在运行前仅按 covariates 检查每个正目标类别是否存在；
- 若缺类别，从 50 户增加到 100 户，不查看模型结果；
- iterative proportional fitting 收敛阈值 `1e-8`，最多 1,000 轮；
- 权重上限为中位正权重的 10 倍；截断量和加权 ESS 必须报告；
- 无法收敛时该 run 的 standardized result 为 unavailable，不能用 raw 值替代。

这一步使主比较对应 Carr respondent-sample composition，不把 ACS cohort 的原始撤离率
直接与 Carr 0.8879 相减。

### 8.2 预检

预检只检查真实后端与时间链，不估计正式方差：

```text
20 whole households
2 new development seeds
1–2 decision adults per household
full system only
packy-deepseek-v4-flash
thinking-high
25 × 30-minute steps
all four order sequences represented
no overlap with E2 or other paid tasks
```

预检通过条件：

- 2/2 run `VALID`；
- `n_failed == 0`，fallback 最终比例 ≤1%；
- order receipt、message、perception、commitment、execution 时间均单调合法；
- 无跨户 warning、World route leakage、无 outcome/PII 字段；
- 每个 intent 有 outcome；
- summary 中 raw 与 standardized 指标均能生成或给出结构化 unavailable 原因。

预检结果只标 `PILOT_PREFLIGHT`，不进入正式效果表。

### 8.3 正式 cohort 与 seed tuple

正式起始 cohort 为 50 户，每个 run 使用一个完整 seed tuple：

```text
cohort_seed
profile_seed
order_assignment_seed
hazard_seed
warning_delivery_seed
network_delivery_seed
arbitration_seed
llm_seed
```

freeze 脚本从一个 master seed 确定性生成 tuple，排除所有 E1 开发 seed、E2 seed 和
历史 pilot seed。seed tuple 逐项写入 freeze，不只记录一个模糊 run seed。

### 8.4 sizing 阶段

两个 preflight seed 不用于 sizing。另设 5 个未用于开发的真实 sizing seed，配置与
正式 E1 完全相同；sample-size 决定时只读取预声明指标的 run-level SD，不读取均值、
方向或 Carr gap 好坏。

用于 sizing 的比例尺度主指标固定为：

```text
Carr-standardized focal evacuation rate
order-to-departure CDF MAE on the 0.5/1/2/3/4/5-hour grid
complete safe household departure rate
care-recipient-left-behind rate
```

对每个指标的 5-seed SD 计算单侧 95% 标准差上界：

```python
sigma_upper = s * sqrt((n0 - 1) / chi2.ppf(0.05, n0 - 1))
required_R = ceil((sigma_upper / 0.03) ** 2)
target_R = max(8, max(required_R_across_four_metrics))
formal_R = min(20, target_R)
precision_target_met = target_R <= 20
```

预算上限为 20 个总 seed。如果 `required_R > 20`，冻结 20 个并在结果中明确写
“预算上限下未达到 MCSE 0.03 目标”，不能静默截断后宣称精度达标。

5 个 sizing seed 在以下条件全部满足时可计入正式估计：配置、prompt、代码、数据和
指标 hash 与 formal freeze 完全一致；样本量决定未读取均值/方向；run 均通过正式
有效性门槛。否则它们只保留为 sizing pilot。

任一 sizing 指标因 eligible denominator 为 0 而不可计算时，先把 cohort 从 50 户
增加到 100 户并以新 run ID 重跑全部 5 个 sizing seed；不得只重跑缺失指标的 seed。
若 100 户仍不可计算，该指标从正式效果估计中标为 `UNAVAILABLE_BY_DESIGN`，但不能
换成一个结果更好的新指标。

### 8.5 E1 正式指标

#### Carr-standardized focal 指标

```text
weighted focal evacuation rate and absolute gap to Carr reference
conditional order-to-departure CDF at 0.5/1/2/3/4/5 hours
CDF mean absolute error
age 65+ signed-gap error
household size 3+ signed-gap error
low-income signed-gap error
```

order-to-departure CDF 只纳入直接收到 official receipt 且最终撤离的 focal resident，
使用首次直接 receipt。模拟在最晚命令后有至少 5 小时完整观察窗。未撤离者由撤离率
指标处理，不混入 conditional departure-time CDF。

Carr 零车辆组 n=0，继续标记不可估计，不新增结果导向的替代对比。

#### Household/network/process 指标

```text
complete safe household departure rate
coordinated household rate
split-departure household rate
care recipient left behind
vehicle/capacity/caregiver rejection rates
sent → delivered → processed → accepted/rejected funnel
help request and response rates
execution rejection → later plan revision rate
evacuation before/after first direct official receipt
```

#### System 指标

```text
VALID / INVALID / ABORTED
logical decisions
n_ok / n_cache / n_failed / n_fallback
prompt/completion tokens
estimated cost
run wall clock
```

### 8.6 不确定性

- 模拟结果以独立 run 为重复单位，报告 mean、SD、MCSE 和 95% t interval；
- Carr 撤离比例报告 Wilson interval；Carr subgroup/time metrics 使用冻结的 bootstrap；
- simulation-minus-reference 运行 20,000 次分层 bootstrap：重采样 Carr respondents，
  同时重采样 formal runs，并重新计算对应差值；
- resident/household 行不能直接当独立重复；明细模型必须对 run/household 聚类；
- 不用“点估计接近”代替区间，也不声明统计等价，除非另有预声明 equivalence margin。

### 8.7 freeze 与运行命令

```bash
cd /Users/linnuo/Documents/agentSimulation/disastersociety

.venv/bin/pytest -q \
  tests/test_datalayer.py \
  tests/test_carr_e1_traits.py \
  tests/test_e1_profiles.py \
  tests/test_carr_e1_v2.py

.venv/bin/python scripts/freeze_carr_e1_v2_preflight.py
.venv/bin/python scripts/run_carr_e1_v2_preflight.py \
  --config experiments/carr/configs/carr_s_e1_empirical_v2_preflight.yaml
.venv/bin/python scripts/summarize_carr_e1_v2.py \
  --config experiments/carr/configs/carr_s_e1_empirical_v2_preflight.yaml

.venv/bin/python scripts/freeze_carr_e1_v2_sizing.py
.venv/bin/python scripts/run_carr_e1_v2_sizing.py
.venv/bin/python scripts/freeze_carr_e1_v2_formal.py
.venv/bin/python scripts/run_carr_e1_v2_formal.py
.venv/bin/python scripts/summarize_carr_e1_v2_formal.py
```

每个 freeze 记录配置、seed tuple、runner、Resident、profile assembler、World、
Interaction、prompt、模型注册、data/codebook QA、测试文件和分析脚本 SHA-256。

---

## 9. W7：E2 r7 publication audit 与正式结论规则

### 9.1 输入

E2 r7 预期 keyset 为：

```text
12 frozen seeds ×
{full, full_minus_memory, full_minus_feedback,
 full_minus_planning, full_minus_interaction}
= 60 unique cells
```

### 9.2 publication audit

保留冻结 summarizer，不用结果导向修改它；新增
`scripts/audit_carr_e2_v8_r5_publication.py`，检查：

1. 实际 keyset 与 freeze 中的 12×5 keyset 完全一致；
2. 每 seed 恰有五个唯一 condition；
3. terminal summary、metrics、provenance 的 seed/condition/run ID 一致；
4. freeze/config/prompt/code/model/data hash 一致；
5. 每格终态、失败、fallback、token、成本和墙钟齐全；
6. 每个模块的有效配对数和全部排除原因；
7. 每个机制的作用机会分母；
8. 所有 60 格均 `VALID` 时状态为 `COMPLETE_VALID`；
9. 存在 `INVALID` 但仍有可分析配对时为 `COMPLETE_WITH_EXCLUSIONS`；
10. 缺格或关键 hash 不一致时为 `NOT_READY_FOR_CLAIM`。

不得只因“目录里有 60 个 key”就写 ready。

### 9.3 统计输出

每个模块输出：

```text
paired seed-level values
full-minus-drop mean
SD
MCSE
frozen 95% t interval
positive-direction seed count / valid pair count
opportunity numerator / denominator
manipulation check
predeclared downstream outcomes
failure/fallback/tokens/cost/wall clock
```

### 9.4 模块主张规则

不做事后换检验。正式解释固定为：

- manipulation check 的 95% interval 在预声明方向上排除 0，且至少 75% 有效 seed
  同向：支持“开关改变了目标过程”；
- 对应下游结果也满足同一规则：支持“该过程变化伴随预声明的行为后果”；
- manipulation check 支持、下游 interval 跨 0：只写“改变了内部过程，下游后果
  未确定”；
- 作用机会分母为 0 或过低：写“缺少作用机会”，不解释为模块无效；
- 两者都不稳定：该模块主张不受支持；
- 不使用“显著”一词时不追加结果导向 p 值；如附录报告四项 p 值，使用 Holm 校正。

每个 drop-one 仍只估计完整系统背景下的条件移除效应，不声称识别全部模块交互。

### 9.5 运行命令与产物

```bash
cd /Users/linnuo/Documents/agentSimulation/disastersociety
.venv/bin/python scripts/summarize_carr_e2_v8_r7.py
.venv/bin/python scripts/audit_carr_e2_v8_r5_publication.py
.venv/bin/python scripts/plot_carr_e2_v8_r7.py
```

论文产物：

1. 四模块逐 seed 配对点图；
2. 配对均值与 95% interval forest plot；
3. manipulation check、作用机会和下游结果并列表；
4. 完整终态/失败/成本 appendix table；
5. `docs/EVIDENCE_LEDGER.md` 的状态更新及依据 hash。

---

## 10. W8：H1 独立人工评价协议

H1 不能由另一个 LLM 自动代替。LLM-as-judge 可以单列自动化诊断，但不能写成人工
或专家证据。

### 10.1 外部前置条件

- 至少两名互不讨论正式 packet 的独立评分者；
- 在招募前完成适用的知情同意、数据保护和机构伦理/IRB determination；
- 没有专业资格证明时称 `human raters`，不称 experts。

### 10.2 packet 抽样

- 分析单位：一个完整 household trajectory packet；
- 正式 packet：48 个；
- 训练 packet：8 个，不进入分析；
- 两名评分者都评价全部 48 个正式 packet；
- 从 E1 正式 `VALID` runs 抽样；
- 分层变量：撤离/未撤离、1/2 决策成人、有/无 care recipient、有/无约束拒绝；
- 保存每个 packet inclusion probability；
- 汇总总体评分时使用 inverse-probability weight，同时报告各 strata 原始分布。

确定性抽样算法：

1. 仅保留 E1 formal `VALID` run 中具有完整 ledger 的 household；
2. household 归入上述四个二元变量形成的 16 个 strata；
3. 每个 stratum 内按
   `sha256(h1_sampling_seed + run_id + household_id)` 升序；
4. 第一轮每个非空 stratum 抽 1 个；
5. 后续轮次每个 stratum 每轮再抽 1 个，直到达到 48 或该 stratum 耗尽；
6. 若轮转结束仍不足 48，从所有剩余候选按当前已抽 inclusion rate
   `selected_in_stratum / available_in_stratum` 最小者优先补齐；并列按稳定 hash；
7. 对每个选中 packet 保存其 stratum、候选总数、选中总数和
   `inclusion_probability = selected_in_stratum / available_in_stratum`；
8. 如果完整候选 household 少于 48，不得重复抽样；冻结实际 n 并把样本不足写入
   H1 状态，不用一个 household 的多个片段冒充独立 packet。

### 10.3 盲法 packet 内容

展示：

```text
可观察的静态家庭信息
按时间投递的信息和消息
居民显式计划与行动意图
World 执行或拒绝结果
计划修订
最终家庭状态
```

删除：模型名、seed、内部 condition、Carr donor/respondent ID、身份、地址、隐藏
chain-of-thought 和论文期望方向。packet 顺序对每名评分者独立随机化。

### 10.4 1–5 锚定量表

六项评分：

1. information grounding；
2. cross-time consistency；
3. plan feasibility；
4. household coordination；
5. adaptation after failure；
6. overall plausibility（主项）。

统一锚点：

```text
1 = 多次明显违背已知信息、时间或资源，轨迹难以成立
2 = 存在重要矛盾或不可行行为，只有少量部分合理
3 = 大体可解释，但有至少一个明显缺口或未解决冲突
4 = 过程连贯且约束基本满足，仅有轻微可解释问题
5 = 信息、时间、计划、家庭资源和失败适应均清楚且一致
```

每项 rubric 再提供 2–3 个项目内行为例子；训练后不得根据正式评分分布修改锚点。

### 10.5 分析

- 主结果：overall plausibility 的加权分布和均值/中位数；
- 次结果：其余五项的加权分布；
- 一致性：quadratic weighted Cohen's kappa；
- 20,000 次 household-level bootstrap 95% interval；
- kappa 只表示评分一致性，不表示评分高；
- 报告分歧最大的 packet 及结构化原因；
- 缺失评分不由另一评分者代填，记录退出原因并报告完整率。

### 10.6 文件

- `scripts/build_carr_h1_packets.py`
- `experiments/carr/protocol/carr_h1_v1_rubric.yaml`
- `experiments/carr/protocol/carr_h1_v1_freeze.json`
- `scripts/analyze_carr_h1_ratings.py`
- `tests/test_carr_h1_packets.py`

---

## 11. W9：等价提示与有限跨模型复核

### 11.1 等价提示敏感性

新增 v8b，只改变措辞和字段排列，不改变字段、工具 schema、模块开关或输出语义。

比较必须使用：

```text
same cohort
same scenario
same component seed tuple
same model seed
same condition
prompt A versus prompt B
```

固定使用 5 个新的 paired seed。E2 对两个 prompt 都运行完整
`full + four drop-one`，共 `5 seeds × 2 prompts × 5 conditions = 50 runs`；
E1 对两个 prompt 运行相同的 5 个 full-only seed tuple，共 10 runs。

E2 对每个模块计算：

```text
delta_A = full_A - drop_A
delta_B = full_B - drop_B
prompt_difference = delta_B - delta_A
```

E1 full-only 计算相同 seed tuple 下 `metric_B - metric_A`。

预声明 practical equivalence margins：

```text
rate/proportion and paired-effect metrics: [-0.10, +0.10]
CDF MAE:                           [-0.05, +0.05]
```

只有 prompt-difference 的 95% paired interval 完全落在 margin 内，才称在该容忍
范围内等价；同向但 interval 未落入 margin 只称方向一致，不用“区间重叠”代替
等价判断。

### 11.2 有限跨模型复核

模型固定为：

```text
packy-deepseek-v4-flash
qwen3.5-plus
glm-5
```

全部经同一 Packy 代理，因此结论名称固定为“同一代理下的模型族敏感性”。

E2：

- 在 W7 正式规则下得到支持的模块进入有限复核；
- 这是对正发现的限定确认，不称完整模型稳健性；
- 三个模型必须在同一批新 paired seeds、cohort 和 scenario 上都运行；
- 每个进入复核的模块固定使用 4 个新的 paired seeds；
- DeepSeek 必须在这些新 seed 上同步重跑，不能拿旧 DeepSeek seed 与新模型比较；
- 每个模型报告作用机会分母、模型内配对效应和同 seed 模型间差值。

E1：

- DeepSeek 与 Qwen 各运行恰好 3 个相同 seed tuple 的 full-only 复核；
- 报告 focal/household/process 主指标的同 seed 差值；
- 不重新调 prompt 或指标来适应替代模型。

若 E2 没有模块通过正式支持规则，不执行“只挑最好的模块”跨模型确认；如仍运行，
只能标为探索性。

---

## 12. W10：100/500/1000 居民规模实验

### 12.1 scale 的定义

100/500/1000 指 **总居民数**，包括 decision residents 和 nondecision/care members。
cohort 以 whole household 为单位嵌套扩展，绝不拆户；报告最接近目标的实际人数。

三个规模使用同一排序后的 household pool：100 是 500 的前缀，500 是 1000 的前缀。
同时报告：

```text
total residents
decision residents
care recipients
households
social edges
actual awake residents
logical LLM decisions
```

### 12.2 固定工作负载

```text
25 steps
30 minutes per step
event-wake only
each step wakes 5% of decision residents by named deterministic schedule
social graph uses radius_m=1500, k_neighbors=6, k_friends=4, rewire_p=0.1
4 official events per 100 residents over the full run
same per-100-resident message opportunity density
DeepSeek V4 Flash thinking-high
cache disabled for latency measurement
concurrency = 6
request timeout = 600 seconds
3 fixed workload seeds per scale
no overlapping paid experiment
```

100-resident preflight 先测得 logical decisions、tokens、wall time 和内部估算成本。
500/1000 的运行预算按该 preflight 的线性投影乘 1.5 冻结；预算只作为 run
完整性边界，不作为论文贡献。

每个 scale run 的硬墙钟上限固定为 24 小时。可用内存上限在 freeze 时读取测试机
物理内存并固定为 80%，把具体字节数写入 freeze；超过时写 `ABORTED` summary，
不得让操作系统无记录地终止进程。

### 12.3 输出

```text
VALID / INVALID / ABORTED and reason
completed logical decisions / second
simulated resident-steps / second
p50 / p95 backend latency
scheduled versus completed decisions
scheduled versus delivered/processed messages
peak and terminal queue backlog
prompt/completion tokens per logical decision
estimated cost per logical decision
peak RSS
wall clock
failed/fallback decisions
```

只报告 resident-steps/second 会被大量 sleeping residents 虚增，因此必须同时报告
logical decisions/second。

### 12.4 稳定门槛

某一规模只有同时满足以下条件才称“在本测试配置下稳定完成”：

```text
3/3 runs VALID
0 ABORTED
final fallback rate <= 1%
no unexplained lost decision or message
no unexplained terminal queue backlog
no run exceeds frozen timeout, memory or budget
```

结论必须限定到测试机器、Packy 代理、DeepSeek 配置、并发和日期；1000 居民完成
只支持运行包络，不支持行为真实性。

---

## 13. 实施产物与验收总表

| 工作包 | 必须生成的核心产物 | 验收命令/检查 |
|---|---|---|
| W1 | donor v2、population v2、codebook、QA、hash | datalayer tests + 4,317/9,968 结构复现 |
| W2 | household/person trait donors、field-role、codebook、QA | exact literal/lineage/leakage tests |
| W3 | complete profile JSONL、restricted linkage、QA | reproducibility/source/focal/coordinator tests |
| W4 | v2 party/commitment/care/departure ledgers | 12 个家庭执行端到端测试 + E2 regression |
| W5 | E1 runner、信息/状态/执行 ledgers | 12 个信息隔离与 runner 测试 |
| W6 | preflight/sizing/formal freeze、raw runs、E1 summary | hash、终态、raking、区间与联合 bootstrap |
| W7 | E2 publication audit、summary、3 组图表 | 60-cell exact keyset + paired analysis |
| W8 | blind packets、rubric、ratings、H1 summary | 48×2 完整评分和 weighted kappa |
| W9 | prompt paired matrix、cross-model matrix | same-seed prompt/model differences |
| W10 | 9 个 scale runs、system summary | 3 scales × 3 seeds 与稳定门槛 |

---

## 14. 接手者的工作方式

每次只领取一个工作包，并按以下顺序完成：

```text
读取输入合同
→ 建立或修改列出的对象/脚本
→ 写单元与端到端测试
→ 运行离线测试
→ 生成冻结文件和 hash
→ 通过付费前置门
→ 执行真实模型
→ 运行独立 summarizer/audit
→ 更新 EVIDENCE_LEDGER
```

每次汇报只使用：

```text
当前工作包：W?
实现内容：文件、对象、函数
生成产物：绝对路径
验证结果：命令、通过/失败数、关键 QA
实验状态：ENGINEERING_VALIDATION / PILOT / RUNNING / VERIFIED / INVALID
下一步：明确的下一个工作包或阻塞
```

另一个模型如果发现本文与当前代码不一致，应输出具体文件、行号、失败测试和建议
修订，不得默默改写实验问题。任何正式实验结果只有在对应 freeze、终态、hash、
排除和 summary 全部完成后，才能进入 `docs/EVIDENCE_LEDGER.md` 和论文 Results。
