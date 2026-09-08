# Carr Q13.6 派生列修复前快照

本目录保存 2026-08-02 修复前的两个派生文件，避免覆盖后丢失审计依据。

- `survey_clean_pre_fix.csv`：旧 SHA-256 `46539f3162428803a250e59f30d81c87ac9d4d2551c3561d71069ad078daee4b`；
- `survey_clean_qa_pre_fix.json`：旧 SHA-256 `126a30c012a0a6040c57f5db7754e28e8a1f199bd92c8d721e72a10170cb0c2b`。

旧清洗脚本把出发时 fire/smoke 感知错映射为 `Q13.6_2/Q13.6_3`；问卷和 Qualtrics 表头显示正确映射为 `Q13.6_1/Q13.6_2`。这两个字段均为 post-outcome，未进入 Carr-R runtime input，也未参与 E1 v1.1 的撤离率、时序、渠道或群体差异参照。

机器可读的修复、哈希和影响审计见：

`disastersociety/experiments/carr/protocol/carr_s_e1_reference_q136_mapping_amendment.json`
