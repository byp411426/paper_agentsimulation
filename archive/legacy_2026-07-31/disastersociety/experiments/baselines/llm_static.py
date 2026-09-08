"""已归档的 LLM 静态 persona 开发基线（个体预测辅助分析）。

给 LLM 喂人口学信息,单次询问撤离决策,不包含社交交互或动态更新。
核心撤离标签已经修复，但已有输出生成于修复前，仍为 INVALID_FOR_CLAIM。
本脚本只能用于同一评估样本上的辅助比较，不预设 LLM 优于传统模型。

该脚本导出 respondent ID、使用错误 ECE 定义且缺少当前网关 provenance，
仅保留作历史记录。
"""

from __future__ import annotations

import argparse
import json
import pandas as pd
from pathlib import Path
from tqdm import tqdm
import time

# 直接使用 OpenAI API(项目的 LLMGateway 是为仿真设计的,这里用简单调用)
import os
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    print("⚠️  需要安装 openai: pip install openai")

# ===== 配置 =====
SURVEY_CSV = "eventpacks/carr_2018/behavior/survey_clean.csv"
OUT_DIR = Path("experiments/baselines/results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ===== Prompt 模板 =====
PROMPT_TEMPLATE = """You are a resident of Redding, California during the 2018 Carr Wildfire.

Your demographics:
- Age group: {age_desc}
- Household size: {household_size} people
- Vehicle count: {vehicle_count}
- Annual household income: {income_desc}

Context:
It's July 23, 2018, around 1:15 PM. The Carr Fire has just started near French Gulch.

Question:
During this wildfire event, will you evacuate or stay?

Answer with ONLY a JSON object in this exact format:
{{"decision": "yes" or "no", "confidence": 0-100}}

Do not include any explanation or other text."""

# ===== 人口学描述映射 =====
AGE_MAP = {
    1: "under 18", 2: "18-24", 3: "25-34", 4: "35-44",
    5: "45-54", 6: "55-64", 7: "65-74", 8: "75-84", 9: "85 or older",
    -1: "prefer not to answer"
}

INCOME_MAP = {
    1: "less than $10,000", 2: "$10,000-$14,999", 3: "$15,000-$24,999",
    4: "$25,000-$34,999", 5: "$35,000-$49,999", 6: "$50,000-$74,999",
    7: "$75,000-$99,999", 8: "$100,000-$149,999", 9: "$150,000-$199,999",
    10: "more than $200,000", -1: "prefer not to answer"
}


def safe_int(value, default=-1):
    if pd.isna(value):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def display_number(value):
    return "unknown" if pd.isna(value) else str(safe_int(value, default=-1))


def format_prompt(row: pd.Series) -> str:
    """格式化单个响应者的 prompt"""
    age_code = safe_int(row['age_group'])
    income_code = safe_int(row['income_bracket'])
    return PROMPT_TEMPLATE.format(
        age_desc=AGE_MAP.get(age_code, "unknown"),
        household_size=display_number(row['household_size']),
        vehicle_count=display_number(row['vehicle_count']),
        income_desc=INCOME_MAP.get(income_code, "unknown"),
    )

def parse_llm_response(text: str) -> tuple[int, float]:
    """解析 LLM 响应,返回 (decision, confidence)"""
    try:
        # 尝试直接解析 JSON
        result = json.loads(text.strip())
        decision = 1 if result['decision'].lower() == 'yes' else 0
        confidence = float(result['confidence']) / 100.0  # 归一化到 0-1
        return decision, confidence
    except:
        # 回退:搜索关键词
        text_lower = text.lower()
        if 'yes' in text_lower or 'evacuate' in text_lower:
            return 1, 0.5
        elif 'no' in text_lower:
            return 0, 0.5
        else:
            return 0, 0.5  # 默认不撤离

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='gpt-4o-mini', help='LLM model name')
    parser.add_argument('--n', type=int, default=50, help='Sample size (default 50, -1 for all)')
    args = parser.parse_args()

    if not HAS_OPENAI:
        print("错误: 需要安装 openai 库")
        return

    # ===== 读取问卷 =====
    df = pd.read_csv(SURVEY_CSV)
    df = df[df["evacuation_eval_eligible"]].copy()
    print(f"✓ 读取 {len(df)} 条响应")

    # 采样(为了快速测试,默认只跑 50 条)
    if args.n > 0 and args.n < len(df):
        df_sample = df.sample(n=args.n, random_state=42)
        print(f"  采样 {args.n} 条进行测试")
    else:
        df_sample = df
        print(f"  使用全部 {len(df)} 条")

    # ===== 初始化 LLM 客户端(PACKY 或 OpenAI) =====
    base_url = os.environ.get("LLM_BASE_URL", "https://www.packyapi.com/v1")
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    client = OpenAI(base_url=base_url, api_key=api_key)
    print(f"  后端: {base_url} | 模型: {args.model}")

    # ===== 批量查询 =====
    predictions = []
    confidences = []

    for idx, row in tqdm(df_sample.iterrows(), total=len(df_sample), desc="查询 LLM"):
        prompt = format_prompt(row)
        try:
            response = client.chat.completions.create(
                model=args.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,  # 降低采样变化；在线端点不保证严格确定
                max_tokens=300    # DeepSeek 需要更多 token(含 reasoning)
            )
            text = response.choices[0].message.content
            decision, confidence = parse_llm_response(text)
            predictions.append(decision)
            confidences.append(confidence)
        except Exception as e:
            print(f"\n⚠️  行 {idx} 失败: {e}")
            predictions.append(0)  # 默认不撤离
            confidences.append(0.5)

    df_sample = df_sample.copy()
    df_sample['llm_pred'] = predictions
    df_sample['llm_confidence'] = confidences

    # ===== 评估指标 =====
    from sklearn.metrics import f1_score, brier_score_loss, accuracy_score

    y_true = df_sample['evacuated'].values
    y_pred = df_sample['llm_pred'].values
    y_proba = df_sample['llm_confidence'].values

    # F1 (macro)
    f1 = f1_score(y_true, y_pred, average='macro')

    # Brier score
    brier = brier_score_loss(y_true, y_proba)

    # Accuracy
    acc = accuracy_score(y_true, y_pred)

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

    # ===== 输出结果 =====
    print(f"\n{'='*60}")
    print(f"LLM 静态 persona 基线 ({args.model})")
    print(f"{'='*60}")
    print(f"样本数: {len(df_sample)}")
    print(f"Accuracy: {acc:.3f}")
    print(f"F1 (macro): {f1:.3f}")
    print(f"Brier: {brier:.3f}")
    print(f"ECE: {ece:.3f}")

    # 混淆矩阵
    from sklearn.metrics import confusion_matrix
    cm = confusion_matrix(y_true, y_pred)
    print(f"\n混淆矩阵:")
    print(f"            预测:不撤离  预测:撤离")
    print(f"真实:不撤离    {cm[0,0]:6d}    {cm[0,1]:6d}")
    print(f"真实:撤离      {cm[1,0]:6d}    {cm[1,1]:6d}")

    # ===== 保存结果 =====
    results = {
        'model': args.model,
        'n_samples': len(df_sample),
        'accuracy': float(acc),
        'f1_macro': float(f1),
        'brier': float(brier),
        'ece': float(ece),
        'confusion_matrix': cm.tolist()
    }

    out_path = OUT_DIR / f"llm_static_{args.model.replace('/', '_')}.json"
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ 已保存结果: {out_path}")

    # 保存详细预测
    detail_path = OUT_DIR / f"llm_static_{args.model.replace('/', '_')}_predictions.csv"
    df_sample[['respondent_id', 'evacuated', 'llm_pred', 'llm_confidence']].to_csv(detail_path, index=False)
    print(f"✓ 已保存详细预测: {detail_path}")

if __name__ == '__main__':
    main()
