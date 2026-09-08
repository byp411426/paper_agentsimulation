"""E1 校准版 — empirical_prob(spec §5.3)+ E0b 匿名化对照。

每个受访者采样 k=8 次(T=0.7),撤离频率 = 校准概率 p:
  y_pred = (p >= 0.5), Brier/ECE 直接用 p(替代自报置信度)。

--anon 开关切换 E0b 匿名化 prompt(合成地名,只描述决策时刻可知的信息),
命名版与匿名版的 Δ 指标就是污染效应的量化。

运行:
  LLM_API_KEY=... python experiments/carr/e1_calibrated.py --n=335 --k=8
  LLM_API_KEY=... python experiments/carr/e1_calibrated.py --n=335 --k=8 --anon
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

SURVEY_CSV = "eventpacks/carr_2018/behavior/survey_clean.csv"
OUT_DIR = Path("experiments/carr/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

AGE_MAP = {1: "under 18", 2: "18-24", 3: "25-34", 4: "35-44", 5: "45-54",
           6: "55-64", 7: "65-74", 8: "75-84", 9: "85+", -1: "unknown"}
INCOME_MAP = {1: "<$10k", 2: "$10-15k", 3: "$15-25k", 4: "$25-35k", 5: "$35-50k",
              6: "$50-75k", 8: "$75-100k", 11: "$100-150k", 12: "$150-200k",
              13: ">$200k", -1: "unknown"}

STAY_REASONS = """Most residents did evacuate — but a real minority stayed. People stayed for concrete
reasons: to protect their property from fire or looting, because they lacked a vehicle or
money to leave, because they had livestock or pets they couldn't move, because of a work
obligation, because they distrusted the orders or believed the fire wouldn't reach them,
or because a household member had mobility limitations.

Decide the way THIS particular person realistically would, weighing their age, household,
and resources against those reasons to stay. Be realistic — do not assume everyone leaves,
and do not assume everyone stays.

Will you evacuate, or stay?

Answer ONLY with a JSON object:
{"action": "evacuate" or "stay", "reason": "brief first-person explanation", "confidence": 0-100}
"""


def build_prompt(row: pd.Series, anon: bool) -> str:
    age = AGE_MAP.get(int(row["age_group"]), "unknown")
    income = INCOME_MAP.get(int(row["income_bracket"]), "unknown")
    hh = int(row["household_size"])
    veh = int(row["vehicle_count"])
    person = f"""Your real circumstances:
- Your age: {age}
- People in your household: {hh}
- Vehicles you have: {veh}
- Annual household income: {income}
"""
    if anon:
        # E0b: 合成地名;只描述决策当晚可知的信息(不含"史上最惨烈"的后见之明)
        scene = """You are a specific resident of Cedarville, a city of about 90,000 people in rural
Northern California, on a hot, dry evening in late July. A fast-moving wildfire that
started in the hills this afternoon is spreading toward the city. Smoke is heavy,
officials are urging people in the western neighborhoods to leave, and the situation
is worsening by the hour.
"""
    else:
        # 命名版(与前一轮 E1 完全一致,保证可比)
        scene = """You are a specific resident of Redding, California on the evening of July 23, 2018.
