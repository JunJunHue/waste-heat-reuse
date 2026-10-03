# Decision log

Key modeling and engineering choices, with the reasoning behind each. This doubles as pitch-deck material.

| # | Date | Decision | Why | Alternatives rejected |
|---|------|----------|-----|-----------------------|
| D1 | 2026-10-03 | Run the same engine on both sites, then let the results pick the pitch site | The brief requires us to justify our site choice. Doing it quantitatively is our innovation hook | Picking a site by intuition |
| D2 | 2026-10-03 | Split the optimization into a design MILP (peak and annual), then an 8760-hour LP dispatch, then a rule-based dispatch for Monte Carlo | A combined 8760 × binary MILP takes minutes to hours to solve. Splitting it keeps every scenario solving in seconds, so we can precompute many what-ifs | A single monolithic MILP |
| D3 | 2026-10-03 | No basemap tile server. The map draws only bundled GeoJSON (streets, water, footprints) | The demo must work with wifi off (Execution rubric) | MapLibre demo tiles, Protomaps |
| D4 | 2026-10-03 | Precompute structural scenarios. Recompute carbon price and grid decarbonization in the browser | These two are linear in hourly arrays we already ship, so the sliders stay instant with no backend | A live Python backend |
