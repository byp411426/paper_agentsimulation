"""Documented host interfaces for unchanged upstream AgentSociety blocks.

This is a local environment/memory/LLM bridge, not an AgentSociety replacement.
The actual NeedsBlock, PlanBlock and CognitionBlock execute from vendor/.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta
import json
import logging
import re
from types import SimpleNamespace
from pydantic import BaseModel
from .ga_support import get_embedding

class BlockParams(BaseModel):
    pass

class DotDict(dict):
    def __getattr__(self, key):
        return self.get(key)
    def __setattr__(self, key, value):
        self[key] = value

class Block:
    def __init__(self, *, toolbox, agent_memory, block_params=None):
        self.memory = agent_memory
        self.llm = toolbox.llm
        self.environment = toolbox.environment
        self.params = block_params or getattr(self, "ParamsType", BlockParams)()
    def set_agent(self, agent):
        self.agent = agent

AgentToolbox = SimpleNamespace
Agent = SimpleNamespace

def get_logger():
    return logging.getLogger("disastersociety.baselines.agentsociety")

class FormatPrompt:
    def __init__(self, template, memory=None):
        self.template, self.memory, self.text = template, memory, None
    async def format(self, **kwargs):
        def replace(match):
            token = match.group(0)
            if token in ("{{", "}}"):
                return token[0]
            area, name, field = match.groups()
            if area:
                values = self.memory.status.data if area == "profile" else kwargs.get("context", {})
                return str(values.get(name, "not provided"))
            return str(kwargs[field]) if field in kwargs else token
        # One pass over the template: never parse or unescape inserted JSON.
        pattern = r"\{\{|\}\}|\$\{(profile|context)\.([^}]+)\}|\{([a-zA-Z_][a-zA-Z_0-9]*)\}"
        self.text = re.sub(pattern, replace, self.template)
    def to_dialog(self):
        if self.text is None:
            raise RuntimeError("Prompt must be formatted before use")
        return [{"role": "user", "content": self.text}]

class Status:
    def __init__(self, data):
        self.data = deepcopy(data)
    async def get(self, key, *args, **kwargs):
        return deepcopy(self.data.get(key, "not provided"))
    async def update(self, key, value, *args, **kwargs):
        self.data[key] = deepcopy(value)

class Stream:
    def __init__(self, environment):
        self.rows, self.environment = [], environment
    async def add(self, *, topic, description, **kwargs):
        node_id = len(self.rows)
        self.rows.append({"id": node_id, "step": self.environment.step,
                          "topic": topic, "description": str(description)})
        return node_id
    async def search(self, query, top_k=20, **kwargs):
        import numpy as np
        q = get_embedding(query)
        rows = sorted(self.rows, key=lambda r: float(np.dot(q, get_embedding(r["description"]))), reverse=True)[:top_k]
        return json.dumps(rows, ensure_ascii=False)
    async def search_today(self, top_k=20):
        return json.dumps(self.rows[-top_k:], ensure_ascii=False)
    async def get_by_ids(self, ids):
        return [deepcopy(self.rows[i]) for i in ids]
    async def add_cognition_to_memory(self, ids, conclusion):
        return await self.add(topic="cognition", description=json.dumps({"evidence": ids, "conclusion": conclusion}))

class Memory:
    def __init__(self, status, environment):
        self.status, self.stream = Status(status), Stream(environment)

class Environment:
    def __init__(self):
        self.step = 0
        self.step_minutes = 30
        self.payload = {}
    def get_tick(self):
        return (8 * 60 + self.step * self.step_minutes) * 60
    def get_datetime(self, format_time=False):
        tick = self.get_tick()
        day, seconds = divmod(tick, 86400)
        if format_time:
            return day, f"{seconds//3600:02}:{seconds%3600//60:02}:00"
        return day, seconds
    def sense(self, name):
        if name == "workday":
            return False  # A bounded emergency response episode, without an employment environment.
        if name == "other_information":
            return json.dumps(self.payload, ensure_ascii=False)
        return "not provided"
