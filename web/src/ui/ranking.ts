import type { Offtaker, ScenarioBundle } from "../results";
import { ui } from "../state";
import { esc, fmtInt, nice } from "../format";
import { miniBars } from "./dimbars";

const TABS = [
  { id: "connected", label: "Connected" },
  { id: "rejected", label: "Not chosen" },
  { id: "ranked", label: "All ranked" },
] as const;

export function renderRanking(el: HTMLElement, b: ScenarioBundle) {
  const s = ui.get();
  const counts = {
    connected: b.offtakers.filter((o) => o.status === "connected").length,
    rejected: b.offtakers.filter((o) => o.status === "rejected").length,
    ranked: b.offtakers.length,
  };
  const list = b.offtakers
    .filter((o) => (s.tab === "ranked" ? true : o.status === s.tab))
    .sort((a, c) => a.rank - c.rank);
  const d = b.results.design;
  el.innerHTML = `
    <div class="panel-head">
      <h2>Who gets the heat — and why</h2>
      <p class="muted">${fmtInt(b.results.counts.eligible)} measured buildings scored on the brief's five fit dimensions + proximity + equity.
      An optimizer (MILP, ${fmtInt(d.binaries)} binary decisions on the real street grid) then chose ${counts.connected}.</p>
    </div>
    <div class="tabs" role="tablist">${TABS.map((t) => `<button role="tab" class="tab ${s.tab === t.id ? "active" : ""}" data-tab="${t.id}">${t.label}<span class="count">${counts[t.id]}</span></button>`).join("")}</div>
    <div class="legend-dims"><span>Fit fingerprint:</span> temp · capacity · timing · season · continuity · proximity · <span class="eq">equity</span></div>
    <ol class="rank-list">${list.map(row).join("")}</ol>`;
  el.querySelectorAll<HTMLButtonElement>(".tab").forEach((btn) =>
    btn.addEventListener("click", () => ui.set({ tab: btn.dataset.tab as typeof s.tab })));
  el.querySelectorAll<HTMLLIElement>(".rank-row").forEach((li) =>
    li.addEventListener("click", () => ui.set({ selectedId: li.dataset.id! })));
}

function row(o: Offtaker): string {
  const sel = ui.get().selectedId === o.id;
  const chips = [
    o.status === "connected" ? `<span class="chip chip-connected">Connected</span>` : o.status === "rejected" ? `<span class="chip chip-rejected">Not chosen</span>` : "",
    o.is_nycha ? `<span class="chip chip-nycha">NYCHA</span>` : "",
  ].join("");
  return `<li class="rank-row ${sel ? "selected" : ""}" data-id="${o.id}" tabindex="0">
    <span class="rank-num">#${o.rank}</span>
    <span class="rank-main"><span class="rank-name">${esc(nice(o.name))}</span>
      <span class="rank-meta">${chips}<span>${fmtInt(o.heat_mwh)} MWh/yr${o.units_res ? ` · ${fmtInt(o.units_res)} homes` : ""}</span></span></span>
    ${miniBars(o)}
    <span class="rank-score">${(o.total_score * 100).toFixed(0)}</span></li>`;
}
