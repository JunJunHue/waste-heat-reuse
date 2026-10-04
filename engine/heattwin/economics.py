"""System economics and outcome KPIs for a network design (annual basis, 25-year horizon).

The system view adds up value to all stakeholders; the deal room (M5) splits these same cash flows by ownership
model. Environmental KPIs use physical emission factors and the real hourly grid; LL97 penalties use the law's
coefficients.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .assumptions import Assumptions
from .network import Design, crf

MWH_PER_MMBTU = 0.293071


def npv(rate: float, cashflows: list[float]) -> float:
    """cashflows[0] at t=0 (undiscounted), cashflows[t] at end of year t."""
    return float(sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows)))


def payback_years(capex: float, annual: float) -> float:
    return float(capex / annual) if annual > 0 else float("inf")


def run(design: Design, a: Assumptions, cop_avg: float, grid_t_per_mwh: float, elec_price: float,
        high_svi: float = 0.6) -> dict:
    c = design.connected
    loss = a.v("network.heat_loss_fraction")
    E = float(c.delivered_mwh.sum())                     # MWh/yr delivered to buildings
    produced = E / (1 - loss)                            # MWh/yr leaving the heat pump
    elec_mwh = produced / cop_avg
    src_mwh = produced - elec_mwh

    # ---- capex
    soft = 1 + a.v("finance.soft_cost_fraction")
    cap_pipes = float(design.pipes.capex_usd.sum()) * soft
    cap_hp = design.hp_mw * 1000 * a.v("heat_pump.capex_per_kw_th") * soft
    cap_conn = float(c.conn_capex_usd.sum()) * soft
    capex = cap_pipes + cap_hp + cap_conn

    # ---- annual flows (system view)
    customer_avoided = float((c.delivered_mwh * c.avoided_cost_per_mwh).sum())
    elec_cost = elec_mwh * elec_price
    om = cap_hp / soft * a.v("heat_pump.om_pct_capex") + cap_pipes / soft * a.v("finance.network_om_pct_capex")
    dc_savings = src_mwh * elec_price / a.v("supply.dc_cooling_plant_cop")
    ll97 = float((c.delivered_mwh * c.ll97_value_per_mwh).sum())
    annual_system = customer_avoided - elec_cost - om + dc_savings + ll97

    years = int(a.v("finance.analysis_years"))
    rate = a.v("network.design_discount_rate")
    system_npv = npv(rate, [-capex] + [annual_system] * years)
    lcoh = (capex * crf(rate, years) + elec_cost + om - dc_savings) / E if E else float("nan")

    # ---- environment (physical factors; real 2023 grid intensity)
    total_fuel = (c.gas_kbtu + c.oil_kbtu + c.steam_kbtu).replace(0, np.nan)
    eff = {"gas": a.v("demand.boiler_eff_gas"), "oil": a.v("demand.boiler_eff_oil"), "steam": a.v("demand.steam_to_heat_eff")}
    ef = {"gas": a.v("emissions.ef_natural_gas_physical"), "oil": a.v("emissions.ef_oil2_physical"), "steam": a.v("emissions.ef_steam_physical")}
    t_per_mwh_heat = sum((c[f"{f}_kbtu"] / total_fuel).fillna(0) * ef[f] / 1000 / eff[f] / MWH_PER_MMBTU for f in eff)
    t_fuel_avoided = float((c.delivered_mwh * t_per_mwh_heat).sum())
    t_grid_added = elec_mwh * grid_t_per_mwh
    t_dc_cooling_avoided = src_mwh / a.v("supply.dc_cooling_plant_cop") * grid_t_per_mwh
    tco2e = t_fuel_avoided - t_grid_added + t_dc_cooling_avoided

    # ---- community
    high_vuln = c.is_nycha | (c.svi >= high_svi)
    homes = float(c.units_res.sum())
    homes_hv = float(c.loc[high_vuln, "units_res"].sum())
    heat_hv = float(c.loc[high_vuln, "delivered_mwh"].sum())
    discount = a.v("finance.heat_price_discount")
    customer_savings = discount * customer_avoided
    nycha_savings = discount * float((c.delivered_mwh * c.avoided_cost_per_mwh)[c.is_nycha].sum())

    return {
        "capex_usd": {"total": capex, "pipes": cap_pipes, "heat_pump": cap_hp, "connections": cap_conn},
        "annual_usd": {
            "customer_avoided_fuel_cost": customer_avoided, "hp_electricity": elec_cost, "om": om,
            "dc_cooling_savings": dc_savings, "ll97_penalties_avoided": ll97, "system_net": annual_system,
            "customer_savings_at_discount": customer_savings, "nycha_savings_at_discount": nycha_savings,
        },
        "energy_mwh": {"delivered": E, "produced": produced, "hp_electricity": elec_mwh, "dc_heat_recovered": src_mwh},
        "kpis": {
            "system_npv_usd": system_npv, "lcoh_usd_per_mwh": lcoh, "simple_payback_yr": payback_years(capex, annual_system),
            "tco2e_avoided_per_yr": tco2e, "tco2e_fuel_avoided": t_fuel_avoided, "tco2e_grid_added": t_grid_added,
            "tco2e_dc_cooling_avoided": t_dc_cooling_avoided,
            "ll97_penalties_avoided_usd_per_yr": ll97, "buildings_connected": int(len(c)),
            "homes_served": homes, "homes_high_vulnerability": homes_hv,
            "share_heat_to_high_vulnerability": heat_hv / E if E else 0.0,
            "nycha_homes_served": float(c.loc[c.is_nycha, "units_res"].sum()),
            "cop_avg": cop_avg, "hp_mw": design.hp_mw, "pipe_km": design.stats.get("pipe_km", 0.0),
            "dc_heat_reused_share": src_mwh / (design.stats.get("dc_heat_available_mwh") or np.nan),
        },
    }
