"""Vapor-compression heat pump model (CoolProp), lifting data-center return water to network supply temperature.

Cycle: saturated evaporation at T_evap = T_source_out - approach (+5 K superheat), compression with a fixed
isentropic efficiency to the condensing pressure at T_cond = T_sink_out + approach, condensation with 2 K subcooling,
isenthalpic expansion. Heating COP = (h2 - h3) / (h2 - h1).

Evaluating CoolProp 8,760 times per scenario is slow, so `CopTable` precomputes a 1 K grid and interpolates.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import CoolProp.CoolProp as CP
import numpy as np

REFRIGERANT = "R1234ze(E)"  # low-GWP HFO used in large district-heating HPs; Tcrit 109 C
K = 273.15
SUPERHEAT_K = 5.0
SUBCOOL_K = 2.0


@dataclass(frozen=True)
class CycleResult:
    cop_heating: float
    cop_carnot: float
    t_evap_c: float
    t_cond_c: float

    @property
    def carnot_fraction(self) -> float:
        return self.cop_heating / self.cop_carnot


@lru_cache(maxsize=4096)
def cycle(t_source_out_c: float, t_sink_out_c: float, eta_is: float = 0.70, approach_k: float = 3.0,
          refrigerant: str = REFRIGERANT) -> CycleResult:
    """Single-stage cycle. Temperatures are the water-side outlet temperatures (the binding pinch points)."""
    t_evap = t_source_out_c - approach_k + K
    t_cond = t_sink_out_c + approach_k + K
    if t_cond <= t_evap:
        raise ValueError("sink must be warmer than source")
    t_crit = CP.PropsSI("Tcrit", refrigerant)
    if t_cond >= t_crit - 2:
        raise ValueError(f"condensing at {t_cond - K:.1f} C exceeds {refrigerant} limit ({t_crit - K - 2:.1f} C)")

    p_evap = CP.PropsSI("P", "T", t_evap, "Q", 1, refrigerant)
    p_cond = CP.PropsSI("P", "T", t_cond, "Q", 0, refrigerant)
    t1 = t_evap + SUPERHEAT_K
    h1 = CP.PropsSI("H", "T", t1, "P", p_evap, refrigerant)
    s1 = CP.PropsSI("S", "T", t1, "P", p_evap, refrigerant)
    h2s = CP.PropsSI("H", "P", p_cond, "S", s1, refrigerant)
    h2 = h1 + (h2s - h1) / eta_is
    h3 = CP.PropsSI("H", "T", t_cond - SUBCOOL_K, "P", p_cond, refrigerant)
    cop = (h2 - h3) / (h2 - h1)
    cop_carnot = t_cond / (t_cond - t_evap)
    return CycleResult(cop, cop_carnot, t_evap - K, t_cond - K)


class CopTable:
    """Bilinear-interpolated COP over (source outlet, sink outlet) on a 1 K grid."""

    def __init__(self, eta_is: float, approach_k: float, src_range=(10, 66), sink_range=(35, 95)):
        self.src = np.arange(*src_range, 1.0)
        self.sink = np.arange(*sink_range, 1.0)
        grid = np.full((len(self.src), len(self.sink)), np.nan)
        for i, ts in enumerate(self.src):
            for j, tk in enumerate(self.sink):
                if tk - ts >= 5:
                    try:
                        grid[i, j] = cycle(float(ts), float(tk), eta_is, approach_k).cop_heating
                    except ValueError:
                        pass
        self.grid = grid

    def __call__(self, t_src, t_sink) -> np.ndarray:
        t_src = np.clip(np.asarray(t_src, float), self.src[0], self.src[-1])
        t_sink = np.clip(np.asarray(t_sink, float), self.sink[0], self.sink[-1])
        fi = (t_src - self.src[0])
        fj = (t_sink - self.sink[0])
        i0 = np.clip(np.floor(fi).astype(int), 0, len(self.src) - 2)
        j0 = np.clip(np.floor(fj).astype(int), 0, len(self.sink) - 2)
        di, dj = fi - i0, fj - j0
        g = self.grid
        v = (g[i0, j0] * (1 - di) * (1 - dj) + g[i0 + 1, j0] * di * (1 - dj)
             + g[i0, j0 + 1] * (1 - di) * dj + g[i0 + 1, j0 + 1] * di * dj)
        if np.isnan(v).any():
            raise ValueError("COP requested outside the feasible table (lift < 5 K or above refrigerant limit)")
        return v
