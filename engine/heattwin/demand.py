"""Building heat demand: measured annual fuel (LL84) -> useful heat -> hourly space heat + DHW.

Each building's hourly demand is a linear combination of three normalized shapes (residential space heat,
commercial space heat, DHW), so 8,760-hour profiles for hundreds of buildings cost one small matrix product.
"""
from __future__ import annotations

import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd

from .assumptions import Assumptions
from .data import sources as S
from .site import Site

KBTU_TO_MWH = 0.000293071
RES_TYPES = ("Multifamily", "Residence", "Senior", "Dormitory", "Hotel")
# Normalized DHW draw profile by local hour (multifamily; morning and evening peaks). ASHRAE Handbook (HVAC
# Applications, Service Water Heating) shape. It only shapes hours; the annual total comes from LL84.
DHW_HOURLY = np.array([0.6, 0.4, 0.3, 0.3, 0.4, 0.8, 1.6, 2.0, 1.7, 1.4, 1.2, 1.1,
                       1.0, 0.9, 0.9, 0.9, 1.0, 1.3, 1.6, 1.6, 1.4, 1.2, 1.0, 0.8])


def shapes(hourly: pd.DataFrame, a: Assumptions) -> dict[str, np.ndarray]:
    """Normalized (sum = 1) hourly shapes for the year."""
    t = hourly.t_out_c.to_numpy()
    local = pd.to_datetime(hourly.local)
    hod, dow = local.dt.hour.to_numpy(), local.dt.dayofweek.to_numpy()
    hdh = np.clip(a.v("demand.t_balance_point") - t, 0, None)
    occupied = (dow < 5) & (hod >= 6) & (hod < 19)
    com = hdh * np.where(occupied, 1.0, 0.6)         # night/weekend setback for commercial buildings
    dhw = DHW_HOURLY[hod]
    return {"sh_res": hdh / hdh.sum(), "sh_com": com / com.sum(), "dhw": dhw / dhw.sum()}


def required_supply_temp(t_out: np.ndarray, t_design_supply: float, a: Assumptions) -> np.ndarray:
    """Outdoor-reset curve: design supply at the design outdoor temp, falling to the floor at the balance point."""
    t_bal, t_des = a.v("demand.t_balance_point"), a.v("demand.t_design_outdoor")
    x = np.clip((t_bal - t_out) / (t_bal - t_des), 0, 1)
    t_min = a.v("demand.t_supply_min_reset")
    return t_min + (t_design_supply - t_min) * x


def nycha_apartments() -> dict[str, int]:
    """Development name -> apartments, from the NYCHA Development Data Book (authoritative; PLUTO undercounts)."""
    rows = json.loads(S.nycha_databook().read_text())
    out: dict[str, int] = {}
    for r in rows:
        n = int(float(str(r.get("total_number_of_apartments", "0")).replace(",", "") or 0))
        out[r["development"].strip().upper()] = out.get(r["development"].strip().upper(), 0) + n
    return out


