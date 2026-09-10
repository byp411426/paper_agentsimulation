"""Export complete household histories with method/model names removed. No judging API."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


RUBRIC = """# 行为合理性试评分规范 v1（评分前固定）

每个案例是一个合成住户的完整仿真过程。只评价行为过程是否说得通；不预测真人，不评价代码实现优劣。

每户给一个 1—5 的整数总体评分，不做四项加权：
1：主要行为过程存在严重明确矛盾，难以根据当时输入解释。
2：反复或关键环节出现明显无依据行为，但仍有部分可解释过程。
3：整体基本可解释，存在明显的理由不足或前后脱节。
4：大部分选择与信息、处境及历史一致，仅有局部轻微不足。
5：没有发现明显行为矛盾，重要选择和变化都有输入或上下文依据。
完全没有决策或资料不足以判断时为 null，说明缺什么。没有社会互动时该方面不适用，不能自动扣分或加分。

考虑四类依据：居民当时知道什么；家庭的资源、照护、角色等约束；计划变化及执行反馈的连贯性；互动、分歧与承诺的衔接。
撤离、等待、拒绝、分开行动、误信转述本身均不自动奖惩。不能要求居民事前知道之后的封路、灾情或其他人的私有信息。
区分发送、实际送达、处理、接受，以及请求和实际执行。没有唤醒／没有模型决策的时段不等于主动选择等待。

固定世界限制：车辆出发后瞬时转移至安全区；到达安全区的居民不再决策；不支持步行出发、回程接送。
求助和提供帮助是表达行为，本身不会完成接送。不能要求模型用不存在的功能救援，也不能把求助当作完成救援。
world_* 和 household_commitments 是供核验的事实，不意味着每名居民都知道它们；以 decision_inputs 为居民的实际输入。

保留原始背景矛盾。遇到独居标签与人数冲突，单列 input_issues，评估其是否影响判断；不要偷偷改输入或把这种输入缺陷算作模型行为错误。
不因自然语言有小瑕疵就大幅降分，不因看似合作、成功撤离或文笔好就给高分。每户至少给两条具体记录证据；证据不足不能编造。
只对所分配的案例评分，不读取其他评审结论、模型名称、论文、方法代码或程序错误率。此为单次试评分，没有校准过的评审一致性证据。

输出 JSON 数组，每项字段：case_id、score、confidence（high/medium/low）、rationale_zh、evidence（step、resident_id、assessment_zh）、input_issues、limitations。
"""


def export_review(audit, output: Path, household_ids: list[str]) -> dict:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Existing review inputs are protected: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / "rubric.md").write_text(RUBRIC, encoding="utf-8")
    mapping = {hid: f"H{i + 1:03}" for i, hid in enumerate(sorted(audit.profile_h))}
    for hid, p in sorted(audit.profile_h.items()):
        for j, m in enumerate(p["member_profiles"]):
            mapping[m["resident_id"]] = f"{mapping[hid]}_R{j + 1}"
    cases = []
    for i, hid in enumerate(household_ids):
        trace = audit.household_trace(hid)
        for step in trace["steps"]:
            step.pop("agents_before", None)
            step.pop("agents_after", None)
            step.pop("source", None)
        trace.pop("selection_rule", None)
        trace["case_id"] = f"CASE_{i + 1:03}"
        trace["evidence_status"] = audit.provenance.get("kind", "real_model_run; original_inputs_preserved")
        raw = json.dumps(trace, ensure_ascii=False)
        for old, new in sorted(mapping.items(), key=lambda pair: -len(pair[0])):
            raw = raw.replace(old, new)
        raw = raw.replace(str(audit.cfg["run"]["run_id"]), "RUN")
        path = output / f"case_{i + 1:03}.json"
        path.write_text(raw + "\n", encoding="utf-8")
        cases.append({"case_id": trace["case_id"], "household_id": hid,
                      "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return {"selection": "supplied household IDs fixed before scoring", "selected_households": len(household_ids),
            "rubric_sha256": hashlib.sha256(RUBRIC.encode()).hexdigest(), "cases": cases}
