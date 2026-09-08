# Carr 行为数据状态

本目录中的派生文件由 `scripts/clean_survey.py` 从原始 Qualtrics CSV
确定性生成。2026-07-31 已依据问卷 PDF 和 CSV 问题文本核验核心映射：

- `Q9.1`：是否撤离；
- `Q13.3/Q13.4`：撤离日期与时间；
- `Q5.2`、`Q6`、`Q7`：命令类型、时间和多选接收渠道。

文件：

- `survey_clean.csv`：335 条完整答卷，保留 outcome 缺失和排除原因；
- `evaluation_respondents.csv`：330 条 `Q9.1` 有效的冻结评价集合；
- `survey_clean_qa.json`：源文件哈希、字段映射和 QA 统计。

不含 respondent ID 的 Carr-R 共用拆分和字段角色协议位于
`../../../experiments/carr/protocol/`：

- `carr_r_split.csv`：198 train、66 validation、66 test；
- `carr_r_split_manifest.json`：源哈希、分层计数和矛盾记录规则；
- `field_roles.yaml`：prediction、channel prevalence 和 departure
  reference 三类 estimand 的输入/校准/评价/排除角色。

本次修复不追溯改变历史结果。此前使用占位标签产生的 JSON、CSV 和日志仍为
`INVALID_FOR_CLAIM`，必须在统一样本和无泄漏输入下重新运行。

详细审计见仓库 `docs/CARR_VARIABLE_AUDIT.md`。
