"""Join a complete real run, program checks, and independent household scores."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from scripts.audit_archived_run import digest, dump, read_json, read_jsonl
from scripts.collect_behavior_scores import collect


def summarize(run: Path, evaluation: Path, score_paths: list[Path], output: Path) -> dict:
    status = read_json(run / "execution_status.json")
    provenance = read_json(run / "provenance.json")
    audit = read_json(evaluation / "audit_results.json")
    manifest = read_json(evaluation / "review_manifest.json")
    if status["status"] != "VALID" or status["completed_steps"] != status["planned_steps"]:
        raise ValueError("A complete VALID run is required")
    if provenance.get("backend") != "real":
        raise ValueError("Do not label a scripted fixture as a real-model pilot")
    profiles = read_jsonl(run / "selected_profiles.jsonl")
    households = {p["household_id"] for p in profiles}
    if ({c["household_id"] for c in manifest["cases"]} != households
            or len(households) != audit["households"]):
        raise ValueError("Behavior review and program metrics must cover the same households")
    sources = read_json(evaluation / "source_manifest.json")["files_sha256"]
    if any(digest(run / name) != expected for name, expected in sources.items()):
        raise ValueError("Source run changed after program evaluation")
    behavior = collect(evaluation / "review_inputs", evaluation / "review_manifest.json", score_paths)
    calls = read_jsonl(run / "llm_calls.jsonl")
    member_household = {m["resident_id"]: p["household_id"] for p in profiles for m in p["member_profiles"]}
    decisions = [d for e in read_jsonl(run / "events/events.jsonl") for d in e["decisions"]]
    coverage = []
    for case in manifest["cases"]:
        rows = [d for d in decisions if member_household[d["agent"]] == case["household_id"]]
        coverage.append({"case_id": case["case_id"], "decisions": len(rows),
            "proposals": sum(bool(d["decision"].get("party_proposal")) for d in rows),
            "message_responses": sum(len(d["decision"].get("message_responses", [])) for d in rows),
            "evacuation_requests": sum(d["decision"]["action"] == "evacuate" for d in rows),
            "rejected_requests": sum(d["outcome"]["status"] == "rejected" for d in rows)})
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Existing results are protected")
    output.mkdir(parents=True, exist_ok=True)
    result = {"kind": "completed_real_model_development_pilot", "households": len(households),
        "seed": provenance["seed"], "completed_steps": status["completed_steps"],
        "decision_count": audit["decision_count"], "wall_clock_seconds": status.get("wall_clock_seconds"),
        "gateway": status["gateway"], "call_status_counts": dict(Counter(c["status"] for c in calls)),
        "schema_repair_requests": sum(c.get("schema_repairs", 0) for c in calls if c["status"] == "ok"),
        "behavior": behavior, "metrics": audit["metrics"], "additional_checks": audit["additional_checks"],
        "behavior_opportunities": coverage,
        "input_checks": audit["input_checks"], "terminal_export_checks": audit["terminal_export_checks"],
        "source_identity": audit["source_identity"], "formal_scenario_pass_rate": None,
        "formal_method_comparison": False,
        "cost_note": "运行预算估值，不是服务商实际账单；不含另行完成的接口探测。"}
    dump(output / "results.json", result)
    mean_text = f"{behavior['mean']:.3f} / 5" if behavior["mean"] is not None else "N/A"
    rows = [f"| 行为合理性 | {mean_text} | {behavior['scored_households']} 户可评分 |"]
    for name, label in (("information", "观察／接收记录错误率"), ("consensus", "家庭共识状态错误率"),
                        ("execution", "意图与执行状态混淆率")):
        m = audit["metrics"][name]
        value = f"{m['errors']} / {m['checked']}" if m["rate"] is not None else "N/A"
        rows.append(f"| {label} | {value} | 检查 {m['checked']} 条；无法核验 {m['unverifiable']} 条 |")
    rows.append("| 正式场景过程检查通过率 | 未实施 | 不用软件回归测试冒充正式场景实验 |")
    text = f"""# 修复后的真实模型试验结果

本次是新生成的 {len(households)} 户、{status['completed_steps']} 步完整真实模型运行，seed {provenance['seed']}，状态 VALID。
实际产生 {audit['decision_count']} 次居民决策；成功逻辑模型调用 {status['gateway']['n_ok']} 次，缓存 {status['gateway']['n_cache']} 次，失败 {status['gateway']['n_failed']} 次，规则降级 {status['gateway']['n_fallback']} 次。

| 指标 | 结果 | 覆盖 |
|---|---|---|
""" + "\n".join(rows) + "\n\n## 逐户行为意见\n\n"
    for row in behavior["scores"]:
        score = "N/A" if row["score"] is None else f"{row['score']} / 5"
        text += f"- **{row['case_id']}：{score}**。{row['rationale_zh']}\n"
    text += "\n## 实际经历了哪些行为情形\n\n这些是样本覆盖说明，不是越高越好的评价分数。\n\n| 住户 | 决策次数 | 提案次数 | 消息回应次数 | 撤离请求 | 被拒绝的行动请求 |\n|---|---:|---:|---:|---:|---:|\n"
    for row in coverage:
        text += "| " + " | ".join(str(row[k]) for k in ("case_id", "decisions", "proposals", "message_responses", "evacuation_requests", "rejected_requests")) + " |\n"
    text += """
## 结论范围

已完成真实模型生成、完整日志、程序核验、独立行为评分和结果汇总这一轮流程。
这是一轮小规模开发试验，没有基线对照或跨种子重复，不能写成方法优越性结论。
每户一次独立评分，没有评审一致性估计；分数不是真人预测准确率。
同样的家庭来自不同规模的运行时，社会网络和信息分配也可能变化，不能直接用旧 24 户子集分数估计代码修复的因果效果。
程序三项错误率的具体范围及全局资源、非撤离、导出检查均保留在 results.json；不能只看主表而忽略辅助检查中的错误。
执行协助、等待、拒绝和撤离成功本身不自动奖惩；行为意见须结合每户实际输入和量表理解。
"""
    (output / "results.md").write_text(text, encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--evaluation", type=Path, required=True)
    ap.add_argument("--scores", type=Path, nargs="+", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = summarize(args.run, args.evaluation, args.scores, args.output)
    print({"households": result["households"], "decisions": result["decision_count"],
           "behavior_mean": result["behavior"]["mean"], "metrics": result["metrics"]})


if __name__ == "__main__":
    main()
