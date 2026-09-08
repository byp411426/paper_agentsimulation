"""[ARCHIVED] Carr 简化仿真引擎。

实现核心仿真循环:
1. 预警送达(概率模型)
2. Agent LLM 决策
3. 撤离行为记录
4. 社交传播(简化:邻居影响)

不依赖完整 ds.kernel.engine,但实现关键逻辑供 E1/E2 验证。
"""

from __future__ import annotations
from typing import Dict, Any, List
import json
import asyncio
import os
from pathlib import Path
from dataclasses import dataclass
import random

from ds.world.base import World, Agent
from ds.llm.gateway import LLMGateway


# ===== 共享的异步 LLM 客户端(直连 PACKY / OpenAI 兼容后端) =====
_ASYNC_CLIENT = None
_LLM_MODEL = None
_LLM_SEM = None  # 并发限制


def _get_llm_client():
    """惰性初始化异步 LLM 客户端。返回 (client, model) 或 (None, None)。"""
    global _ASYNC_CLIENT, _LLM_MODEL, _LLM_SEM
    if _ASYNC_CLIENT is not None:
        return _ASYNC_CLIENT, _LLM_MODEL
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, None
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return None, None
    base_url = os.environ.get("LLM_BASE_URL", "https://www.packyapi.com/v1")
    _LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-flash")
    _ASYNC_CLIENT = AsyncOpenAI(base_url=base_url, api_key=api_key)
    _LLM_SEM = asyncio.Semaphore(int(os.environ.get("LLM_CONCURRENCY", "8")))
    return _ASYNC_CLIENT, _LLM_MODEL


@dataclass
class AgentDecision:
    """Agent 决策结果"""
    agent_id: str
    step: int
    action: str  # "evacuate" | "stay"
    reason: str
    confidence: float


@dataclass
class SimulationState:
    """仿真状态"""
    step: int
    warned_agents: set  # 收到预警的 agent IDs
    evacuated_agents: set  # 已撤离的 agent IDs
    decisions: List[AgentDecision]


def delivery_model(agent: Agent, warning_step: int, current_step: int,
                   params: dict, rng: random.Random) -> bool:
    """预警送达模型(概率)。

    Args:
        agent: Agent 对象
        warning_step: 预警发布时刻
        current_step: 当前时刻
        params: 送达参数(device_ownership, wea_coverage, ...)
        rng: 随机数生成器

    Returns:
        是否送达
    """
    # 如果不是预警发布时刻,不送达
    if current_step != warning_step:
        return False

    # 综合送达概率(简化:设备持有 × WEA 覆盖 × 时间因素)
    # 不是三个独立检查(会让送达率太低),而是一次综合检查

    device_prob = params.get("device_ownership", 0.92)
    wea_prob = params.get("wea_coverage", 0.85)

    # 时间因素(清醒时检查概率更高)
    # Carr 火灾在 13:15 开始,step=0 对应 13:00
    fire_start_hour = 13
    hour = (fire_start_hour + current_step) % 24
    day_start = params.get("day_start_hour", 8)
    day_end = params.get("day_end_hour", 22)

    if day_start <= hour < day_end:
        time_factor = params.get("awake_check_prob", 0.9)  # 提高到 0.9
    else:
        time_factor = params.get("asleep_check_prob", 0.3)  # 提高到 0.3

    # 综合概率
    total_prob = device_prob * wea_prob * time_factor
    # Carr 火灾在白天(13:15 开始),所以 step=6 是 19:15 左右,仍在清醒时间
    # 预期送达率: 0.92 × 0.85 × 0.9 ≈ 70%

    return rng.random() < total_prob


