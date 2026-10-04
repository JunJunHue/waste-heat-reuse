"""Data-center heat supply: hourly IT load -> recoverable heat at the capture point.

Site 1 IT load is derived from the building's own LL84 disclosure (docs/DECISIONS.md D7); other sites use the
ranged parameter in their site config.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .assumptions import Assumptions
from .data import sources as S
from .scenario import Scenario
from .site import Site


def derive_it_load(site: Site, a: Assumptions) -> dict:
    """IT load = (building electricity - office baseline) / PUE, every input from LL84 2023."""
    dc = site.data_center
    if not dc.ll84_bbl:
        p = dc.it_load_mw
        return {"value": p.value, "low": p.low, "high": p.high, "method": "site config parameter", "source": p.source,
                "confidence": p.confidence}
    ll = pd.DataFrame(json.loads(S.nyc_ll84(2023).read_text()))
    ll["kwh"] = pd.to_numeric(ll.electricity_use_grid_purchase, errors="coerce")
    ll["gfa"] = pd.to_numeric(ll.property_gfa_self_reported, errors="coerce")
    me = ll[ll.nyc_borough_block_and_lot == dc.ll84_bbl].iloc[0]
    offices = ll[(ll.primary_property_type == "Office") & (ll.gfa > 500_000) & (ll.kwh > 0)]
    intensity = offices.kwh / offices.gfa
    bldg_mw = me.kwh / 8760 / 1000
    base = lambda q: intensity.quantile(q) * me.gfa / 8760 / 1000
    q = a["supply.office_baseline_quantile"]
    pue = a["supply.pue_air_cooled"]
    central = (bldg_mw - base(q.value)) / pue.value
    low = (bldg_mw - base(q.high)) / pue.high
    high = (bldg_mw - base(q.low)) / pue.low
    return {
        "value": round(float(central), 1), "low": round(float(low), 1), "high": round(float(high), 1), "confidence": "medium",
        "method": "LL84 building electricity minus LL84 office-median baseline, divided by PUE",
        "steps": {
            "building_electricity_gwh": round(float(me.kwh) / 1e6, 1),
            "building_avg_mw": round(float(bldg_mw), 1),
            "building_gfa_ft2": int(me.gfa),
            "office_peer_count": int(len(offices)),
            "office_intensity_kwh_ft2_median": round(float(intensity.quantile(0.5)), 1),
            "office_baseline_mw": round(float(base(q.value)), 1),
            "dc_load_mw": round(float(bldg_mw - base(q.value)), 1),
            "pue": pue.value,
        },
        "source": f"NYC LL84 2023, BBL {dc.ll84_bbl}",
    }


def run(site: Site, a: Assumptions, hourly: pd.DataFrame, sc: Scenario, it_mw: float) -> pd.DataFrame:
    """Hourly recoverable heat (MW_th) and capture temperatures for a scenario."""
    hours = np.arange(len(hourly))
    amp = a.v("supply.it_diurnal_amplitude")
    local_hour = pd.to_datetime(hourly.local).dt.hour.to_numpy()
    it = it_mw * (1 + sc.it_growth) * (1 + amp * np.sin(2 * np.pi * (local_hour - 9) / 24))
    liquid = sc.cooling == "liquid"
    capture = a.v("supply.capture_fraction_liquid" if liquid else "supply.capture_fraction_air")
    t_in = a.v("supply.t_return_liquid_cooled" if liquid else "supply.t_return_air_cooled")
    return pd.DataFrame({
        "hour": hours,
        "it_load_mw": it,
        "q_src_mw": it * capture,                     # heat available to the heat-pump evaporator
        "q_total_heat_mw": it,                        # all IT heat must leave the building
        "t_src_in_c": np.full(len(hours), t_in),      # DC return water entering the HP evaporator
        "t_src_out_c": np.full(len(hours), t_in - a.v("supply.source_delta_t")),
    })
