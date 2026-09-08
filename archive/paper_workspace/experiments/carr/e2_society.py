"""E2 群体验证 — 真实 LLM 社会仿真,多种子(spec E2 + 统计总协议)。

自包含脚本(不依赖旧 runner):
  合成人口(PUMS 采样) → 校准送达模型 → LLM 撤离决策 → 群体指标
  每个种子输出: 送达率 / 撤离率 / 渠道 L1 / 撤离时序曲线
  多种子报告 mean ± std。

校准送达参数(见 RESULTS.md): device=0.85, wea=0.75, awake=0.8, asleep=0.3
Carr 火灾 13:15 开始,step=小时;单条强制令在 step 6(19:15,清醒时段)。

运行:
  LLM_API_KEY=... python experiments/carr/e2_society.py --n=1000 --seeds 41 42 43 44 45
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
from pathlib import Path

import numpy as np
import pandas as pd

SURVEY_CSV = "eventpacks/carr_2018/behavior/survey_clean.csv"
PUMS_CSV = "eventpacks/carr_2018/population/pums.csv"
OUT_DIR = Path("experiments/carr/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ===== 校准后的送达参数(E2 已验证 L1=0.113 的配置) =====
DELIVERY = dict(device_ownership=0.85, wea_coverage=0.75,
                awake_check_prob=0.8, asleep_check_prob=0.3,
                day_start_hour=8, day_end_hour=22)
FIRE_START_HOUR = 13          # 13:15 起火
WARNING_STEP = 6              # 强制令 19:15
MAX_STEP = 24                 # 跑 24 小时足够(撤离集中在预警后数小时)

STAY_REASONS = """Most residents did evacuate — but a real minority stayed. People stayed for concrete
reasons: to protect their property from fire or looting, because they lacked a vehicle or
money to leave, because they had livestock or pets they couldn't move, because of a work
obligation, because they distrusted the orders or believed the fire wouldn't reach them,
or because a household member had mobility limitations.

Decide the way THIS particular household realistically would. Be realistic — do not
assume everyone leaves, and do not assume everyone stays.

Will your household evacuate now, or stay?

Answer ONLY with a JSON object:
{"action": "evacuate" or "stay", "reason": "brief explanation", "confidence": 0-100}
"""


def build_prompt(demo: dict, warned: bool, step: int) -> str:
    hour = (FIRE_START_HOUR + step) % 24
    status = ("You just received an official MANDATORY EVACUATION order for your area "
              "via emergency alert." if warned else
              "You have not received any official order, but you can see heavy smoke "
              "to the west and neighbors are talking about the fire.")
    return f"""You are the head of a specific household in Redding, California on the evening of
July 23, 2018 (around {hour}:00). The Carr Wildfire is spreading toward the city.

Your household:
- Householder age group: {demo.get('age', 'unknown')}
- Household size: {demo.get('household_size', 2)}
- Vehicles: {demo.get('vehicles', 1)}
- Income bracket: {demo.get('income', 'unknown')}

{status}

