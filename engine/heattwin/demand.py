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
    agg["propane_kbtu"] = 0.0
    agg["elecheat_kbtu"] = 0.0   # LL84 electricity is whole-building use, not heating; not counted as switchable heat
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


# ---------------------------------------------------------------- Site 2: synthetic demand
def fuel_mix_for_tracts(geoids: pd.Series, a: Assumptions) -> pd.DataFrame:
    """Household heating-fuel shares per tract: DOE LEAD (TEN-HFL cohorts) when cached, else labeled fallback."""
    from .data.cache import RAW
    p = RAW / "doe_lead" / "NY_AMI_census_tracts_2022.csv"
    fallback = pd.DataFrame({"GEOID": geoids.unique()}).assign(
        gas=a.v("rural.fuel_share_gas"), oil=a.v("rural.fuel_share_oil"), propane=a.v("rural.fuel_share_propane"),
        elecheat=a.v("rural.fuel_share_elec"), fuel_mix_source="FALLBACK estimate (rural.fuel_share_*)")
    if not p.exists():
        return fallback
    df = pd.read_csv(p, dtype={"FIP": str}, low_memory=False)
    col = next((c for c in df.columns if "HFL" in c.upper()), None)
    if col is None or "UNITS" not in df:
        return fallback
    df["FIP"] = df.FIP.str.zfill(11)
    df = df[df.FIP.isin(set(geoids))]
    fuel = df[col].astype(str).str.upper()
    key = np.select([fuel.str.contains("UTILITY GAS|NATURAL GAS"), fuel.str.contains("FUEL OIL|KEROSENE"),
                     fuel.str.contains("BOTTLED|LP|PROPANE"), fuel.str.contains("ELECTRIC")],
                    ["gas", "oil", "propane", "elecheat"], "other")
    piv = df.assign(fuel=key).pivot_table(index="FIP", columns="fuel", values="UNITS", aggfunc="sum").fillna(0)
    for f in ("gas", "oil", "propane", "elecheat"):
        if f not in piv:
            piv[f] = 0.0
    tot = piv[["gas", "oil", "propane", "elecheat"]].sum(axis=1).replace(0, np.nan)
    out = piv[["gas", "oil", "propane", "elecheat"]].div(tot, axis=0).reset_index().rename(columns={"FIP": "GEOID"})
    out["fuel_mix_source"] = "DOE LEAD 2022 tract heating-fuel mix"
    return pd.concat([out.dropna(), fallback[~fallback.GEOID.isin(out.dropna().GEOID)]], ignore_index=True)


