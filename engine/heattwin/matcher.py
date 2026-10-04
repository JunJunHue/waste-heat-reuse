"""Offtaker matcher: score every candidate on the brief's five fit dimensions (+ proximity and equity).

Every dimension is in [0, 1] and is reported separately, so the ranking is explainable:
  temperature  - heat-pump COP at the building's demand-weighted required supply temperature (physics)
  capacity     - annual heat demand on a log scale (anchor loads justify a connection)
  timing       - load factor (mean/peak): flat 24/7 loads match a flat data-center source
  seasonality  - summer demand relative to the annual average (DHW keeps heat useful year-round)
  continuity   - long-term anchor stability of the occupant type (rubric in assumptions.yaml)
  proximity    - straight-line distance from the data center (network routing comes later)
  equity       - CDC SVI percentile of the tract; NYCHA public housing scores 1.0
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .assumptions import Assumptions
from .demand import required_supply_temp
from .heatpump import CopTable

DIMS = ["temperature", "capacity", "timing", "seasonality", "continuity", "proximity", "equity"]
LABELS = {
    "temperature": "low required temperature (efficient heat pump)", "capacity": "large anchor load",
    "timing": "steady round-the-clock demand", "seasonality": "year-round hot-water demand",
    "continuity": "stable long-term owner", "proximity": "close to the data center",
    "equity": "serves a high-vulnerability community",
}


def _haversine_m(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * np.arcsin(np.sqrt(h))


def _continuity(row, a: Assumptions) -> float:
    t = str(row.ll84_type or "")
    if row.is_nycha:
        return a.v("continuity.public_housing")
    if any(k in t for k in ("Hospital", "College", "University", "School", "Medical")):
        return a.v("continuity.institution")
    if any(k in t for k in ("Multifamily", "Residence", "Senior", "Dormitory")):
        return a.v("continuity.multifamily")
    if "Hotel" in t:
        return a.v("continuity.hotel")
    if "Office" in t:
        return a.v("continuity.office")
    return a.v("continuity.other")


def score(off: pd.DataFrame, M: np.ndarray, hourly: pd.DataFrame, t_src_out: float, dc_lonlat: tuple[float, float],
          a: Assumptions, cop: CopTable, equity_weight: float | None = None) -> pd.DataFrame:
    """Return off with s_<dim> columns, total score, rank and a one-line rationale."""
    df = off.copy()
    t_out = hourly.t_out_c.to_numpy()
    approach = a.v("heat_pump.approach_k")

    # temperature: demand-weighted required supply temperature over the year -> COP
    t_req_avg = np.array([
        (required_supply_temp(t_out, td, a) * M[i]).sum() / M[i].sum()
        for i, td in enumerate(df.t_supply_design_c.to_numpy())
    ])
    dhw_floor = a.v("demand.t_dhw_min")
    t_sink = np.maximum(t_req_avg, dhw_floor * (df.dhw_mwh / df.heat_mwh).to_numpy()) + approach
    cop_b = cop(np.full(len(df), t_src_out), t_sink)
    cop_hi, cop_lo = float(cop(t_src_out, 50 + approach)), float(cop(t_src_out, 85 + approach))
    s_temp = np.clip((cop_b - cop_lo) / (cop_hi - cop_lo), 0, 1)
    s_temp = np.where(df.needs_steam_conversion, 0.85 * s_temp, s_temp)  # conversion adds cost and risk
    df["t_req_avg_c"] = t_req_avg
    df["cop_at_building"] = cop_b

    df["s_temperature"] = s_temp
    df["s_capacity"] = np.clip(np.log(df.heat_mwh / 300) / np.log(20_000 / 300), 0, 1)
    lf = M.mean(axis=1) / M.max(axis=1)
    df["load_factor"] = lf
    df["s_timing"] = np.clip((lf - lf.min()) / (lf.max() - lf.min()), 0, 1)
    month = pd.to_datetime(hourly.local).dt.month.to_numpy()
    summer = np.isin(month, [6, 7, 8, 9])
    summer_ratio = (M[:, summer].sum(axis=1) / summer.sum()) / (M.sum(axis=1) / M.shape[1])
    df["summer_ratio"] = summer_ratio
    df["s_seasonality"] = np.clip(summer_ratio / summer_ratio.max(), 0, 1)
    df["s_continuity"] = df.apply(lambda r: _continuity(r, a), axis=1)
    dist = _haversine_m(dc_lonlat[0], dc_lonlat[1], df.lon.to_numpy(), df.lat.to_numpy())
    df["distance_m"] = dist
    df["s_proximity"] = np.clip(1 - dist / a.v("matcher.max_distance_m"), 0, 1)
    df["s_equity"] = np.where(df.is_nycha, 1.0, df.svi.fillna(df.svi.median()))

    w = {d: a.v(f"matcher.w_{d}") for d in DIMS if d != "equity"}
    w["equity"] = a.v("matcher.w_equity") if equity_weight is None else equity_weight
    total_w = sum(w.values())
    df["fit_score"] = sum(w[d] * df[f"s_{d}"] for d in DIMS if d != "equity") / (total_w - w["equity"])
    df["total_score"] = sum(w[d] * df[f"s_{d}"] for d in DIMS) / total_w
    df["eligible"] = dist <= a.v("matcher.max_distance_m")
    df = df.sort_values(["eligible", "total_score"], ascending=[False, False]).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)
    df["rationale"] = df.apply(_rationale, axis=1)
    return df


def _rationale(r) -> str:
    s = {d: r[f"s_{d}"] for d in DIMS}
    top = sorted(s, key=s.get, reverse=True)[:2]
    weak = min(s, key=s.get)
    text = f"Strong on {LABELS[top[0]]} and {LABELS[top[1]]}"
    if s[weak] < 0.35:
        text += f"; weaker on {LABELS[weak].split(' (')[0]}"
    return text + "."
