# paper_agentsimulation

DisasterSociety：动态灾害中的生成式居民与家庭社会仿真研究。

本仓库于 2026-09-08 整理实际实验源码、当前 IEEE 期刊论文以及已有实验记录。Resident 是独立认知与决策单位，Household 承担共享资源、照护责任和协调约束；当前案例为 Carr-informed controlled scenario。

## 从这里开始

| 内容 | 入口 |
|---|---|
| 实际实验源码、配置和测试 | [disastersociety/](disastersociety/) |
| 9 月 9 日代码修复与离线验证 | [修复说明](docs/evaluation_repair_20260909.md) · [验证记录](docs/evaluation_repair_20260909_verification.json) |
| 9 月 10 日：8 户实验与评价入口 | [本地 Codex 运行指令](docs/run_evaluation_pilot_codex.md) |
| 当前英文论文 | [main.tex](paper/ieee_journal/source/main.tex) · [PDF](paper/ieee_journal/source/main.pdf) |
| 论文图片和可编辑 Draw.io | [figures/](paper/ieee_journal/figures/) |
| 9 月 5 日实验批次 | [main_experiments_20260905/](paper/ieee_journal/working/main_experiments_20260905/) |
| 已有结果汇总 | [主实验结果.md](paper/ieee_journal/working/main_experiments_20260905/results/主实验结果.md) |
| 消融、跨模型及历史运行记录 | [experiments/carr/](disastersociety/experiments/carr/) |
| 数据来源与公开范围 | [DATA_AVAILABILITY.md](DATA_AVAILABILITY.md) |
| 整理来源、文件哈希与排除清单 | [release/import_manifest.json](release/import_manifest.json) |
| 当前执行边界 | [AGENTS.md](AGENTS.md) |

## 当前实验状态

- 9 月 10 日新增单次 8 户运行入口、程序核验、独立行为评分材料导出／汇总与完整结果报告。已验证带鉴权的聊天补全请求可成功；未鉴权的模型列表请求返回 403 不代表实际模型调用不可用。尚无正式方法对比。
- 9 月 9 日已修正家庭背景映射、消息和执行记录等问题，另存修正后的 24 户输入。旧记录与论文数值保留。
- 9 月 5 日批次的三次 24 户运行均有 `accepted.json`，分别对应 seed7201 的 attempt3、seed8301 的 attempt1、seed9401 的 attempt1。此前失败或中断尝试一并保留。
- 同批次 100 户 seed101 因接口余额耗尽停在 24/25 步，第 25 步尚缺 43 个决策；没有完成标记。seed202 未启动。
- 已有四项消融和跨模型记录保留原来的实验身份、状态与结论范围。其他历史批次的 100 户记录不能替代上述未完成运行。
- 主结果的评价目标、对照及图表仍在讨论。论文中的旧数值和结论需要逐项核对；软件测试、运行完成、行为合理与方法优越是不同结论。
- 本轮明确授权的执行范围是独立分支及修复后单次 8 户小试验；不自动扩展新对照、额外 seed 或整套消融。历史冻结文件里的执行计划不构成新的运行授权。

## 安装与检查

Python 3.11+，依赖锁定文件位于 `disastersociety/uv.lock`。

```sh
cd disastersociety
uv sync --frozen --extra dev --extra ml
uv run --frozen --extra dev --extra ml pytest -q
```

测试使用 mock 后端作软件检查，不代表真实模型效果。原始问卷及其受访者级派生数据未公开，依赖这些数据的测试不能在公开副本中直接完成；实际检查结果见 [release/VALIDATION.md](release/VALIDATION.md)。

当前论文已附 PDF。如本地安装 TeX Live 与 `latexmk`：

```sh
cd paper/ieee_journal/source
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

## 快照与路径说明

`disastersociety/` 来自实际实验源码目录；`paper/` 来自论文工作目录。两处源文件不做覆盖合并。论文工作目录中独有的 Carr 脚本和结果保存在 `archive/paper_workspace/experiments/carr/`，仅供历史追溯。

冻结代码、配置、输入、原始模拟日志和论文文件保持导入时的字节。历史记录中的绝对路径保留原貌，`accepted.json` 和部分执行脚本因此仍指向原机器目录；它们不是任意机器上一键重跑的承诺。不要修改冻结文件来消除路径差异。

`docs/research_history/`、`docs/source_entries/` 和 `archive/` 中的旧计划、状态说明及命令属于历史记录；以本页、当前 `AGENTS.md` 和实际实验状态为当前入口。仓库不包含 Codex 私人聊天历史、API 密钥、SQLite 缓存或原始受访者数据。
