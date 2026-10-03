"""Typed loader for config/assumptions.yaml. Every entry must carry unit, source and confidence."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "config" / "assumptions.yaml"


class Assumption(BaseModel):
    value: float
    unit: str
    source: str
    confidence: Literal["high", "medium", "low"]
    low: float | None = None
    high: float | None = None

    @model_validator(mode="after")
    def _range_brackets_value(self) -> "Assumption":
        if self.low is not None and self.low > self.value:
            raise ValueError(f"low {self.low} > value {self.value}")
        if self.high is not None and self.high < self.value:
            raise ValueError(f"high {self.high} < value {self.value}")
        return self


class Assumptions:
    """Access as `a["policy.ll97_penalty"]` (Assumption) or `a.v("policy.ll97_penalty")` (float)."""

    def __init__(self, entries: dict[str, Assumption]):
        self._entries = entries

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "Assumptions":
        raw = yaml.safe_load(path.read_text())
        entries = {
            f"{group}.{key}": Assumption(**spec)
            for group, items in raw.items()
            for key, spec in items.items()
        }
        return cls(entries)

    def __getitem__(self, key: str) -> Assumption:
        return self._entries[key]

    def v(self, key: str) -> float:
        return self._entries[key].value

    def items(self):
        return self._entries.items()
