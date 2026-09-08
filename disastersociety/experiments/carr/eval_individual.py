"""Carr 个体指标占位诊断（INVALID_FOR_CLAIM）。

对比三类模型的个体预测能力:
1. 传统 ML(LR/RF)
2. LLM 静态 persona
3. 情境化一次性 LLM / 简化 Carr run

评估指标: F1 (macro), Brier score, ECE

撤离标签已按 Q9.1 修复，但历史 run 没有合法的 agent ↔ respondent 映射。
本脚本中的“前 N 个匹配”只用于检查指标代码，不能用于模型比较或论文结论。
"""

from __future__ import annotations

import argparse
import json
import pandas as pd
from pathlib import Path
from sklearn.metrics import f1_score, brier_score_loss, accuracy_score, confusion_matrix
import numpy as np


def load_simulation_decisions(run_dir: Path) -> pd.DataFrame:
    """从仿真日志加载 agent 决策。

    Args:
        run_dir: 仿真运行目录

    Returns:
        DataFrame(agent_id, evacuated, confidence)
    """
    events_file = run_dir / "events.jsonl"
    if not events_file.exists():
        raise FileNotFoundError(f"日志文件不存在: {events_file}")

    # 读取所有撤离事件
    evacuations = {}
    with open(events_file) as f:
        for line in f:
            event = json.loads(line)
            if event.get("type") == "evacuation":
                agent_id = event["agent_id"]
                confidence = event.get("confidence", 0.5)
                evacuations[agent_id] = {
                    "evacuated": 1,
                    "confidence": confidence
                }

    # 从 metadata 读取所有 agent(包括未撤离的)
    metadata_file = run_dir / "metadata.json"
    with open(metadata_file) as f:
        metadata = json.load(f)

    n_agents = metadata["n_agents"]

    # 构造完整 DataFrame(未撤离的标为 0)
    decisions = []
    for i in range(n_agents):
        agent_id = f"hh_{i}"
        if agent_id in evacuations:
            decisions.append({
                "agent_id": agent_id,
                "evacuated": 1,
                "confidence": evacuations[agent_id]["confidence"]
            })
        else:
            decisions.append({
                "agent_id": agent_id,
                "evacuated": 0,
                "confidence": 0.3  # 未撤离,低置信度
            })

    return pd.DataFrame(decisions)


def load_survey_ground_truth(survey_csv: Path) -> pd.DataFrame:
    """加载通过 Q9.1 筛选且进入冻结评价集合的问卷标签。

    Args:
        survey_csv: 清洗后的问卷 CSV

    Returns:
        DataFrame(respondent_id, evacuated)
    """
    df = pd.read_csv(survey_csv)
    df = df[df["evacuation_eval_eligible"]].copy()
    # 简化:用 respondent_id 作为匹配键
    # 真实场景需要在仿真时保留 PUMS sample_id → respondent_id 的映射
    return df[["respondent_id", "evacuated"]]


def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray) -> dict:
    """计算评估指标。

    Args:
        y_true: 真实标签
        y_pred: 预测标签
        y_proba: 预测概率

    Returns:
        指标字典
    """
    # Accuracy
    acc = accuracy_score(y_true, y_pred)

    # F1 (macro)
    f1 = f1_score(y_true, y_pred, average='macro')

    # Brier score
    brier = brier_score_loss(y_true, y_proba)

    # ECE (Expected Calibration Error)
    bins = 10
    bin_indices = (y_proba * bins).astype(int)
    bin_indices = bin_indices.clip(0, bins - 1)
    ece = 0.0
    for i in range(bins):
        mask = bin_indices == i
        if mask.sum() > 0:
            bin_acc = (y_true[mask] == y_pred[mask]).mean()
            bin_conf = y_proba[mask].mean()
            ece += mask.sum() / len(y_true) * abs(bin_acc - bin_conf)

    # Confusion matrix
    cm = confusion_matrix(y_true, y_pred)

    return {
        "accuracy": float(acc),
        "f1_macro": float(f1),
        "brier": float(brier),
        "ece": float(ece),
        "confusion_matrix": cm.tolist(),
    }


