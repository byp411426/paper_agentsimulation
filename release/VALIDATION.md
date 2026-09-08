# 2026-09-08 导入检查

本次工作是将既有论文与实验材料整理到 GitHub，未修改科学代码、输入、指标、实验结果或论文内容，未启动新的付费实验。

## 文件一致性

- 5,432 个导入文件逐个与导入清单中的 SHA-256 核对，差异数为 0。
- `paper/ieee_journal/working/main_experiments_20260905/freeze.json` 的 `files_sha256` 含 62 项，62/62 与发布副本中的文件一致。
- 三个 24 户 `accepted.json` 指向的运行目录、`run_summary.json` 和分析目录均存在。100 户 seed101 保持未完成状态。
- 生成的根目录说明、数据说明、检查报告及导入清单为本次新增的仓库文档；历史文件未被它们覆盖。

## 离线测试

在整理后的 `disastersociety/` 运行现有完整测试集，使用原项目已经安装的 Python 3.13 环境，关闭 pytest 缓存并从测试进程环境中移除 API 密钥、token、密码与 secret 变量。执行命令等价于：

```sh
python -m pytest -q --tb=short -p no:cacheprovider
```

结果：**152 passed, 3 failed, 1 skipped**，约 9.54 秒。

| 未通过项目 | 原因 |
|---|---|
| `test_carr_cleaning_matches_questionnaire_branches` | 原始 `Wong_Carr_Wildfire_Dataset.csv` 未公开 |
| `test_carr_protocol_roles_and_split_are_complete_and_deterministic` | 同样依赖未公开原始问卷 |
| `test_v2_codebook_decodes_labels_and_na` | 缺失值实际为 NaN，测试预期 None；在原始源码目录独立复现同一失败，非导入造成 |

因此，本仓库不声称完整测试集通过，也不以这些软件测试宣称行为有效或方法优越。本次为保留真实实验快照，没有为了测试通过而修改既有代码或断言。

## 凭据与数据检查

- 使用 Gitleaks 8.30.1 默认规则、归档与解码扫描，对发布副本执行凭据检查；工具下载包 SHA-256 与官方 release 校验文件一致。
- 初始通用密钥规则命中 251,305 条 `llm_calls.jsonl` 中的 `key` 字段。逐条解析后，全部是 64 位十六进制 SHA-256，且源码确认该字段来自 `LLMCache.make_key(model, messages, seed, temperature)`，不是 API 密钥。
- `.gitleaks.toml` 仅豁免该日志文件中的完整 SHA-256 `key` 文本。复扫仍有 179 条同字段的分块截断误报，逐条核对完整 JSON 记录后均为同类缓存标识；未发现实际凭据。扫描并非无条件零命中，不能省略这一步人工语义复核。
- 另外扫描常见 API token、私钥、带口令 URL、Bearer token 与硬编码凭据模式，未发现实际凭据。
- SQLite 缓存、原始问卷、受访者级预测与关联表、私人聊天记录、环境文件及原始下载包不进入此次公开提交。原机器上的文件未删除。

## 复现限制

冻结记录及部分脚本保留原机器绝对路径；需要在其他机器运行时另行适配路径。问卷相关分析需要合法取得原始数据；历史无费用精确回放还需要未公开的本地响应缓存。历史文件中的冻结计划不构成重新执行付费实验的授权。
