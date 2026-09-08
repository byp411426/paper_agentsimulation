"""Build review figures and paper fragments from the saved offline results."""
from collections import Counter
from pathlib import Path
import csv
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

HERE = Path(__file__).resolve().parent
RESULT = json.loads((HERE / "results.json").read_text())
TOTAL = RESULT["totals"]
PROPOSALS = list(csv.DictReader((HERE / "proposal_event_checks.csv").open()))
CN = FontProperties(fname="/System/Library/Fonts/Supplemental/Songti.ttc")
plt.rcParams.update({"font.family": "Arial", "font.size": 10, "axes.linewidth": .65,
                     "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
                     "axes.spines.top": False, "axes.spines.right": False})
COLORS = {"executed": "#18776F", "rejected": "#B57722", "cancelled": "#697782", "accepted": "#7B8FA7"}


def save(fig, stem):
    for ext in ("png", "pdf", "svg"):
        fig.savefig(HERE / f"{stem}.{ext}", dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def formation_figure(chinese):
    stages = TOTAL["proposal_stages"]
    outcomes = TOTAL["agreement_outcomes"]
    a_keys = ["feasible_agreement", "pending_response", "declined", "invalid_membership", "resource_conflict"]
    b_keys = ["executed", "rejected", "cancelled", "accepted"]
    a_labels = ["形成可行约定", "尚未得到回应", "参与者拒绝", "成员组合不合约束", "已有约定占用资源"] if chinese else [
        "Feasible agreement", "Response pending", "Participant declined", "Invalid member assignment", "Active resource conflict"]
    b_labels = ["实际执行", "执行被拒绝", "约定取消", "计划在窗口之后"] if chinese else [
        "Executed", "Execution rejected", "Cancelled", "Scheduled beyond horizon"]
    fig, axs = plt.subplots(1, 2, figsize=(10.8, 3.7), gridspec_kw={"wspace": .76})
    for ax, keys, labels, values, colors in [
        (axs[0], a_keys, a_labels, stages, [COLORS["executed"], "#B7C3CE", "#8796A2", "#BCA786", "#C8C1B7"]),
        (axs[1], b_keys, b_labels, outcomes, [COLORS[k] for k in b_keys])]:
        counts = [values.get(k, 0) for k in keys]
        ax.barh(range(len(keys)), counts, height=.58, color=colors)
        ax.set_yticks(range(len(keys)), labels)
        ax.invert_yaxis()
        ax.set_xlim(0, max(counts) * 1.23)
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=5))
        ax.xaxis.grid(True, color="#E5E8EB", linewidth=.65)
        ax.set_axisbelow(True)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0, pad=9)
        for i, n in enumerate(counts):
            ax.text(n + max(counts) * .035, i, str(n), va="center", fontsize=11)
        ax.set_xlabel("约定／提议版本数" if chinese else "Proposal / agreement versions", fontproperties=CN if chinese else None)
        if chinese:
            for lab in ax.get_yticklabels(): lab.set_fontproperties(CN)
    titles = ["A   49 条提议的形成结果", "B   12 条约定的执行结果"] if chinese else [
        "A   Formation of 49 proposals", "B   Outcomes of 12 agreements"]
    for ax, title in zip(axs, titles):
        ax.set_title(title, loc="left", pad=17, fontproperties=CN if chinese else None, fontsize=12)
    fig.subplots_adjust(bottom=.20, top=.82, left=.19, right=.97)
    save(fig, "proposal_outcomes_zh" if chinese else "proposal_outcomes")


