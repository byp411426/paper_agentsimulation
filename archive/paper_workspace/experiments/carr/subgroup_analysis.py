"""E1 分群误差分析(spec E1:不同年龄/车辆/收入群体的误差差距)。

对比传统 RF 与校准版 LLM 在各人口子群上的准确率,回答:
"哪类人谁预测得更好?" — 这是比总 F1 更有论文价值的表。

运行(等 e1_calibrated 完成后):
  python experiments/carr/subgroup_analysis.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

RES = Path("experiments/carr/results")
BASE = Path("experiments/baselines/results")

LLM_PRED = RES / "e1_calibrated_named_deepseek-v4-flash_predictions.csv"
RF_PRED = BASE / "traditional_RandomForest_predictions.csv"
LR_PRED = BASE / "traditional_LogisticRegression_predictions.csv"


def subgroup_table(df: pd.DataFrame, group_col: str, groups: dict) -> pd.DataFrame:
    rows = []
    for label, mask in groups.items():
        sub = df[mask]
        if len(sub) < 5:
            continue
        rows.append({
            "group": f"{group_col}:{label}",
            "n": len(sub),
            "true_evac_rate": sub["evacuated"].mean(),
            "LLM_acc": (sub["llm_pred"] == sub["evacuated"]).mean(),
            "RF_acc": (sub["rf_pred"] == sub["evacuated"]).mean(),
            "LR_acc": (sub["lr_pred"] == sub["evacuated"]).mean(),
            "LLM_p_mean": sub["p_evacuate"].mean(),
        })
    return pd.DataFrame(rows)


def main():
    llm = pd.read_csv(LLM_PRED)
    rf = pd.read_csv(RF_PRED)[["respondent_id", "RandomForest_pred"]]
    lr = pd.read_csv(LR_PRED)[["respondent_id", "LogisticRegression_pred"]]

    df = llm.merge(rf, on="respondent_id").merge(lr, on="respondent_id")
    df = df.rename(columns={"pred": "llm_pred",
                            "RandomForest_pred": "rf_pred",
                            "LogisticRegression_pred": "lr_pred"})
    print(f"✓ 合并 {len(df)} 条(LLM 校准版 × RF × LR)\n")

    tables = []

    # 年龄:老年(65+) vs 中年 vs 青年
    tables.append(subgroup_table(df, "age", {
        "18-44 (2-4)": df["age_group"].between(2, 4),
        "45-64 (5-6)": df["age_group"].between(5, 6),
        "65+ (7-9)": df["age_group"].between(7, 9),
    }))
    # 车辆
    tables.append(subgroup_table(df, "vehicles", {
        "0-1": df["vehicle_count"] <= 1,
        "2": df["vehicle_count"] == 2,
        "3+": df["vehicle_count"] >= 3,
    }))
    # 收入
    tables.append(subgroup_table(df, "income", {
        "low(<$50k)": df["income_bracket"].between(1, 5),
        "mid($50-100k)": df["income_bracket"].isin([6, 8]),
        "high(>$100k)": df["income_bracket"].isin([11, 12, 13]),
    }))
    # 家庭规模
    tables.append(subgroup_table(df, "household", {
        "1 (独居)": df["household_size"] == 1,
        "2": df["household_size"] == 2,
        "3+": df["household_size"] >= 3,
    }))
    # 真实行为
    tables.append(subgroup_table(df, "outcome", {
        "撤离者": df["evacuated"] == 1,
        "留守者": df["evacuated"] == 0,
    }))

    full = pd.concat(tables, ignore_index=True)
    pd.set_option("display.float_format", lambda v: f"{v:.3f}")
    print(full.to_string(index=False))

    out = RES / "subgroup_analysis.csv"
    full.to_csv(out, index=False)
    print(f"\n✓ 已保存: {out}")

    # 关键差距摘要
    print("\n=== 摘要:LLM 相对 RF 的每群准确率差(正=LLM更好) ===")
    full["LLM_minus_RF"] = full["LLM_acc"] - full["RF_acc"]
    for _, r in full.iterrows():
        bar = "+" if r.LLM_minus_RF >= 0 else "-"
        print(f"  {r.group:<22} n={int(r.n):<4} Δ={r.LLM_minus_RF:+.3f} {bar}")


if __name__ == "__main__":
    main()
