"""Write compact, frontend-ready files to web/public/data/<site>/ (the browser never calls external APIs)."""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from .site import ROOT, Site

WEB_DATA = ROOT / "web" / "public" / "data"


def _write_geojson(gdf: gpd.GeoDataFrame, path: Path, precision: int = 6) -> None:
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.set_precision(10 ** -precision)
    path.write_text(gdf.to_json(drop_id=True, na="null"))


def _clean(o):
    """JSON-safe: numpy -> python, NaN/inf -> None."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


OFFTAKER_COLS = ["id", "name", "rank", "ll84_type", "address", "primary_fuel", "heat_mwh", "sh_mwh", "dhw_mwh", "peak_mw",
                 "units_res", "units_source", "is_nycha", "svi", "distance_m", "t_req_avg_c", "cop_at_building",
                 "load_factor", "summer_ratio", "needs_steam_conversion", "s_temperature", "s_capacity", "s_timing",
                 "s_seasonality", "s_continuity", "s_proximity", "s_equity", "fit_score", "total_score", "rationale",
                 "lon", "lat", "bins"]
VALUE_COLS = ["avoided_cost_per_mwh", "hp_elec_cost_per_mwh", "dc_cooling_savings_per_mwh", "ll97_value_per_mwh",
              "equity_value_per_mwh", "net_value_per_mwh", "annual_value_usd", "delivered_mwh", "conn_capex_usd",
              "tco2e_avoided_per_mwh"]


def export_result(res, out_root: Path = WEB_DATA) -> Path:
    """Write one scenario's results: offtakers.json, network.geojson, results.json."""
    out = out_root / res.site.id / res.scenario.id
    out.mkdir(parents=True, exist_ok=True)
    d = res.design
    connected, rejected = set(d.connected.id), d.rejected.set_index("id")
    shortlisted = connected | set(rejected.index)
    el = res.ranked[res.ranked.eligible]
    ranked = el[(el["rank"] <= 150) | el.id.isin(shortlisted)].copy()   # never hide a building the optimizer considered
    ranked = ranked[[c for c in OFFTAKER_COLS if c in ranked]]
    vals = pd.concat([d.connected, d.rejected])[["id", *VALUE_COLS]].drop_duplicates("id").set_index("id")
    records = []
    for r in ranked.to_dict("records"):
        status = "connected" if r["id"] in connected else ("rejected" if r["id"] in rejected.index else "not_shortlisted")
        rec = {**r, "status": status, "reason": rejected.reason.get(r["id"]) if status == "rejected" else None,
               "bins": [str(b) for b in r.get("bins", [])]}
        if r["id"] in vals.index:
            rec.update(vals.loc[r["id"]].to_dict())
        records.append(rec)
    screened = res.screened.sort_values("heat_mwh", ascending=False).head(25).to_dict("records")
    (out / "offtakers.json").write_text(json.dumps(_clean({"offtakers": records, "screened_out": screened})))

    pipes = d.pipes.copy()
    if len(pipes):
        pipes["flow_mw"] = pipes.flow_mw.round(2)
        _write_geojson(pipes[["flow_mw", "dn", "length_m", "geometry"]], out / "network.geojson")
    else:
        (out / "network.geojson").write_text('{"type":"FeatureCollection","features":[]}')

    sup = res.supply
    results = {
        "scenario": res.scenario.to_dict(),
        "it_load": res.it_load,
        "supply": {"it_load_mw_mean": float(sup.it_load_mw.mean()), "q_src_mw_mean": float(sup.q_src_mw.mean()),
                   "q_src_gwh": float(sup.q_src_mw.sum() / 1000), "t_src_in_c": float(sup.t_src_in_c.iloc[0]),
                   "t_src_out_c": float(sup.t_src_out_c.iloc[0])},
        "design": {"hp_mw": d.hp_mw, "hp_max_mw": d.hp_max_mw, "objective_usd_per_yr": d.objective_usd_per_yr,
                   "solve_seconds": d.solve_seconds, "status": d.status, **d.stats},
        "economics": res.econ,
        "validation": res.validation,
        "cop": {"avg": res.econ["kpis"]["cop_avg"], "min": float(res.cop_hourly.min()), "max": float(res.cop_hourly.max())},
        "counts": {"candidates_scored": int(len(res.ranked)), "eligible": int(res.ranked.eligible.sum()),
                   "screened_out": int(len(res.screened)), "shortlisted_for_milp": int(len(d.connected) + len(d.rejected))},
    }
    (out / "results.json").write_text(json.dumps(_clean(results), indent=1))
    return out


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
        "labels": {
            "price_source": meta["price_source"],
            "demand_source": ("MEASURED: NYC LL84 2023 benchmarking (validated vs NYCHA metered steam)" if site.adapter == "nyc"
                              else "SYNTHETIC: Overture footprints x EIA RECS 2020 Northeast intensities (no benchmarking law upstate)"),
            "data_quality": "measured" if site.adapter == "nyc" else "synthetic",
        },
        "scenarios": sorted(p.name for p in out.iterdir() if p.is_dir()),
        "default_scenario": f"{site.data_center.existing_cooling}_g0_eq15",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (WEB_DATA / "sites.json").write_text(json.dumps({"sites": sorted(p.name for p in WEB_DATA.iterdir() if p.is_dir())}))
    return out


