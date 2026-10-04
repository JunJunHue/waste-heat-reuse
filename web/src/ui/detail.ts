import type { Offtaker } from "../results";
import { ui } from "../state";
import { esc, fmtInt, fmtNum, fmtUsd, nice } from "../format";
import { fullBars } from "./dimbars";

/** Building detail: why it ranks where it does, what it would gain, and why the optimizer chose it (or not). */
export function renderDetail(el: HTMLElement, o: Offtaker) {
  const status = o.status === "connected"
    ? `<div class="status-box ok"><b>Connected by the optimizer.</b> Receives ${fmtInt(o.delivered_mwh)} MWh/yr of recovered heat.</div>`
    : o.status === "rejected"
      ? `<div class="status-box no"><b>Not chosen:</b> ${esc(o.reason)}</div>`
      : `<div class="status-box muted-box">Ranked, but outside the optimizer's shortlist (top 50 by score + 20 largest loads).</div>`;
  el.innerHTML = `
    <button class="back" aria-label="Back to list">← All buildings</button>
    <div class="detail-head">
      <div class="detail-rank">#${o.rank}</div>
      <div><h2>${esc(nice(o.name))}</h2>
      <p class="muted">${esc(o.ll84_type ?? "")}${o.address ? ` · ${esc(nice(o.address))}` : ""}</p></div>
    </div>
    <div class="facts">
      <div><b>${fmtInt(o.units_res)}</b><span>homes${o.is_nycha ? " (NYCHA data book)" : ""}</span></div>
      <div><b>${fmtInt(o.heat_mwh)}</b><span>MWh/yr heat (measured)</span></div>
      <div><b>${fmtInt(o.distance_m)} m</b><span>from data center</span></div>
      <div><b class="cap">${o.primary_fuel}</b><span>today's heating fuel</span></div>
    </div>
    ${status}
    <h3>Fit across the brief's dimensions</h3>
    ${fullBars(o)}
    <p class="rationale">${esc(o.rationale)} Needs ~${fmtNum(o.t_req_avg_c, 0)} °C on average → heat-pump COP ${fmtNum(o.cop_at_building, 2)}${o.needs_steam_conversion ? "; steam plant needs a hot-water conversion at the building interface" : ""}.</p>
    ${o.net_value_per_mwh != null ? valueBreakdown(o) : ""}`;
  el.querySelector(".back")!.addEventListener("click", () => ui.set({ selectedId: null }));
}

/** $/MWh value stack as a diverging bar list (blue = gain, red = cost), with the net on its own row. */
function valueBreakdown(o: Offtaker): string {
  const items: [string, number, string][] = [
    ["Fuel the building no longer buys", o.avoided_cost_per_mwh ?? 0, "Blended by the building's fuel mix (EIA 2023 gas; NYCHA metered steam)"],
    ["Heat-pump electricity", -(o.hp_elec_cost_per_mwh ?? 0), "18.0¢/kWh (EIA NY commercial 2023) ÷ COP, incl. 6% network losses"],
    ["Data-center cooling avoided", o.dc_cooling_savings_per_mwh ?? 0, "The heat pump does the data center's cooling work"],
    ["LL97 penalties avoided", o.ll97_value_per_mwh ?? 0, o.is_nycha ? "NYCHA is on a separate LL97 pathway — no penalty credit taken" : "$268/tCO₂e × 75% likelihood the building is over its 2030 cap"],
    ["Community value (design weight)", o.equity_value_per_mwh ?? 0, "Equity shadow price used by the optimizer — NOT counted as cash"],
  ];
  const max = Math.max(...items.map(([, v]) => Math.abs(v)), Math.abs(o.net_value_per_mwh ?? 0), 1);
  const bar = (v: number) => `<span class="vb-track"><span class="vb-fill ${v >= 0 ? "pos" : "neg"}" style="width:${(Math.abs(v) / max) * 50}%;${v >= 0 ? "left:50%" : `right:50%`}"></span></span>`;
  return `<h3>Value of connecting, per MWh delivered</h3>
    <div class="value-bars">${items.map(([l, v, h]) => `<div class="vb-row" title="${esc(h)}"><span class="vb-label">${l}</span>${bar(v)}<span class="vb-val">${v >= 0 ? "+" : "−"}$${Math.abs(v).toFixed(0)}</span></div>`).join("")}
    <div class="vb-row net"><span class="vb-label">Net (system view)</span>${bar(o.net_value_per_mwh ?? 0)}<span class="vb-val">${(o.net_value_per_mwh ?? 0) >= 0 ? "+" : "−"}$${Math.abs(o.net_value_per_mwh ?? 0).toFixed(0)}</span></div></div>
    <p class="muted small">≈ ${fmtUsd(o.annual_value_usd)}/yr gross value · connection capex ${fmtUsd(o.conn_capex_usd)}. Hover a row for its source.</p>`;
}