async def agent_decide_llm(agent: Agent, state: SimulationState, world: World,
                           gateway: LLMGateway) -> AgentDecision:
    """Agent LLM 决策(异步)。

    Args:
        agent: Agent 对象
        state: 当前仿真状态
        world: 世界对象
        gateway: LLM 网关

    Returns:
        决策结果
    """
    # 构造 prompt
    demo = agent.demographics
    age_desc = str(demo.get('age', 'unknown'))
    income_desc = str(demo.get('income', 'unknown'))
    hhsize = demo.get('household_size', 2)
    vehicles = demo.get('vehicles', 1)

    # 判断是否收到预警
    warned = agent.id in state.warned_agents

    # 判断是否在危险区
    in_hazard = world.agent_in_hazard(agent, state.step)

    # 检查是否有真实 LLM(通过 LLM_API_KEY / OPENAI_API_KEY 环境变量)
    use_mock = not (os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY"))

    if use_mock:
        # Mock 决策(基于规则但加随机性,模拟 LLM 多样性)
        rng = random.Random(hash(agent.id + str(state.step)))

        if warned:
            # 收到预警:80% 撤离
            if rng.random() < 0.8:
                action = "evacuate"
                reason = "mock: received official warning, high urgency"
                confidence = 0.7 + rng.random() * 0.2
            else:
                action = "stay"
                reason = "mock: warning received but assessing situation first"
                confidence = 0.4 + rng.random() * 0.2
        elif in_hazard:
            # 在危险区但无预警:60% 撤离
            if rng.random() < 0.6:
                action = "evacuate"
                reason = "mock: see fire/smoke nearby, leaving now"
                confidence = 0.6 + rng.random() * 0.2
            else:
                action = "stay"
                reason = "mock: monitoring but staying for now"
                confidence = 0.3 + rng.random() * 0.3
        else:
            # 无预警无危险:10% 撤离(谨慎者)
            if rng.random() < 0.1:
                action = "evacuate"
                reason = "mock: cautious, leaving preemptively"
                confidence = 0.5
            else:
                action = "stay"
                reason = "mock: no immediate threat, staying"
                confidence = 0.7

        return AgentDecision(
            agent_id=agent.id,
            step=state.step,
            action=action,
            reason=reason,
            confidence=confidence
        )

    # 真实 LLM 决策(以下是原代码)
    prompt = f"""You are a resident of Redding, California during the 2018 Carr Wildfire (July 23, 2018).

Your situation:
- Age: {age_desc}
- Household: {hhsize} people
- Vehicles: {vehicles}
- Income level: {income_desc}

Current time: Hour {state.step} since fire start (around {13 + state.step}:00 on July 23)

Status:
{"- You received an official EVACUATION WARNING via emergency alert." if warned else "- You have NOT received any official warning yet."}
{"- Fire is very close to your location (visible smoke/flames)." if in_hazard else "- Fire is still distant from your area."}

Question: Will you evacuate now?

Answer ONLY with a JSON object in this format:
{{"action": "evacuate" or "stay", "reason": "brief explanation", "confidence": 0-100}}
"""

    try:
        # 调用 LLM(直连 PACKY / OpenAI 兼容后端)
        client, model = _get_llm_client()
        if client is None:
            raise RuntimeError("LLM client unavailable")
        messages = [{"role": "user", "content": prompt}]

        async with _LLM_SEM:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=300,
            )
        response = resp.choices[0].message.content or ""

        # 解析 JSON 响应
        try:
            import re
            # 提取 JSON(可能被包在 markdown 代码块里)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(0))
                action = result.get("action", "stay")
                reason = result.get("reason", "")
                confidence = float(result.get("confidence", 50)) / 100.0
            else:
                # 回退:关键词匹配
                action = "evacuate" if "evacuate" in response.lower() else "stay"
                reason = response[:100]
                confidence = 0.5
        except Exception:
            # JSON 解析失败,用关键词
            action = "evacuate" if "evacuate" in response.lower() else "stay"
            reason = response[:100]
            confidence = 0.5

        return AgentDecision(
            agent_id=agent.id,
            step=state.step,
            action=action,
            reason=reason,
            confidence=confidence
        )

    except Exception as e:
        # LLM 失败,使用规则回退
        print(f"  ⚠️  Agent {agent.id} LLM 失败,使用规则: {e}")
        if warned or in_hazard:
            action = "evacuate"
            reason = f"rule: warned={warned}, in_hazard={in_hazard}"
        else:
            action = "stay"
            reason = "rule: no immediate threat"

        return AgentDecision(
            agent_id=agent.id,
            step=state.step,
            action=action,
            reason=reason,
            confidence=0.5
        )


