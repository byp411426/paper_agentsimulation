"""E3 机制消融矩阵 v2(spec v2 §3 E3)— 证明每个设计机制的因果贡献。

完整模型 = 官方推送 + 媒体 + 邻居转发 + 社媒 + 环境线索(浓烟) + LLM 家庭决策。

校准/验证切分(论文写明):
  * 信息层参数(媒体/转发/社媒率)按问卷渠道边际做一次粗校准 —— 输入侧;
  * 决策层(LLM prompt/温度)完全不动 —— 撤离率与时序是样本外验证目标。

配对种子:hash 抽签(同 seed 同机制同人 → 跨 arm 结果一致),arm 间差异只来自被拆机制。

arms:
  full        推送+媒体+转发+社媒+环境, LLM
  no_relay    拆邻居转发
  no_media    拆媒体+社媒
  no_env      拆环境线索
  push_only   只留推送(=已发表 E2 配置)
  rule        全渠道, 规则决策(令0.80/0.30, 环境0.40/0.15)
  no_demo     全渠道, LLM 无人口学

运行:
  LLM_API_KEY=... python experiments/carr/e3_ablation.py --n 500 --seeds 41 42 43 44 45
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

PUMS_CSV = "eventpacks/carr_2018/population/pums.csv"
TRUTH_JSON = Path("experiments/carr/results/channel_truth_5cat.json")
OUT_DIR = Path("experiments/carr/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ===== 时间线 =====
FIRE_START_HOUR = 13
WARNING_STEP = 6              # 强制令 19:15
MAX_STEP = 24
MEDIA_WINDOW = range(6, 19)
ENV_WINDOW = range(8, 19)     # 21:15 起火光浓烟大范围可见

# ===== 送达参数(E2 已校准并验证) =====
DELIVERY = dict(device_ownership=0.85, wea_coverage=0.75,
                awake_check_prob=0.8, asleep_check_prob=0.3,
                day_start_hour=8, day_end_hour=22)

# ===== 信息层参数(按渠道边际粗校准;决策层不动) =====
P_MEDIA = 0.007     # 每步经电视/广播首次得知令(目标边际 media-first ≈ 4.2%)
P_SOCIAL = 0.002    # 每步经社媒首次得知(目标 ≈ 0.9%)
P_RELAY = 0.02      # 知情者对每邻居转发一次(目标 neighbor-first ≈ 2.4%)
P_ENV = 0.04        # 每步因浓烟自行警觉(无令;真值归入 none 类)
K_NEIGHBORS = 6
RULE_ORDER = (0.80, 0.30)   # 规则 arm: 收到令(首判, 复判)
RULE_ENV = (0.40, 0.15)     # 规则 arm: 仅环境线索

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

CHANNEL_STATUS = {
    "official_push": "You just received an official MANDATORY EVACUATION order for your "
                     "area via an emergency alert on your phone.",
    "media": "You just saw on live TV/radio news that a mandatory evacuation order has "
             "been issued for your part of the city.",
    "neighbor": "A neighbor just called you, saying an evacuation order is out for your "
                "area and that they are leaving now.",
    "social": "You just saw posts on social media saying your area is under an "
              "evacuation order, with photos of the approaching fire.",
    "environment": "You have NOT received any official order, but heavy smoke and an "
                   "orange glow are now visible from your home, ash is falling, and "
                   "some neighbors are packing their cars.",
}
ORDER_CHANNELS = {"official_push", "media", "neighbor", "social"}


def draw(seed: int, mech: str, a: int, step: int = 0) -> float:
    h = hashlib.sha256(f"{seed}|{mech}|{a}|{step}".encode()).hexdigest()
    return int(h, 16) % (2**32) / 2**32


def hour_of(step: int) -> int:
    return (FIRE_START_HOUR + step) % 24


def is_awake(step: int) -> bool:
    return DELIVERY["day_start_hour"] <= hour_of(step) < DELIVERY["day_end_hour"]


def push_delivered(seed: int, agent: int) -> bool:
    t = (DELIVERY["awake_check_prob"] if is_awake(WARNING_STEP)
         else DELIVERY["asleep_check_prob"])
    p = DELIVERY["device_ownership"] * DELIVERY["wea_coverage"] * t
    return draw(seed, "push", agent) < p


def neighbor_graph(seed: int, n: int, k: int = K_NEIGHBORS) -> list[list[int]]:
    import networkx as nx
    g = nx.random_regular_graph(k, n, seed=seed)
    return [sorted(g.neighbors(i)) for i in range(n)]


def build_prompt(demo: dict | None, channel: str, step: int) -> str:
    status = CHANNEL_STATUS[channel]
    if demo is None:
        hh_block = "You are the head of a typical household in Redding.\n"
    else:
        hh_block = f"""Your household:
