# 交给本地 Codex：继续单次 8 户实验

本轮已授权一个修复后小规模真实模型试验。只做当前 8 户、seed 7201、25 步，不扩大到 100 户、不追加 seed 或整套消融，不修改论文数值。此前接口连通性在远程执行环境的网络审批阶段被取消，没有新的真实模型仿真结果。

## 运行入口

在 `fix/evaluation-foundations-20260909` 分支，进入 `disastersociety/`。使用现有项目环境，或按根 README 用 `uv sync --frozen --extra dev --extra ml` 安装锁定依赖。

先检查输入（无模型调用）：

```sh
python -m scripts.run_evaluation_pilot --output experiments/carr/runs/evaluation_pilot_8hh_attempt1
```

再运行这一个真实试验：

```sh
python -m scripts.run_evaluation_pilot --run --output experiments/carr/runs/evaluation_pilot_8hh_attempt1
```

若使用 uv 环境，把 `python` 换成 `uv run --frozen --extra dev --extra ml python`。

密钥仅通过已有 `PACKY_API_KEY` 环境变量或终端隐藏输入提供，不写进命令、文件、日志和提交。已有密钥则直接执行；缺少密钥才请用户在本机安全输入。模型配置只保存环境变量名称。配置中的 2 美元预算使用每百万输入／输出 token 各 1 美元的内部估值，不是已核验的代理实际价格或严格账户扣费上限。

入口保护已有目录，失败记录也保留；不要覆盖失败尝试。若遇到接口错误，报告实际状态、已完成步数和调用记录，不自动换模型、改成 mock 或循环重试整个实验。每次传输的尝试上限设为两次；模型输出不符合结构时还可能触发一次修复请求，因此一个决策可能不止两次传输。网关最终失败即中止，未完成运行不产生行为总分。

完成后输出：

- `.../e1_pilot_8hh_20260910/`：实际原始运行，包括模型输入、事件、执行状态和来源记录。
- `.../evaluation/audit_results.json`：程序指标；无机会为 null，不填零。
- `.../evaluation/check_records.json`：逐条核验依据，包括另列的资源／非撤离检查。
- `.../evaluation/review_inputs/` 与 `review_manifest.json`：全部 8 户的匿名完整记录与冻结量表。

## 完成行为评分

为行为评审启动新的独立 Codex 会话；只提供 `evaluation/review_inputs/`，不提供方法名、模型名、代码、之前的分数或程序错误率。要求先读 `rubric.md`，再读全部案例及所有实际决策输入，按量表输出 `behavior_scores.json`。不能把无决策时段当成主动等待；不把救援表达当成已完成接送；不预填分数。若不能启动独立会话，明确标记行为评分待完成，不能由已知结果的同一会话假装盲评。

评分结束后，由运行会话汇总：

```sh
python -m scripts.collect_behavior_scores \
  --review experiments/carr/runs/evaluation_pilot_8hh_attempt1/evaluation/review_inputs \
  --manifest experiments/carr/runs/evaluation_pilot_8hh_attempt1/evaluation/review_manifest.json \
  --scores experiments/carr/runs/evaluation_pilot_8hh_attempt1/evaluation/behavior_scores.json \
  --output experiments/carr/runs/evaluation_pilot_8hh_attempt1/evaluation/behavior_summary.json
```

最后交付同一批 8 户的行为分数、三项错误条数／检查条数、逐户具体问题、运行是否完整及失败／缓存调用统计。第五项正式场景指标继续标记未实施。不要把旧 24 户的分母挪进新结果，不声称本次小样本证明方法优于基线。
