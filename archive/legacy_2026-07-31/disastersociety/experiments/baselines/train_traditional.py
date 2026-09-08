"""已归档的传统 ML 开发基线（个体预测辅助分析）。

训练 Logistic Regression / Random Forest / XGBoost 预测撤离决策,
输出 F1 / Brier / ECE。核心标签已经修复，但已有输出生成于修复前，仍为
INVALID_FOR_CLAIM；冻结共用 split 后才可进行公平比较。

该脚本使用旧随机 split 和错误 ECE 定义，仅保留作历史记录。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, brier_score_loss, log_loss
import json

# ===== 配置 =====
SURVEY_CSV = "eventpacks/carr_2018/behavior/survey_clean.csv"
OUT_DIR = Path("experiments/baselines/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ===== 读取清洗后问卷 =====
df = pd.read_csv(SURVEY_CSV)
df = df[df["evacuation_eval_eligible"]].copy()
print(f"✓ 读取 {len(df)} 条响应")
print(f"  撤离率: {df['evacuated'].mean():.2%}")

# ===== 特征工程 =====
# **关键**: 只用人口学特征,不用行为特征(避免信息泄漏)
#
# 为保持 demographic-only 条件而排除:
#   - warned_official / received_* / heard_*（事件暴露变量）
#   - warning/evacuation timestamps（过程或 outcome 变量）
#   - departure_*_perception（撤离时测得的 post-outcome 变量）
#
# 允许的特征(纯人口学):
#   - age_group: 年龄分档(1-9, 缺失保留)
#   - household_size: 家庭人数(0-10, 10 表示 10+)
#   - vehicle_count: 车辆数(0-6)
#   - income_bracket: 收入分档(1-10, 缺失保留)

feature_cols = [
    'age_group', 'household_size', 'vehicle_count', 'income_bracket'
]

X = df[feature_cols].fillna(0).values  # 简单填充缺失值
y = df['evacuated'].values

print(f"✓ 特征维度: {X.shape}")
print(f"  目标分布: 撤离={y.sum()}, 未撤离={(1-y).sum()}")
print(f"  特征列表: {feature_cols}")

# ===== 训练/测试划分 =====
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# ===== 训练三个基线 =====
models = {
    'LogisticRegression': LogisticRegression(max_iter=500, random_state=42),
    'RandomForest': RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42),
}

results = {}
for name, model in models.items():
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    # 评估指标
    f1 = f1_score(y_test, y_pred, average='macro')
    brier = brier_score_loss(y_test, y_proba)

    # ECE(校准误差):分 10 个 bin,计算每个 bin 的准确率 vs 平均置信度
    bins = np.linspace(0, 1, 11)
    bin_indices = np.digitize(y_proba, bins) - 1
    bin_indices = np.clip(bin_indices, 0, 9)
    ece = 0.0
    for i in range(10):
        mask = bin_indices == i
        if mask.sum() > 0:
            acc = (y_test[mask] == y_pred[mask]).mean()
            conf = y_proba[mask].mean()
            ece += mask.sum() / len(y_test) * abs(acc - conf)

    results[name] = {
        'f1_macro': float(f1),
        'brier': float(brier),
        'ece': float(ece),
        'test_size': len(y_test),
    }

    print(f"\n{name}:")
    print(f"  F1 (macro): {f1:.3f}")
    print(f"  Brier: {brier:.3f}")
    print(f"  ECE: {ece:.3f}")

# ===== 保存结果 =====
out_path = OUT_DIR / "traditional_baselines.json"
with open(out_path, 'w') as f:
    json.dump(results, f, indent=2)
print(f"\n✓ 已保存基线结果: {out_path}")
print("\n下一步:")
print("  1. 冻结 train/validation/test 划分")
print("  2. 在同一 evaluation respondent 集合上运行所有比较")
print("  3. 将结果写入带配置和 provenance 的新目录")
