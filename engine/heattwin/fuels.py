"""Heating fuels a building can switch away from. Prices come from the site's config; physics from assumptions."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .assumptions import Assumptions
from .site import Site

MWH_PER_MMBTU = 0.293071
FUELS = ("gas", "oil", "steam", "propane", "elecheat")   # offtaker columns are f"{fuel}_kbtu"


def efficiency(a: Assumptions, fuel: str) -> float:
    return {
        "gas": a.v("demand.boiler_eff_gas"), "oil": a.v("demand.boiler_eff_oil"),
        "steam": a.v("demand.steam_to_heat_eff"), "propane": a.v("demand.boiler_eff_gas"), "elecheat": 1.0,
    }[fuel]


def price_usd_per_mmbtu(a: Assumptions, site: Site, fuel: str) -> float:
    key = site.prices[fuel]
    v = a.v(key)
    return v * MWH_PER_MMBTU if a[key].unit.startswith("USD/MWh") else v   # electricity is quoted per MWh


def physical_t_per_mmbtu(a: Assumptions, fuel: str, grid_t_per_mwh: float) -> float:
    return {
        "gas": a.v("emissions.ef_natural_gas_physical") / 1000, "oil": a.v("emissions.ef_oil2_physical") / 1000,
        "steam": a.v("emissions.ef_steam_physical") / 1000, "propane": a.v("emissions.ef_propane_physical") / 1000,
        "elecheat": grid_t_per_mwh * MWH_PER_MMBTU,
    }[fuel]


def ll97_t_per_mmbtu(a: Assumptions, fuel: str) -> float:
    return {
        "gas": a.v("policy.ll97_ef_natural_gas") * 1000, "oil": a.v("policy.ll97_ef_fuel_oil_2") * 1000,
        "steam": a.v("policy.ll97_ef_district_steam") * 1000, "propane": a.v("policy.ll97_ef_natural_gas") * 1000,
        "elecheat": a.v("policy.ll97_ef_electricity") * 1000 * MWH_PER_MMBTU,
    }[fuel]


def shares(df: pd.DataFrame) -> dict[str, pd.Series]:
    cols = {f: df.get(f"{f}_kbtu", pd.Series(0.0, index=df.index)).fillna(0) for f in FUELS}
    total = sum(cols.values()).replace(0, np.nan)
    return {f: (c / total).fillna(0) for f, c in cols.items()}


def per_mwh_heat(df: pd.DataFrame, fn) -> pd.Series:
    """Blend a per-MMBtu-of-fuel quantity fn(fuel) into a per-MWh-of-useful-heat value using each row's fuel mix."""
    a_shares = shares(df)
    return sum(a_shares[f] * fn(f) for f in FUELS)