def timeline_figure(chinese):
    rows = [r for r in PROPOSALS if r["recorded_feasible"] == "True"]
    rows.sort(key=lambda r: (int(r["expected_formed_step"]), int(r["planned_departure_step"]), r["run"], r["message_id"]))
    fig, ax = plt.subplots(figsize=(10.4, 5.0))
    ax.axvspan(25, 27, color="#F0F2F4", zorder=0)
    for step in (3, 7, 9):
        ax.axvline(step, color="#AEB7C0", lw=.8, ls=(0, (3, 3)), zorder=0)
    ax.axvline(25, color="#7D8791", lw=.8, zorder=0)
    labels = []
    markers = {"executed": "o", "rejected": "X", "cancelled": "s", "accepted": ">"}
    mapping = []
    for i, row in enumerate(rows):
        start, due = int(row["expected_formed_step"]), int(row["planned_departure_step"])
        status = row["terminal_commitment_status"]
        end = int(row["terminal_step"]) if row["terminal_step"] else due
        color = COLORS[status]
        ax.plot([start, end], [i, i], color=color, lw=2, ls="--" if status == "accepted" else "-", zorder=2)
        ax.scatter(start, i, s=40, marker="o", facecolor="white", edgecolor=color, lw=1.3, zorder=4)
        ax.plot([due, due], [i-.19, i+.19], color="#9EA7AF", lw=1, zorder=1)
        ax.scatter(end, i, s=54, marker=markers[status], facecolor="white" if status == "accepted" else color,
                   edgecolor=color, lw=1.2, zorder=5)
        route = ("主路" if "primary" in row["route_id"] else "备选路") if chinese else ("R1" if "primary" in row["route_id"] else "R2")
        label = (f"约定 {i+1:02d} · {route}" if chinese else f"Agreement {i+1:02d} · {route}")
        labels.append(label)
        mapping.append({"figure_row": i+1, **row})
    ax.set_yticks(range(len(rows)), labels)
    ax.invert_yaxis()
    ax.set_ylim(len(rows)-.45, -.7)
    ax.set_xlim(1, 27)
    ax.set_xticks([1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 26])
    ax.tick_params(axis="y", length=0, pad=9)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("模拟时间步（每步 30 分钟）" if chinese else "Simulation step (30 minutes per step)",
                  fontproperties=CN if chinese else None, labelpad=10)
    event_labels = [(3, "建议撤离" if chinese else "Advisory", 1.05),
                    (7, "强制撤离" if chinese else "Mandatory", 1.05),
                    (9, "主路关闭" if chinese else "R1 closes", 1.13),
                    (25, "观察窗口结束" if chinese else "Horizon", 1.05)]
    for step, label, height in event_labels:
        ax.text(step, height, label, transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                fontproperties=CN if chinese else None, color="#53616D", fontsize=10)
    if chinese:
        for lab in ax.get_yticklabels(): lab.set_fontproperties(CN)
    legend_labels = ["约定形成", "实际执行", "执行拒绝", "取消", "窗口后计划", "计划出发时间"] if chinese else [
        "Formed", "Executed", "Rejected", "Cancelled", "Beyond horizon", "Planned departure"]
    handles = [Line2D([], [], marker="o", ls="", color="#53616D", markerfacecolor="white", label=legend_labels[0])]
    handles += [Line2D([], [], marker=markers[s], ls="", color=COLORS[s], markerfacecolor="white" if s == "accepted" else COLORS[s],
                       label=legend_labels[i+1]) for i,s in enumerate(["executed", "rejected", "cancelled", "accepted"])]
    handles.append(Line2D([], [], marker="|", ls="", color="#9EA7AF", label=legend_labels[-1], markersize=9))
    fig.legend(handles=handles, loc="lower center", ncol=6, frameon=False, bbox_to_anchor=(.53, -.015),
               prop=CN if chinese else None, handletextpad=.45, columnspacing=1.35)
    fig.subplots_adjust(left=.22, right=.97, bottom=.17, top=.81)
    save(fig, "agreement_timeline_zh" if chinese else "agreement_timeline")
    if not chinese:
        with (HERE / "figure_event_mapping.csv").open("w", newline="") as f:
            w=csv.DictWriter(f, fieldnames=list(mapping[0])); w.writeheader(); w.writerows(mapping)


