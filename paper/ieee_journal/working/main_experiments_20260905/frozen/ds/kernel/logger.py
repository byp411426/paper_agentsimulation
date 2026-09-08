"""Structured run logger (spec §3 step ⑦, v2: flush before assert_valid raises).

Writes one JSONL line per step to events.jsonl (full state/decision/message/world
snapshot), plus a final summary.json. Everything is plain dicts so DuckDB can query
the logs directly without a schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RunLogger:
    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self._f = open(self.events_path, "w", encoding="utf-8")
        self._closed = False

    def dump_step(self, record: dict[str, Any]) -> None:
        """Append one step record. Caller builds the dict (engine)."""
        self._f.write(json.dumps(record, ensure_ascii=False, default=_json_default) + "\n")

    def flush(self) -> None:
        if not self._closed:
            self._f.flush()

    def dump_final(self, summary: dict[str, Any]) -> None:
        self.flush()
        (self.run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, default=_json_default),
            encoding="utf-8",
        )

    def close(self) -> None:
        if not self._closed:
            self._f.flush()
            self._f.close()
            self._closed = True

    def read_events(self) -> list[dict]:
        """Read back all step records (used by tests / determinism check)."""
        with open(self.events_path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


def _json_default(o: Any):
    # tuples -> lists, sets -> sorted lists, anything else -> str
    if isinstance(o, set):
        return sorted(o, key=str)
    if isinstance(o, tuple):
        return list(o)
    return str(o)
