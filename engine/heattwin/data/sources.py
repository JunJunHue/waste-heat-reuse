"""One function per open-data source. Each returns local cached path(s) and never invents data.

If a source is unreachable the function raises FetchError, and the caller (fetch_site) decides whether a
labeled proxy is acceptable. Proxies are recorded in the manifest and surfaced in the UI.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

from .cache import RAW, FetchError, fetch, record_derived

SOCRATA = "https://data.cityofnewyork.us/resource"


# ---------------------------------------------------------------- NYC (Site 1)
def nyc_footprints(site_id: str, bbox: list[float]) -> Path:
    """NYC Building Footprints (5zhs-2jue): polygons with height_roof (ft) and BIN/BBL."""
    w, s, e, n = bbox
    return fetch("nyc_footprints", f"{site_id}.geojson", f"{SOCRATA}/5zhs-2jue.geojson", {
        "$where": f"within_box(the_geom, {n}, {w}, {s}, {e})",
        "$limit": 50000,
    })


def nyc_pluto(site_id: str, bbox: list[float]) -> Path:
    """MapPLUTO tax lots (64uk-42ks): residential units, owner (NYCHA), building class, floor area."""
    w, s, e, n = bbox
    cols = ("bbl,address,ownername,bldgclass,landuse,bldgarea,resarea,comarea,officearea,retailarea,"
            "numbldgs,numfloors,unitsres,unitstotal,yearbuilt,yearalter1,yearalter2,latitude,longitude,"
            "bct2020,zipcode")
    return fetch("nyc_pluto", f"{site_id}.json", f"{SOCRATA}/64uk-42ks.json", {
        "$select": cols,
        "$where": f"latitude between {s} and {n} and longitude between {w} and {e}",
        "$limit": 50000,
    })


def nyc_ll84(year: int = 2023) -> Path:
    """LL84 energy benchmarking (5zyy-y8am), Manhattan only, selected columns. Fuel use is in kBtu."""
    cols = ("report_year,property_name,nyc_borough_block_and_lot,nyc_building_identification,address_1,"
            "postal_code,primary_property_type,largest_property_use_type,year_built,number_of_buildings,"
            "property_gfa_self_reported,site_eui_kbtu_ft,natural_gas_use_kbtu,district_steam_use_kbtu,"
            "fuel_oil_2_use_kbtu,fuel_oil_4_use_kbtu,fuel_oil_5_6_use_kbtu,electricity_use_grid_purchase,"
            "total_location_based_ghg,latitude,longitude")
    return fetch("nyc_ll84", f"ll84_{year}_manhattan.json", f"{SOCRATA}/5zyy-y8am.json", {
        "$select": cols,
        "$where": f"report_year='{year}' and starts_with(nyc_borough_block_and_lot, '1')",
        "$limit": 50000,
    })


def nycha_databook() -> Path:
    """NYCHA Development Data Book (evjd-dqpz): authoritative apartment and resident counts (PLUTO undercounts NYCHA)."""
    return fetch("nycha", "development_data_book.json", f"{SOCRATA}/evjd-dqpz.json", {
        "$select": "development,tds_,total_number_of_apartments,number_of_current_apartments,total_population,borough",
        "$where": "borough='MANHATTAN'", "$limit": 5000})


def nycha_steam(year: int = 2023) -> Path:
    """NYCHA steam consumption and cost (smdw-73pj): metered monthly Con Ed steam bills per development."""
    return fetch("nycha", f"steam_{year}_manhattan.json", f"{SOCRATA}/smdw-73pj.json", {
        "$select": "development_name,revenue_month,rate_class,sum(consumption_mlbs) as mlbs,sum(current_charges) as usd",
        "$where": f"borough='MANHATTAN' and starts_with(revenue_month, '{year}')",
        "$group": "development_name,revenue_month,rate_class", "$limit": 50000})


# ---------------------------------------------------------------- Streets & context (no Overpass)
# OSM/Overpass was unreachable from our build environment (connections refused / hung), so street
# geometry comes from official sources that serve plain HTTPS downloads. See docs/DECISIONS.md (D5).
def nyc_cscl(site_id: str, bbox: list[float]) -> Path:
    """NYC Street Centerline (CSCL, inkn-q76z): authoritative street segments; pipes follow public ROW."""
    w, s, e, n = bbox
    return fetch("nyc_cscl", f"{site_id}.geojson", f"{SOCRATA}/inkn-q76z.geojson", {
        "$select": "the_geom,physicalid,full_street_name,rw_type,status,streetwidth,segmentlength,from_level_code,to_level_code",
        "$where": f"within_box(the_geom, {n}, {w}, {s}, {e})",
        "$limit": 50000,
    })


def nyc_parks(site_id: str, bbox: list[float]) -> Path:
    """NYC Parks properties (enfh-gkve) for map context."""
    w, s, e, n = bbox
    return fetch("nyc_parks", f"{site_id}.geojson", f"{SOCRATA}/enfh-gkve.geojson", {
        "$select": "multipolygon,name311,typecategory",
        "$where": f"intersects(multipolygon, 'POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))')",
        "$limit": 5000,
    })


def tiger_roads(county_fips: str) -> Path:
    """Census TIGER/Line 2022 all-roads for a NY county (used for Site 2 routing)."""
    name = f"tl_2022_36{county_fips}_roads.zip"
    return fetch("census_tiger", name, f"https://www2.census.gov/geo/tiger/TIGER2022/ROADS/{name}", timeout=600)


def tiger_areawater(county_fips: str) -> Path:
    """Census TIGER/Line 2022 area hydrography (Hudson River, Cayuga Lake) for map context."""
    name = f"tl_2022_36{county_fips}_areawater.zip"
    return fetch("census_tiger", name, f"https://www2.census.gov/geo/tiger/TIGER2022/AREAWATER/{name}", timeout=600)


OVERTURE_RELEASE = "2026-09-23.0"


def overture(site_id: str, theme: str, typ: str, bbox: list[float]) -> Path:
    """Overture Maps features in a bbox (DuckDB reads only the row groups that intersect the bbox from S3)."""
    import duckdb

    dest = RAW / "overture" / f"{site_id}_{typ}.parquet"
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    w, s, e, n = bbox
    url = f"s3://overturemaps-us-west-2/release/{OVERTURE_RELEASE}/theme={theme}/type={typ}/*"
    tmp = dest.with_suffix(".parquet.part")
    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
    con.sql(f"""COPY (SELECT * EXCLUDE (geometry), ST_AsWKB(geometry) AS geometry_wkb
        FROM read_parquet('{url}', hive_partitioning=1)
        WHERE bbox.xmin >= {w} AND bbox.xmax <= {e} AND bbox.ymin >= {s} AND bbox.ymax <= {n})
        TO '{tmp}' (FORMAT PARQUET)""")
    tmp.rename(dest)  # atomic: a crashed run never leaves a partial file that looks cached
    record_derived("overture", dest, f"Overture {OVERTURE_RELEASE} {theme}/{typ} clipped to bbox {bbox}", url=url)
    return dest


# ---------------------------------------------------------------- Equity (both sites)
def cdc_svi_ny() -> Path:
    """CDC/ATSDR Social Vulnerability Index 2022, New York census tracts."""
    return fetch("cdc_svi", "svi_2022_ny_tract.csv", "https://svi.cdc.gov/Documents/Data/2022/csv/states/NewYork.csv")


def census_tracts_ny() -> Path:
    """Census cartographic boundary tracts (2022, 1:500k), New York."""
    return fetch("census_tiger", "cb_2022_36_tract_500k.zip",
                 "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_36_tract_500k.zip", timeout=300)


def doe_lead_ny_tract() -> Path:
    """DOE LEAD Tool 2022 (Area Median Income cohorts, census tract) for New York.

    The state zip is ~550 MB; we stream it once, keep only the tract-level AMI CSV, and drop the zip.
    """
    dest = RAW / "doe_lead" / "NY_AMI_census_tracts_2022.csv"
    if dest.exists():
        return dest
    url = "https://data.openei.org/files/6219/NY-2022-LEAD-data.zip"
    z = fetch("doe_lead", "NY-2022-LEAD-data.zip", url, timeout=1800)
    with zipfile.ZipFile(z) as zf:
        names = [n for n in zf.namelist() if "AMI" in n and "Census Tracts" in n.replace("_", " ") and n.endswith(".csv")]
        if not names:
            names = [n for n in zf.namelist() if "AMI" in n and "tract" in n.lower() and n.endswith(".csv")]
        if not names:
            raise FetchError(f"doe_lead: no tract AMI CSV in archive; members: {zf.namelist()[:20]}")
        dest.write_bytes(zf.read(names[0]))
    record_derived("doe_lead", dest, f"extracted '{names[0]}' from state archive", url=url)
    z.unlink()
    return dest


# ---------------------------------------------------------------- Weather, grid (both sites)
def open_meteo(site_id: str, lat: float, lon: float, year: int) -> Path:
    """Open-Meteo historical reanalysis (ERA5-based), hourly, UTC."""
    return fetch("open_meteo", f"{site_id}_{year}.json", "https://archive-api.open-meteo.com/v1/archive", {
        "latitude": lat, "longitude": lon,
        "start_date": f"{year}-01-01", "end_date": f"{year}-12-31",
        "hourly": "temperature_2m,relative_humidity_2m,dew_point_2m,wind_speed_10m,shortwave_radiation",
        "timezone": "GMT",
    })


def eia930_nyis(year: int) -> Path:
    """EIA-930 hourly net generation by fuel for NYISO (NYIS) -> used for hourly grid carbon intensity."""
    dest = RAW / "eia930" / f"nyis_{year}.parquet"
    if dest.exists():
        return dest
    frames = []
    for half in ("Jan_Jun", "Jul_Dec"):
        url = f"https://www.eia.gov/electricity/gridmonitor/sixMonthFiles/EIA930_BALANCE_{year}_{half}.csv"
        p = fetch("eia930", f"EIA930_BALANCE_{year}_{half}.csv", url, timeout=1800)
        df = pd.read_csv(p, low_memory=False, thousands=",")
        frames.append(df[df["Balancing Authority"] == "NYIS"])
    out = pd.concat(frames)
    out.to_parquet(dest)
    record_derived("eia930", dest, "NYIS rows from EIA-930 six-month BALANCE files", url="https://www.eia.gov/electricity/gridmonitor/")
    for half in ("Jan_Jun", "Jul_Dec"):  # keep disk small; the parquet holds everything we use
        (RAW / "eia930" / f"EIA930_BALANCE_{year}_{half}.csv").unlink(missing_ok=True)
    return dest


def nyiso_dam_lbmp(year: int) -> Path:
    """NYISO day-ahead zonal LBMP, hourly, from monthly archives on mis.nyiso.com."""
    dest = RAW / "nyiso" / f"damlbmp_zone_{year}.parquet"
    if dest.exists():
        return dest
    frames = []
    for m in range(1, 13):
        name = f"{year}{m:02d}01damlbmp_zone_csv.zip"
        p = fetch("nyiso", name, f"http://mis.nyiso.com/public/csv/damlbmp/{name}", timeout=120, retries=2)
        with zipfile.ZipFile(p) as zf:
            for n in zf.namelist():
                frames.append(pd.read_csv(io.BytesIO(zf.read(n))))
    out = pd.concat(frames)
    out.to_parquet(dest)
    record_derived("nyiso", dest, "concatenated monthly DAM zonal LBMP archives", url="http://mis.nyiso.com/public/P-2Alist.htm")
    return dest
