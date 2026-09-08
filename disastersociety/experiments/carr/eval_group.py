"""Carr 群体指标诊断（PILOT）— 撤离曲线和渠道听说比例。

当前脚本用于检查历史群体指标管线:
1. 撤离时序曲线(模拟 vs 问卷加权)
2. 渠道听说比例(模拟 vs 问卷边际)

重要限制:
- survey_clean.csv 的撤离标签与时间已按 Q9.1、Q13.3/Q13.4 修复;
- delivery 参数按同一问卷接收边际校准;
- 模拟渠道只区分 official 与 none。

因此输出是开发期诊断，不能称为独立群体验证。
"""

from __future__ import annotations

import argparse
import json
import pandas as pd
import numpy as np
from pathlib import Path
from scipy import stats
import matplotlib.pyplot as plt


def load_evacuation_curve(run_dir: Path) -> pd.DataFrame:
    """从仿真日志构造撤离时序曲线。

    Args:
        run_dir: 仿真运行目录

    Returns:
        DataFrame(step, cumulative_evacuated, evacuation_rate)
    """
    events_file = run_dir / "events.jsonl"

    # 读取所有撤离事件
    evacuations = []
    with open(events_file) as f:
        for line in f:
            event = json.loads(line)
            if event.get("type") == "evacuation":
                evacuations.append({
                    "step": event["step"],
                    "agent_id": event["agent_id"]
                })

    if not evacuations:
        print("⚠️  没有撤离事件")
        return pd.DataFrame(columns=["step", "cumulative_evacuated", "evacuation_rate"])

    df_evac = pd.DataFrame(evacuations)

    # 从 metadata 读取总 agent 数
    metadata_file = run_dir / "metadata.json"
    with open(metadata_file) as f:
        metadata = json.load(f)
    n_agents = metadata["n_agents"]

    # 按步聚合
    curve = df_evac.groupby("step").size().cumsum().reset_index()
    curve.columns = ["step", "cumulative_evacuated"]
    curve["evacuation_rate"] = curve["cumulative_evacuated"] / n_agents

    return curve


def load_survey_curve(survey_csv: Path) -> pd.DataFrame:
    """从问卷构造撤离时序曲线(加权)。

    Args:
        survey_csv: 清洗后的问卷 CSV

    Returns:
        DataFrame(hour, cumulative_evacuated, evacuation_rate)
    """
    df = pd.read_csv(survey_csv)

    # 筛选有合法撤离标签和时间的已撤离者
    evacuated = df[
        df["evacuation_eval_eligible"]
        & df["evacuated"].eq(1)
        & df["evacuation_hour_since_ignition"].notna()
    ].copy()

    if len(evacuated) == 0:
        print("⚠️  问卷中无撤离者")
        return pd.DataFrame(columns=["hour", "cumulative_evacuated", "evacuation_rate"])

    evacuated["evac_step"] = (
        evacuated["evacuation_hour_since_ignition"].clip(lower=0).round().astype(int)
    )

    # 按步聚合(加权:每条响应代表若干真实居民)
    # 简化:均匀权重
    curve = evacuated.groupby("evac_step").size().cumsum().reset_index()
    curve.columns = ["step", "cumulative_evacuated"]
    curve["evacuation_rate"] = curve["cumulative_evacuated"] / len(df)

    return curve


def calculate_ks_statistic(curve1: pd.DataFrame, curve2: pd.DataFrame) -> float:
    """计算两条曲线的 KS 统计量(最大垂直距离)。

    Args:
        curve1: 曲线1(step, evacuation_rate)
        curve2: 曲线2(step, evacuation_rate)

    Returns:
        KS 统计量(0-1,越小越好)
    """
    # 对齐步数范围
    all_steps = sorted(set(curve1["step"].tolist() + curve2["step"].tolist()))

    # 插值填充
    rate1 = np.interp(all_steps, curve1["step"], curve1["evacuation_rate"], left=0, right=curve1["evacuation_rate"].iloc[-1])
    rate2 = np.interp(all_steps, curve2["step"], curve2["evacuation_rate"], left=0, right=curve2["evacuation_rate"].iloc[-1])

    # KS 统计量
    ks = np.max(np.abs(rate1 - rate2))
    return float(ks)


def calculate_rmse(curve1: pd.DataFrame, curve2: pd.DataFrame) -> float:
    """计算两条曲线的 RMSE。

    Args:
        curve1: 曲线1(step, evacuation_rate)
        curve2: 曲线2(step, evacuation_rate)

    Returns:
        RMSE
    """
    all_steps = sorted(set(curve1["step"].tolist() + curve2["step"].tolist()))
    rate1 = np.interp(all_steps, curve1["step"], curve1["evacuation_rate"], left=0, right=curve1["evacuation_rate"].iloc[-1])
    rate2 = np.interp(all_steps, curve2["step"], curve2["evacuation_rate"], left=0, right=curve2["evacuation_rate"].iloc[-1])

    rmse = np.sqrt(np.mean((rate1 - rate2)**2))
    return float(rmse)


