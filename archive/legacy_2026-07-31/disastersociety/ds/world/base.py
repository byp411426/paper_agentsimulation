"""[ARCHIVED] 旧 Carr runner 使用的基础世界数据结构。

定义仿真世界的标准数据模型:Agent / Warning / HazardZone / World。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class Agent:
    """仿真 agent(家庭/个体)。"""
    id: str
    demographics: Dict[str, Any]  # {age, income, household_size, vehicles, ...}
    location: Dict[str, Any]  # {tract, lat, lon}
    state: str = "home"  # 初始状态:home/evacuating/evacuated
    memory: List[Dict] = field(default_factory=list)  # 记忆事件
    trust: Dict[str, float] = field(default_factory=dict)  # 信任分数


@dataclass
class Warning:
    """预警消息。"""
    step: int  # 发布时刻(仿真步)
    kind: str  # 类型:mandatory/voluntary/shelter
    zone: str  # 覆盖区域:all/tract_id/...
    text: str  # 预警文本
    channels: List[str] = field(default_factory=lambda: ["wea"])  # 渠道:wea/tv/radio/social


@dataclass
class HazardZone:
    """时序危险区。"""
    step: int  # 生效时刻
    geometry: Dict[str, Any]  # GeoJSON 几何(Polygon/Point)
    buffer_km: float = 0.0  # 缓冲半径(简化版用)
    radius_km: float = 0.0  # Point 类型用半径
    severity: str = "high"  # 危险等级


@dataclass
class World:
    """完整的仿真世界。"""
    name: str  # 事件名(如 "carr_2018")
    agents: List[Agent]
    hazard_zones: List[HazardZone]
    warnings: List[Warning]
    delivery_params: Dict[str, Any]
    max_step: int = 48
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_warnings_at_step(self, step: int) -> List[Warning]:
        """获取某一步的所有预警。"""
        return [w for w in self.warnings if w.step == step]

    def get_hazard_at_step(self, step: int) -> Optional[HazardZone]:
        """获取某一步的危险区。"""
        zones = [h for h in self.hazard_zones if h.step == step]
        return zones[0] if zones else None

    def agent_in_hazard(self, agent: Agent, step: int) -> bool:
        """判断 agent 是否在危险区内(简化版:距离判断)。"""
        hazard = self.get_hazard_at_step(step)
        if not hazard:
            return False

        # 简化:如果 hazard 是 Point 类型,用半径判断
        if hazard.geometry.get("type") == "Point":
            import math
            coords = hazard.geometry["coordinates"]  # [lon, lat]
            agent_lat = agent.location.get("lat", 0)
            agent_lon = agent.location.get("lon", 0)

            # 简单的 Haversine 距离(km)
            dlat = math.radians(agent_lat - coords[1])
            dlon = math.radians(agent_lon - coords[0])
            a = math.sin(dlat/2)**2 + math.cos(math.radians(coords[1])) * \
                math.cos(math.radians(agent_lat)) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            dist_km = 6371 * c  # 地球半径

            return dist_km <= (hazard.radius_km + hazard.buffer_km)

        # 真实版:用 shapely 做空间查询
        return False
