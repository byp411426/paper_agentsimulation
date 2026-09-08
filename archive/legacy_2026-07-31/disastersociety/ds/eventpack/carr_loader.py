"""[ARCHIVED] Carr Fire 简化事件包加载器。

从 eventpacks/carr_2018/ 加载:
- 合成人口(PUMS + ACS → IPF)
- 火场边界时序
- 预警时间线

输出标准化的 World 对象,供仿真引擎使用。
"""

from __future__ import annotations

import pandas as pd
import geopandas as gpd
from pathlib import Path
from typing import List, Dict, Any
import json

from ds.world.base import World, Agent, Warning, HazardZone
from ds.population.synth import run_ipf

# ===== 路径配置 =====
EVENTPACK_ROOT = Path("eventpacks/carr_2018")

# 人口数据
PUMS_CSV = EVENTPACK_ROOT / "population/pums.csv"
ACS_CSV = EVENTPACK_ROOT / "population/acs_marginals.csv"

# 火场边界
PERIMETER_GEOJSON = EVENTPACK_ROOT / "hazard/perimeters.geojson"

# 预警时间线(如果存在)
WARNINGS_CSV = EVENTPACK_ROOT / "warnings/warnings.csv"

# 送达参数(如果存在)
DELIVERY_PARAMS_YAML = EVENTPACK_ROOT / "warnings/delivery_params.yaml"


def load_carr_population(target_n: int = 1000, seed: int = 42) -> List[Agent]:
    """从 PUMS + ACS 合成 Carr 人口。

    Args:
        target_n: 目标家庭数(默认 1000)
        seed: 随机种子

    Returns:
        Agent 对象列表
    """
    print(f"加载 Carr 合成人口(目标 {target_n} 户)...")

    # 读取 PUMS 种子和 ACS 边际
    pums = pd.read_csv(PUMS_CSV)
    acs = pd.read_csv(ACS_CSV)

    print(f"  ✓ PUMS 种子: {len(pums)} 户")
    print(f"  ✓ ACS 边际: {len(acs)} 个 tract")

    # 运行 IPF 合成
    # 注意:这里需要 ds.population.synth 模块完整实现
    # 如果还没实现,先用简单采样占位
    try:
        synth_households = run_ipf(pums, acs, target_n=target_n, seed=seed)
        print(f"  ✓ IPF 合成: {len(synth_households)} 户")
    except NotImplementedError:
        print(f"  ⚠️  IPF 未实现,使用 PUMS 简单采样")
        synth_households = pums.sample(n=min(target_n, len(pums)), random_state=seed)

    # 转换成 Agent 对象
    agents = []
    for idx, row in synth_households.iterrows():
        # PUMS 列名映射(基于实际 CSV 格式)
        agent = Agent(
            id=f"hh_{idx}",
            demographics={
                "age": row.get("householder_age_group", 5),  # 年龄组(1-9)
                "income": row.get("household_income", 50000),  # 家庭收入($)
                "household_size": row.get("household_size", 2),  # 家庭人数
                "vehicles": row.get("vehicle_count", 1),  # 车辆数
            },
            location={
                "tract": row.get("tract_id", "unknown"),
                "lat": row.get("lat", 40.5865),  # Redding 中心
                "lon": row.get("lon", -122.3917),
            },
            state="home"  # 初始都在家
        )
        agents.append(agent)

    print(f"✓ 生成 {len(agents)} 个 agent")
    return agents


def load_carr_hazard(max_step: int = 48) -> List[HazardZone]:
    """从火场边界 GeoJSON 生成时序危险区。

    简化版:用单个最终边界 + 缓冲圈近似时序推进。
    真实版需要多个时间点的边界数据。

    Args:
        max_step: 仿真步数(默认 48 = 2天,每步1小时)

    Returns:
        HazardZone 对象列表(每步一个)
    """
    print(f"加载 Carr 火场边界...")

    if not PERIMETER_GEOJSON.exists():
        print(f"  ⚠️  火场边界文件不存在: {PERIMETER_GEOJSON}")
        print(f"  使用占位:Redding 中心半径 10km")
        # 占位:固定圆形危险区
        return [
            HazardZone(
                step=step,
                geometry={"type": "Point", "coordinates": [-122.3917, 40.5865]},
                radius_km=10.0
            )
            for step in range(max_step)
        ]

    gdf = gpd.read_file(PERIMETER_GEOJSON)
    print(f"  ✓ 读取 {len(gdf)} 个边界要素")

    # 简化:取第一个边界,逐步扩大模拟推进
    # 真实应该有多个时间点的边界,或用火蔓延模型
    final_geom = gdf.iloc[0].geometry

    hazard_zones = []
    for step in range(max_step):
        # 简化:假设火场从 step=0 开始,每步扩大 500m
        buffer_km = step * 0.5  # 0.5km/step
        hazard_zones.append(
            HazardZone(
                step=step,
                geometry=final_geom.__geo_interface__,  # GeoJSON
                buffer_km=buffer_km
            )
        )

    print(f"✓ 生成 {len(hazard_zones)} 个时序危险区")
    return hazard_zones


