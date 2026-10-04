import type { Results } from "../results";
import { fmtInt, fmtNum } from "../format";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
type Tab = "demand" | "supply" | "optimizer";

/** "How we know": the three claims judges probe first, each backed by data on screen. */
export function renderEvidence(el: HTMLElement, r: Results) {
  let tab: Tab = "demand";
  const draw = () => {
    el.innerHTML = `
      <div class="ev-head"><h3>How we know</h3>
        <div class="tabs small">${(["demand", "supply", "optimizer"] as Tab[]).map((t) =>
          `<button class="tab ${t === tab ? "active" : ""}" data-t="${t}">${{ demand: "Demand", supply: "Supply", optimizer: "Optimizer" }[t]}</button>`).join("")}</div></div>
      <div class="ev-body">${tab === "demand" ? demand(r) : tab === "supply" ? supply(r) : optimizer(r)}</div>`;
    el.querySelectorAll<HTMLButtonElement>(".tab").forEach((b) => b.addEventListener("click", () => { tab = b.dataset.t as Tab; draw(); }));
    if (tab === "demand") wireChartHover(el, r);
  };
  draw();
}

function demand(r: Results): string {
  const v = r.validation;
  if (!v?.months) return `<p class="muted">No metered validation available for this site.</p>`;
  return `<p class="ev-claim">Our demand model matches <b>Fulton Houses' real Con Ed steam bills</b>: monthly R² = <b>${v.r2.toFixed(3)}</b>,
    annual ${fmtInt(v.annual_modeled_mwh)} vs ${fmtInt(v.annual_metered_mwh)} MWh.</p>
    ${chart(v.months, v.metered_mwh, v.modeled_mwh)}
    <p class="muted small">Metered: NYC Open Data smdw-73pj (NYCHA steam bills, 2023), ${v.steam_price_usd_per_mmbtu.toFixed(1)} $/MMBtu paid.
    Modeled: LL84 annual fuel → useful heat → hourly space heat (real 2023 weather) + hot water.</p>`;
}

function supply(r: Results): string {
  const s = r.it_load.steps;
  if (!s) return `<p class="ev-claim">IT load ${r.it_load.value} MW (${r.it_load.low}–${r.it_load.high}) — ${r.it_load.source}</p>`;
  return `<p class="ev-claim">IT load isn't public, so we <b>derived it from the building's own energy disclosure</b>.</p>
    <ol class="steps">
      <li><b>${fmtNum(s.building_electricity_gwh)} GWh</b> grid electricity in 2023 (LL84) = <b>${fmtNum(s.building_avg_mw)} MW</b> average</li>
      <li>minus an office baseline of <b>${fmtNum(s.office_baseline_mw)} MW</b> (median of ${s.office_peer_count} large Manhattan offices, ${fmtNum(s.office_intensity_kwh_ft2_median)} kWh/ft²)</li>
      <li>= <b>${fmtNum(s.dc_load_mw)} MW</b> data-center load ÷ PUE ${fmtNum(s.pue)}</li>
      <li>= <b>${fmtNum(r.it_load.value)} MW IT</b> (range ${fmtNum(r.it_load.low)}–${fmtNum(r.it_load.high)}) → ${fmtNum(r.supply.q_src_mw_mean)} MW recoverable at ${fmtNum(r.supply.t_src_in_c, 0)} °C</li>
    </ol>`;
}

function optimizer(r: Results): string {
  const d = r.design;
  return `<p class="ev-claim">A mixed-integer program chose buildings, pipe routes and heat-pump size together — maximizing system value on the real street grid.</p>
    <div class="facts four">
      <div><b>${fmtInt(d.graph_edges)}</b><span>street segments (NYC CSCL)</span></div>
      <div><b>${fmtInt(d.binaries)}</b><span>yes/no decisions</span></div>
      <div><b>${fmtNum(d.solve_seconds, 0)} s</b><span>HiGHS solve</span></div>
      <div><b>${(d.mip_gap * 100).toFixed(1)}%</b><span>proven optimality gap</span></div>
    </div>
    <p class="muted small">Heat pump ${fmtNum(d.hp_mw)} MW of ${fmtNum(d.hp_max_mw)} MW the data center can firmly supply. Every building it skipped carries a reason — see "Not chosen".</p>`;
}

