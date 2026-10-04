import type { Results } from "../results";
import { fmtInt, fmtPct, fmtUsd } from "../format";

interface Tile { label: string; value: string; sub: string; tone?: "community" | "climate" | "money" | "tech" }

export function renderKpis(el: HTMLElement, r: Results) {
  const k = r.economics.kpis;
  // Community outcomes lead; engineering and money follow (theme: waste heat -> community value).
  const tiles: Tile[] = [
    { label: "Homes heated", value: fmtInt(k.homes_served), sub: `${fmtInt(k.nycha_homes_served)} in NYCHA public housing`, tone: "community" },
    { label: "Heat to high-vulnerability homes", value: fmtPct(k.share_heat_to_high_vulnerability), sub: "NYCHA or tract SVI ≥ 60th pct", tone: "community" },
    { label: "CO₂e avoided", value: `${fmtInt(k.tco2e_avoided_per_yr)} t/yr`, sub: "real 2023 hourly NY grid", tone: "climate" },
    { label: "LL97 penalties avoided", value: `${fmtUsd(k.ll97_penalties_avoided_usd_per_yr)}/yr`, sub: "$268/tCO₂e, private buildings", tone: "climate" },
    { label: "Data-center heat reused", value: fmtPct(k.dc_heat_reused_share), sub: `${fmtInt(k.buildings_connected)} buildings · ${k.pipe_km.toFixed(1)} km pipe`, tone: "tech" },
    { label: "Heat-pump COP", value: k.cop_avg.toFixed(2), sub: `${r.cop.min.toFixed(1)}–${r.cop.max.toFixed(1)} across the year`, tone: "tech" },
  ];
  el.innerHTML = tiles
    .map((t) => `<div class="kpi kpi-${t.tone}"><div class="kpi-label">${t.label}</div><div class="kpi-value">${t.value}</div><div class="kpi-sub">${t.sub}</div></div>`)
    .join("");
}
