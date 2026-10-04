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


class _UniqueKeyLoader(yaml.SafeLoader):
    """PyYAML silently keeps the last of duplicate keys; for assumptions that would silently drop data."""


def _construct_mapping(loader, node, deep=False):
    keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise ValueError(f"duplicate keys in assumptions.yaml: {sorted(dupes)} (line {node.start_mark.line + 1})")
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


class Assumptions:
    """Access as `a["policy.ll97_penalty"]` (Assumption) or `a.v("policy.ll97_penalty")` (float)."""

    def __init__(self, entries: dict[str, Assumption]):
        self._entries = entries

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "Assumptions":
        raw = yaml.load(path.read_text(), Loader=_UniqueKeyLoader)
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