COMPARE_KPIS = [
    # key, label, unit, better ("high"|"low"), group
    ("homes_served", "Homes heated", "homes", "high", "community"),
    ("homes_high_vulnerability", "High-vulnerability homes heated", "homes", "high", "community"),
    ("share_heat_to_high_vulnerability", "Heat to high-vulnerability homes", "share", "high", "community"),
    ("tco2e_avoided_per_yr", "CO₂e avoided", "t/yr", "high", "climate"),
    ("water_saved_m3_per_yr", "Cooling water not evaporated", "m³/yr", "high", "climate"),
    ("dc_heat_reused_share", "Data-center heat reused", "share", "high", "technical"),
    ("cop_avg", "Heat-pump COP", "", "high", "technical"),
    ("buildings_connected", "Offtakers connected", "", "high", "technical"),
    ("pipe_km", "Network length", "km", "low", "technical"),
    ("lcoh_usd_per_mwh", "Levelized cost of heat", "$/MWh", "low", "economic"),
    ("system_npv_usd", "System NPV (6%, 25 yr)", "$", "high", "economic"),
    ("ll97_penalties_avoided_usd_per_yr", "LL97 penalties avoided", "$/yr", "high", "economic"),
]


def export_compare(site_ids: list[str], scenario_id: str = "air_g0_eq15", fallback_scenario: str = "liquid_g0_eq15") -> Path:
    """Same KPIs, same engine, both sites: the evidence behind our site choice."""
    sites = []
    for sid in site_ids:
        site = Site.load(sid)
        d = WEB_DATA / sid
        res_path = next((d / s / "results.json" for s in (scenario_id, fallback_scenario) if (d / s / "results.json").exists()), None)
        if res_path is None:
            continue
        r = json.loads(res_path.read_text())
        man = json.loads((d / "manifest.json").read_text())
        sites.append({"id": sid, "name": site.name, "kind": site.kind, "scenario": r["scenario"]["id"],
                      "data_quality": man["labels"]["data_quality"], "demand_source": man["labels"]["demand_source"],
                      "it_load_mw": r["it_load"]["value"], "dc_heat_gwh": r["supply"]["q_src_gwh"],
                      "kpis": r["economics"]["kpis"], "capex_usd": r["economics"]["capex_usd"]["total"],
                      "delivered_gwh": r["economics"]["energy_mwh"]["delivered"] / 1000})
    out = {"kpis": [{"key": k, "label": l, "unit": u, "better": b, "group": g} for k, l, u, b, g in COMPARE_KPIS],
           "sites": sites}
    (WEB_DATA / "compare.json").write_text(json.dumps(_clean(out), indent=1))
    return WEB_DATA / "compare.json"
