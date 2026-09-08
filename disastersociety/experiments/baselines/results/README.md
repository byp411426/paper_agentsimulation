# Baseline 结果状态

本目录中的历史 JSON、CSV 和日志均保留作开发记录。`traditional_baselines.json`
和 `llm_static_deepseek-v4-flash.json` 生成于 2026-07-31 标签修复之前，
当时 `evacuated` 等于 `warned_official`；传统模型与 LLM 也未使用同一评估
样本。因此这些历史数值均为 `INVALID_FOR_CLAIM`。

`carr_r_validation_pilot.json` 是修复标签、冻结 330 人集合、冻结字段角色和
60/20/20 split 后生成的新结果，但只打开 validation，状态为
`PILOT_VALIDATION_ONLY`。其传统模型和训练 prevalence 基线使用相同的
198 人训练集、66 人 validation 和四个人口学 runtime inputs；test 的 66 人
仍保持封存。该结果可用于检查管线、类别不平衡和配置，不得写成正式模型
优劣结论。配套 predictions CSV 不含 respondent ID，并由 `.gitignore` 排除。

`deepseek_v4flash_legacy_validation_reanalysis.json` 将历史
DeepSeek demographic-only 响应连接到修复后的标签，并只评价冻结
validation。重新解释历史 `confidence` 时，yes 决策使用 `confidence` 作为
撤离概率，no 决策使用 `1-confidence`；因此避免了旧脚本把“对不撤离的信心”
错误当成撤离概率。该结果为 `PILOT_LEGACY_REANALYSIS`，不是新的 API run。

新的 `run_carr_r_deepseek.py` 已按同一字段协议、无标识输出、统一网关和
validation-only 配置实现。2026-07-31 的连通性检查在任何网络请求前因当前
进程未设置 `PACKY_API_KEY`、`LLM_API_KEY` 或兼容旧脚本的
`OPENAI_API_KEY` 而停止，因此尚无新的付费结果，
也没有产生失败计费。test 仍保持封存。

所有历史与 validation pilot 的 F1、Brier 或 ECE 均不得写入摘要或正式
Results。正式比较必须先冻结静态 LLM、情境一次性基线及统一分析配置，
再一次性打开 test。
