"""五分类渠道真值:从原始 Carr 问卷重算"首次听说渠道"边际分布。

原 clean_survey 的四分类把 TV/广播/网站等都归入 "none"(47.8%)——
E3 完整模型有媒体渠道后,需要把 media 拆出来才有对照。

Q6.1 是多选("如何收到强制令"),问卷无法给出"首次"顺序,
故用与仿真一致的优先级近似: official_push > media > neighbor > social > none。
(此近似在论文 limitation 注明。)

映射(PDF codebook):
  official_push: Q6.1_1 反拨911 / Q6.1_2 短信 / Q6.1_6 官员当面 / Q6.1_13 订阅警报
  media:         Q6.1_3 电视 / Q6.1_4 广播 / Q6.1_12 网站 / Q6.1_8 手机应用
  neighbor:      Q6.1_9 有人告知(邻居/朋友/家人)
  social:        Q6.1_7 社交媒体
  none:          其余(含只看到火/传单/路牌等)
"""

from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

RAW = "Wong_Carr_Wildfire_Dataset.csv"
OUT = Path("experiments/carr/results/channel_truth_5cat.json")
MSG = "Received message (check all that apply)"

df = pd.read_csv(RAW, header=[0, 1], low_memory=False)
df.columns = [c[0] for c in df.columns]
df = df[df["ResponseId"] != '{"ImportId":"_recordId"}']
df = df[df["Finished"] == "TRUE"].reset_index(drop=True)
print(f"✓ {len(df)} 条完整响应")

def got(col):
    return df.get(col, pd.Series(index=df.index)).eq(MSG)

push = got("Q6.1_1") | got("Q6.1_2") | got("Q6.1_6") | got("Q6.1_13")
media = got("Q6.1_3") | got("Q6.1_4") | got("Q6.1_12") | got("Q6.1_8")
neighbor = got("Q6.1_9")
social = got("Q6.1_7")

cat = pd.Series("none", index=df.index)
cat[social] = "social"
cat[neighbor] = "neighbor"
cat[media] = "media"
cat[push] = "official_push"   # 最高优先级最后赋值

counts = cat.value_counts()
n = len(df)
truth = {k: round(counts.get(k, 0) / n, 4)
         for k in ("official_push", "media", "neighbor", "social", "none")}
print("五分类渠道真值(优先级近似):")
for k, v in truth.items():
    print(f"  {k:<14}: {v:.1%}")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"n": n, "priority": "push>media>neighbor>social",
                           "marginals": truth}, indent=2))
print(f"✓ 已保存: {OUT}")
