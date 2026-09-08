"""LLM response cache = model snapshot (spec M0 §2).

Same (model, messages, seed, temperature) -> byte-identical response on replay,
even if the live model later changes. This is the foundation of our
reproducibility claim: "same config re-run = 100% cache hit" (spec §10.2).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path


class LLMCache:
    def __init__(self, path: str | Path = "experiments/runs/llm_cache.sqlite"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: we may touch it from asyncio.to_thread later
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS cache(
                key TEXT PRIMARY KEY, model TEXT, response TEXT,
                prompt_tokens INT, completion_tokens INT, created_at REAL)"""
        )
        self.db.commit()

    @staticmethod
    def make_key(model: str, messages: list, seed: int, temperature: float) -> str:
        blob = json.dumps(
            {"m": model, "msg": messages, "s": seed, "t": temperature},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    def get(self, key: str):
        row = self.db.execute(
            "SELECT response, prompt_tokens, completion_tokens FROM cache WHERE key=?",
            (key,),
        ).fetchone()
        return row if row else None

    def put(self, key: str, model: str, response: str, pt: int, ct: int) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO cache VALUES(?,?,?,?,?,?)",
            (key, model, response, pt, ct, time.time()),
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()
