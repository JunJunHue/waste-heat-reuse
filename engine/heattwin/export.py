"""Write compact, frontend-ready files to web/public/data/<site>/ (the browser never calls external APIs)."""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd

from .site import ROOT, Site

WEB_DATA = ROOT / "web" / "public" / "data"


def _write_geojson(gdf: gpd.GeoDataFrame, path: Path, precision: int = 6) -> None:
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.set_precision(10 ** -precision)
    path.write_text(gdf.to_json(drop_id=True, na="null"))


def export_site(site: Site) -> Path:
    src, out = site.processed_dir, WEB_DATA / site.id
    out.mkdir(parents=True, exist_ok=True)

    b = gpd.read_parquet(src / "buildings.parquet")
    cols = ["bin", "address", "height_m", "units_res", "is_nycha", "has_ll84", "ll84_property", "svi",
            "energy_burden_pct", "gas_kbtu", "steam_kbtu", "oil2_kbtu", "oil4_kbtu", "geometry"]
    from shapely.geometry import Point
    dc_pt = Point(site.data_center.lon, site.data_center.lat)
    b["is_dc"] = b.geometry.contains(dc_pt)
    b = b[cols + ["is_dc"]].copy()
    b["heat_fuel_mmbtu"] = ((b.gas_kbtu + b.steam_kbtu + b.oil2_kbtu + b.oil4_kbtu) / 1000).round(1)
    b = b.drop(columns=["gas_kbtu", "steam_kbtu", "oil2_kbtu", "oil4_kbtu"])
    b["height_m"] = b.height_m.round(1)
    b["units_res"] = b.units_res.round(0)
    b["svi"] = b.svi.round(3)
    b["geometry"] = b.geometry.simplify(0.000005)
    _write_geojson(b, out / "buildings.geojson")

    _write_geojson(gpd.read_parquet(src / "streets.parquet")[["full_street_name", "geometry"]], out / "streets.geojson")
    _write_geojson(gpd.read_parquet(src / "context.parquet"), out / "context.geojson")

    meta = json.loads((src / "hourly_meta.json").read_text())
    dc = site.data_center
    manifest = {
        "site": {"id": site.id, "name": site.name, "kind": site.kind, "bbox": site.study_area.bbox},
        "data_center": {"name": dc.name, "lon": dc.lon, "lat": dc.lat,
                        "it_load_mw": dc.it_load_mw.model_dump(), "existing_cooling": dc.existing_cooling},
        "layers": {"buildings": "buildings.geojson", "streets": "streets.geojson", "context": "context.geojson"},
        "labels": {"price_source": meta["price_source"]},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (WEB_DATA / "sites.json").write_text(json.dumps({"sites": sorted(p.name for p in WEB_DATA.iterdir() if p.is_dir())}))
    return out
