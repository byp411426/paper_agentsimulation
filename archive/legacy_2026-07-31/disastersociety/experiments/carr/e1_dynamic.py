"""[ARCHIVED] Carr 情境化一次性 LLM 基线（历史文件名为 e1_dynamic）。

把 335 个真实问卷受访者逐个实例化为 agent,喂真实人口学属性 + 动态火情/预警,
让 LLM 做撤离决策,和受访者本人的真实选择对比。

每名受访者只调用一次模型。本脚本不实现多步记忆、反馈或规划，不能称为
DisasterSociety 完整动态模型。当前 evacuated 还是 warned_official 的占位
标签，现有结果为 INVALID_FOR_CLAIM。

对比三个基线:
  - 传统 ML(LR/RF): F1=0.594
  - LLM 静态(单次问答): 见 llm_static 结果
  - LLM 动态(本脚本): 加入火情逼近的时序上下文

运行:
  LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=deepseek-v4-flash \
    python experiments/carr/e1_dynamic.py --n=335 --concurrency=8
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


def build_prompt(row: pd.Series) -> str:
    """真实严重场景 + 明确留守理由(arm-honest:不含问卷自报风险感知)。

    场景匹配真实 Carr 大火(史上最惨烈之一,多数区域下达撤离令)。
    科学难点是识别"即使在强制令下仍留守的少数人"。prompt 明确给出真实留守
    理由(源自问卷 Q10.1),让 LLM 对合适的人口画像判断"留守",避免全体撤离塌缩。
    """
    age = AGE_MAP.get(int(row["age_group"]), "unknown")
    income = INCOME_MAP.get(int(row["income_bracket"]), "unknown")
    hh = int(row["household_size"])
    veh = int(row["vehicle_count"])
    return f"""You are a specific resident of Redding, California on the evening of July 23, 2018.
The Carr Wildfire is spreading rapidly toward the city; smoke is heavy and officials are
urging people in western neighborhoods to leave. This will become one of the most
destructive fires in California history.

Your real circumstances:
- Your age: {age}
- People in your household: {hh}
- Vehicles you have: {veh}
- Annual household income: {income}

Most residents did evacuate — but a real minority stayed. People stayed for concrete
reasons: to protect their property from fire or looting, because they lacked a vehicle or
money to leave, because they had livestock or pets they couldn't move, because of a work
obligation, because they distrusted the orders or believed the fire wouldn't reach them,
or because a household member had mobility limitations.

Decide the way THIS particular person realistically would, weighing their age, household,
and resources against those reasons to stay. Be realistic — do not assume everyone leaves,
and do not assume everyone stays.

Will you evacuate, or stay?

