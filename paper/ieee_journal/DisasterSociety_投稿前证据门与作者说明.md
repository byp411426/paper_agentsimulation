# DisasterSociety 投稿前证据门与作者说明

用途：本文件保存不应进入论文正文的项目状态、已发现问题与投稿 release gate。论文正文位于 `DisasterSociety_期刊完整中文审阅稿.md`。

## 一、当前可进入主文的证据

- E2 v8 r7 的 60 个 `seed × condition` 运行全部达到 `VALID` 终态，四项消融各有 12 个完整同 seed 配对；6,693 次真实模型调用中失败数和规则回退数均为 0。该矩阵及其完整性检查承担当前主定量结论。
- E1 v2 的三个 24 户运行、E3/E3a 的配置敏感性运行和 E3c 的两个 100 户运行已经完成，但正文仅将它们分别用作完整系统过程描述、探索性敏感性分析和运行包络。
- Carr 场景只能表述为 Carr-informed 受控案例。CAL FIRE perimeter 是最终空间边界，TIGER/Line 提供道路几何，算法控制的道路关闭不代表 Carr Fire 的历史关闭时序。

## 二、E1/E3c 指标修正

- 既有汇总脚本 `disastersociety/scripts/summarize_carr_e1_v2.py` 把“至少出现一个成功 executed departure party 的家庭率”误命名为 `complete_safe_household_departure_rate`。该字段不检查家庭全体成员终态。
- 正文已从 `member_profiles` 与最终 `world.member_locations` 重算成员终态：E1 三个 seed 的终态全员安全家庭率为 29.2%、41.7% 和 33.3%，合计 25/72（34.7%）；原 51.4% 仅表示至少一个出发组成功执行。
- E3c 两个 seed 的终态全员安全家庭率为 25% 和 23%；原 47% 和 42% 仅表示至少一个出发组成功执行。
- 既有 `split` 字段表示同一家庭出现多个 executed parties，不等于最终成员分处安全区与家的家庭。正文已经分别报告最终部分出发家庭率。
- 投稿前必须修正规范汇总脚本，为终态全员安全、至少一个成功出发组、最终部分出发和多个执行出发组补回归测试，并同步 `docs/EVIDENCE_LEDGER.md`。

## 三、复现与测试门

- 当前规范虚拟环境复核为 129 passed、2 failed。两项失败分别涉及 `ds/agents/carr.py` 重建哈希与冻结哈希不一致，以及 PUMS codebook 缺失标签的 `NaN`/`None` 表示差异。
- E1 v2 的位置回退和社区消息抽取仍存在 Python 内置 `hash(...)` 路径。投稿前应改为稳定哈希或固定并记录 `PYTHONHASHSEED`，随后执行跨进程重放。
- E2 直接调用通用 EventPack loader 并写入完整来源记录；E1 v2 是通用 Engine 上的 Carr 专用居民、世界、互动和事件源适配器。正文与架构图必须保留这一实现边界。
- 当前完整测试不能写成“全部通过”，E1 v2 也不能写成由 run seed 即可保证跨进程字节级确定性复现。

## 四、数据与引用门

- Zenodo 记录页称有 338 份完成答卷，但与 Zenodo API checksum 一致的存档 CSV 包含 335 条 `Finished=TRUE` 且 `Progress=100` 的记录。本文的 335/330/293/37/292 均按存档 payload 与公开清洗规则重算，不应表述为 Zenodo 页面直接报告的样本量。
- 2014–2018 ACS 5-year PUMS 用作整户 donor，2018 ACS 5-year Summary File 提供四组 tract 家庭边际。PUMS 不是现实居民名册，家庭边际拟合也不等于成员级人口已经校准。
- 当前正文 31 条参考文献已按首次出现顺序排列；原 `[1]–[18]` 已经独立核验 DOI 与核心元数据，数据与案例来源使用 Census、CAL FIRE 和 Zenodo 一手页面。
- 数据与代码声明中的仓库 URL/DOI、release 或 commit、许可证、受限材料申请方式，以及伦理审批和二次使用结论仍需作者填写。

## 五、图片与成稿门

- 正文只保留图 1–3：人物/家庭灾害响应示例、DisasterSociety 总体架构、居民社会过程的方法机制闭环。详细内容、版式、颜色和验收规则见 `DisasterSociety_论文图片设计需求.md`。
- E1、E2、E3/E3a 和 E3c 的结果不另制正文图片，由表 III–VII 报告。E1/E3c 的家庭状态必须继续按成员终态计算；E2/E3 的效应方向、配对区间和重复单位必须在表格中保持当前口径。
- 作者确认中文稿后，再从空白 IEEEtran journal 模板迁移，不从旧 `source/main.tex` 拼接旧研究问题、旧个体预测或跨灾害迁移叙事。

## 六、投稿前最终清单

1. 修复 E1/E3c 汇总脚本并同步证据台账。
2. 关闭两项当前测试失败并完成 E1 跨进程重放。
3. 完成 E1、E3、E3a 与 E3c 的来源、样本、终态和排除审查，再决定其最终主文或补充材料位置。
4. 生成图 1–3 的矢量版本及 `figures/manifest.json`。
5. 补齐数据、代码、伦理、作者贡献、资助、利益冲突和 AI 使用披露。
6. 重建 IEEE LaTeX 与 BibTeX，编译并分别检查图片、表格的首次引用、编号、版芯和参考文献格式。
