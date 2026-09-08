# 2026-07-31 旧 Carr 路径归档

## 归档原因

这些文件形成了一条绕开通用 `ds/kernel` 的 Carr 专用运行路径。该路径能够
产生开发期运行记录，但没有完整接入统一 LLM 网关、记忆、信任、家庭协调和
社会传播；其中部分说明还使用了“完整仿真”“真实验证”等超出证据的表述。

历史 `e1_dynamic.py` 每名受访者只调用一次模型，并在提示中包含事后灾害
严重性和问卷留守理由。它不是动态、多步或无泄漏的行为基线。

## 原路径

| 归档文件 | 原活跃路径 | 证据状态 |
|---|---|---|
| `disastersociety/ds/engine/runner.py` | `disastersociety/ds/engine/runner.py` | `PILOT` 实现 |
| `disastersociety/ds/world/base.py` | `disastersociety/ds/world/base.py` | `PILOT` 简化数据结构 |
| `disastersociety/ds/eventpack/carr_loader.py` | `disastersociety/ds/eventpack/carr_loader.py` | `PILOT` 简化加载器 |
| `disastersociety/experiments/carr/run_carr.py` | `disastersociety/experiments/carr/run_carr.py` | `PILOT` 运行入口 |
| `disastersociety/experiments/carr/e1_dynamic.py` | `disastersociety/experiments/carr/e1_dynamic.py` | `INVALID_FOR_CLAIM` |
| `disastersociety/experiments/baselines/train_traditional.py` | `disastersociety/experiments/baselines/train_traditional.py` | `INVALID_FOR_CLAIM` 旧随机拆分与错误 ECE |
| `disastersociety/experiments/baselines/llm_static.py` | `disastersociety/experiments/baselines/llm_static.py` | `INVALID_FOR_CLAIM` 旧标签、标识导出与不完整 provenance |

## 保留在原处的证据

- `disastersociety/experiments/carr/runs/`：历史运行日志；
- `disastersociety/experiments/carr/results/`：一次性模型结果；
- `disastersociety/experiments/baselines/results/`：传统与静态 LLM 结果；
- `disastersociety/eventpacks/carr_2018/`：数据资产与 provenance。

## 后续原则

新的 Carr runner 必须直接实现通用 kernel 协议。不得把本目录文件复制回
活跃路径后仅修改名称；若借用局部逻辑，应重新实现、测试并在证据台账记录。