{STAY_REASONS}"""


def delivery_ok(params: dict, step: int, rng: random.Random) -> bool:
    hour = (FIRE_START_HOUR + step) % 24
    awake = params["day_start_hour"] <= hour < params["day_end_hour"]
    t = params["awake_check_prob"] if awake else params["asleep_check_prob"]
    p = params["device_ownership"] * params["wea_coverage"] * t
    return rng.random() < p


def parse(text: str) -> int:
    try:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return 1 if str(json.loads(m.group(0)).get("action", "stay")).lower() == "evacuate" else 0
    except Exception:
        pass
    return 1 if "evacuate" in text.lower() else 0


async def llm_decide(client, model, sem, prompt):
    async with sem:
        try:
            resp = await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": prompt}],
                temperature=0.7, max_tokens=300)
            return parse(resp.choices[0].message.content or ""), False
        except Exception:
            return -1, True  # 失败


def survey_channel_truth() -> dict:
    df = pd.read_csv(SURVEY_CSV)
    c = df["heard_from"].value_counts()
    n = len(df)
    return {k: c.get(k, 0) / n for k in ("official", "neighbor", "social", "none")}


async def run_one_seed(seed: int, n: int, client, model, sem) -> dict:
    # 合成人口(直接 PUMS 采样,与 carr_loader 一致)
    pums = pd.read_csv(PUMS_CSV)
    hh = pums.sample(n=n, replace=True, random_state=seed).reset_index(drop=True)
    demos = [dict(age=r.get("householder_age_group"), income=r.get("household_income"),
                  household_size=r.get("household_size"), vehicles=r.get("vehicle_count"))
             for _, r in hh.iterrows()]

    rng = random.Random(seed)
    warned: set[int] = set()
    evacuated: dict[int, int] = {}          # idx -> evac step
    n_fail = 0
    n_calls = 0

    for step in range(MAX_STEP):
        # ① 预警送达(仅 step 6 发布;每人只判定一次)
        if step == WARNING_STEP:
            for i in range(n):
                if i not in evacuated and delivery_ok(DELIVERY, step, rng):
                    warned.add(i)

        # ② 唤醒:收到预警且未撤离的家庭决策(收到当步 + 后续 2 步再考虑一次)
        to_decide = [i for i in warned if i not in evacuated
                     and step in (WARNING_STEP, WARNING_STEP + 2)]
        if not to_decide:
            continue

        prompts = [build_prompt(demos[i], warned=True, step=step) for i in to_decide]
        outs = await asyncio.gather(*[llm_decide(client, model, sem, p) for p in prompts])
        n_calls += len(outs)
        for i, (act, failed) in zip(to_decide, outs):
            if failed:
                n_fail += 1
                continue
            if act == 1:
                evacuated[i] = step

    # ===== 指标 =====
    sim_channels = {
        "official": len(warned) / n,
        "neighbor": 0.0, "social": 0.0,      # 本版无社交传播(消融点,论文注明)
        "none": (n - len(warned)) / n,
    }
    truth = survey_channel_truth()
    l1 = sum(abs(sim_channels[k] - truth[k]) for k in truth)

    curve = {}
    for s in range(MAX_STEP):
        curve[s] = sum(1 for v in evacuated.values() if v <= s) / n

    return dict(seed=seed, n=n, delivered=len(warned), delivered_rate=len(warned) / n,
                evacuated=len(evacuated), evac_rate=len(evacuated) / n,
                channel_l1=l1, llm_calls=n_calls, llm_failures=n_fail,
                fail_rate=(n_fail / n_calls if n_calls else 0.0), curve=curve)


async def main_async(args):
    from openai import AsyncOpenAI
    base_url = os.environ.get("LLM_BASE_URL", "https://www.packyapi.com/v1")
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = args.model or os.environ.get("LLM_MODEL", "deepseek-v4-flash")
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    sem = asyncio.Semaphore(args.concurrency)

    truth = survey_channel_truth()
    print(f"E2 多种子社会仿真 — {model} | n={args.n} | seeds={args.seeds}")
    print(f"问卷渠道真值: {truth}\n")

    results = []
    for seed in args.seeds:
        print(f"--- seed {seed} ---")
        r = await run_one_seed(seed, args.n, client, model, sem)
        print(f"  送达 {r['delivered_rate']:.1%} | 撤离 {r['evac_rate']:.1%} | "
              f"L1={r['channel_l1']:.3f} | 调用 {r['llm_calls']} | 失败率 {r['fail_rate']:.2%}")
        results.append(r)

    rates = np.array([r["evac_rate"] for r in results])
    l1s = np.array([r["channel_l1"] for r in results])
    dels = np.array([r["delivered_rate"] for r in results])
    fails = np.array([r["fail_rate"] for r in results])

    summary = dict(
        model=model, n=args.n, seeds=args.seeds,
        survey_truth=dict(evac_rate=0.743, channels=truth),
        delivered_rate_mean=float(dels.mean()), delivered_rate_std=float(dels.std()),
        evac_rate_mean=float(rates.mean()), evac_rate_std=float(rates.std()),
        channel_l1_mean=float(l1s.mean()), channel_l1_std=float(l1s.std()),
        fail_rate_max=float(fails.max()),
        per_seed=results,
    )

    print(f"\n{'='*60}")
    print(f"E2 汇总({len(args.seeds)} 种子)")
    print(f"{'='*60}")
    print(f"送达率:   {dels.mean():.1%} ± {dels.std():.1%}  (问卷 official 46.6%)")
    print(f"撤离率:   {rates.mean():.1%} ± {rates.std():.1%}  (问卷 74.3%)")
    print(f"渠道 L1:  {l1s.mean():.3f} ± {l1s.std():.3f}  (阈值 <0.2 优秀)")
    print(f"最大失败率: {fails.max():.2%}" + ("  ⚠️ 超1%" if fails.max() > 0.01 else "  ✓"))

    out = OUT_DIR / f"e2_society_{model.replace('/', '_')}.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n✓ 已保存: {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=1000)
    p.add_argument("--seeds", type=int, nargs="+", default=[41, 42, 43, 44, 45])
    p.add_argument("--model", default=None)
    p.add_argument("--concurrency", type=int, default=10)
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
