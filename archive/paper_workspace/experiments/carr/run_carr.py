"""运行完整的 Carr Fire 仿真 (M4 真实世界验证)。

从 eventpack 加载真实数据,运行仿真,输出撤离行为供 E1/E2 评估。

运行: python experiments/carr/run_carr.py --n=1000 --steps=48
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime

# 添加项目根到 path
import sys
sys.path.insert(0, str(Path(__file__).parents[2]))

from ds.eventpack.carr_loader import load_carr_world
from ds.engine.runner import run_simulation
from ds.llm.gateway import LLMGateway


def main():
    parser = argparse.ArgumentParser(description="运行 Carr Fire 仿真")
    parser.add_argument("--n", type=int, default=100, help="合成人口规模")
    parser.add_argument("--steps", type=int, default=48, help="仿真步数(小时)")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--model", default="gpt-4o-mini", help="LLM 模型")
    parser.add_argument("--budget", type=float, default=10.0, help="预算(USD)")
    parser.add_argument("--run-id", default=None, help="运行 ID(默认自动生成)")
    args = parser.parse_args()

    # ===== 生成运行 ID =====
    if args.run_id:
        run_id = args.run_id
    else:
        run_id = f"carr_{args.n}hh_seed{args.seed}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print(f"\n{'='*70}")
    print(f"Carr Fire 仿真")
    print(f"{'='*70}")
    print(f"运行 ID: {run_id}")
    print(f"人口规模: {args.n} 户")
    print(f"仿真步数: {args.steps} 步")
    print(f"随机种子: {args.seed}")
    print(f"LLM 模型: {args.model}")
    print(f"预算: ${args.budget}")
    print(f"{'='*70}\n")

    # ===== 加载 Carr 世界 =====
    world = load_carr_world(target_n=args.n, max_step=args.steps, seed=args.seed)

    # ===== 初始化 LLM 网关 =====
    # LLMGateway 需要的配置格式: {"models": {"role_name": {"model": ..., "temperature": ...}}}
    models_cfg = {
        "models": {
            "default": {
                "model": args.model,
                "temperature": 0.7,
                "max_tokens": 500
            },
            "cheap": {
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "max_tokens": 300
            }
        }
    }

    out_dir = Path(f"experiments/carr/runs/{run_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    gateway = LLMGateway(
        run_id=run_id,
        models_cfg=models_cfg,
        budget_usd=args.budget,
        log_dir=str(out_dir / "llm_logs")
    )

    # ===== 运行仿真 =====
    print(f"开始仿真...\n")

    try:
        results = run_simulation(
            world=world,
            gateway=gateway,
            seed=args.seed,
            log_path=str(out_dir / "events.jsonl")
        )
    except NotImplementedError as e:
        print(f"\n⚠️  仿真引擎未完全实现: {e}")
        print(f"   Phase 4 加载器和脚本骨架已就绪,等待引擎完工")
        return
    except Exception as e:
        print(f"\n✗ 仿真失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # ===== 保存元数据 =====
    metadata = {
        "run_id": run_id,
        "eventpack": "carr_2018",
        "n_agents": args.n,
        "max_step": args.steps,
        "seed": args.seed,
        "model": args.model,
        "budget_usd": args.budget,
        "timestamp": datetime.now().isoformat(),
    }

    with open(out_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # ===== 输出结果摘要 =====
    print(f"\n{'='*70}")
    print(f"✓ 仿真完成")
    print(f"{'='*70}")
    print(f"输出目录: {out_dir}")
    print(f"  - events.jsonl: 完整事件日志")
    print(f"  - metadata.json: 运行元数据")
    print(f"  - llm_logs/: LLM 调用日志")

    # 统计撤离行为
    if results:
        evacuated_count = sum(1 for a in world.agents if a.state == "evacuated")
        evac_rate = evacuated_count / len(world.agents)
        print(f"\n撤离统计:")
        print(f"  撤离数: {evacuated_count} / {len(world.agents)}")
        print(f"  撤离率: {evac_rate:.1%}")

    print(f"\n下一步: 运行 E1/E2 评估")
    print(f"  python experiments/carr/eval_individual.py --run-id={run_id}")
    print(f"  python experiments/carr/eval_group.py --run-id={run_id}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
