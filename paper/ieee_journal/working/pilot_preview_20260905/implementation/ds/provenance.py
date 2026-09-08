"""Run fingerprint (spec v2 §2.6): git SHA, config snapshot, lockfile hash, models.

Written to every run directory as provenance.json so any figure in the paper can
be traced back to the exact code + config that produced it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except Exception:
        return "unknown"


def _git_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, text=True
        )
        return bool(out.strip())
    except Exception:
        return False


def _file_hash(path: str | Path) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def write_provenance(
    run_dir: str | Path,
    config: dict[str, Any],
    models: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    prov = {
        "git_sha": _git_sha(),
        "git_dirty": _git_dirty(),
        "config": config,
        "models": models or [],
        "lockfile_sha": _file_hash("uv.lock") or _file_hash("pyproject.toml"),
    }
    if extra:
        prov.update(extra)
    out = run_dir / "provenance.json"
    out.write_text(json.dumps(prov, indent=2, ensure_ascii=False), encoding="utf-8")
    return out