def offtakers_from_ll84(buildings: gpd.GeoDataFrame, a: Assumptions, site: Site) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """One offtaker per LL84 property (campuses aggregate their footprints). Only measured buildings qualify.

    Returns (candidates, screened_out) where screened_out keeps every excluded property with its reason.
    """
    b = buildings[buildings.has_ll84].copy()
    b["w"] = b.volume_m3
    agg = b.groupby("ll84_property").agg(
        gas_kbtu=("gas_kbtu", "sum"), steam_kbtu=("steam_kbtu", "sum"), elec_kbtu=("elec_kbtu", "sum"),
        oil_kbtu=("oil2_kbtu", "sum"), oil4_kbtu=("oil4_kbtu", "sum"), oil56_kbtu=("oil56_kbtu", "sum"),
        gfa_m2=("gfa_m2", "sum"), units_res=("units_res", "sum"), is_nycha=("is_nycha", "max"),
        ll84_type=("ll84_type", "first"), year_built=("yearbuilt", "median"), address=("address", "first"),
        svi=("svi", "mean"), energy_burden_pct=("energy_burden_pct", "mean"), GEOID=("GEOID", "first"),
        height_m=("height_m", "max"), n_buildings=("bin", "count"), bins=("bin", list),
    )
    w = b.groupby("ll84_property").w.sum()
    agg["lon"] = (b.lon * b.w).groupby(b.ll84_property).sum() / w
    agg["lat"] = (b.lat * b.w).groupby(b.ll84_property).sum() / w
    agg["oil_kbtu"] = agg.oil_kbtu + agg.oil4_kbtu + agg.oil56_kbtu
    agg = agg.drop(columns=["oil4_kbtu", "oil56_kbtu"]).reset_index().rename(columns={"ll84_property": "name"})
    agg["id"] = "o" + agg.index.astype(str)

    is_res = agg.ll84_type.fillna("").str.contains("|".join(RES_TYPES))
    agg["is_residential"] = is_res
    frac = np.where(is_res, a.v("demand.fossil_to_heat_fraction_res"), a.v("demand.fossil_to_heat_fraction_com"))
    useful_kbtu = frac * (agg.gas_kbtu * a.v("demand.boiler_eff_gas") + agg.oil_kbtu * a.v("demand.boiler_eff_oil")) \
        + agg.steam_kbtu * a.v("demand.steam_to_heat_eff")
    agg["heat_mwh"] = useful_kbtu * KBTU_TO_MWH
    dhw_share = np.where(is_res, a.v("demand.dhw_share_res"), a.v("demand.dhw_share_com"))
    agg["dhw_mwh"] = agg.heat_mwh * dhw_share
    agg["sh_mwh"] = agg.heat_mwh - agg.dhw_mwh
    agg["primary_fuel"] = agg[["gas_kbtu", "steam_kbtu", "oil_kbtu"]].idxmax(axis=1).str.replace("_kbtu", "")
    agg.loc[agg[["gas_kbtu", "steam_kbtu", "oil_kbtu"]].sum(axis=1) == 0, "primary_fuel"] = "electric"
    agg["t_supply_design_c"] = np.where(agg.year_built.fillna(1950) < 1980,
                                        a.v("demand.t_supply_design_pre1980"), a.v("demand.t_supply_design_post1980"))
    agg["needs_steam_conversion"] = agg.steam_kbtu > 0.5 * (agg.gas_kbtu + agg.oil_kbtu + agg.steam_kbtu)

    # NYCHA: PLUTO undercounts apartments on campuses; use the Data Book (LL84 names like "ELLIOTT/CHELSEA ADDITION").
    book = nycha_apartments()
    def _nycha_units(row) -> float:
        if not row.is_nycha:
            return row.units_res
        parts = [p.strip().upper() for p in str(row["name"]).split("/")]
        n = sum(book.get(p, 0) for p in parts)
        return float(n) if n else row.units_res
    agg["units_source"] = np.where(agg.is_nycha, "NYCHA Development Data Book", "MapPLUTO (apportioned)")
    agg["units_res"] = agg.apply(_nycha_units, axis=1)

    # Screening: explicit, sourced exclusions + an intensity cap. Excluded rows are returned, never dropped silently.
    agg["fossil_kbtu_ft2"] = (agg.gas_kbtu + agg.oil_kbtu + agg.steam_kbtu) / (agg.gfa_m2 * 10.7639)
    agg["screen_reason"] = None
    for ex in site.screening.exclusions:
        hit = agg.name.str.contains(ex.pattern, regex=True, na=False) & agg.screen_reason.isna()
        agg.loc[hit, "screen_reason"] = ex.reason
    # On-site generation signature (e.g. PENN 1): buys far less grid electricity than peers while burning far more fuel.
    agg["elec_kbtu_ft2"] = agg.elec_kbtu / (agg.gfa_m2 * 10.7639)
    typ = agg.ll84_type.fillna("Other")
    big = typ.map(typ.value_counts()) >= 10
    med_e = agg.elec_kbtu_ft2.groupby(typ).transform("median").where(big, agg.elec_kbtu_ft2.median())
    med_f = agg.fossil_kbtu_ft2.groupby(typ).transform("median").where(big, agg.fossil_kbtu_ft2.median())
    cogen = (agg.elec_kbtu_ft2 < 0.3 * med_e) & (agg.fossil_kbtu_ft2 > 2 * med_f) & agg.screen_reason.isna()
    agg.loc[cogen, "screen_reason"] = ("On-site generation signature: grid electricity <30% of peer median while fossil "
                                       "fuel >2x peer median (gas is making power, not just heat)")
    cap = site.screening.max_fossil_intensity_kbtu_ft2
    hit = (agg.fossil_kbtu_ft2 > cap) & agg.screen_reason.isna()
    agg.loc[hit, "screen_reason"] = f"Fossil fuel intensity above {cap:.0f} kBtu/ft2 (likely on-site generation or data error)"
    small = (agg.heat_mwh < a.v("demand.min_annual_heat_mwh")) & agg.screen_reason.isna()
    agg.loc[small, "screen_reason"] = f"Annual heat below {a.v('demand.min_annual_heat_mwh'):.0f} MWh (phase-1 threshold)"

    screened = agg[agg.screen_reason.notna()][["id", "name", "ll84_type", "heat_mwh", "fossil_kbtu_ft2", "screen_reason", "lon", "lat"]]
    keep = agg[agg.screen_reason.isna()].drop(columns=["screen_reason"]).reset_index(drop=True)
    return gpd.GeoDataFrame(keep, geometry=gpd.points_from_xy(keep.lon, keep.lat), crs="EPSG:4326"), screened.reset_index(drop=True)