def load_channel_distribution(run_dir: Path) -> dict:
    """从仿真日志统计渠道听说比例。

    Args:
        run_dir: 仿真运行目录

    Returns:
        {"official": 0.7, "neighbor": 0.2, "social": 0.05, "none": 0.05}
    """
    events_file = run_dir / "events.jsonl"

    # 统计收到预警的 agent
    warned_agents = set()
    with open(events_file) as f:
        for line in f:
            event = json.loads(line)
            if event.get("type") == "warning_delivered":
                warned_agents.add(event["agent_id"])

    # 从 metadata 读取总数
    metadata_file = run_dir / "metadata.json"
    with open(metadata_file) as f:
        metadata = json.load(f)
    n_agents = metadata["n_agents"]

    # 简化:所有收到预警的都算 official,其他算 none
    # 真实版需要区分渠道(官方/邻居/社交媒体)
    official = len(warned_agents)
    none = n_agents - official

    return {
        "official": official / n_agents,
        "neighbor": 0.0,  # 简化版没有邻居传播
        "social": 0.0,
        "none": none / n_agents
    }


def load_survey_channel_distribution(survey_csv: Path) -> dict:
    """从问卷统计粗粒度多选渠道 prevalence。

    Args:
        survey_csv: 清洗后的问卷 CSV

    Returns:
        {"official": ..., "neighbor": ..., "social": ..., "none": ...}
    """
    df = pd.read_csv(survey_csv)

    warned = df[df["warned_official"].eq(1)].copy()
    total = len(warned) or 1
    official_cols = [
        "heard_reverse_911", "heard_text", "heard_television", "heard_radio",
        "heard_flyer", "heard_public_official", "heard_subscribed_service",
        "heard_billboard",
    ]
    official = warned[official_cols].max(axis=1).sum()
    interpersonal = warned["heard_interpersonal"].sum()
    online = warned[
        ["heard_social_media", "heard_website", "heard_smartphone_app"]
    ].max(axis=1).sum()
    none = warned["warning_channel_count"].eq(0).sum()

    return {
        "official": official / total,
        "neighbor": interpersonal / total,
        "social": online / total,
        "none": none / total,
    }


def calculate_l1_distance(dist1: dict, dist2: dict) -> float:
    """计算两个渠道向量的 L1 距离。

    Args:
        dist1: 分布1
        dist2: 分布2

    Returns:
        L1 距离。多选 prevalence 的总和可以超过 1，因此这不是总变差距离。
    """
    keys = set(dist1.keys()) | set(dist2.keys())
    l1 = sum(abs(dist1.get(k, 0) - dist2.get(k, 0)) for k in keys)
    return float(l1)


def main():
    parser = argparse.ArgumentParser(description="Carr 群体指标诊断（PILOT）")
    parser.add_argument("--run-id", required=True, help="仿真运行 ID")
    parser.add_argument("--survey", default="eventpacks/carr_2018/behavior/survey_clean.csv",
                        help="问卷 CSV 路径")
    args = parser.parse_args()

    run_dir = Path(f"experiments/carr/runs/{args.run_id}")
    if not run_dir.exists():
        print(f"✗ 运行目录不存在: {run_dir}")
        return

    print(f"\n{'='*70}")
    print(f"Carr 群体指标诊断（PILOT，不是独立验证）")
    print(f"{'='*70}")
    print(f"运行 ID: {args.run_id}")
    print(f"问卷: {args.survey}\n")

    # ===== 1. 撤离曲线对比 =====
    print(f"{'='*70}")
    print(f"1. 撤离时序曲线")
    print(f"{'='*70}\n")

    sim_curve = load_evacuation_curve(run_dir)
    print(f"✓ 模拟曲线: {len(sim_curve)} 个时间点")
    if len(sim_curve) > 0:
        print(f"  最终撤离率: {sim_curve['evacuation_rate'].iloc[-1]:.1%}")
        print(f"  首次撤离: step {sim_curve['step'].iloc[0]}\n")

    survey_curve = load_survey_curve(Path(args.survey))
    print(f"✓ 问卷曲线: {len(survey_curve)} 个时间点")
    if len(survey_curve) > 0:
        print(f"  最终撤离率: {survey_curve['evacuation_rate'].iloc[-1]:.1%}")
        print(f"  首次撤离: step {survey_curve['step'].iloc[0]}\n")

    if len(sim_curve) > 0 and len(survey_curve) > 0:
        ks = calculate_ks_statistic(sim_curve, survey_curve)
        rmse = calculate_rmse(sim_curve, survey_curve)

        print(f"评估指标:")
        print(f"  KS 统计量: {ks:.3f} (最大垂直距离)")
        print(f"  RMSE: {rmse:.3f}\n")

    # ===== 2. 渠道听说比例对比 =====
    print(f"{'='*70}")
    print(f"2. 渠道听说比例")
    print(f"{'='*70}\n")

    sim_channels = load_channel_distribution(run_dir)
    survey_channels = load_survey_channel_distribution(Path(args.survey))

    print(f"模拟分布:")
    for ch, pct in sim_channels.items():
        print(f"  {ch:<12}: {pct:.1%}")

    print(f"\n问卷分布:")
    for ch, pct in survey_channels.items():
        print(f"  {ch:<12}: {pct:.1%}")

    l1_dist = calculate_l1_distance(sim_channels, survey_channels)
    print(f"\n评估指标:")
    print(f"  L1 距离: {l1_dist:.3f} (总变差距离,越小越好)\n")

    # ===== 总结 =====
    print(f"{'='*70}")
    print(f"Carr 群体指标诊断总结")
    print(f"{'='*70}")
    if len(sim_curve) > 0 and len(survey_curve) > 0:
        print(f"撤离曲线: KS={ks:.3f}, RMSE={rmse:.3f}")
    print(f"渠道分布: L1={l1_dist:.3f}")
    print("\n限制: 当前标签、时间和渠道均含占位或同源校准，")
    print("这些距离只能用于开发诊断，不能用于论文中的“验证通过”判断。")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