def documents():
    event_lines=[]
    names={"delivery":"消息投递记录", "processing":"消息处理记录", "feasible_agreement":"可行家庭约定记录"}
    for kind,c in TOTAL["event_records"].items():
        event_lines.append(f"| {names[kind]} | {c['tp']} | {c['fp']} | {c['fn']} | {100*c['precision']:.1f}% | {100*c['recall']:.1f}% |")
    terminal=Counter()
    for r in RESULT['runs']: terminal.update(r['household_terminal_counts'])
    report=f'''# DisasterSociety 本方法主实验结果

2026-09-06，已有数据的离线整理稿。新增模型调用 **0 次**，新增模拟运行 **0 次**。

## 当前完成到哪里

我们方法这一侧的结果提取、记录一致性统计、过程图、可追溯明细和正文段落稿已生成。使用三个已验收的 24 户完整运行，保留全部结果；不修改原始实验、冻结定义、论文正文，不填入尚未运行的外部方法数值。

三次运行采用同一批 24 户、44 名成员，其中 31 名决策居民；每次 25 步、每步 30 分钟。以下合计是三次运行中的事件记录量，不是 72 个独立家庭或 132 名独立受试者。不以 seed 编号作为正文比较对象，不进行伪独立显著性检验。

## 1. 已计算的本方法结果

### 信息来源和世界状态

| 检查项 | 冲突数 / 检查量 | 比例 |
|---|---:|---:|
| 结构化信息来源／归属违规 | {TOTAL['input_packets_with_structural_source_violation']} / {TOTAL['decisions']} 次决策输入 | {100*TOTAL['input_packets_with_structural_source_violation']/TOTAL['decisions']:.1f}% |
| 已记录物理状态的冲突时间步 | {TOTAL['steps_with_world_conflict']} / {TOTAL['steps']} 步 | {100*TOTAL['steps_with_world_conflict']/TOTAL['steps']:.1f}% |

信息检查核对私人输入与本人状态、官方信息收据归属、消息收件者和投递时间、执行记忆来源，以及道路认知更新的已有依据。不将自然语言猜测、谣言或人物改变主意自动判错。**这里的 0 不等于已证明所有自然语言内容绝无信息越界。**

物理检查覆盖全体成员位置与实际出发的一致性、出发时刻、同意及当步行动、车辆归属与容量、重复使用、随行成员照护字段、路线开放和容量。全部 75 步都检查，包含没有出发的步骤，以免漏掉“没有行动却改变位置”。其中实际有 {TOTAL['departure_attempts']} 次出发意图，形成 {TOTAL['executed_departure_parties']} 次实际队伍出发、{TOTAL['moved_members']} 次成员转移。车辆容量来自场景配置和画像，而非让模型自己的陈述作为标准。

**物理检查不包括未记录的完整车辆内部状态，也没有穷尽证明每一个拒绝都是唯一正确的仲裁结果。**

### 社会事件记录

| 事件类型 | 正确记录 | 多记／错记 | 漏记 | 精确率 | 召回率 |
|---|---:|---:|---:|---:|---:|
{chr(10).join(event_lines)}

精确率 = 正确记录 /（正确记录 + 多记或错记）；召回率 = 正确记录 /（正确记录 + 漏记）。分母为 0 时为 NA，不计满分。消息以“消息—收件人—时间步”为单位；家庭约定以提议版本为单位。

投递事件从居民逐步收件箱重建；处理事件从当步收件箱及实际决策重建，不把投递当作处理，也不将程序处理标记解释为语义理解。可行约定从原始结构化提议、接受／拒绝回应、成员／车辆条件和本批处理顺序重建，再与记录的参与者、车辆、路线、照护分配和时刻核对。659 次核心行动及回应字段均与只读缓存中的原始结构化回复相符。

这些百分比评价**记录是否符合发生过的事件及本批规则**，不是“人类模拟真实性满分”，也不是“家庭协作成功率”。它们属于本次新增的离线分析，不能冒称原实验预先声明的主要终点。

## 2. 实际家庭过程是什么样的

49 条家庭提议的去向：

| 结果 | 条数 |
|---|---:|
| 形成可行约定 | 12 |
| 尚未得到必要回应 | 16 |
| 参与者明确拒绝 | 8 |
| 成员组合不符合场景约束 | 12 |
| 成员同意后仍与已有约定产生资源冲突 | 1 |

上述 12 条成员组合问题中，7 条涉及决策同行成员，5 条涉及随行非决策成员。它们是模型提出的提议问题；模拟器识别并拒绝它们，不是世界状态已经出错。

12 条已形成约定的后续是：**4 条实际执行、5 条执行被拒绝、1 条取消、2 条计划在第 26 步出发，超出第 25 步观察窗口。** 后两条不能算成功，也不能作为已观察到的执行失败。

![提议与约定的实际去向]({HERE}/proposal_outcomes_zh.png)

这张图以提议／约定版本为单位，两个面板的分母分别是 49 和 12，不把多人约定版本当作独立家庭，也不把更多撤离直接解释为更高模拟质量。

## 3. 全部约定在什么时间发生

下图展示所有 12 条已形成约定，没有只挑成功案例。约定实例跨三次已有运行，按相同场景时间步对齐；不是同一个世界中的 12 户。灰色短竖线是计划出发时刻；圆点／叉／方块是实际执行、拒绝或取消；右侧浅灰区在观察窗口之外。

![全部家庭约定的时间过程]({HERE}/agreement_timeline_zh.png)

第 3、7、9 步竖线标明场景中建议撤离、强制撤离和主路关闭的发布时间，不表示所有居民都直接收到该信息。每一行均可通过 figure_event_mapping.csv 回到原始约定和运行日志。

## 4. 对这些结果的判断

已有数据支持：在检查范围内，个人输入具有对应来源，社会事件记录可核验，已执行行动与成员状态相符。家庭过程并非全部顺利：等待回应、明确拒绝、约定取消及执行受阻均被保留。

已有数据不支持把本方法写成“普遍更善于协调”或“比其他模拟框架更好”。当前完成的是本方法结果，比较方法尚未运行；由程序规则保障的一致性，其他方法也可能满足。正文应分别说明记录正确性和行为过程，不把它们拼成一个真实性总分。

旧的群体终态统计仍保留：三次运行合计 {terminal['all_safe']} 个家庭—运行记录全员到安全区、{terminal['partly_safe']} 个部分到达、{terminal['none_safe']} 个无人到达；这些是描述性结果，不用于把“全撤离”设成最优答案。seek_help 和 offer_help 只作为已生成的求助／帮助意图；没有实际转移时不计为完成接送。

## 5. 数据和检查范围

- 本批 100 户运行仅有前 24 步完整日志，继续保留，未混入完整终局统计，也未续跑。
- 已有 E2 四项消融和 E3 跨模型结果保留，本次没有以新指标覆盖旧指标，也没有启动补跑。
- 对提取器做了 6 类检查，分别在三次已有运行上执行，共 18 项均通过：不存在的官方信息来源、虚构约定、漏记约定、空事件集不计满分、无行动的成员转移、合法静止步骤。
- 核查中修正了提取器的一处顺序假设：同一步内两个提议竞争同一车辆，应按照本批已记录的回应处理顺序核对，不能按照先发提议的顺序判定谁先占用。原始实验没有改动。跨框架比较若允许不同合法处理顺序，须另行定义允许的结果集合，不能据此把另一个合法调度判错。

## 文件入口

- [主结果表 CSV]({HERE}/method_result_table.csv)
- [方法比较表中的本方法结果行]({HERE}/method_comparison_row.csv)
- [逐条提议与约定结果]({HERE}/proposal_event_checks.csv)
- [逐次输入检查]({HERE}/information_input_checks.csv)
- [逐步世界状态检查]({HERE}/world_step_checks.csv)
- [结果、范围和来源]({HERE}/results.json)
- [论文正文段落与表格稿]({HERE}/main_experiment_ours.tex)
- [英文时间图 PDF]({HERE}/agreement_timeline.pdf)；[英文提议结果图 PDF]({HERE}/proposal_outcomes.pdf)
- [离线提取程序]({HERE}/extract_results.py)；[图表生成程序]({HERE}/build_artifacts.py)
'''
    (HERE / "本方法主实验结果.md").write_text(report)
    manuscript=r'''% Review fragment only. Not inserted into main.tex.
\subsection{Generated Household Response Processes}
The completed experiments use a cohort of 24 households with 44 members,
including 31 decision-making residents, over 25 half-hour steps. We analyze
all three previously completed runs. Counts below describe recorded events
across these runs; repeated appearances of a household are not treated as
independent population samples.

The generated processes contain 49 household proposals. Twelve become
feasible commitments, 16 remain awaiting a required response, and eight are
explicitly declined. Twelve proposals are rejected for incompatible member
assignments, and one encounters an active resource conflict after the
participants agree. Of the 12 formed commitments, four execute, five are
rejected at execution, and one is cancelled. The remaining two schedule
departure at step 26, beyond the observation horizon, and therefore have no
observed terminal execution outcome. These results distinguish proposal,
agreement, and movement without treating staying or declining to coordinate
as simulation errors.

A separate, retrospective record-level analysis checks structured information
sources and event/state consistency. No structured source-ownership violation
is detected in 659 recorded decision inputs. Reconstructed delivery,
processing, and feasible-commitment events agree with the corresponding
records (125, 59, and 12 events, respectively). No conflict is detected across
the 75 complete steps for the checked member-movement, vehicle-use, and
route constraints. These checks evaluate recorded process consistency under
the implemented scenario; they do not measure agreement with real human
behavior or establish superiority over other simulation frameworks.

\begin{table}[t]
\centering
\footnotesize
\setlength{\tabcolsep}{4pt}
\caption{DisasterSociety: retrospective record consistency in the completed
24-household experiments. Counts aggregate three existing runs. Event
precision/recall concerns recorded events, not human evacuation prediction.}
\label{tab:ours-record-consistency-review}
\begin{tabular}{lrr}
\hline
Check & Result & Exposure \\
\hline
Source violations & 0 & 659 inputs \\
Delivery P/R & 100\%/100\% & 125 events \\
Processing P/R & 100\%/100\% & 59 events \\
Commitment P/R & 100\%/100\% & 12 events \\
State-conflict steps & 0 & 75 steps \\
\hline
\end{tabular}
\end{table}

% Suggested figure captions (figure choice remains under review):
% Proposal outcomes: All 49 proposal versions and subsequent outcomes of
% the 12 formed agreements. The panels have different denominators.
% Agreement timeline: All formed agreement versions aligned by scenario
% step across the three runs. Event markers denote agreement formation and
% observed execution, rejection, or cancellation; planned departures beyond
% the horizon are explicitly marked. R1/R2 are the primary/alternate routes.
'''
    (HERE / "main_experiment_ours.tex").write_text(manuscript)
    definitions='''# 统计定义与本批适用范围

本文件明确新增离线分析的范围，不更改原实验冻结指标，也不授权新增实验。

1. 结构化信息来源违规比例：一份决策输入存在至少一项已定义来源／归属矛盾，计一次；分母是所有已完成决策的输入包。不是按自然语言真假评分。核查项见 extract_results.py 的 input_errors。
2. 社会事件记录精确率／召回率：对消息投递、消息处理、可行约定分别计算，不把不同分母加权合成总分。投递和处理以消息 ID、收件人、时间步为键；可行约定以提议版本为键并核对时刻、参与者及资源字段。NA 不替换为 0 或 1。
3. 物理状态冲突步比例：一个完整时间步中出现任一已列明的成员位置、执行来源、出发时刻、车辆归属／容量／重复使用、随行成员照护字段、路线开放／容量矛盾，计一次；分母为全部完整时间步。本指标不声称覆盖未落盘的车辆内部状态和所有错误拒绝。
4. 提议结果分类互斥且穷尽本批 49 条提议；最终约定结果只在 12 条已形成约定中统计。等待回应不等于拒绝，未来窗口外不等于失败，提议版本不等于独立家庭。
5. 信息、事件和物理状态检查都只评价当前场景及记录范围。它们不构成人类行为真实性总分；外部框架结果不能通过本方法日志推算。
6. 本批有一对在同一步竞争同一辆车的提议。核对原运行需遵守实际回应处理顺序。未来外部方法采用另一合法调度时，应按允许的结果集合检查资源一致性，而非强制选中同一个提议 ID。
7. 复用三个已有完整运行不等于新增三次运行。合计分母表示已有日志暴露量；不将重复家庭或时间步当作独立统计样本，不画以 seed 为比较对象的正文图。
'''
    (HERE / "统计定义与范围.md").write_text(definitions)
    row={"method":"DisasterSociety", "households_per_run":24, "decision_residents_per_run":31,
         "existing_complete_runs":len(RESULT["runs"]), "input_source_violation_rate":TOTAL["input_packets_with_structural_source_violation"]/TOTAL["decisions"],
         "input_denominator":TOTAL["decisions"], "commitment_record_precision":TOTAL["event_records"]["feasible_agreement"]["precision"],
         "commitment_record_recall":TOTAL["event_records"]["feasible_agreement"]["recall"],
         "reference_commitment_events":TOTAL["event_records"]["feasible_agreement"]["tp"]+TOTAL["event_records"]["feasible_agreement"]["fn"],
         "world_conflict_step_rate":TOTAL["steps_with_world_conflict"]/TOTAL["steps"], "world_step_denominator":TOTAL["steps"],
         "scope":"retrospective structured record consistency; not human realism"}
    with (HERE / "method_comparison_row.csv").open("w", newline="") as f:
        w=csv.DictWriter(f, fieldnames=list(row)); w.writeheader(); w.writerow(row)


if __name__ == "__main__":
    for zh in (False, True):
        formation_figure(zh)
        timeline_figure(zh)
    documents()
    print(str(HERE / "本方法主实验结果.md"))
    print("Created 4 figures in PNG/PDF/SVG, Chinese report, metric definitions, and a LaTeX review fragment.")
