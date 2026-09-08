# 数据与复现材料

本公开仓库包含实验代码、历史冻结协议、用于模拟的合成家庭输入、运行状态、模拟事件与模型调用元数据、分析结果、论文及图表。原始文件保持导入时的字节，文件清单及 SHA-256 见 `release/import_manifest.json`。

## 人口与地理资产

已包含从公开政府数据提取或派生的 PUMS donor 表、合成人口、ACS 边际、Shasta 道路与 tract GeoJSON、Carr 最终火场边界及受控路线资产。其来源、提取方式、哈希和解释边界见：

- `disastersociety/eventpacks/carr_2018/provenance/download_log.yaml`
- `disastersociety/eventpacks/carr_2018/population/pums_2018_v2_codebook.yaml`
- `disastersociety/eventpacks/carr_2018/manifest.yaml`

大体积原始下载包不在仓库中。`raw/README.md` 仅解释缺失情况，不代表原始包已发布或完成原始数据重建验证。涉及原始包的重建需从 provenance 中列出的来源另行取得并核验。

## 问卷与私人材料

未发布原始 Wong Carr 问卷数据、`survey_clean.csv`、`evaluation_respondents.csv`、受访者级预测、Carr-R 受访者级模型记录，以及 `restricted/` 下的来源关联表。也未发布私人 Codex 对话或凭据。

问卷相关代码、字段角色、编码方案、聚合 QA 与汇总结果仍保留。依赖原始问卷的清洗或评价测试需要单独取得有权使用的数据；公开仓库不提供绕过数据许可或访问限制的方法。

## 缓存和运行状态

SQLite 响应缓存、本地虚拟环境及下载压缩包保留在原机器，不在公开仓库。已发布的 `llm_calls.jsonl` 中 `key` 字段为 `LLMCache.make_key()` 计算的 SHA-256 请求缓存标识，不是 API 凭据。

本次整理未启动任何新模型实验。未完成、中断、诊断与工程验证记录保留其原始身份，不因公开上传而变成正式科学结果。缺少响应缓存意味着此公开副本不具备全部历史运行的无费用精确回放能力。
