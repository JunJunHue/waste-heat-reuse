"""Site configuration: everything site-specific lives in config/sites/<id>.yaml, never in code."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
SITES_DIR = ROOT / "config" / "sites"


class RangedParam(BaseModel):
    value: float
    low: float
    high: float
    confidence: str
    source: str


class DataCenter(BaseModel):
    name: str
    lon: float
    lat: float
    it_load_mw: RangedParam
    existing_cooling: str
    ll84_bbl: str | None = None


class StudyArea(BaseModel):
    bbox: list[float]  # [west, south, east, north]


class Grid(BaseModel):
    iso: str
    lbmp_zone: str
    lbmp_avg_key: str


class Weather(BaseModel):
    lat: float
    lon: float
    year: int


class Exclusion(BaseModel):
    pattern: str
    reason: str
    source: str


class Screening(BaseModel):
    max_fossil_intensity_kbtu_ft2: float = 200
    exclusions: list[Exclusion] = []


class Site(BaseModel):
    id: str
    name: str
    kind: str
    county_fips: str
    adapter: str  # which building-data adapter prepare.py uses: "nyc" or "synthetic_upstate"
    data_center: DataCenter
    study_area: StudyArea
    grid: Grid
    weather: Weather
    screening: Screening = Screening()

    @classmethod
    def load(cls, site_id: str) -> "Site":
        return cls(**yaml.safe_load((SITES_DIR / f"{site_id}.yaml").read_text()))

    @property
    def processed_dir(self) -> Path:
        return ROOT / "data" / "processed" / self.id