def hourly_matrix(off: pd.DataFrame, shp: dict[str, np.ndarray]) -> np.ndarray:
    """(n_offtakers x 8760) hourly heat demand in MW_th."""
    res = off.is_residential.to_numpy()[:, None]
    sh = off.sh_mwh.to_numpy()[:, None] * np.where(res, shp["sh_res"][None, :], shp["sh_com"][None, :])
    return sh + off.dhw_mwh.to_numpy()[:, None] * shp["dhw"][None, :]


def validate_against_nycha_steam(ranked: pd.DataFrame, M_by_id: dict[str, np.ndarray], hourly: pd.DataFrame,
                                 a: Assumptions, development: str = "FULTON") -> dict:
    """Modeled monthly heat vs metered Con Ed steam bills (NYCHA smdw-73pj), for a steam-heated campus."""
    row = ranked[ranked.name.str.upper() == development]
    if row.empty:
        return {}
    model = pd.Series(M_by_id[row.iloc[0].id], index=pd.to_datetime(hourly.local).dt.month).groupby(level=0).sum()
    bills = pd.DataFrame(json.loads(S.nycha_steam(2023).read_text()))
    bills = bills[bills.development_name.str.upper() == development]
    bills["month"] = bills.revenue_month.str[5:7].astype(int)
    metered_mmbtu = bills.groupby("month").mlbs.apply(lambda s: s.astype(float).sum()) * 1.194
    metered = metered_mmbtu * a.v("demand.steam_to_heat_eff") * 0.293071   # MWh useful heat
    usd = bills.groupby("month").usd.apply(lambda s: s.astype(float).sum())
    df = pd.DataFrame({"modeled_mwh": model, "metered_mwh": metered}).dropna()
    r = np.corrcoef(df.modeled_mwh, df.metered_mwh)[0, 1]
    return {
        "development": development, "months": df.index.tolist(),
        "modeled_mwh": df.modeled_mwh.round(0).tolist(), "metered_mwh": df.metered_mwh.round(0).tolist(),
        "r2": float(r ** 2), "annual_modeled_mwh": float(df.modeled_mwh.sum()), "annual_metered_mwh": float(df.metered_mwh.sum()),
        "steam_cost_usd": float(usd.sum()), "steam_price_usd_per_mmbtu": float(usd.sum() / metered_mmbtu.sum()),
        "source": "NYC Open Data smdw-73pj (NYCHA steam consumption and cost), 2023 bills",
    }
