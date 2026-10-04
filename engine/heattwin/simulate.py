"""Run the full engine chain for one site + scenario: supply -> demand -> match -> network MILP -> economics."""
from __future__ import annotations

import time
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd

from . import demand as D
from . import economics as EC
from . import matcher as MT
from . import network as N
from . import supply as SU
from .assumptions import Assumptions
from .heatpump import CopTable
from .scenario import Scenario
from .site import Site

N_TOP_SCORE = 50   # MILP candidates: best-scoring buildings ...
N_TOP_HEAT = 20    # ... plus the largest anchors, so big loads are never pre-filtered away


@dataclass
class Result:
    site: Site
    scenario: Scenario
    it_load: dict
    supply: pd.DataFrame
    ranked: pd.DataFrame
    screened: pd.DataFrame
    design: N.Design
    econ: dict
    cop_hourly: np.ndarray
    t_net_hourly: np.ndarray
    validation: dict
    timings: dict


def run(site_id: str, sc: Scenario, a: Assumptions | None = None, cop: CopTable | None = None) -> Result:
    t = {}
    t0 = time.time()
    a = a or Assumptions.load()
    site = Site.load(site_id)
    P = site.processed_dir
    buildings = gpd.read_parquet(P / "buildings.parquet")
    hourly = pd.read_parquet(P / "hourly.parquet")
    streets = gpd.read_parquet(P / "streets.parquet")
    cop = cop or CopTable(a.v("heat_pump.isentropic_efficiency"), a.v("heat_pump.approach_k"))
    t["load"] = time.time() - t0

    it = SU.derive_it_load(site, a)
    sup = SU.run(site, a, hourly, sc, it["value"])
    t_src_out = float(sup.t_src_out_c.iloc[0])

    off, screened = D.offtakers_from_ll84(buildings, a, site)
    shp = D.shapes(hourly, a)
    M = D.hourly_matrix(off, shp)
    off["peak_mw"] = M.max(axis=1)
    ranked = MT.score(off, M, hourly, t_src_out, (site.data_center.lon, site.data_center.lat), a, cop, sc.equity_weight)
    t["match"] = time.time() - t0 - t["load"]

    t_net = N.network_supply_temp(hourly.t_out_c.to_numpy(), a)
    approach = a.v("heat_pump.approach_k")
    cop_h = cop(sup.t_src_out_c.to_numpy(), t_net + approach)
    w = M.sum(axis=0)
    cop_avg = float((cop_h * w).sum() / w.sum())
    cop_design = float(cop(t_src_out, a.v("network.t_supply_design_c") + approach))
    elec = a.v("prices.electricity_commercial_ny_2023")

    el = ranked[ranked.eligible]
    cands = pd.concat([el.head(N_TOP_SCORE), el.sort_values("heat_mwh", ascending=False).head(N_TOP_HEAT)]).drop_duplicates("id")
    cands = N.building_value(cands, a, np.full(len(cands), cop_avg), elec, sc.equity_weight, ll97=True)
    design = N.optimize(cands, streets, (site.data_center.lon, site.data_center.lat), float(sup.q_src_mw.min()), cop_design, a)
    design.stats["dc_heat_available_mwh"] = float(sup.q_src_mw.sum())
    t["milp"] = design.solve_seconds

    grid_t = float(hourly.grid_tco2_per_mwh.mean())
    econ = EC.run(design, a, cop_avg, grid_t, elec)
    validation = D.validate_against_nycha_steam(ranked, M_lookup(off, M), hourly, a) if site.adapter == "nyc" else {}
    t["total"] = time.time() - t0
    return Result(site, sc, it, sup, ranked, screened, design, econ, cop_h, t_net, validation, t)


def M_lookup(off: pd.DataFrame, M: np.ndarray) -> dict[str, np.ndarray]:
    return dict(zip(off.id, M))