// ---- line chart: two series, one y-axis (MWh), 2px lines, 8px markers, legend + direct end labels, hover per month
const W = 340, H = 150, PAD = { l: 40, r: 64, t: 10, b: 22 };

function chart(months: number[], metered: number[], modeled: number[]): string {
  const max = Math.max(...metered, ...modeled) * 1.08;
  const x = (i: number) => PAD.l + (i / (months.length - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - v / max) * (H - PAD.t - PAD.b);
  const path = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const ticks = [0, 0.5, 1].map((f) => Math.round((max * f) / 500) * 500);
  const last = months.length - 1;
  return `<figure class="chart" data-max="${max}">
    <div class="chart-legend"><span class="key s1"></span>Metered (bills) <span class="key s2"></span>Modeled</div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Monthly heat, metered vs modeled">
      ${ticks.map((t) => `<line class="grid" x1="${PAD.l}" x2="${W - PAD.r}" y1="${y(t)}" y2="${y(t)}"/><text class="axis" x="${PAD.l - 6}" y="${y(t) + 3}" text-anchor="end">${t >= 1000 ? `${t / 1000}k` : t}</text>`).join("")}
      ${months.map((m, i) => (i % 2 === 0 ? `<text class="axis" x="${x(i)}" y="${H - 6}" text-anchor="middle">${MONTHS[m - 1]}</text>` : "")).join("")}
      <path class="line s1" d="${path(metered)}"/><path class="line s2" d="${path(modeled)}"/>
      ${metered.map((v, i) => `<circle class="dot s1" cx="${x(i)}" cy="${y(v)}" r="4"/>`).join("")}
      ${modeled.map((v, i) => `<circle class="dot s2" cx="${x(i)}" cy="${y(v)}" r="4"/>`).join("")}
      <text class="end-label" x="${x(last) + 8}" y="${y(metered[last]) + (metered[last] > modeled[last] ? -4 : 10)}">Metered</text>
      <text class="end-label" x="${x(last) + 8}" y="${y(modeled[last]) + (modeled[last] >= metered[last] ? -4 : 10)}">Modeled</text>
      <line class="crosshair" x1="0" x2="0" y1="${PAD.t}" y2="${H - PAD.b}" visibility="hidden"/>
      ${months.map((_, i) => `<rect class="hit" data-i="${i}" x="${x(i) - (W - PAD.l - PAD.r) / (2 * last)}" y="0" width="${(W - PAD.l - PAD.r) / last}" height="${H}"/>`).join("")}
    </svg>
    <div class="chart-tip" hidden></div>
    <table class="sr-only"><thead><tr><th>Month</th><th>Metered MWh</th><th>Modeled MWh</th></tr></thead>
      <tbody>${months.map((m, i) => `<tr><td>${MONTHS[m - 1]}</td><td>${metered[i]}</td><td>${modeled[i]}</td></tr>`).join("")}</tbody></table>
  </figure>`;
}

function wireChartHover(root: HTMLElement, r: Results) {
  const fig = root.querySelector<HTMLElement>(".chart");
  if (!fig) return;
  const tip = fig.querySelector<HTMLElement>(".chart-tip")!;
  const cross = fig.querySelector<SVGLineElement>(".crosshair")!;
  const v = r.validation;
  fig.querySelectorAll<SVGRectElement>(".hit").forEach((rect) => {
    rect.addEventListener("mouseenter", () => {
      const i = Number(rect.dataset.i);
      const cx = Number(rect.getAttribute("x")) + Number(rect.getAttribute("width")) / 2;
      cross.setAttribute("x1", String(cx)); cross.setAttribute("x2", String(cx)); cross.setAttribute("visibility", "visible");
      tip.hidden = false;
      tip.innerHTML = `<b>${MONTHS[v.months[i] - 1]} 2023</b><br/><span class="key s1"></span>Metered ${fmtInt(v.metered_mwh[i])} MWh<br/><span class="key s2"></span>Modeled ${fmtInt(v.modeled_mwh[i])} MWh`;
      tip.style.left = `${(cx / W) * 100}%`;
    });
  });
  fig.querySelector("svg")!.addEventListener("mouseleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); });
}
