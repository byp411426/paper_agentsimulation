"""探索 Carr 问卷结构,推断关键字段映射(一次性脚本)。

读取原始 Qualtrics CSV,分析列名模式和非空率,输出候选映射。
运行: uv run python scripts/explore_survey.py
"""

import pandas as pd
from pathlib import Path

raw_csv = Path("Wong_Carr_Wildfire_Dataset.csv")
if not raw_csv.exists():
    print(f"❌ 找不到 {raw_csv},请确认已复制到项目根")
    exit(1)

# Qualtrics 双行 header:第 1 行 Q 代码,第 2 行问题文本,第 3 行起是数据
df = pd.read_csv(raw_csv, header=[0, 1], low_memory=False)
print(f"✓ 读取 {len(df)} 行 × {len(df.columns)} 列")

# 展平列名:取第一层(Q 代码)
df.columns = [c[0] for c in df.columns]

# 过滤掉 Qualtrics 元数据列(StartDate/Progress/Finished...)
meta_cols = ["StartDate", "EndDate", "Progress", "Duration (in seconds)",
             "Finished", "RecordedDate", "ResponseId", "DistributionChannel", "UserLanguage"]
q_cols = [c for c in df.columns if c not in meta_cols]

print(f"\n问卷实质列: {len(q_cols)} 个 (去除元数据后)")
print(f"前 30 个 Q 列: {q_cols[:30]}")

# 分析非空率(找高填写率的核心问题)
nonzero = {}
for col in q_cols[:50]:  # 先看前 50 列
    nonzero[col] = df[col].notna().sum()

top_filled = sorted(nonzero.items(), key=lambda x: -x[1])[:20]
print(f"\n非空率最高的前 20 列:")
for col, cnt in top_filled:
    print(f"  {col}: {cnt}/{len(df)} ({100*cnt/len(df):.0f}%)")

# 根据常见疏散问卷结构,推测关键字段
# Q2.x 通常是 screening(是否在火场期间在该地区)
# Q4-Q8 可能是撤离决策、时间、来源
# Q13-Q18 可能是风险感知
# Q30+ 可能是人口学(年龄/收入/家庭)

print(f"\n=== 推测关键字段(需人工验证 PDF codebook)===")
print("Q2.1:", df["Q2.1"].value_counts().head(3))
print("\nQ4.2:", df["Q4.2"].value_counts().head(3))
print("\nQ6.1 系列(多选框?):", [c for c in q_cols if c.startswith("Q6.1")])
print("\nQ9/Q10(可能是撤离时间/来源?):", [c for c in q_cols if c.startswith("Q9.") or c.startswith("Q10.")])

# 导出列名清单供手工映射
with open("survey_columns.txt", "w") as f:
    f.write("\n".join(q_cols))
print(f"\n✓ 已导出全部列名到 survey_columns.txt,请配合 PDF codebook 手工映射关键字段")
