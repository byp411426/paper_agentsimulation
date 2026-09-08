"""Validated EventPack loading plus in-memory event sources."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from ds.eventpack.schema import EventPackManifest, LoadedEventPack
from ds.interaction.messages import Event


class ListEventSource:
    def __init__(self, events: list[Event]):
        self.events = sorted(events, key=lambda e: e.step)

    def events_due(self, step: int) -> list[Event]:
        return [e for e in self.events if e.step == step]


def toy_warning_events(warning_step: int, text: str = "EVACUATION ORDER issued. "
                       "Leave immediately.") -> ListEventSource:
    return ListEventSource([
        Event(step=warning_step, kind="warning", text=text, recipients="all"),
    ])


def load_eventpack(
    root: str | Path,
    *,
    require_assets: bool = True,
) -> LoadedEventPack:
    root = Path(root).resolve()
    manifest_path = root / "manifest.yaml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"EventPack manifest not found: {manifest_path}")
    manifest = EventPackManifest.model_validate(
        yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    )
    assets = {
        relative: (root / relative).resolve()
        for relative in manifest.data
    }
    missing = [
        relative
        for relative, path in assets.items()
        if not path.exists()
    ]
    if require_assets and missing:
        raise FileNotFoundError(
            f"EventPack {manifest.event_id} missing declared assets: {missing}"
        )
    provenance_path = (root / manifest.provenance).resolve()
    if require_assets and not provenance_path.is_file():
        raise FileNotFoundError(
            f"EventPack provenance not found: {manifest.provenance}"
        )
    return LoadedEventPack(
        root=root,
        manifest=manifest,
        assets=assets,
        provenance_path=provenance_path,
    )


def load_warning_events(
    path: str | Path,
    *,
    recipient_override: dict[int, object] | None = None,
) -> ListEventSource:
    """Load warning/control events without treating scenario rows as history."""
    frame = pd.read_csv(path)
    required = {"step", "kind", "text"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"warning event table missing columns: {sorted(missing)}")
    events: list[Event] = []
    for row in frame.to_dict(orient="records"):
        raw_kind = str(row["kind"]).strip().lower()
        kind, payload = _event_kind(raw_kind)
        step = int(row["step"])
        zone = _optional_text(row.get("zone"))
        recipients: object = zone or "all"
        if recipient_override and step in recipient_override:
            recipients = recipient_override[step]
        payload["source_kind"] = raw_kind
        channels = _optional_text(row.get("channels"))
        if channels:
            payload["channels"] = channels.split(";")
        events.append(
            Event(
                step=step,
                kind=kind,
                text=str(row.get("text", "")),
                zone=zone,
                recipients=recipients,
                payload=payload,
            )
        )
    return ListEventSource(events)


def _event_kind(raw_kind: str) -> tuple[str, dict]:
    if raw_kind in {"advisory", "voluntary", "mandatory", "warning"}:
        return "warning", {"severity": raw_kind}
    if raw_kind in {"order"}:
        return "order", {"severity": raw_kind}
    if raw_kind in {"shelter", "shelter_open"}:
        return "shelter_open", {}
    if raw_kind == "update":
        return "hazard_update", {}
    if raw_kind in {"road_closed", "hazard_update"}:
        return raw_kind, {}
    raise ValueError(f"unsupported EventPack event kind: {raw_kind}")


def _optional_text(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None