The Carr Wildfire is spreading rapidly toward the city; smoke is heavy and officials are
urging people in western neighborhoods to leave. This will become one of the most
destructive fires in California history.
"""
    return scene + "\n" + person + "\n" + STAY_REASONS


def parse(text: str) -> int:
    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            r = json.loads(m.group(0))
            return 1 if str(r.get("action", "stay")).lower() == "evacuate" else 0
    except Exception:
        pass
    return 1 if "evacuate" in text.lower() else 0


async def sample_once(client, model, sem, prompt):
    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,          # 采样温度(empirical_prob 的前提)
                max_tokens=300,
            )
            return parse(resp.choices[0].message.content or "")
        except Exception:
            return -1  # 失败标记


async def respondent_prob(client, model, sem, row, k, anon, progress, total):
    prompt = build_prompt(row, anon)
    outs = await asyncio.gather(*[sample_once(client, model, sem, prompt)
                                  for _ in range(k)])
    valid = [o for o in outs if o >= 0]
    p = sum(valid) / len(valid) if valid else 0.5
    n_fail = len(outs) - len(valid)
    progress["done"] += 1
    if progress["done"] % 25 == 0:
        print(f"  ...{progress['done']}/{total}")
    return p, n_fail


def ece_from_proba(y_true, p, n_bins=10):
    """校准 ECE:bin 内 |实际撤离率 - 平均预测概率|(标准定义,直接用 p)。"""
    y_true = np.asarray(y_true, float)
    p = np.asarray(p, float)
    idx = np.clip((p * n_bins).astype(int), 0, n_bins - 1)
    e = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.sum():
            e += m.sum() / len(p) * abs(y_true[m].mean() - p[m].mean())
    return float(e)


async def main_async(args):
    from openai import AsyncOpenAI
    from sklearn.metrics import (f1_score, brier_score_loss, accuracy_score,
                                 confusion_matrix, roc_auc_score)

    df = pd.read_csv(SURVEY_CSV)
    if 0 < args.n < len(df):
        df = df.sample(n=args.n, random_state=42).reset_index(drop=True)
    arm = "anon" if args.anon else "named"
    print(f"✓ E1 校准版({arm}): {len(df)} 受访者 × k={args.k} 采样")

    base_url = os.environ.get("LLM_BASE_URL", "https://www.packyapi.com/v1")
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = args.model or os.environ.get("LLM_MODEL", "deepseek-v4-flash")
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    sem = asyncio.Semaphore(args.concurrency)
    print(f"  后端: {base_url} | 模型: {model} | 并发: {args.concurrency}\n")

    progress = {"done": 0}
    results = await asyncio.gather(*[
        respondent_prob(client, model, sem, row, args.k, args.anon, progress, len(df))
        for _, row in df.iterrows()])

    probs = np.array([r[0] for r in results])
    fails = int(sum(r[1] for r in results))
    total_calls = len(df) * args.k
    fail_rate = fails / total_calls
    y_true = df["evacuated"].values
    y_pred = (probs >= 0.5).astype(int)

    metrics = {
        "arm": arm, "model": model, "n": len(df), "k": args.k,
        "total_calls": total_calls, "failed_calls": fails,
        "fail_rate": round(fail_rate, 4),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro")),
        "brier": float(brier_score_loss(y_true, probs)),
        "ece": ece_from_proba(y_true, probs),
        "auc": float(roc_auc_score(y_true, probs)) if len(set(y_true)) > 1 else None,
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "pred_evac_rate": float(y_pred.mean()),
        "mean_prob": float(probs.mean()),
        "true_evac_rate": float(y_true.mean()),
    }

    print(f"\n{'='*60}")
    print(f"E1 校准版({arm}) — {model}, k={args.k}")
    print(f"{'='*60}")
    print(f"失败率: {fail_rate:.2%} ({fails}/{total_calls})" +
          ("  ⚠️ >1% 按预注册应作废重跑!" if fail_rate > 0.01 else "  ✓ <1%"))
    print(f"Accuracy: {metrics['accuracy']:.3f}")
    print(f"F1 (macro): {metrics['f1_macro']:.3f}")
    print(f"Brier: {metrics['brier']:.3f}")
    print(f"ECE: {metrics['ece']:.3f}")
    print(f"AUC: {metrics['auc']:.3f}")
    print(f"平均预测概率: {metrics['mean_prob']:.3f} | 真实撤离率: {metrics['true_evac_rate']:.3f}")
    cm = np.array(metrics["confusion_matrix"])
    print(f"\n混淆矩阵(阈值0.5):")
    print(f"            预测:不撤离  预测:撤离")
    print(f"真实:不撤离    {cm[0,0]:6d}    {cm[0,1]:6d}")
    print(f"真实:撤离      {cm[1,0]:6d}    {cm[1,1]:6d}")

    out = OUT_DIR / f"e1_calibrated_{arm}_{model.replace('/', '_')}.json"
    out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    detail = df[["respondent_id", "evacuated", "age_group", "household_size",
                 "vehicle_count", "income_bracket"]].copy()
    detail["p_evacuate"] = probs
    detail["pred"] = y_pred
    detail_path = OUT_DIR / f"e1_calibrated_{arm}_{model.replace('/', '_')}_predictions.csv"
    detail.to_csv(detail_path, index=False)
    print(f"\n✓ 指标: {out}")
    print(f"✓ 逐行预测: {detail_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=335)
    p.add_argument("--k", type=int, default=8)
    p.add_argument("--model", default=None)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--anon", action="store_true", help="E0b 匿名化 arm")
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