- Householder age group: {demo.get('age', 'unknown')}
- Household size: {demo.get('household_size', 2)}
- Vehicles: {demo.get('vehicles', 1)}
- Income bracket: {demo.get('income', 'unknown')}
"""
    return f"""You are the head of a specific household in Redding, California on the evening of
July 23, 2018 (around {hour_of(step)}:00). The Carr Wildfire is spreading toward the city.

{hh_block}
{status}

{STAY_REASONS}"""


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
            return -1, True


ARMS = {
    #            media  relay  env    llm   demo
    "full":      (True,  True,  True,  True,  True),
    "no_relay":  (True,  False, True,  True,  True),
    "no_media":  (False, True,  True,  True,  True),
    "no_env":    (True,  True,  False, True,  True),
    "push_only": (False, False, False, True,  True),
    "rule":      (True,  True,  True,  False, True),
    "no_demo":   (True,  True,  True,  True,  False),
}


async def run_arm_seed(arm: str, seed: int, n: int, client, model, sem) -> dict:
    use_media, use_relay, use_env, use_llm, use_demo = ARMS[arm]

    pums = pd.read_csv(PUMS_CSV)
    hh = pums.sample(n=n, replace=True, random_state=seed).reset_index(drop=True)
    demos = [dict(age=r.get("householder_age_group"), income=r.get("household_income"),
                  household_size=r.get("household_size"), vehicles=r.get("vehicle_count"))
             for _, r in hh.iterrows()]
    nbrs = neighbor_graph(seed, n)

    informed: dict[int, tuple[int, str]] = {}
    evacuated: dict[int, int] = {}
    relayed: set[int] = set()
    pending: dict[int, list[int]] = {}
    n_calls = n_fail = 0

    def inform(i: int, step: int, ch: str):
        if i not in informed:
            informed[i] = (step, ch)
            pending[i] = [step, step + 2]

    for step in range(MAX_STEP):
        if step == WARNING_STEP:
            for i in range(n):
                if push_delivered(seed, i):
                    inform(i, step, "official_push")

        if use_media and step in MEDIA_WINDOW and is_awake(step):
            for i in range(n):
                if i in informed:
                    continue
                if draw(seed, "media", i, step) < P_MEDIA:
                    inform(i, step, "media")
                elif draw(seed, "social", i, step) < P_SOCIAL:
                    inform(i, step, "social")

        if use_relay:
            for i, (s0, _) in list(informed.items()):
                if step == s0 + 1 and i not in relayed and informed[i][1] in ORDER_CHANNELS:
                    relayed.add(i)
                    for j in nbrs[i]:
                        if j not in informed and draw(seed, "relay", i * n + j) < P_RELAY:
                            inform(j, step, "neighbor")

        if use_env and step in ENV_WINDOW:
            for i in range(n):
                if i not in informed and draw(seed, "env", i, step) < P_ENV:
                    inform(i, step, "environment")

        due = [i for i, ss in pending.items() if step in ss and i not in evacuated]
        if not due:
            continue

        if use_llm:
            prompts = [build_prompt(demos[i] if use_demo else None,
                                    informed[i][1], step) for i in due]
            outs = await asyncio.gather(*[llm_decide(client, model, sem, p)
                                          for p in prompts])
            n_calls += len(outs)
            for i, (act, failed) in zip(due, outs):
                if failed:
                    n_fail += 1
                elif act == 1:
                    evacuated[i] = step
        else:
            for i in due:
                first = step == pending[i][0]
                p1, p2 = (RULE_ORDER if informed[i][1] in ORDER_CHANNELS else RULE_ENV)
                if draw(seed, "ruledec", i, step) < (p1 if first else p2):
                    evacuated[i] = step

    # ===== 指标 =====
    truth = json.loads(TRUTH_JSON.read_text())["marginals"]
    cats = ("official_push", "media", "neighbor", "social", "none")
    sim = {c: 0 for c in cats}
    env_informed = 0
    for _, (s, ch) in informed.items():
        if ch == "environment":
            env_informed += 1          # 无令知情 → 真值口径归 none
        else:
            sim[ch] += 1
    sim["none"] = n - sum(sim.values())
    sim = {c: v / n for c, v in sim.items()}
    l1 = sum(abs(sim[c] - truth[c]) for c in cats)

    ev = sorted(evacuated.values())
    return dict(arm=arm, seed=seed, n=n,
                order_coverage=sum(1 for _, (s, c) in informed.items()
                                   if c in ORDER_CHANNELS) / n,
                any_awareness=len(informed) / n,
                env_share=env_informed / n,
                evac_rate=len(evacuated) / n,
                channel_l1=l1, sim_channels=sim,
                median_evac_step=float(np.median(ev)) if ev else None,
                llm_calls=n_calls, llm_failures=n_fail,
                fail_rate=(n_fail / n_calls if n_calls else 0.0))


async def main_async(args):
    from openai import AsyncOpenAI
    base_url = os.environ.get("LLM_BASE_URL", "https://www.packyapi.com/v1")
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = args.model or os.environ.get("LLM_MODEL", "deepseek-v4-flash")
    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    sem = asyncio.Semaphore(args.concurrency)

    truth = json.loads(TRUTH_JSON.read_text())["marginals"]
    print(f"E3 消融矩阵 v2 — {model} | n={args.n} | seeds={args.seeds}")
    print(f"arms: {args.arms}")
    print(f"渠道真值: {truth} | 真实撤离率 74.3% | 真实收令率 ≈57.3%\n")

    all_results = []
    for arm in args.arms:
        for seed in args.seeds:
            r = await run_arm_seed(arm, seed, args.n, client, model, sem)
            all_results.append(r)
            print(f"[{arm:>9} s{seed}] 收令 {r['order_coverage']:.1%} | "
                  f"总知情 {r['any_awareness']:.1%} | 撤离 {r['evac_rate']:.1%} | "
                  f"L1={r['channel_l1']:.3f} | 调用{r['llm_calls']} 败{r['llm_failures']}")

    df = pd.DataFrame(all_results)
    summary = {}
    print(f"\n{'='*88}")
    print(f"{'arm':<10}{'收令率':<15}{'总知情':<15}{'撤离率':<15}{'渠道L1':<15}{'中位撤离步'}")
    print(f"{'-'*88}")
    for arm in args.arms:
        s = df[df.arm == arm]
        med = s.median_evac_step.dropna()
        summary[arm] = {k: float(v) for k, v in dict(
            order_cov_mean=s.order_coverage.mean(), order_cov_std=s.order_coverage.std(),
            aware_mean=s.any_awareness.mean(), aware_std=s.any_awareness.std(),
            evac_mean=s.evac_rate.mean(), evac_std=s.evac_rate.std(),
            l1_mean=s.channel_l1.mean(), l1_std=s.channel_l1.std(),
            med_step=med.mean() if len(med) else float("nan")).items()}
        print(f"{arm:<10}"
              f"{s.order_coverage.mean():.1%}±{s.order_coverage.std():.1%}   "
              f"{s.any_awareness.mean():.1%}±{s.any_awareness.std():.1%}   "
              f"{s.evac_rate.mean():.1%}±{s.evac_rate.std():.1%}   "
              f"{s.channel_l1.mean():.3f}±{s.channel_l1.std():.3f}   "
              f"{med.mean() if len(med) else float('nan'):.1f}")

    if "full" in args.arms:
        print(f"\n配对 Δ(arm − full):真实撤离率 74.3%,离 full 越负 = 该机制贡献越大")
        for arm in args.arms:
            if arm == "full":
                continue
            d = [df[(df.arm == arm) & (df.seed == s)].evac_rate.iloc[0]
                 - df[(df.arm == "full") & (df.seed == s)].evac_rate.iloc[0]
                 for s in args.seeds]
            da = [df[(df.arm == arm) & (df.seed == s)].any_awareness.iloc[0]
                  - df[(df.arm == "full") & (df.seed == s)].any_awareness.iloc[0]
                  for s in args.seeds]
            print(f"  {arm:<10} Δ撤离 {np.mean(d):+.1%} ± {np.std(d):.1%}   "
                  f"Δ知情 {np.mean(da):+.1%} ± {np.std(da):.1%}")

    fail_max = df.fail_rate.max()
    print(f"\n最大失败率: {fail_max:.2%}" + ("  ⚠️" if fail_max > 0.01 else "  ✓"))

    out = OUT_DIR / f"e3_ablation_{model.replace('/', '_')}.json"
    out.write_text(json.dumps(dict(
        model=model, n=args.n, seeds=args.seeds,
        params=dict(P_MEDIA=P_MEDIA, P_SOCIAL=P_SOCIAL, P_RELAY=P_RELAY,
                    P_ENV=P_ENV, K=K_NEIGHBORS,
                    RULE_ORDER=RULE_ORDER, RULE_ENV=RULE_ENV,
                    calibration_note="信息层按渠道边际粗校准;决策层未调,撤离率为样本外验证"),
        truth=truth, summary=summary, per_run=all_results),
        indent=2, ensure_ascii=False))
    print(f"✓ 已保存: {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=500)
    p.add_argument("--seeds", type=int, nargs="+", default=[41, 42, 43, 44, 45])
    p.add_argument("--arms", nargs="+", default=list(ARMS.keys()))
    p.add_argument("--model", default=None)
    p.add_argument("--concurrency", type=int, default=12)
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
