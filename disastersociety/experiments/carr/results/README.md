# Carr 结果状态

本目录同时保存当前可跟踪的开发期汇总和归档脚本 `e1_dynamic.py` 的历史输出。

当前汇总：

- `carr_s_nonsaturated_pilot_summary.json`：非饱和 mock `PILOT`；
- `carr_s_robustness_pilot_summary.json`：mock 开发稳健性 `PILOT`；
- `carr_s_deepseek_backend_pilot_v3_summary.json`：从保留的10个 DeepSeek
  run artifact 派生的两种子 `PILOT` 汇总，包含指标映射更正与主张边界。
- `carr_s_deepseek_backend_pilot_v3_expanded_summary.json`：从五个预声明 seed
  的25个 run 派生的 `PILOT` 汇总；保留3个 `INVALID` run 并排除6个不完整对。
- `carr_s_deepseek_backend_reliability_v4_summary.json`：三项新 run ID 的顺序
  工程复核；2项 `VALID`，1项因代理余额不足为 `INVALID`，不回填科学配对。
- `carr_s_formal_e2_v5_availability_seed31_summary.json`：正式矩阵前的五户
  后端可用性门；full与−memory均 `VALID`、零 fallback，不计入机制效应。
- `carr_s_formal_e2_v5_seed101_summary.json`：E2 v5 原计划正式矩阵的首个 seed 批次
  不可变执行清单；5个条件均 `VALID`，仍为 `PILOT` raw execution record。
- `carr_s_formal_e2_v5_seed202_summary.json`：E2 v5 原计划正式矩阵的第二个 seed 批次
  不可变执行清单；5个条件均 `VALID`，仍为 `PILOT` raw execution record。
- `carr_s_formal_e2_v5_cumulative_summary.json`：逐批核验配置与 raw artifact
  哈希后生成的累计进度、配对差和排除记录；v5现已暂停，不得作为 Results。
- `carr_s_formal_e2_v5_protocol_diagnostic.json`：对两个full run的消息漏斗和
  时序缺陷做只读重建；用于解释暂停，不估计修正后的机制效应。
- `carr_s_mechanism_v6_mock_pilot_summary.json`：v6冻结协议的50-run零成本验证
  摘要；证明消息/承诺闭环可执行和可重放，不是生成式后端机制结果。

这些文件均不能直接作为正式 Results。

`e1_dynamic_*` 来自归档脚本 `e1_dynamic.py`。该脚本不是动态多步模型，
运行时使用的是修复前的占位撤离标签，并包含事后灾害严重性和留守理由提示。

因此 `e1_dynamic_*` 为 `INVALID_FOR_CLAIM`。保留文件只用于追踪开发历史、
检查输出格式和避免重复误用，不得作为行为有效性或机制贡献证据。
