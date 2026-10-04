import { DIMS, DIM_HELP, DIM_LABEL, type Offtaker } from "../results";

/** Seven tiny vertical bars: a glanceable fingerprint of a building's fit (row-level). */
export function miniBars(o: Offtaker): string {
  return `<div class="mini-bars" aria-hidden="true">${DIMS.map((d) => {
    const v = (o as unknown as Record<string, number>)[`s_${d}`] ?? 0;
    return `<span class="mb mb-${d}" style="height:${Math.max(2, v * 18)}px" title="${DIM_LABEL[d]} ${(v * 100).toFixed(0)}"></span>`;
  }).join("")}</div>`;
}

/** Full labeled horizontal bars for the detail card. Single hue (magnitude); equity gets the community accent. */
export function fullBars(o: Offtaker): string {
  return `<div class="dim-bars">${DIMS.map((d) => {
    const v = (o as unknown as Record<string, number>)[`s_${d}`] ?? 0;
    return `<div class="dim-row" title="${DIM_HELP[d]}">
      <span class="dim-name">${DIM_LABEL[d]}</span>
      <span class="dim-track"><span class="dim-fill ${d === "equity" ? "equity" : ""}" style="width:${(v * 100).toFixed(1)}%"></span></span>
      <span class="dim-val">${(v * 100).toFixed(0)}</span></div>`;
  }).join("")}</div>`;
}