def main():
    parser = argparse.ArgumentParser(description="Carr 个体指标占位诊断")
    parser.add_argument("--run-id", required=True, help="仿真运行 ID")
    parser.add_argument("--survey", default="eventpacks/carr_2018/behavior/survey_clean.csv",
                        help="问卷 CSV 路径")
    args = parser.parse_args()

    run_dir = Path(f"experiments/carr/runs/{args.run_id}")
    if not run_dir.exists():
        print(f"✗ 运行目录不存在: {run_dir}")
        return

    print(f"\n{'='*70}")
    print(f"Carr 个体指标占位诊断（INVALID_FOR_CLAIM）")
    print(f"{'='*70}")
    print(f"运行 ID: {args.run_id}")
    print(f"问卷: {args.survey}\n")

    # ===== 加载仿真决策 =====
    try:
        sim_decisions = load_simulation_decisions(run_dir)
        print(f"✓ 加载仿真决策: {len(sim_decisions)} 个 agent")
        print(f"  撤离数: {sim_decisions['evacuated'].sum()}")
        print(f"  撤离率: {sim_decisions['evacuated'].mean():.1%}\n")
    except Exception as e:
        print(f"✗ 加载仿真决策失败: {e}")
        return

    # ===== 加载问卷标签 =====
    try:
        survey_truth = load_survey_ground_truth(Path(args.survey))
        print(f"✓ 加载问卷标签: {len(survey_truth)} 条响应")
        print(f"  撤离数: {survey_truth['evacuated'].sum()}")
        print(f"  撤离率: {survey_truth['evacuated'].mean():.1%}\n")
    except Exception as e:
        print(f"✗ 加载问卷真值失败: {e}")
        return

    # ===== 匹配(简化版:假设仿真 agent 和问卷样本无法直接匹配) =====
    # 真实场景需要:
    # 1. 仿真时保留 PUMS sample_id
    # 2. 清洗问卷时也保留 sample_id
    # 3. 通过 sample_id 匹配
    #
    # 个体比较需要完整的匹配机制。群体指标也有独立的数据与校准限制，
    # 不能替代个体真值。
    print("⚠️  E1 个体匹配需要完整的 ID 映射机制")
    print("   当前仿真: agent_id = hh_0, hh_1, ...")
    print("   问卷真值: respondent_id = R_xxx...")
    print("   缺失: PUMS sample_id → respondent_id 映射\n")

    print("当前不提供替代的“验证通过”结论；请先实现合法的 respondent 映射。\n")

    # ===== 占位:假设匹配(用于展示指标计算) =====
    print("占位评估(假设前 N 个 agent 匹配前 N 条问卷):\n")

    n_match = min(len(sim_decisions), len(survey_truth))
    y_true = survey_truth["evacuated"].values[:n_match]
    y_pred = sim_decisions["evacuated"].values[:n_match]
    y_proba = sim_decisions["confidence"].values[:n_match]

    metrics = calculate_metrics(y_true, y_pred, y_proba)

    print(f"{'='*70}")
    print(f"评估指标(占位,匹配前 {n_match} 个)")
    print(f"{'='*70}")
    print(f"Accuracy: {metrics['accuracy']:.3f}")
    print(f"F1 (macro): {metrics['f1_macro']:.3f}")
    print(f"Brier: {metrics['brier']:.3f}")
    print(f"ECE: {metrics['ece']:.3f}")

    cm = np.array(metrics['confusion_matrix'])
    print(f"\n混淆矩阵:")
    print(f"            预测:不撤离  预测:撤离")
    print(f"真实:不撤离    {cm[0,0]:6d}    {cm[0,1]:6d}")
    print(f"真实:撤离      {cm[1,0]:6d}    {cm[1,1]:6d}")

    # ===== 对比基线 =====
    baseline_path = Path("experiments/baselines/results/traditional_baselines.json")
    if baseline_path.exists():
        with open(baseline_path) as f:
            baselines = json.load(f)

        print(f"\n{'='*70}")
        print(f"基线对比")
        print(f"{'='*70}")
        print(f"{'模型':<30} {'F1 (macro)':<12} {'Brier':<10}")
        print(f"{'-'*70}")
        print(f"{'简化 Carr run（占位匹配）':<30} {metrics['f1_macro']:<12.3f} {metrics['brier']:<10.3f}")
        print(f"{'LogisticRegression':<30} {baselines['LogisticRegression']['f1_macro']:<12.3f} {baselines['LogisticRegression']['brier']:<10.3f}")
        print(f"{'RandomForest':<30} {baselines['RandomForest']['f1_macro']:<12.3f} {baselines['RandomForest']['brier']:<10.3f}")

    print(f"\n{'='*70}")
    print("TODO: 修复撤离标签并实现合法 ID 映射后，才能进行正式个体比较")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
