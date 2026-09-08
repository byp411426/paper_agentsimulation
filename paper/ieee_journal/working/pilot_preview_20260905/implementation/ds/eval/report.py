"""One-page HTML run report (spec v2 §2.6).

Not a GUI — just four matplotlib panels stitched into a self-contained HTML file so
you can eyeball a run while debugging a society. Reads the run's events.jsonl and
llm_calls.jsonl and writes report.html into the run dir.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt  # noqa: E402


def _b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=90, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def build_report(run_dir: str | Path) -> Path:
    run_dir = Path(run_dir)
    events = _read_jsonl(run_dir / "events.jsonl")
    calls = _read_jsonl(run_dir / "llm_calls.jsonl")

    steps = [e["step"] for e in events]
    evac = [e["world"].get("n_evacuated", 0) for e in events]
    injured = [e["world"].get("n_injured", 0) for e in events]
    fire = [e["world"].get("fire_size", 0) for e in events]
    awake = [e.get("n_awake", 0) for e in events]
    msgs = [e.get("interaction", {}).get("delivered", 0) for e in events]

    panels = []

    # 1. evacuation / injury curve
    fig, ax = plt.subplots(figsize=(4.2, 3))
    ax.plot(steps, evac, label="evacuated", color="tab:green")
    ax.plot(steps, injured, label="injured", color="tab:red")
    ax.set_xlabel("step"); ax.set_ylabel("count"); ax.set_title("Outcomes")
    ax.legend(fontsize=8)
    panels.append(("Evacuation & injury", _b64(fig)))

    # 2. fire growth
    fig, ax = plt.subplots(figsize=(4.2, 3))
    ax.plot(steps, fire, color="tab:orange")
    ax.set_xlabel("step"); ax.set_ylabel("fire cells"); ax.set_title("Hazard growth")
    panels.append(("Fire size", _b64(fig)))

    # 3. wake / message activity
    fig, ax = plt.subplots(figsize=(4.2, 3))
    ax.plot(steps, awake, label="awake", color="tab:blue")
    ax.plot(steps, msgs, label="msgs delivered", color="tab:purple")
    ax.set_xlabel("step"); ax.set_ylabel("count"); ax.set_title("Activity")
    ax.legend(fontsize=8)
    panels.append(("Wake & messages", _b64(fig)))

    # 4. cost over calls (cumulative)
    fig, ax = plt.subplots(figsize=(4.2, 3))
    cum, tot = [], 0.0
    for c in calls:
        tot += c.get("cost", 0.0) or 0.0
        cum.append(tot)
    ax.plot(range(len(cum)), cum, color="tab:gray")
    ax.set_xlabel("call #"); ax.set_ylabel("USD"); ax.set_title("Cumulative cost")
    panels.append(("Cost", _b64(fig)))

    summary = {}
    sp = run_dir / "summary.json"
    if sp.exists():
        summary = json.loads(sp.read_text())

    html = _render(run_dir.name, panels, summary)
    out = run_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    return out


def _render(title: str, panels: list, summary: dict) -> str:
    imgs = "\n".join(
        f'<div class="panel"><h3>{name}</h3>'
        f'<img src="data:image/png;base64,{b64}"/></div>'
        for name, b64 in panels
    )
    gw = summary.get("gateway", {})
    meta = (f"seed={summary.get('run_seed')} · steps={summary.get('total_steps')} · "
            f"spent=${gw.get('spent', 0)} · fallback={gw.get('fallback_rate', 0):.2%} · "
            f"ok={gw.get('n_ok', 0)} cache={gw.get('n_cache', 0)}")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>DisasterSociety run: {title}</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;background:#fafafa}}
h1{{font-size:20px}} .meta{{color:#555;margin-bottom:16px;font-size:13px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:920px}}
.panel{{background:#fff;border:1px solid #e2e2e2;border-radius:8px;padding:12px}}
.panel h3{{margin:0 0 8px;font-size:14px}} img{{width:100%}}</style></head>
<body><h1>DisasterSociety — {title}</h1>
<div class="meta">{meta}</div>
<div class="grid">{imgs}</div></body></html>"""


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
