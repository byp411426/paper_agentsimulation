"""Validate independent Codex scores against frozen cases; do not generate scores."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from statistics import mean, median

from scripts.audit_archived_run import digest, dump, read_json


def collect(review: Path, manifest_path: Path, score_paths: list[Path]) -> dict:
    manifest = read_json(manifest_path)
    if digest(review / "rubric.md") != manifest["rubric_sha256"]:
        raise ValueError("Rubric changed after case selection")
    cases = {}
    for entry in manifest["cases"]:
        path = review / entry["file"]
        if digest(path) != entry["sha256"]:
            raise ValueError("Review case changed after selection: " + entry["case_id"])
        case = read_json(path)
        if case["case_id"] != entry["case_id"] or case["case_id"] in cases:
            raise ValueError("Duplicate or mismatched case identity")
        cases[case["case_id"]] = case
    scores = {}
    for path in score_paths:
        for row in read_json(path):
            cid, score = row["case_id"], row["score"]
            if cid not in cases or cid in scores:
                raise ValueError("Unknown or duplicate scored case: " + cid)
            if score is not None and (type(score) is not int or not 1 <= score <= 5):
                raise ValueError("Score must be an integer from 1 to 5, or null")
            if row["confidence"] not in ("high", "medium", "low") or not row["rationale_zh"].strip():
                raise ValueError("Missing score rationale or valid confidence")
            if score is not None and len(row["evidence"]) < 2:
                raise ValueError("A scored household requires at least two evidence entries")
            case = cases[cid]
            members = {m["resident_id"] for m in case["profile"]["member_profiles"]}
            steps = {s["step"] for s in case["steps"]}
            for evidence in row["evidence"]:
                if evidence["step"] not in steps or evidence["resident_id"] not in members:
                    raise ValueError("Evidence refers to a missing step or resident")
                if not evidence["assessment_zh"].strip():
                    raise ValueError("Empty evidence assessment")
            for field in ("input_issues", "limitations"):
                if not isinstance(row[field], list):
                    raise ValueError(field + " must be a list")
            scores[cid] = row
    if set(scores) != set(cases):
        raise ValueError("Missing cases; do not silently omit unscored households")
    values = [r["score"] for r in scores.values() if r["score"] is not None]
    return {"kind": "development_behavior_review", "selected_households": len(cases),
        "scored_households": len(values), "unscorable_households": len(cases) - len(values),
        "mean": mean(values) if values else None, "median": median(values) if values else None,
        "range": [min(values), max(values)] if values else None,
        "histogram": dict(sorted(Counter(values).items())),
        "rubric_sha256": manifest["rubric_sha256"],
        "review_manifest_sha256": digest(manifest_path),
        "score_files_sha256": {p.name: digest(p) for p in score_paths},
        "scores": [scores[cid] for cid in sorted(scores)],
        "limitations": ["每户一次评分；不同文件可以由不同独立会话评分，不代表每户多评审。",
                        "无评审一致性估计，无基线比较，不是方法优越性或真人预测证据。",
                        "程序仅核验格式、完整性、哈希及证据坐标，不能自动证实评审的语义判断。"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--review", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--scores", type=Path, nargs="+", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise FileExistsError("Existing summary is protected")
    result = collect(args.review, args.manifest, args.scores)
    dump(args.output, result)
    print({k: result[k] for k in ("selected_households", "scored_households", "mean", "range")})


if __name__ == "__main__":
    main()
