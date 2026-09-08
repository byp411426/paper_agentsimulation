# E2 v8 r7 机制矩阵论文表格（60 格，COMPLETE_VALID）

- 协议：`carr_s_e2_v8_formal_r7`；审计状态：`COMPLETE_VALID`
- 格子：60 计划 / 60 实际 / 60 VALID
- 终态计数：{"VALID": 60}
- 总墙钟：75850s（均值 1264s/格）
- LLM 调用：ok 6693 + cache 0 = 6693；失败 0；fallback 0

## 操纵检查（配对 full − full-minus-module，12 seed）

| 模块 | 指标 | 平均配对差 | SD | MCSE | 95% CI | 正方向占比 | dz |
|---|---|---:|---:|---:|---|---:|---:|
| feedback | preclosure_primary_to_postclosure_alternate_update_rate | 0.9635 | 0.0496 | 0.0143 | [0.932, 0.995] | 1.00 | 19.44 |
| interaction | post_closure_feasible_commitment_rate | 0.9375 | 0.0843 | 0.0243 | [0.884, 0.991] | 1.00 | 11.12 |
| memory | conditional_warning_retention_rate | 1.0000 | 0.0000 | 0.0000 | [1.000, 1.000] | 1.00 | — |
| planning | successful_postclosure_replan_rate | 0.9062 | 0.0942 | 0.0272 | [0.846, 0.966] | 1.00 | 9.62 |

## 下游行为后果（配对方向）

| 模块 | 指标 | 预测方向 | 平均方向差 | 95% CI | 正方向占比 | 零差占比 | dz |
|---|---|---|---:|---:|---:|---:|---:|
| feedback | closed_route_rejections_per_household | lower | 6.5417 | [6.116, 6.968] | 1.00 | 0.00 | 9.75 |
| interaction | coordinated_departure_rate | higher | 0.8125 | [0.714, 0.911] | 1.00 | 0.00 | 5.23 |
| memory | complete_household_safe_departure_rate | higher | -0.1042 | [-0.210, 0.002] | 0.17 | 0.25 | -0.62 |
| planning | complete_household_safe_departure_rate | higher | 0.0104 | [-0.076, 0.096] | 0.42 | 0.17 | 0.08 |

## 证据边界

- 重复单位是独立的 seed × condition run（n=12 seed 对）；不把 resident/household/step 当独立样本。
- memory 的操纵检查差为结构上限且方差为 0；其下游差跨 0，不能写成下游机制已通过。
- 正式结论需结合 EVIDENCE_LEDGER 的 `RUNNING_PENDING_AUDIT` 转 `VERIFIED` 流程，本文档只是表格化中间产物。
