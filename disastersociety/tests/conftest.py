"""Shared pytest fixtures (offline: mock backend, temp cache, zero cost)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pydantic import BaseModel

from ds.llm.backends import MockBackend
from ds.llm.cache import LLMCache
from ds.llm.gateway import LLMGateway


class XSchema(BaseModel):
    x: int


MODELS_CFG = {
    "models": {
        "mock": {"backend": "mock", "input_per_m": 0.0, "output_per_m": 0.0},
        "priced": {"backend": "mock", "input_per_m": 1000.0, "output_per_m": 1000.0},
    }
}


@pytest.fixture
def tmp_run(tmp_path) -> Path:
    return tmp_path


@pytest.fixture
def cache(tmp_path) -> LLMCache:
    return LLMCache(tmp_path / "cache.sqlite")


def make_gateway(tmp_path, *, backends=None, budget=10.0, model_cfg=None) -> LLMGateway:
    return LLMGateway(
        run_id="test",
        models_cfg=model_cfg or MODELS_CFG,
        budget_usd=budget,
        max_concurrency=8,
        log_dir=tmp_path,
        cache=LLMCache(tmp_path / "cache.sqlite"),
        backends=backends,
    )


@pytest.fixture
def gw(tmp_path) -> LLMGateway:
    return make_gateway(tmp_path)
