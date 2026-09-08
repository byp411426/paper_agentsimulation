"""Validated EventPack manifest and asset references."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventPackAsset(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str


class EventPackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    hazard_type: str
    timezone: str
    spatial_crs: str
    simulation_step_minutes: int = Field(gt=0)
    data: dict[str, EventPackAsset]
    provenance: str

    @field_validator("event_id", "hazard_type", "timezone", "spatial_crs")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("EventPack identifier fields cannot be empty")
        return value


class LoadedEventPack(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    root: Path
    manifest: EventPackManifest
    assets: dict[str, Path]
    provenance_path: Path

    def asset(self, relative_path: str) -> Path:
        try:
            return self.assets[relative_path]
        except KeyError as exc:
            raise KeyError(f"undeclared EventPack asset: {relative_path}") from exc

    def provenance(self) -> dict[str, Any]:
        import yaml

        return yaml.safe_load(self.provenance_path.read_text(encoding="utf-8"))
