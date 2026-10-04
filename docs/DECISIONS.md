# Decision log

Key modeling and engineering choices, with the reasoning behind each. This doubles as pitch-deck material.

| # | Date | Decision | Why | Alternatives rejected |
|---|------|----------|-----|-----------------------|
| D1 | 2026-10-03 | Run the same engine on both sites, then let the results pick the pitch site | The brief requires us to justify our site choice. Doing it quantitatively is our innovation hook | Picking a site by intuition |
| D2 | 2026-10-03 | Split the optimization into a design MILP (peak and annual), then an 8760-hour LP dispatch, then a rule-based dispatch for Monte Carlo | A combined 8760 × binary MILP takes minutes to hours to solve. Splitting it keeps every scenario solving in seconds, so we can precompute many what-ifs | A single monolithic MILP |
| D3 | 2026-10-03 | No basemap tile server. The map draws only bundled GeoJSON (streets, water, footprints) | The demo must work with wifi off (Execution rubric) | MapLibre demo tiles, Protomaps |
| D4 | 2026-10-03 | Precompute structural scenarios. Recompute carbon price and grid decarbonization in the browser | These two are linear in hourly arrays we already ship, so the sliders stay instant with no backend | A live Python backend |
| D5 | 2026-10-03 | Streets come from NYC Street Centerline (CSCL) for Site 1 and Census TIGER roads for Site 2, not from OSM | Every Overpass endpoint refused or hung connections from our build machine. CSCL is the city's own authoritative centerline (the source behind LION), so it's a better basis for routing pipes in public rights-of-way | OSMnx/Overpass |
| D6 | 2026-10-03 | Equity attributes come from CDC SVI 2022 (which embeds ACS 2018–22 estimates) and DOE LEAD 2022. We don't call the Census API | The Census API began requiring a key and returned an HTML page with HTTP 200. SVI and LEAD carry the household, poverty, housing-burden, income and energy-burden fields we need. `fetch()` now validates payloads, so error pages can never be cached as data | Census ACS API |
| D7 | 2026-10-03 | Derive 111 8th Ave IT load from the building's own LL84 electricity (57.7 MW avg) minus an LL84-derived office baseline, divided by PUE. Result: 24–37 MW IT, central value 30 | No public IT figure exists. A data-derived range from the building's own mandatory disclosure is defensible when judges probe it. A guessed number is not | Unsourced 5–30 MW guess |
| D8 | 2026-10-03 | Hourly price is NYISO DAM zonal LBMP, with a labeled proxy fallback (EIA-930 load shape scaled to the 2023 SOM published zonal average) | mis.nyiso.com was intermittently unreachable. The real 2023 data was fetched and cached, and the proxy remains a tested fallback that is labeled in the UI | — |