Answer ONLY with a JSON object:
{{"action": "evacuate" or "stay", "reason": "brief first-person explanation", "confidence": 0-100}}
"""


def parse(text: str) -> tuple[int, float]:
    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            r = json.loads(m.group(0))
            act = 1 if str(r.get("action", "stay")).lower() == "evacuate" else 0
            conf = float(r.get("confidence", 50)) / 100.0
            return act, conf
    except Exception:
        pass
    low = text.lower()
    return (1, 0.5) if "evacuate" in low else (0, 0.5)


async def decide(client, model, sem, row):
    prompt = build_prompt(row)
    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,      # 可复现
                max_tokens=300,
            )
            text = resp.choices[0].message.content or ""
            return parse(text)
        except Exception as e:
            print(f"  ⚠️ {row['respondent_id']} 失败: {e}")
            return 0, 0.5


def ece(y_true, y_proba, y_pred, n_bins=10):
    y_true = np.asarray(y_true); y_proba = np.asarray(y_proba); y_pred = np.asarray(y_pred)
    idx = np.clip((y_proba * n_bins).astype(int), 0, n_bins - 1)
    e = 0.0
    for b in range(n_bins):
        m = idx == b
        if m.sum():
            e += m.sum() / len(y_true) * abs((y_true[m] == y_pred[m]).mean() - y_proba[m].mean())
    return float(e)


async def main_async(args):
    from openai import AsyncOpenAI
    from sklearn.metrics import f1_score, brier_score_loss, accuracy_score, confusion_matrix

    df = pd.read_csv(SURVEY_CSV)
    if 0 < args.n < len(df):
        df = df.sample(n=args.n, random_state=42).reset_index(drop=True)
    print(f"✓ {len(df)} 个受访者 respondent-in-the-loop")

    base_url = os.environ.get("LLM_BASE_URL", "https://www.packyapi.com/v1")
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = args.model or os.environ.get("LLM_MODEL", "deepseek-v4-flash")
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    sem = asyncio.Semaphore(args.concurrency)
    print(f"  后端: {base_url} | 模型: {model} | 并发: {args.concurrency}\n")

    # 并发决策(gather 保证顺序对齐),带进度计数
    progress = {"done": 0}

    async def decide_tracked(row):
        r = await decide(client, model, sem, row)
        progress["done"] += 1
        if progress["done"] % 25 == 0:
            print(f"  ...{progress['done']}/{len(df)}")
        return r

    results = await asyncio.gather(*[decide_tracked(row) for _, row in df.iterrows()])

    preds = [r[0] for r in results]
    confs = [r[1] for r in results]
    y_true = df["evacuated"].values
    y_pred = np.array(preds)
    y_proba = np.array(confs)

    metrics = {
        "model": model,
        "n": len(df),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "f1_macro": float(f1_score(y_true, y_pred, average="macro")),
        "brier": float(brier_score_loss(y_true, y_proba)),
        "ece": ece(y_true, y_proba, y_pred),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
        "pred_evac_rate": float(y_pred.mean()),
        "true_evac_rate": float(y_true.mean()),
    }

    print(f"\n{'='*60}")
    print(f"Carr 情境化一次性 LLM 基线 — {model}")
    print(f"{'='*60}")
    print(f"样本数: {metrics['n']}")
    print(f"Accuracy: {metrics['accuracy']:.3f}")
    print(f"F1 (macro): {metrics['f1_macro']:.3f}")
    print(f"Brier: {metrics['brier']:.3f}")
    print(f"ECE: {metrics['ece']:.3f}")
    print(f"预测撤离率: {metrics['pred_evac_rate']:.1%} vs 真实: {metrics['true_evac_rate']:.1%}")
    cm = np.array(metrics["confusion_matrix"])
    print(f"\n混淆矩阵:")
    print(f"            预测:不撤离  预测:撤离")
    print(f"真实:不撤离    {cm[0,0]:6d}    {cm[0,1]:6d}")
    print(f"真实:撤离      {cm[1,0]:6d}    {cm[1,1]:6d}")

    out = OUT_DIR / f"e1_dynamic_{model.replace('/', '_')}.json"
    out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"\n✓ 已保存: {out}")

    # 保存详细预测
    df_out = df[["respondent_id", "evacuated"]].copy()
    df_out["llm_pred"] = preds
    df_out["llm_confidence"] = confs
    detail = OUT_DIR / f"e1_dynamic_{model.replace('/', '_')}_predictions.csv"
    df_out.to_csv(detail, index=False)
    print(f"✓ 详细预测: {detail}")

    # 对比基线
    base = Path("experiments/baselines/results/traditional_baselines.json")
    if base.exists():
        b = json.loads(base.read_text())
        print(f"\n{'='*60}")
        print(f"基线对比")
        print(f"{'='*60}")
        print(f"{'模型':<28}{'F1':<10}{'Brier':<10}{'ECE':<10}")
        print(f"{'-'*58}")
        print(f"{'情境化一次性 LLM':<24}{metrics['f1_macro']:<10.3f}{metrics['brier']:<10.3f}{metrics['ece']:<10.3f}")
        print(f"{'LogisticRegression':<28}{b['LogisticRegression']['f1_macro']:<10.3f}{b['LogisticRegression']['brier']:<10.3f}{b['LogisticRegression'].get('ece',0):<10.3f}")
        print(f"{'RandomForest':<28}{b['RandomForest']['f1_macro']:<10.3f}{b['RandomForest']['brier']:<10.3f}{b['RandomForest'].get('ece',0):<10.3f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=335)
    p.add_argument("--model", default=None)
    p.add_argument("--concurrency", type=int, default=8)
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