def load_carr_warnings() -> List[Warning]:
    """加载预警时间线。

    如果 warnings.csv 存在,读取;否则用占位(单条预警,step=6)。

    Returns:
        Warning 对象列表
    """
    print(f"加载 Carr 预警时间线...")

    if not WARNINGS_CSV.exists():
        print(f"  ⚠️  预警文件不存在: {WARNINGS_CSV}")
        print(f"  使用占位:step=6 发出强制撤离令")
        return [
            Warning(
                step=6,
                kind="mandatory",
                zone="all",
                text="Mandatory evacuation order issued for all residents in the Carr Fire evacuation zone.",
                channels=["wea", "tv", "radio"]  # WEA=无线紧急警报
            )
        ]

    df = pd.read_csv(WARNINGS_CSV)
    print(f"  ✓ 读取 {len(df)} 条预警")

    warnings = []
    for _, row in df.iterrows():
        # channels 可能是分号分隔的字符串
        channels_str = row.get("channels", "wea")
        if isinstance(channels_str, str):
            channels = channels_str.split(";")
        else:
            channels = ["wea"]

        warnings.append(
            Warning(
                step=int(row["step"]),
                kind=row["kind"],
                zone=row.get("zone", "all"),
                text=row["text"],
                channels=channels
            )
        )

    return warnings


def load_carr_delivery_params() -> Dict[str, Any]:
    """加载送达模型参数。

    如果 delivery_params.yaml 存在,读取;否则用默认值。

    Returns:
        参数字典
    """
    print(f"加载送达参数...")

    # 默认参数(基于 2018 Pew/ATUS 数据估计)
    default_params = {
        "device_ownership": 0.92,  # 手机持有率(California 2018)
        "wea_coverage": 0.85,  # WEA 覆盖率(Shasta County)
        "day_start_hour": 8,  # 清醒时间开始
        "day_end_hour": 22,  # 清醒时间结束
        "awake_check_prob": 0.7,  # 清醒时检查手机概率
        "asleep_check_prob": 0.1,  # 睡眠时检查概率
    }

    if not DELIVERY_PARAMS_YAML.exists():
        print(f"  ⚠️  参数文件不存在,使用默认值")
        return default_params

    # 读取 YAML(需要 pyyaml,如果没装就回退到默认)
    try:
        import yaml
        with open(DELIVERY_PARAMS_YAML) as f:
            params = yaml.safe_load(f)
        print(f"  ✓ 读取自定义参数")
        return params
    except ImportError:
        print(f"  ⚠️  需要 pyyaml 读取参数文件,使用默认值")
        return default_params


def load_carr_world(target_n: int = 1000, max_step: int = 48, seed: int = 42) -> World:
    """加载完整的 Carr 世界。

    Args:
        target_n: 合成人口规模
        max_step: 仿真步数
        seed: 随机种子

    Returns:
        World 对象(包含 agents/hazard/warnings/delivery_params)
    """
    print(f"\n{'='*60}")
    print(f"加载 Carr Fire 事件包")
    print(f"{'='*60}\n")

    agents = load_carr_population(target_n=target_n, seed=seed)
    hazard = load_carr_hazard(max_step=max_step)
    warnings = load_carr_warnings()
    delivery_params = load_carr_delivery_params()

    world = World(
        name="carr_2018",
        agents=agents,
        hazard_zones=hazard,
        warnings=warnings,
        delivery_params=delivery_params,
        max_step=max_step
    )

    print(f"\n{'='*60}")
    print(f"✓ Carr 世界加载完成")
    print(f"  Agents: {len(agents)}")
    print(f"  Hazard zones: {len(hazard)} (step 0-{max_step-1})")
    print(f"  Warnings: {len(warnings)}")
    print(f"{'='*60}\n")

    return world


# ===== 命令行测试接口 =====
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100, help="合成人口规模")
    parser.add_argument("--steps", type=int, default=48, help="仿真步数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    world = load_carr_world(target_n=args.n, max_step=args.steps, seed=args.seed)

    # 输出样本统计
    print("\n样本 agent 属性:")
    for i in range(min(3, len(world.agents))):
        agent = world.agents[i]
        income = agent.demographics.get('income', 0)
        # 处理可能是字符串的情况
        try:
            income_val = float(income) if income else 0
            income_str = f"${income_val:,.0f}"
        except (ValueError, TypeError):
            income_str = str(income)

        print(f"  {agent.id}: age={agent.demographics.get('age', 'N/A')}, "
              f"income={income_str}, "
              f"hhsize={agent.demographics.get('household_size', 'N/A')}")
