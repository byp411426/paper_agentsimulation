# Carr Fire 实验状态

当前目录保留活跃的通用-kernel 受控 runner、诊断脚本、历史结果和历史运行证据。旧 Carr 专用 runner 与
一次性 `e1_dynamic.py` 已归档到
`../../../archive/legacy_2026-07-31/disastersociety/`。

状态：

- `eval_individual.py`：修复后的标签读取已接通，但历史 run 的个体匹配仍为 `INVALID_FOR_CLAIM`；
- `eval_group.py`：`PILOT` 群体指标管线诊断；
- `results/`：使用修复前占位标签或事后提示产生的历史结果；
- `runs/`：旧简化 runner 的历史运行记录；
- Carr-S 受控机制 runner：已接入通用 kernel；v5已暂停，v6协议已冻结并通过零成本验证，正式声明后端结果仍为 `PLANNED`。

在共用 split、渠道矛盾处理和 Carr 正式 runner 冻结前，不运行出版用途的
E1/E2 实验。新的 runner 必须直接使用 `ds.kernel.Engine`、统一网关、
标准日志和显式机制开关。

## 受控机制 pilot

活跃的 `runner.py` 直接使用公共 `ds.kernel.Engine`，不是恢复旧 Carr
专用引擎。零成本配置位于
`configs/carr_s_mechanism_pilot.yaml`，运行命令：

```bash
uv run python scripts/run_carr_mechanism_pilot.py
```

该 pilot 从已保存的合成人口开发结果中选择恰有两名成人、一个共享车辆和
一至两名依赖成员的家庭，施加“协调者先收到预警”和“抽象主路线受阻”两个
受控扰动。这些是机制识别操作，不是 Carr 历史道路或预警时序。所有产物
继续标记为 `PILOT`。

非饱和配置位于
`configs/carr_s_mechanism_nonsaturated_pilot.yaml`。它增加配对 seed 控制的
预警接收、家庭消息送达、道路关闭时点和路线容量：

```bash
uv run python scripts/run_carr_mechanism_pilot.py \
  --config experiments/carr/configs/carr_s_mechanism_nonsaturated_pilot.yaml \
  --seeds 101 202 303 404 505 606 707 808 909 1010
```

50个 run 的小型、可跟踪摘要位于
`results/carr_s_nonsaturated_pilot_summary.json`，完整日志与逐 run 矩阵位于
被忽略的 `runs/`。该摘要只用于下一轮声明后端 pilot 设计，不是正式 E2。

## E2 v5 暂停与 v6 冻结

v5 在完成 seed 101/202 后暂停，现有10个付费run及全部raw artifact不删除、
不覆盖。暂停标记位于
`protocol/carr_s_formal_e2_v5_pause.json`，只读漏斗诊断位于
`results/carr_s_formal_e2_v5_protocol_diagnostic.json`。暂停原因是家庭DM暴露、
提议处理时序和interaction指标口径的协议缺陷，不是中间效应方向；剩余14个
v5 seed不再执行。

修复后的v6配置为`configs/carr_s_mechanism_v6_mock_pilot.yaml`，冻结清单位于
`protocol/carr_s_e2_v6_freeze.json`。它分离家庭DM与community送达，拒绝过期
proposal/acceptance，记录在途提议和承诺修订历史，并以扰动后可行承诺形成率
作为interaction主要指标。20户、5条件、10 seed的50-run mock验证全部
`VALID`且可确定性重放；这只放行后续小型声明后端pilot，不放行正式付费矩阵。
