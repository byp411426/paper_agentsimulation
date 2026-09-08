# DisasterSociety IEEE Journal Workspace

本目录是 DisasterSociety 的专用 IEEE journal 工作区。当前论文路线是“动态城市灾害中的生成式居民社会过程仿真与多尺度评价”，以平台/框架、社会过程模型和评价方法为三项贡献。这里不使用任何其他会议模板。

当前任务与工作边界见 [根目录 AGENTS.md](../../AGENTS.md)。本页于 2026-09-05 清理旧进度说明；当前主结果的评价目标、对照和图表仍在讨论。

## 论文工作文件

- `source/main.tex`：当前 IEEEtran journal 英文主稿；已有数值和结论须与当前证据核对。
- `source/references.bib`：主稿使用的 BibTeX 文献库。
- `source/main.pdf`：由当前主稿编译得到的最新审阅 PDF。
- `figures/fig1_running_example.png`、`figures/fig2_system_architecture.png`、`figures/fig3_dynamic_loop.png`：正文实际使用的三张 1672×941 PNG。
- `figures/editable/`：三张图对应的 Draw.io 可编辑源文件。
- `DisasterSociety_期刊完整中文审阅稿.md`：中文审阅与事实对照稿；不得用旧结果覆盖英文主稿中的证据边界。
- `working/`：章节蓝图、证据映射和当前实现阻断项。

## 模板与编译

主稿使用 `\documentclass[journal]{IEEEtran}`。模板资产保存在 `template/`，编译用的 `IEEEtran.cls` 和 `IEEEtran.bst` 位于 `source/`。

```sh
cd /Users/linnuo/tmp/disastersociety/paper/ieee_journal/source
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

## 历史材料

- `archive/pre_20260814_ieee_rebuild/` 保存本次重建前的旧 IEEE 探索稿、旧参考文献和旧图，仅用于回溯，不是编辑入口。
- `output/DisasterSociety_论文中文审阅稿.docx`、`build_chinese_paper_docx.py` 和 `output/assets/` 属于旧中文导出链，不作为当前投稿源。
- `DisasterSociety_IEEE_Journal_Source.zip` 是旧源文件归档，不是当前编辑入口。

## 当前实验入口

- 保留 24 户、100 户主实验，以及已有四项消融和跨模型实验。
- 本批运行记录位于 `working/main_experiments_20260905/`，进度读取 `batch_status.json`，完成情况逐项核对各 run 的 `status.json`、`accepted.json` 和实际日志。
- `working/main_experiments_20260905/指标与执行顺序.md` 记录本批已执行的统计定义；它不等于已确定论文主结果的科学评价方案。
- 当前实际源码位于 `/Users/linnuo/Documents/agentSimulation/disastersociety`，本批运行使用冻结副本。不要使用工作区根目录的早期代码自行启动旧实验路线。
- 旧审阅稿、计划和审计中的进度描述属于历史记录，不替代当前运行状态。运行完成、行为有效和方法优越须分别判断。
