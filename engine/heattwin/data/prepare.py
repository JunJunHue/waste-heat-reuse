"""Turn cached raw files into clean, joined per-site tables in data/processed/<site>/.

Outputs (Site 1, adapter "nyc"):
  buildings.parquet   one row per footprint: geometry, height, PLUTO attributes, LL84 fuel use
                      (apportioned by building volume), tract GEOID, SVI, LEAD energy burden, NYCHA flag
  streets.parquet     street centerline segments (routing graph source)
  context.parquet     water + parks polygons (map context only)
  tracts.parquet      tract polygons with SVI (ACS-derived) and DOE LEAD attributes
  hourly.parquet      8760 rows (UTC): weather, grid carbon intensity, price (real or labeled proxy)
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from ..assumptions import Assumptions
from ..site import Site
from . import sources as S
from .cache import RAW, FetchError

UTM = "EPSG:32618"  # metres, valid for NYC and the Finger Lakes
NA = ["Not Available", "Insufficient access", ""]
LL84_FUELS = {
    "natural_gas_use_kbtu": "gas_kbtu",
    "district_steam_use_kbtu": "steam_kbtu",
    "fuel_oil_2_use_kbtu": "oil2_kbtu",
    "fuel_oil_4_use_kbtu": "oil4_kbtu",
    "fuel_oil_5_6_use_kbtu": "oil56_kbtu",
    "electricity_use_grid_purchase": "elec_kbtu",
}


# ---------------------------------------------------------------- helpers
def _norm_bbls(raw: str) -> list[str]:
    """LL84 BBLs come as '1007230015', '1-01870-0052', or 'a;b;c' campus lists."""
    out = []
    for part in str(raw).replace(",", ";").split(";"):
        p = part.strip().replace("-", "")
        if len(p) == 10 and p.isdigit():
            out.append(p)
    return out


def _bbl_str(x) -> str | None:
    try:
        return str(int(float(x)))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- equity layers (both sites)
def build_tracts(site: Site) -> gpd.GeoDataFrame:
    w, s, e, n = site.study_area.bbox
    tr = gpd.read_file(f"zip://{S.census_tracts_ny()}")
    tr = tr[tr.COUNTYFP == site.county_fips].to_crs("EPSG:4326")
    tr = tr[tr.intersects(gpd.GeoSeries.from_xy([w, e], [s, n]).union_all().envelope)][["GEOID", "geometry"]]

    svi = pd.read_csv(S.cdc_svi_ny(), dtype={"FIPS": str})
    # SVI carries the ACS 2018-22 estimates we need (households, poverty, housing-cost burden); no Census API key required.
    svi = svi[["FIPS", "RPL_THEMES", "RPL_THEME1", "E_TOTPOP", "E_HH", "E_POV150", "EP_POV150", "EP_HBURD"]].rename(columns={
        "FIPS": "GEOID", "RPL_THEMES": "svi", "RPL_THEME1": "svi_socioeconomic", "E_TOTPOP": "pop",
        "E_HH": "households", "E_POV150": "pop_below_150pct_poverty", "EP_POV150": "pct_below_150pct_poverty",
        "EP_HBURD": "pct_housing_cost_burdened"})
    svi.loc[svi.svi < 0, "svi"] = np.nan  # CDC uses -999 for missing
    for c in ("svi_socioeconomic", "pct_below_150pct_poverty", "pct_housing_cost_burdened"):
        svi.loc[svi[c] < 0, c] = np.nan

    tr = tr.merge(svi, on="GEOID", how="left")
    lead = load_lead_tracts()
    if lead is not None:
        tr = tr.merge(lead, on="GEOID", how="left")
    else:
        tr["energy_burden_pct"] = np.nan
        tr["avg_hh_income"] = np.nan
    return tr


def load_lead_tracts() -> pd.DataFrame | None:
    """DOE LEAD: household-weighted average energy burden (% of income) per tract. None if not cached yet."""
    p = RAW / "doe_lead" / "NY_AMI_census_tracts_2022.csv"
    if not p.exists():  # large download is owned by `make data`; prepare never triggers it
        return None
    df = pd.read_csv(p, dtype={"FIP": str}, low_memory=False)
    geo = "FIP" if "FIP" in df else next(c for c in df.columns if c.upper() in ("FIP", "FIPS", "GEOID"))
    units, inc = df.get("UNITS"), df.get("HINCP*UNITS")
    cost_cols = [c for c in ("ELEP*UNITS", "GASP*UNITS", "FULP*UNITS") if c in df]
    if units is None or inc is None or not cost_cols:
        return None
    df["_cost"] = df[cost_cols].sum(axis=1)
    g = df.groupby(geo)[["_cost", "HINCP*UNITS", "UNITS"]].sum()
    out = pd.DataFrame({"energy_burden_pct": 100 * g["_cost"] / g["HINCP*UNITS"].replace(0, np.nan),
                        "avg_hh_income": g["HINCP*UNITS"] / g["UNITS"].replace(0, np.nan)})
    out.index = out.index.astype(str).str.zfill(11)
    return out.rename_axis("GEOID").reset_index()


# ---------------------------------------------------------------- Site 1: NYC buildings
def build_nyc_buildings(site: Site, tracts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    fp = gpd.read_file(S.nyc_footprints(site.id, site.study_area.bbox))
    fp = fp[(fp.last_status_type == "Constructed") & (fp.feature_code == "2100")].copy()
    fp["height_m"] = pd.to_numeric(fp.height_roof, errors="coerce").fillna(0) * 0.3048
    fp = fp[fp.height_m > 2].copy()
    utm = fp.to_crs(UTM)
    fp["footprint_m2"] = utm.area
    fp = fp[fp.footprint_m2 > 20].copy()
    fp["volume_m3"] = fp.footprint_m2 * fp.height_m
    fp["bbl"] = fp.mappluto_bbl.map(_bbl_str).fillna(fp.base_bbl.map(_bbl_str))
    fp = fp[["bin", "bbl", "height_m", "footprint_m2", "volume_m3", "construction_year", "geometry"]]

    # --- PLUTO lot attributes, apportioned to footprints by volume share within the lot
    pl = pd.DataFrame(json.loads(S.nyc_pluto(site.id, site.study_area.bbox).read_text()))
    pl["bbl"] = pl.bbl.map(_bbl_str)
    for c in ("bldgarea", "resarea", "comarea", "officearea", "retailarea", "unitsres", "unitstotal", "numfloors", "yearbuilt"):
        pl[c] = pd.to_numeric(pl[c], errors="coerce")
    pl = pl.drop_duplicates("bbl")
    fp = fp.merge(pl[["bbl", "address", "ownername", "bldgclass", "landuse", "bldgarea", "resarea", "comarea",
                      "unitsres", "unitstotal", "numfloors", "yearbuilt"]], on="bbl", how="left")
    share = fp.volume_m3 / fp.groupby("bbl").volume_m3.transform("sum")
    fp["lot_share"] = share.fillna(1.0)
    fp["gfa_m2"] = (fp.bldgarea * 0.092903 * fp.lot_share).fillna(fp.footprint_m2 * fp.height_m / 3.5)
    fp["units_res"] = (fp.unitsres * fp.lot_share).fillna(0)
    fp["is_nycha"] = fp.ownername.fillna("").str.upper().str.contains("HOUSING AUTHORITY")

    # --- LL84 fuel use: one property may span many BBLs. Assign each BBL to at most one property
    #     (largest GFA first) so umbrella campus rows and their children are never double counted.
    ll = pd.DataFrame(json.loads(S.nyc_ll84(2023).read_text())).replace(NA, np.nan)
    for src in LL84_FUELS:
        ll[src] = pd.to_numeric(ll[src], errors="coerce")
    ll["elec_kbtu_conv"] = ll["electricity_use_grid_purchase"] * 3.412  # kWh -> kBtu
    ll["gfa_ft2"] = pd.to_numeric(ll.property_gfa_self_reported, errors="coerce")
    fuel_cols = [c for c in LL84_FUELS if c != "electricity_use_grid_purchase"]
    ll = ll[ll[fuel_cols + ["electricity_use_grid_purchase"]].notna().any(axis=1)]
    ll["bbls"] = ll.nyc_borough_block_and_lot.map(_norm_bbls)
    site_bbls = set(fp.bbl.dropna())
    ll = ll[ll.bbls.map(lambda b: bool(set(b) & site_bbls))].sort_values("gfa_ft2", ascending=False)
    claimed: dict[str, int] = {}
    keep = []
    for idx, row in ll.iterrows():
        if any(b in claimed for b in row.bbls):
            continue
        for b in row.bbls:
            claimed[b] = idx
        keep.append(idx)
    ll = ll.loc[keep]
    ll["ll84_id"] = ll.index.astype(str)

    bbl_to_prop = pd.DataFrame([(b, i) for b, i in claimed.items() if i in set(keep)], columns=["bbl", "ll84_idx"])
    fp = fp.merge(bbl_to_prop, on="bbl", how="left")
    prop_vol = fp.groupby("ll84_idx").volume_m3.transform("sum")
    fp["ll84_share"] = np.where(fp.ll84_idx.notna(), fp.volume_m3 / prop_vol, 0.0)
    for src, dst in LL84_FUELS.items():
        col = "elec_kbtu_conv" if src == "electricity_use_grid_purchase" else src
        fp[dst] = fp.ll84_idx.map(ll[col]).fillna(0) * fp.ll84_share
    fp["ll84_property"] = fp.ll84_idx.map(ll.property_name)
    fp["ll84_type"] = fp.ll84_idx.map(ll.primary_property_type)
    fp["has_ll84"] = fp.ll84_idx.notna()
    fp = fp.drop(columns=["ll84_idx"])

    fp = gpd.GeoDataFrame(fp, geometry="geometry", crs="EPSG:4326")
    return _attach_tracts(fp, tracts)


def _attach_tracts(b: gpd.GeoDataFrame, tracts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    cent = gpd.GeoDataFrame(b[[]], geometry=b.to_crs(UTM).centroid.to_crs("EPSG:4326"), crs="EPSG:4326")
    j = gpd.sjoin(cent, tracts[["GEOID", "svi", "energy_burden_pct", "avg_hh_income", "pct_below_150pct_poverty", "geometry"]],
                  how="left", predicate="within")
    j = j[~j.index.duplicated()]
    b["GEOID"] = j.GEOID
    b["svi"] = j.svi
    b["energy_burden_pct"] = j.energy_burden_pct
    b["tract_avg_income"] = j.avg_hh_income
    b["tract_pct_poverty150"] = j.pct_below_150pct_poverty
    b["lon"] = cent.geometry.x
    b["lat"] = cent.geometry.y
    return b


def build_nyc_context(site: Site) -> gpd.GeoDataFrame:
    w, s, e, n = site.study_area.bbox
    box = gpd.GeoSeries.from_xy([w, e], [s, n], crs="EPSG:4326").union_all().envelope
    water = gpd.read_file(f"zip://{S.tiger_areawater(site.county_fips)}").to_crs("EPSG:4326")
    water = gpd.clip(water, box).assign(kind="water", name=lambda d: d.FULLNAME)[["kind", "name", "geometry"]]
    parks = gpd.read_file(S.nyc_parks(site.id, site.study_area.bbox))
    parks = gpd.clip(parks, box).assign(kind="park", name=lambda d: d.name311)[["kind", "name", "geometry"]]
    return gpd.GeoDataFrame(pd.concat([water, parks], ignore_index=True), crs="EPSG:4326")


def build_nyc_streets(site: Site) -> gpd.GeoDataFrame:
    st = gpd.read_file(S.nyc_cscl(site.id, site.study_area.bbox))
    # rw_type 1 = street; excludes highways (2), bridges/tunnels, ramps, paper streets, etc.
    st = st[st.rw_type == "1"].explode(index_parts=False).reset_index(drop=True)
    st["length_m"] = st.to_crs(UTM).length
    return st[["physicalid", "full_street_name", "streetwidth", "length_m", "geometry"]]


# ---------------------------------------------------------------- Site 2: synthetic upstate buildings
RES_CLASSES = {"house", "detached", "residential", "semidetached_house", "terrace", "bungalow", "farmhouse", "cabin",
               "static_caravan", "apartments", "dormitory", "houseboat"}
SCHOOL_CLASSES = {"school", "kindergarten", "college", "university"}
CIVIC_CLASSES = {"civic", "government", "public", "fire_station", "community_centre", "library", "townhall",
                 "church", "chapel", "religious", "hospital", "clinic"}
UNHEATED = {"barn", "shed", "garage", "garages", "greenhouse", "farm_auxiliary", "silo", "carport", "roof",
            "storage_tank", "hut", "stable", "cowshed", "parking", "industrial", "warehouse", "transportation"}


def build_upstate_buildings(site: Site, tracts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Overture footprints -> typed buildings with a heat-use class. Every Site 2 building is labeled synthetic."""
    import shapely

    raw = pd.read_parquet(S.overture(site.id, "buildings", "building", site.study_area.bbox))
    g = gpd.GeoDataFrame(raw.drop(columns=["geometry_wkb"]), geometry=shapely.from_wkb(raw.geometry_wkb), crs="EPSG:4326")
    g = g[g.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    g["footprint_m2"] = g.to_crs(UTM).area
    cls = g.get("class", pd.Series(None, index=g.index)).astype("string").str.lower()
    sub = g.get("subtype", pd.Series(None, index=g.index)).astype("string").str.lower()
    floors = pd.to_numeric(g.get("num_floors"), errors="coerce")
    height = pd.to_numeric(g.get("height"), errors="coerce")
    g["floors"] = floors.fillna((height / 3.2).round()).fillna(1).clip(1, 10)
    g["height_m"] = height.fillna(g.floors * 3.2 + 1.5)
    cfg = site.synthetic

    use = pd.Series("unheated", index=g.index)
    use[cls.isin(RES_CLASSES) | sub.eq("residential")] = "residential"
    use[cls.isin(SCHOOL_CLASSES) | sub.eq("education")] = "school"
    use[cls.isin(CIVIC_CLASSES) | sub.isin(["civic", "religious", "medical"])] = "civic"
    untagged = cls.isna() & sub.isna()
    plausible_home = untagged & g.footprint_m2.between(cfg.min_home_footprint_m2, cfg.max_unknown_footprint_m2)
    use[plausible_home] = "residential_assumed"
    use[cls.isin(UNHEATED) | sub.isin(["agricultural", "industrial", "transportation"])] = "unheated"
    g["use"] = use
    g["is_apartment"] = cls.eq("apartments")
    g["units_res"] = np.where(g.use.str.startswith("residential"),
                              np.where(g.is_apartment, np.maximum(1, (g.footprint_m2 * g.floors / 90).round()), 1), 0)
    g["name"] = g.get("names", pd.Series(None, index=g.index)).map(lambda n: n.get("primary") if isinstance(n, dict) else None)
    g["bin"] = "ov" + g.id.astype(str).str[-12:]
    g["is_nycha"] = False
    g["is_dc"] = g.contains(gpd.points_from_xy([site.data_center.lon], [site.data_center.lat])[0])
    g = g[["bin", "name", "use", "is_apartment", "units_res", "footprint_m2", "floors", "height_m", "is_nycha", "is_dc", "geometry"]]
    return _attach_tracts(gpd.GeoDataFrame(g, crs="EPSG:4326"), tracts)


def build_tiger_streets(site: Site) -> gpd.GeoDataFrame:
    w, s, e, n = site.study_area.bbox
    box = gpd.GeoSeries.from_xy([w, e], [s, n], crs="EPSG:4326").union_all().envelope
    rd = gpd.read_file(f"zip://{S.tiger_roads(site.county_fips)}").to_crs("EPSG:4326")
    rd = rd[rd.MTFCC.isin(["S1100", "S1200", "S1400"])]          # primary, secondary, local public roads
    rd = gpd.clip(rd, box).explode(index_parts=False).reset_index(drop=True)
    rd = rd[rd.geometry.geom_type == "LineString"]
    rd["length_m"] = rd.to_crs(UTM).length
    return rd.rename(columns={"FULLNAME": "full_street_name"})[["full_street_name", "length_m", "geometry"]]


def build_water_context(site: Site) -> gpd.GeoDataFrame:
    w, s, e, n = site.study_area.bbox
    box = gpd.GeoSeries.from_xy([w, e], [s, n], crs="EPSG:4326").union_all().envelope
    water = gpd.read_file(f"zip://{S.tiger_areawater(site.county_fips)}").to_crs("EPSG:4326")
    return gpd.clip(water, box).assign(kind="water", name=lambda d: d.FULLNAME)[["kind", "name", "geometry"]]


# ---------------------------------------------------------------- hourly (both sites)
def build_hourly(site: Site, a: Assumptions) -> pd.DataFrame:
    wx = json.loads(S.open_meteo(site.id, site.weather.lat, site.weather.lon, site.weather.year).read_text())["hourly"]
    h = pd.DataFrame(wx).rename(columns={"time": "utc", "temperature_2m": "t_out_c", "relative_humidity_2m": "rh_pct",
                                         "dew_point_2m": "dewpoint_c", "wind_speed_10m": "wind_kmh",
                                         "shortwave_radiation": "ghi_wm2"})
    h["utc"] = pd.to_datetime(h.utc, utc=True)
    h = h.iloc[:8760].reset_index(drop=True)
    h["local"] = h.utc.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d %H:%M")
    h["t_out_c"] = h.t_out_c.interpolate().bfill().ffill()

    # --- grid carbon from EIA-930 (UTC time at END of hour -> hour-beginning)
    eia = pd.read_parquet(S.eia930_nyis(site.weather.year))
    eia["utc"] = pd.to_datetime(eia["UTC Time at End of Hour"], format="%m/%d/%Y %I:%M:%S %p", utc=True) - pd.Timedelta(hours=1)
    fuel = lambda f: pd.to_numeric(eia[f"Net Generation (MW) from {f} (Adjusted)"], errors="coerce").fillna(0).clip(lower=0)
    gas, oil, coal = fuel("Natural Gas"), fuel("All Petroleum Products"), fuel("Coal")
    other = sum(fuel(f) for f in ("Nuclear", "Hydropower and Pumped Storage", "Solar", "Wind", "Other Fuel Sources"))
    total = gas + oil + coal + other
    eia["grid_tco2_per_mwh"] = (gas * a.v("grid.ef_natural_gas_gen") + oil * a.v("grid.ef_petroleum_gen")
                                + coal * a.v("grid.ef_coal_gen") + other * a.v("grid.ef_other_gen")) / total
    eia["grid_load_mw"] = pd.to_numeric(eia["Demand (MW) (Adjusted)"], errors="coerce")
    h = h.merge(eia[["utc", "grid_tco2_per_mwh", "grid_load_mw"]], on="utc", how="left")
    h[["grid_tco2_per_mwh", "grid_load_mw"]] = h[["grid_tco2_per_mwh", "grid_load_mw"]].interpolate().bfill().ffill()

    # --- price: real NYISO DAM LBMP if reachable, else a labeled proxy matched to the published zonal average
    h["lbmp_usd_mwh"], h.attrs["price_source"] = _price(site, a, h)
    return h


def _price(site: Site, a: Assumptions, h: pd.DataFrame) -> tuple[pd.Series, str]:
    try:
        df = pd.read_parquet(S.nyiso_dam_lbmp(site.weather.year))
        df = df[df["Name"] == site.grid.lbmp_zone]
        ts = pd.to_datetime(df["Time Stamp"]).dt.tz_localize("America/New_York", ambiguous="infer", nonexistent="shift_forward")
        p = pd.Series(df["LBMP ($/MWHr)"].values, index=ts.dt.tz_convert("UTC")).groupby(level=0).mean()
        return h.utc.map(p).interpolate().bfill().ffill(), "NYISO DAM zonal LBMP (real)"
    except (FetchError, KeyError, zipfile.BadZipFile):
        beta = a.v("grid.lbmp_proxy_load_exponent")
        shape = (h.grid_load_mw / h.grid_load_mw.mean()) ** beta
        target = a.v(site.grid.lbmp_avg_key)
        scale = target * h.grid_load_mw.sum() / (shape * h.grid_load_mw).sum()  # load-weighted mean == target
        return shape * scale, f"PROXY: EIA-930 load shape^{beta} scaled to published 2023 avg ({site.grid.lbmp_avg_key})"


# ---------------------------------------------------------------- entry point
def prepare(site_id: str) -> Path:
    site = Site.load(site_id)
    a = Assumptions.load()
    out = site.processed_dir
    out.mkdir(parents=True, exist_ok=True)

    tracts = build_tracts(site)
    tracts.to_parquet(out / "tracts.parquet")
    hourly = build_hourly(site, a)
    hourly.to_parquet(out / "hourly.parquet")
    (out / "hourly_meta.json").write_text(json.dumps({"price_source": hourly.attrs["price_source"]}, indent=2))

    if site.adapter == "nyc":
        build_nyc_buildings(site, tracts).to_parquet(out / "buildings.parquet")
        build_nyc_streets(site).to_parquet(out / "streets.parquet")
        build_nyc_context(site).to_parquet(out / "context.parquet")
    elif site.adapter == "synthetic_upstate":
        build_upstate_buildings(site, tracts).to_parquet(out / "buildings.parquet")
        build_tiger_streets(site).to_parquet(out / "streets.parquet")
        build_water_context(site).to_parquet(out / "context.parquet")
    else:
        raise NotImplementedError(f"unknown adapter {site.adapter!r}")
    return out
