"""Network design MILP (PuLP + HiGHS): which buildings to connect, which streets get pipe, how big the heat pump is.

Fixed-charge single-commodity flow on the real street graph (pipes stay in the public right-of-way):

  max  sum_k y_k * (V_k - CRF * C_conn_k)                    annual net value of serving building k
     - sum_e CRF * len_e * (a * x_e + b * (f_ij + f_ji))     pipe cost: fixed per metre + per MW-metre (fit of DN table)
     - CRF * c_hp * hp  -  om * c_hp * hp                    heat pump capex annuity + fixed O&M
  s.t. flow conservation: the source injects sum_k P_k y_k; node n absorbs sum_{k at n} P_k y_k
       f_ij + f_ji <= Fmax * x_e                             no flow without pipe
       sum_k P_k y_k <= hp <= HP_max                         heat pump capacity; HP_max from firm source heat
       x, y binary; f, hp >= 0

V_k = annual delivered heat x (avoided fuel cost - heat-pump electricity cost + LL97 penalty avoided
      + carbon value + equity value) is computed per building beforehand, so the MILP stays linear.
Hourly operation is checked afterwards by the 8760 dispatch (docs/DECISIONS.md D2).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import pulp
from shapely.geometry import LineString, Point

from .assumptions import Assumptions

UTM = "EPSG:32618"
PIPES = {"dn100": 0.107, "dn150": 0.160, "dn200": 0.210, "dn250": 0.263, "dn300": 0.313, "dn400": 0.394, "dn500": 0.492}


def crf(rate: float, years: float) -> float:
    """Capital recovery factor: converts a capex into an equal annual payment."""
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def pipe_capacity_mw(inner_d_m: float, a: Assumptions) -> float:
    dt = a.v("network.supply_temp_c") - a.v("network.return_temp_c")
    area = np.pi * inner_d_m ** 2 / 4
    return area * a.v("network.max_velocity_m_s") * 975.0 * 4.19 * dt / 1000  # rho ~975 kg/m3 at 60-75 C


def network_supply_temp(t_out: np.ndarray, a: Assumptions) -> np.ndarray:
    """Outdoor-reset network supply temperature: design value on the design day, floor (DHW-safe) when mild."""
    t_bal, t_des = a.v("demand.t_balance_point"), a.v("demand.t_design_outdoor")
    x = np.clip((t_bal - t_out) / (t_bal - t_des), 0, 1)
    lo, hi = a.v("network.t_supply_floor_c"), a.v("network.t_supply_design_c")
    return lo + (hi - lo) * x


def pick_dn(flow_mw: float, a: Assumptions) -> tuple[str, float]:
    """Smallest standard pipe that carries the flow; returns (dn, cost per metre)."""
    for dn, d in PIPES.items():
        if pipe_capacity_mw(d, a) >= flow_mw:
            return dn, a.v(f"pipes.{dn}") * a.v("network.pipe_cost_multiplier_nyc")
    raise ValueError(f"flow {flow_mw:.1f} MW exceeds DN500")


# ---------------------------------------------------------------- street graph
def street_graph(streets: gpd.GeoDataFrame, snap_m: float = 1.0) -> nx.Graph:
    """Undirected graph in UTM metres; segment endpoints within snap_m merge into one node."""
    g = nx.Graph()
    utm = streets.to_crs(UTM)
    key = lambda x, y: (round(x / snap_m) * snap_m, round(y / snap_m) * snap_m)
    for geom_utm, geom_ll in zip(utm.geometry, streets.geometry):
        if geom_utm is None or geom_utm.is_empty:
            continue
        coords = list(geom_utm.coords)
        u, v = key(*coords[0][:2]), key(*coords[-1][:2])
        if u == v:
            continue
        length = geom_utm.length
        if g.has_edge(u, v) and g.edges[u, v]["length"] <= length:
            continue
        g.add_edge(u, v, length=length, geom=geom_ll)
    biggest = max(nx.connected_components(g), key=len)
    return g.subgraph(biggest).copy()


def _nearest_nodes(g: nx.Graph, xy: np.ndarray) -> tuple[list, np.ndarray]:
    nodes = list(g.nodes)
    arr = np.array(nodes)
    d2 = ((arr[None, :, :] - xy[:, None, :]) ** 2).sum(axis=2)
    idx = d2.argmin(axis=1)
    return [nodes[i] for i in idx], np.sqrt(d2[np.arange(len(xy)), idx])


# ---------------------------------------------------------------- per-building annual value
def building_value(cands: pd.DataFrame, a: Assumptions, cop_avg: np.ndarray, elec_price: float,
                   equity_weight: float, ll97: bool) -> pd.DataFrame:
    """Annual $ value per building if connected (system view: all stakeholders combined)."""
    df = cands.copy()
    mwh_per_mmbtu = 0.293071
    e = df.heat_mwh * a.v("network.hp_energy_coverage")  # heat the network delivers; the rest stays on existing boilers
    total_fuel = (df.gas_kbtu + df.oil_kbtu + df.steam_kbtu).replace(0, np.nan)
    share = {f: (df[f"{f}_kbtu"] / total_fuel).fillna(0) for f in ("gas", "oil", "steam")}
    eff = {"gas": a.v("demand.boiler_eff_gas"), "oil": a.v("demand.boiler_eff_oil"), "steam": a.v("demand.steam_to_heat_eff")}
    price = {"gas": a.v("prices.gas_commercial_ny_2023"), "oil": a.v("prices.oil2_ny_2023"), "steam": a.v("prices.steam_coned_2023")}
    # $/MWh of useful heat the building pays today, blended by its fuel mix
    df["avoided_cost_per_mwh"] = sum(share[f] * price[f] / eff[f] / mwh_per_mmbtu for f in share)
    df["hp_elec_cost_per_mwh"] = elec_price / cop_avg / (1 - a.v("network.heat_loss_fraction"))

    # LL97-accounted emissions (2024-29 coefficients): fuel avoided minus heat-pump electricity added
    ef = {"gas": a.v("policy.ll97_ef_natural_gas"), "oil": a.v("policy.ll97_ef_fuel_oil_2"), "steam": a.v("policy.ll97_ef_district_steam")}
    t_fuel_per_mwh = sum(share[f] * ef[f] * 1000 / eff[f] / mwh_per_mmbtu for f in share)       # tCO2e per MWh useful heat
    t_elec_per_mwh = a.v("policy.ll97_ef_electricity") * 1000 / cop_avg / (1 - a.v("network.heat_loss_fraction"))
    df["tco2e_avoided_per_mwh"] = t_fuel_per_mwh - t_elec_per_mwh
    ll97_rate = a.v("policy.ll97_penalty") * a.v("policy.ll97_capture_fraction") if ll97 else 0.0
    df["ll97_value_per_mwh"] = np.where(df.is_nycha, 0.0, df.tco2e_avoided_per_mwh * ll97_rate)
    df["carbon_value_per_mwh"] = df.tco2e_avoided_per_mwh * a.v("finance.carbon_value")
    df["equity_value_per_mwh"] = equity_weight * a.v("network.equity_value_per_weight") * df.s_equity

    # Value to the data center: heat the HP evaporator removes is heat the DC cooling plant no longer rejects.
    src_per_mwh = (1 - 1 / cop_avg) / (1 - a.v("network.heat_loss_fraction"))      # MWh source heat per MWh delivered
    df["dc_cooling_savings_per_mwh"] = src_per_mwh * elec_price / a.v("supply.dc_cooling_plant_cop")

    df["delivered_mwh"] = e
    df["net_value_per_mwh"] = (df.avoided_cost_per_mwh - df.hp_elec_cost_per_mwh + df.dc_cooling_savings_per_mwh
                               + df.ll97_value_per_mwh + df.carbon_value_per_mwh + df.equity_value_per_mwh)
    df["annual_value_usd"] = e * df.net_value_per_mwh
    df["peak_net_mw"] = df.peak_mw * a.v("network.hp_peak_coverage")
    conv = np.where(df.needs_steam_conversion, a.v("building_interface.steam_conversion_cost_per_kw"), 0)
    # HX sized for the network's share of peak; existing boilers/steam stay as peak and backup supply
    df["interface_capex_usd"] = df.peak_net_mw * 1000 * (a.v("building_interface.substation_cost_per_kw") + conv)
    return df


# ---------------------------------------------------------------- MILP
@dataclass
class Design:
    connected: pd.DataFrame
    rejected: pd.DataFrame
    pipes: gpd.GeoDataFrame
    hp_mw: float
    hp_max_mw: float
    objective_usd_per_yr: float
    solve_seconds: float
    status: str
    stats: dict = field(default_factory=dict)


def optimize(cands: pd.DataFrame, streets: gpd.GeoDataFrame, dc_lonlat: tuple[float, float],
             q_src_firm_mw: float, cop_design: float, a: Assumptions, time_limit: int = 120) -> Design:
    g = street_graph(streets)
    pts = gpd.GeoSeries(gpd.points_from_xy(cands.lon, cands.lat), crs="EPSG:4326").to_crs(UTM)
    cand_nodes, service_m = _nearest_nodes(g, np.c_[pts.x, pts.y])
    dc_pt = gpd.GeoSeries([Point(*dc_lonlat)], crs="EPSG:4326").to_crs(UTM)[0]
    (src,), _ = _nearest_nodes(g, np.array([[dc_pt.x, dc_pt.y]]))
    cands = cands.assign(node=cand_nodes, service_m=service_m)
    cands["conn_capex_usd"] = cands.interface_capex_usd + cands.service_m * a.v("network.service_line_cost_per_m")

    r = crf(a.v("network.design_discount_rate"), a.v("finance.analysis_years"))
    fixed_m = a.v("network.pipe_cost_fixed_per_m") * a.v("network.pipe_cost_multiplier_nyc")
    var_mw_m = a.v("network.pipe_cost_per_mw_m") * a.v("network.pipe_cost_multiplier_nyc")
    c_hp = a.v("heat_pump.capex_per_kw_th") * 1000
    hp_max = q_src_firm_mw * cop_design / (cop_design - 1)   # evaporator duty limited by firm source heat
    f_max = min(pipe_capacity_mw(PIPES["dn500"], a), hp_max)   # tightest valid big-M for the flow-pipe link

    m = pulp.LpProblem("heat_network", pulp.LpMaximize)
    K = list(cands.index)
    E = list(g.edges)
    y = pulp.LpVariable.dicts("y", K, cat="Binary")
    x = pulp.LpVariable.dicts("x", range(len(E)), cat="Binary")
    f = {}
    for i, (u, v) in enumerate(E):
        f[(i, 0)] = pulp.LpVariable(f"f_{i}_uv", lowBound=0)
        f[(i, 1)] = pulp.LpVariable(f"f_{i}_vu", lowBound=0)
    hp = pulp.LpVariable("hp", lowBound=0, upBound=hp_max)

    P = cands.peak_net_mw.to_dict()
    val = (cands.annual_value_usd - r * cands.conn_capex_usd).to_dict()
    m += (pulp.lpSum(val[k] * y[k] for k in K)
          - pulp.lpSum(r * g.edges[E[i]]["length"] * (fixed_m * x[i] + var_mw_m * (f[(i, 0)] + f[(i, 1)])) for i in range(len(E)))
          - (r + a.v("heat_pump.om_pct_capex")) * c_hp * hp)

    inflow = {n: [] for n in g.nodes}
    outflow = {n: [] for n in g.nodes}
    for i, (u, v) in enumerate(E):
        outflow[u].append(f[(i, 0)]); inflow[v].append(f[(i, 0)])
        outflow[v].append(f[(i, 1)]); inflow[u].append(f[(i, 1)])
        m += f[(i, 0)] + f[(i, 1)] <= f_max * x[i]
    demand_at = {n: [] for n in g.nodes}
    for k in K:
        demand_at[cands.at[k, "node"]].append(P[k] * y[k])
    total = pulp.lpSum(P[k] * y[k] for k in K)
    for n in g.nodes:
        if n == src:
            m += pulp.lpSum(outflow[n]) - pulp.lpSum(inflow[n]) == total - pulp.lpSum(demand_at[n])
        else:
            m += pulp.lpSum(inflow[n]) - pulp.lpSum(outflow[n]) == pulp.lpSum(demand_at[n])
    m += total <= hp
    # valid inequality (tightens the LP relaxation): a building off the source node needs a pipe at its node
    incident = {n: [] for n in g.nodes}
    for i, (u, v) in enumerate(E):
        incident[u].append(x[i]); incident[v].append(x[i])
    for k in K:
        n = cands.at[k, "node"]
        if n != src:
            m += y[k] <= pulp.lpSum(incident[n])

    solver = pulp.HiGHS(msg=False, timeLimit=time_limit, gapRel=0.005)
    import time
    t0 = time.time()
    m.solve(solver)
    dt = time.time() - t0
    status = pulp.LpStatus[m.status]
    try:
        info = m.solverModel.getInfo()
        gap = float(info.mip_gap)
    except Exception:
        gap = float("nan")
    if status not in ("Optimal",) and m.sol_status not in (1, 2):
        raise RuntimeError(f"network MILP failed: {status}")

    sel = [k for k in K if (y[k].value() or 0) > 0.5]
    connected = cands.loc[sel].copy()
    hp_mw = float(hp.value() or 0)

    # pipes: built edges with their design flow, re-costed with the actual DN table
    rows = []
    for i, (u, v) in enumerate(E):
        if (x[i].value() or 0) > 0.5:
            flow = (f[(i, 0)].value() or 0) + (f[(i, 1)].value() or 0)
            if flow < 1e-6:
                continue
            dn, cost_m = pick_dn(flow, a)
            ed = g.edges[u, v]
            rows.append({"flow_mw": flow, "dn": dn, "length_m": ed["length"], "capex_usd": cost_m * ed["length"],
                         "geometry": ed["geom"]})
    pipes = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326") if rows else \
        gpd.GeoDataFrame(columns=["flow_mw", "dn", "length_m", "capex_usd", "geometry"], geometry="geometry", crs="EPSG:4326")

    built = {src} | {n for i, (u, v) in enumerate(E) if (x[i].value() or 0) > 0.5 for n in (u, v)}
    hp_ann_per_mw = (r + a.v("heat_pump.om_pct_capex")) * c_hp
    rejected = _explain_rejections(cands.drop(index=sel), g, built, src, r, fixed_m, var_mw_m, hp_ann_per_mw,
                                   hp_mw >= hp_max - 1e-3)
    return Design(connected, rejected, pipes, hp_mw, hp_max, float(pulp.value(m.objective)), dt, status, {
        "graph_nodes": g.number_of_nodes(), "graph_edges": g.number_of_edges(), "candidates": len(K),
        "binaries": len(K) + len(E), "pipe_km": float(pipes.length_m.sum() / 1000) if len(pipes) else 0.0,
        "mip_gap": gap, "time_limit_s": time_limit,
    })


def _explain_rejections(rej: pd.DataFrame, g: nx.Graph, built_nodes: set, src, r: float, fixed_m: float,
                        var_mw_m: float, hp_ann_per_mw: float, supply_binding: bool) -> pd.DataFrame:
    """Why wasn't each candidate chosen? Price its full marginal cost: new main from the BUILT network, trunk
    upsizing all the way from the source, extra heat-pump capacity, and the building connection."""
    lengths = nx.multi_source_dijkstra_path_length(g, built_nodes, weight="length")
    from_src = nx.single_source_dijkstra_path_length(g, src, weight="length")
    rej = rej.copy()
    reasons, margins, ext = [], [], []
    for _, c in rej.iterrows():
        path_m = float(lengths.get(c.node, np.inf))
        ann_pipe = r * (path_m * fixed_m + float(from_src.get(c.node, np.inf)) * var_mw_m * c.peak_net_mw)
        ann_hp = hp_ann_per_mw * c.peak_net_mw
        ann_conn = r * c.conn_capex_usd
        cost = ann_pipe + ann_hp + ann_conn
        margin = c.annual_value_usd - cost
        margins.append(margin)
        ext.append(path_m)
        if c.annual_value_usd <= 0:
            per = c.get("net_value_per_mwh")
            detail = f" (${per:,.0f}/MWh net)" if per is not None and np.isfinite(per) else ""
            reasons.append(f"Heat-pump heat costs more than this building's current heat{detail}")
        elif supply_binding and margin >= 0:
            reasons.append("Data-center heat fully allocated to higher-value users")
        else:
            ext_txt = f"{path_m:,.0f} m new main + " if path_m > 1 else ""
            verdict = "exceeds" if margin < 0 else "roughly equals"
            reasons.append(f"Cost to serve (~${cost / 1e3:,.0f}k/yr: {ext_txt}pipe ${ann_pipe / 1e3:,.0f}k, heat pump "
                           f"${ann_hp / 1e3:,.0f}k, connection ${ann_conn / 1e3:,.0f}k) {verdict} its value "
                           f"(${c.annual_value_usd / 1e3:,.0f}k/yr)")
    rej["reason"] = reasons
    rej["est_margin_usd_per_yr"] = margins
    rej["extension_m"] = ext
    return rej