def offtakers_synthetic(buildings: gpd.GeoDataFrame, a: Assumptions, site: Site) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Site 2: homes grouped into grid clusters + schools/civic individually + labeled hypothetical anchors.

    All demand is SYNTHETIC (RECS 2020 Northeast per-household intensities; school intensity; greenhouse intensity).
    """
    cfg = site.synthetic
    eff = a.v("synthetic_demand.rural_heating_system_eff")
    b = buildings[~buildings.is_dc].copy()
    utm = b.to_crs("EPSG:32618")
    b["x"], b["y"] = utm.centroid.x, utm.centroid.y
    mmbtu = lambda sh, dhw: (sh, dhw)
    sf = mmbtu(a.v("synthetic_demand.sf_space_heat_mmbtu"), a.v("synthetic_demand.sf_water_heat_mmbtu"))
    apt = mmbtu(a.v("synthetic_demand.apt_space_heat_mmbtu"), a.v("synthetic_demand.apt_water_heat_mmbtu"))
    res = b[b.use.str.startswith("residential")].copy()
    res["sh_site_mmbtu"] = res.units_res * np.where(res.is_apartment, apt[0], sf[0])
    res["dhw_site_mmbtu"] = res.units_res * np.where(res.is_apartment, apt[1], sf[1])
    res["cell"] = (res.x // cfg.cluster_m).astype(int).astype(str) + "_" + (res.y // cfg.cluster_m).astype(int).astype(str)

    rows = []
    for cell, grp in res.groupby("cell"):
        homes = float(grp.units_res.sum())
        rows.append({"name": f"{int(homes)} homes (cluster {cell})", "ll84_type": "Residential cluster (synthetic)",
                     "kind": "residential_cluster", "units_res": homes, "is_residential": True,
                     "sh_site_mmbtu": grp.sh_site_mmbtu.sum(), "dhw_site_mmbtu": grp.dhw_site_mmbtu.sum(),
                     "x": grp.x.mean(), "y": grp.y.mean(), "bins": grp.bin.tolist(), "svi": grp.svi.mean(),
                     "energy_burden_pct": grp.energy_burden_pct.mean(), "GEOID": grp.GEOID.mode().iat[0] if grp.GEOID.notna().any() else None,
                     "distribution_m": homes * cfg.service_m_per_home, "n_buildings": len(grp)})
    inst = b[b.use.isin(["school", "civic"])].copy()
    school_kbtu = a.v("synthetic_demand.school_heat_kbtu_ft2")
    for _, r in inst.iterrows():
        site_mmbtu = r.footprint_m2 * r.floors * 10.7639 * school_kbtu / 1000
        rows.append({"name": r["name"] or f"{r.use.title()} building", "ll84_type": f"{r.use.title()} (synthetic)",
                     "kind": r.use, "units_res": 0.0, "is_residential": False,
                     "sh_site_mmbtu": site_mmbtu * 0.9, "dhw_site_mmbtu": site_mmbtu * 0.1,
                     "x": r.x, "y": r.y, "bins": [r.bin], "svi": r.svi, "energy_burden_pct": r.energy_burden_pct,
                     "GEOID": r.GEOID, "distribution_m": 0.0, "n_buildings": 1})
    dc = gpd.GeoSeries(gpd.points_from_xy([site.data_center.lon], [site.data_center.lat]), crs="EPSG:4326").to_crs("EPSG:32618")[0]
    for anc in cfg.hypothetical_anchors:
        mwh = anc.area_m2 * a.v("synthetic_demand.greenhouse_heat_kwh_m2") / 1000
        site_mmbtu = mwh / MWH_PER_MMBTU_ / eff
        rows.append({"name": anc.name, "ll84_type": "HYPOTHETICAL anchor", "kind": "hypothetical", "units_res": 0.0,
                     "is_residential": True,   # 24/7 heated: residential space-heat shape is the closer proxy
                     "sh_site_mmbtu": site_mmbtu, "dhw_site_mmbtu": 0.0, "x": dc.x + anc.offset_m[0], "y": dc.y + anc.offset_m[1],
                     "bins": [], "svi": np.nan, "energy_burden_pct": np.nan, "GEOID": None, "distribution_m": 0.0,
                     "n_buildings": 0, "note": anc.note})
    off = pd.DataFrame(rows)
    ll = gpd.GeoSeries(gpd.points_from_xy(off.x, off.y), crs="EPSG:32618").to_crs("EPSG:4326")
    off["lon"], off["lat"] = ll.x.to_numpy(), ll.y.to_numpy()
    off["svi"] = off.svi.fillna(buildings.svi.median())
    off["GEOID"] = off.GEOID.fillna(buildings.GEOID.mode().iat[0])

    # fuel mix -> per-fuel site kBtu so the shared fuel valuation applies unchanged
    mix = fuel_mix_for_tracts(off.GEOID, a).set_index("GEOID")
    site_kbtu = (off.sh_site_mmbtu + off.dhw_site_mmbtu) * 1000
    for f in ("gas", "oil", "propane", "elecheat"):
        off[f"{f}_kbtu"] = site_kbtu * off.GEOID.map(mix[f]).fillna(a.v(f"rural.fuel_share_{'elec' if f == 'elecheat' else f}"))
    off["steam_kbtu"] = 0.0
    off["fuel_mix_source"] = off.GEOID.map(mix.fuel_mix_source).fillna("FALLBACK estimate (rural.fuel_share_*)")
    hyp = off.kind.eq("hypothetical")
    off.loc[hyp, ["gas_kbtu", "oil_kbtu", "elecheat_kbtu"]] = 0.0
    off.loc[hyp, "propane_kbtu"] = site_kbtu[hyp]      # a new greenhouse's counterfactual: a propane-fired boiler
    off.loc[hyp, "fuel_mix_source"] = "Counterfactual: propane boiler (hypothetical anchor)"

    off["heat_mwh"] = site_kbtu / 1000 * MWH_PER_MMBTU_ * eff
    off["dhw_mwh"] = off.dhw_site_mmbtu * MWH_PER_MMBTU_ * eff
    off["sh_mwh"] = off.heat_mwh - off.dhw_mwh
    off["primary_fuel"] = off[["gas_kbtu", "oil_kbtu", "propane_kbtu", "elecheat_kbtu"]].idxmax(axis=1).str.replace("_kbtu", "")
    off["is_nycha"] = False
    off["units_source"] = np.where(off.kind.eq("residential_cluster"), "Overture footprints (1 home per house)", "—")
    off["year_built"] = np.nan
    off["t_supply_design_c"] = a.v("demand.t_supply_design_pre1980")
    off["needs_steam_conversion"] = False
    off["address"] = None
    off["gfa_m2"] = np.nan
    off["synthetic"] = True
    off["distribution_capex_usd"] = off.distribution_m * a.v("network.service_line_cost_per_m") * a.v("rural.pipe_cost_multiplier")
    off["id"] = "s" + off.index.astype(str)

    small = (off.heat_mwh < a.v("demand.min_annual_heat_mwh")) & ~hyp
    screened = off[small].assign(screen_reason=f"Annual heat below {a.v('demand.min_annual_heat_mwh'):.0f} MWh (phase-1 threshold)")
    screened = screened[["id", "name", "ll84_type", "heat_mwh", "screen_reason", "lon", "lat"]]
    keep = off[~small].reset_index(drop=True)
    return gpd.GeoDataFrame(keep, geometry=gpd.points_from_xy(keep.lon, keep.lat), crs="EPSG:4326"), screened.reset_index(drop=True)


MWH_PER_MMBTU_ = 0.293071