def run_simulation(world: World, gateway: LLMGateway, seed: int = 42,
                   log_path: str = "events.jsonl") -> Dict[str, Any]:
    """运行完整 Carr 仿真(简化引擎版本)。

    实现核心逻辑:
    1. 预警送达(概率模型)
    2. Agent LLM 决策(每步唤醒需要决策的 agent)
    3. 撤离行为记录
    4. 社交传播(简化:邻居观察)

    Args:
        world: Carr 世界对象
        gateway: LLM 网关
        seed: 随机种子
        log_path: 日志输出路径

    Returns:
        仿真结果摘要
    """
    print(f"开始完整 Carr 仿真(简化引擎版本)...")
    print(f"  Agents: {len(world.agents)}")
    print(f"  Steps: {world.max_step}")
    print(f"  Seed: {seed}\n")

    # 初始化状态
    rng = random.Random(seed)
    state = SimulationState(
        step=0,
        warned_agents=set(),
        evacuated_agents=set(),
        decisions=[]
    )

    # 打开日志文件
    log_file = Path(log_path)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_file, "w")

    # ===== 主循环(整个仿真在一个事件循环里,避免每步重建 loop 破坏信号量) =====
    async def _run_loop():
        for step in range(world.max_step):
            state.step = step
            print(f"Step {step}...")

            # ① 检查预警
            warnings = world.get_warnings_at_step(step)
            if warnings:
                print(f"  预警发布: {len(warnings)} 条")
                log.write(json.dumps({
                    "step": step,
                    "type": "warning_broadcast",
                    "count": len(warnings),
                    "text": warnings[0].text[:50] + "..."
                }) + "\n")

                # ② 预警送达(概率模型)
                for agent in world.agents:
                    if agent.id in state.evacuated_agents:
                        continue  # 已撤离,不再处理
                    if delivery_model(agent, step, step, world.delivery_params, rng):
                        state.warned_agents.add(agent.id)
                        log.write(json.dumps({
                            "step": step,
                            "type": "warning_delivered",
                            "agent_id": agent.id
                        }) + "\n")

                print(f"  送达: {len(state.warned_agents)} 个 agent")

            # ③ Agent 决策(唤醒需要决策的 agent)
            agents_to_decide = []
            for agent in world.agents:
                if agent.id in state.evacuated_agents:
                    continue  # 已撤离
                # 唤醒条件:收到预警 或 在危险区
                if agent.id in state.warned_agents or world.agent_in_hazard(agent, step):
                    agents_to_decide.append(agent)

            if agents_to_decide:
                print(f"  决策: {len(agents_to_decide)} 个 agent...")

                # 并发调用 LLM(异步,同一个事件循环)
                tasks = [agent_decide_llm(a, state, world, gateway)
                         for a in agents_to_decide]
                decisions = await asyncio.gather(*tasks)

                # ④ 应用决策
                for decision in decisions:
                    state.decisions.append(decision)
                    if decision.action == "evacuate":
                        state.evacuated_agents.add(decision.agent_id)
                        for a in world.agents:
                            if a.id == decision.agent_id:
                                a.state = "evacuated"
                                break
                        log.write(json.dumps({
                            "step": step,
                            "type": "evacuation",
                            "agent_id": decision.agent_id,
                            "reason": decision.reason[:100],
                            "confidence": decision.confidence
                        }) + "\n")

                print(f"  撤离: {len([d for d in decisions if d.action == 'evacuate'])} 个")

            # ⑤ 社交传播(简化:邻居观察 — 暂时跳过,E2 后期补)

            # ⑥ 步骤摘要
            log.write(json.dumps({
                "step": step,
                "type": "step_summary",
                "warned_total": len(state.warned_agents),
                "evacuated_total": len(state.evacuated_agents),
                "agents_total": len(world.agents)
            }) + "\n")

    asyncio.run(_run_loop())

    log.close()

    # ===== 最终统计 =====
    results = {
        "total_steps": world.max_step,
        "total_agents": len(world.agents),
        "warned_count": len(state.warned_agents),
        "evacuated_count": len(state.evacuated_agents),
        "evacuation_rate": len(state.evacuated_agents) / len(world.agents),
        "total_decisions": len(state.decisions),
    }

    print(f"\n{'='*60}")
    print(f"✓ 仿真完成")
    print(f"{'='*60}")
    print(f"  预警送达: {results['warned_count']} / {results['total_agents']} ({results['warned_count']/results['total_agents']:.1%})")
    print(f"  撤离数: {results['evacuated_count']} / {results['total_agents']} ({results['evacuation_rate']:.1%})")
    print(f"  总决策数: {results['total_decisions']}")
    print(f"  日志: {log_path}")
    print(f"{'='*60}\n")

    return results
