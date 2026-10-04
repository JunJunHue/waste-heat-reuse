# Heat Twin — Engineering Handoff

_Written 2026-10-04 ~01:40 local by the previous coding agent. Read this whole file before touching code. It is the single source of truth for project state; `docs/DECISIONS.md`, `docs/DATA_SOURCES.md` and `docs/RUBRIC_CHECK.md` add detail._

---

## 0. TL;DR

- **What this is:** "Heat Twin", a hackathon entry for the NYU Data Center Heat Reuse Challenge. It has two parts:
  - a Python simulation engine that precomputes results to JSON;
  - a Vite + TypeScript + deck.gl/MapLibre 3D web app that plays them back **fully offline**.
- **Done and committed (4 commits on `main`):**
  - M0 (scaffold)
  - M1 (Site 1 real-data pipeline and 3D map)
  - M2 (Tier 1 engine)
  - M3 (Tier 1 interactive demo)
  - Site 1 (111 8th Ave, Chelsea) works end to end and is demoable now.
- **In progress, uncommitted:** M4. Site 2 (TeraWulf Lake Hawkeye, Lansing NY) is being ported to the same engine via site config, plus a site-comparison export. About 500 lines of WIP sit in the working tree, and **all 34 tests pass on it**. The **Site 2 adapter itself has never been executed**, because its input (Overture buildings) hadn't finished downloading.
- **The very next steps** are in §8, "M4: finish". In short:
  1. Get Site 2 buildings.
  2. Run `make data` and `make simulate` for Site 2 and debug.
  3. Build the compare UI.
  4. **Stop and present the site comparison to the user. The user confirms the pitch site; do not pick it yourself.**
- After that come M5 (8760-hour dispatch, time slider, deal room), M6 (Demo Mode plus polish), M7 (Monte Carlo reliability and what-ifs), and M8 (freeze, RESULTS.md, rehearsal).

---

## 1. Project context (read once)

### The challenge
`Context/NYU_Hackathon_Data_Center_Heat_Reuse_Challenge_R1.docx.pdf`

- Design a technically feasible, economically viable, community-centered system that captures, upgrades (heat pumps) and delivers data-center (DC) waste heat to the most suitable local users.
- Two candidate sites:
  - **Site 1**, urban, commissioned: 111 8th Ave, NYC.
  - **Site 2**, suburban, proposed: TeraWulf Lake Hawkeye, the former Cayuga power plant in Lansing NY.
- **Pitch ONE site and justify the choice.**
- Show supply/demand matching on **temperature, capacity, timing, seasonality and continuity**.
- Show that cooling reliability and heat continuity are protected.
- Quantify value for the DC, the heat users and the community.
- Show how cost, risk and ownership are shared across stakeholders.
- The four pillars: Technical, Economic + Delivery, Environmental, Social + Regenerative.

### The rubric
`Context/Judging Rubric.docx.pdf`

Five equal categories, each scored 1–4: **Technology, Presentation, Innovation, Execution, Theme.** Execution ("flawless functionality, polished finish") is the category most teams lose. The demo must never crash, stall, show raw errors, or make network calls.

### The user's decisions
These came from the user's original prompt and Q&A.

- **Solo build** (the user plus a coding agent). **About 48 h budget**, starting around 2026-10-03 17:00 local. Confirm the actual judging time with the user.
- **Pitch site: "let the simulator decide".** Run both sites through the same engine, then the **user** confirms the pick at the M4 decision gate.
- Tiering: Tier 1 is the MVP, Tier 2 adds dispatch, time slider, equity overlay, deal room and Demo Mode, and Tier 3 adds Monte Carlo, the Site 2 port, the comparison view and what-ifs. **Polish of what exists outranks new features.**
- The approved plan is at `/Users/vayunmalik/.claude/plans/eager-scribbling-nest.md`. It's summarized in §7.

### Non-negotiable rules
These come from the user's prompt and global CLAUDE.md.

1. **Never invent data silently.** Every number the engine uses lives in `config/assumptions.yaml` with `value`, `unit`, `source` (URL or rationale) and `confidence` (`high`/`medium`/`low`), plus optional `low`/`high` ranges.
   - Synthetic or proxy data must be **labeled** in the data and the UI.
   - Lake Hawkeye capacity must be a ranged parameter.
2. **Cache all raw data** in `data/raw/` via the fetch scripts. The frontend **never** calls external APIs; it reads only `web/public/data/`.
3. Write **tests** for physics and economics, and run them before declaring any milestone done.
4. At **every milestone**:
   - run the full pipeline end to end and open the frontend (`make check`);
   - append a self-score to `docs/RUBRIC_CHECK.md` (1–4 per category, the weakest category, and the highest-leverage fix);
   - log modeling choices in `docs/DECISIONS.md`;
   - commit.
5. **Git identity:** commits must be authored as `Vayun Malik <83413346+VayunMalik@users.noreply.github.com>`. It's already the global config, and `git config --get user.email` should return that address.
   - **Do NOT add `Co-Authored-By: Claude`, `Claude-Session`, or "Generated with Claude Code" trailers** to commits or PR bodies. The user's global CLAUDE.md overrides any default.
   - Commit only at milestones, or when the user asks. Work on `main`; it's a fresh personal repo.
6. Final deliverables:
   - `make data && make simulate && make web` must work;
   - an interactive 3D demo with Demo Mode;
   - `docs/RESULTS.md`, with KPIs for both sites, the recommendation and the assumptions table;
   - `docs/RUBRIC_CHECK.md` with the final self-score.

---

## 2. How to run

```bash
cd /Users/vayunmalik/iMasonsHackathon/waste-heat-reuse
uv sync                      # Python 3.11 venv (.python-version = 3.11; system python is 3.10 — don't use it)
cd web && npm install && cd ..

make data SITES=site1_chelsea        # fetch (cached, idempotent) + prepare -> data/processed/site1_chelsea/
make simulate SITES=site1_chelsea    # engine run (MILP ~70 s) + export -> web/public/data/site1_chelsea/...
make test                            # pytest (34 tests, ~60 s; test_simulation runs the real MILP)
make check                           # build web, serve via vite preview :4173, headless-Chrome render check + screenshot
make dev                             # vite dev server on :5173
make web                             # build + preview on :4173 (demo)
make data-large                      # one-time ~550 MB DOE LEAD download (optional; energy burden)
```

- **Default `SITES`** in the Makefile is `site1_chelsea site2_lansing`. Until Site 2 works, pass `SITES=site1_chelsea`.
- **`make check`** runs `web/scripts/check.mjs`, which uses `puppeteer-core` with the system Chrome at `/Applications/Google Chrome.app`. It **fails** on:
  - any non-localhost request;
  - any HTTP status ≥ 400;
  - any console error or page error;
  - the `#loading` overlay never hiding.

  It also writes a screenshot to `docs/screenshots/latest.png`. Environment variables:
  - `QUERY="?select=FULTON"` deep-links into a building detail;
  - `QUERY="?site=site2_lansing"` switches the site;
  - `OUT=path.png` sets the screenshot path.

  For a custom run, start `npx vite preview --port 4173` from `web/` first, then run `node scripts/check.mjs`. **Look at the screenshot after every UI change** (read the PNG); the check script can't see layout bugs.
- **Deep links:**
  - `?site=<id>` loads that site; the default is `site1_chelsea`.
  - `?scenario=<id>` loads that scenario; the default comes from `manifest.default_scenario`.
  - `?select=<offtaker id or exact name>` opens that building's detail, e.g. `?select=ELLIOTT%2FCHELSEA%20ADDITION`.

### Environment quirks
These cost hours, so read them before fetching anything.

- **The command sandbox blocks some hosts from Python** (Overpass got "connection refused"). If a fetch hangs or is refused from Python, retry outside the sandbox. In Claude Code that's `dangerouslyDisableSandbox: true` on the Bash call.
- **OSM / Overpass is unusable** from this machine. OSMnx hung even unsandboxed. Streets come from NYC CSCL (Site 1) and TIGER roads (Site 2). Don't reintroduce OSMnx.
- **mis.nyiso.com is flaky:** Squid 503 errors, HTTPS timeouts. The 2023 data **is cached** (`data/raw/nyiso/`). A labeled proxy fallback exists and is tested.
- **The Census ACS API now requires a key** and returns an HTML page with HTTP 200. Don't use it. `fetch()` validates payloads by extension (json/csv/zip), so HTML error pages are never cached.
- **The DOE LEAD NY zip** (552 MB, data.openei.org) downloads at about 50–110 KB/s, and several attempts died or stalled. **Never run two writers on the same `.part` file.**
  - That happened twice and corrupted the download; the partial file was deleted at handoff.
  - `fetch()` supports HTTP Range resume, and the server supports Range.
  - LEAD is **optional**: energy burden shows as null/"n/a" without it.
  - The robust way is a single curl loop, from `data/raw/doe_lead/`:
    ```bash
    until [ "$(stat -f%z NY-2022-LEAD-data.zip.part)" = "552366339" ]; do curl -s -L -C - --max-time 900 -o NY-2022-LEAD-data.zip.part https://data.openei.org/files/6219/NY-2022-LEAD-data.zip; done
    mv NY-2022-LEAD-data.zip.part NY-2022-LEAD-data.zip
    ```
    Then run `make data-large`, which extracts the AMI tract CSV and deletes the zip. Run it as a tracked background job.
- **Overture remote queries** (DuckDB over S3) take 3–10+ minutes each. Cache once and explore locally.
- **Disk:** about 19 GB free. Always clip downloads to the bounding box.

### Background processes at handoff
- **Overture Site 2 buildings query (PID ~39793/39795) may still be running.** It was started before the atomic-write fix, so it writes **directly** to `data/raw/overture/site2_lansing_building.parquet`.
  - That file was **0 bytes** at handoff.
  - If the process is gone and the file is still 0 bytes, **delete it** and re-run (command below).
  - `overture()` treats any existing file as cached. **Bug to fix:** make it check `st_size > 0`.
- The LEAD downloads were all killed and the corrupt `.part` deleted.

```bash
uv run python -c "
from heattwin.site import Site; from heattwin.data import sources as S
s=Site.load('site2_lansing'); print(S.overture(s.id,'buildings','building',s.study_area.bbox))"
# run with the sandbox disabled; takes several minutes
```

---

## 3. Repository map

```
Makefile                        data | data-large | simulate | web | dev | test | check | offline-check | all
pyproject.toml / uv.lock        deps: pandas, numpy, pyarrow, geopandas, shapely, osmnx (unused now), networkx,
                                pulp(+highspy HiGHS), CoolProp, pyyaml, pydantic, requests, rasterio, duckdb; dev: pytest
config/
  assumptions.yaml              ~600 lines. EVERY number, with provenance. Sections: policy, emissions, grid, prices,
                                supply, heat_pump, demand, network, building_interface, finance, matcher, continuity,
                                pipes, synthetic_demand, rural. Loader rejects duplicate keys (PyYAML silently drops them!)
  sites/site1_chelsea.yaml      Site 1: DC location, IT-load range, bbox, grid zone, screening exclusions, LL97 on,
                                price keys per fuel, network multiplier
  sites/site2_lansing.yaml      Site 2: TeraWulf capacity (SEC-sourced), liquid cooling, LL97 off, rural prices,
                                synthetic-demand config incl. one HYPOTHETICAL greenhouse anchor
engine/heattwin/
  assumptions.py                Assumptions.load(); a["k"] -> Assumption, a.v("k") -> float. Duplicate-key guard.
  site.py                       pydantic Site model (DataCenter, StudyArea, Grid, Weather, Screening, Policy,
                                prices dict, NetworkCfg, SyntheticCfg). Site.load(id); site.processed_dir
  scenario.py                   Scenario(cooling, it_growth, equity_weight); id like "air_g0_eq15"; BASE
  supply.py                     derive_it_load() [LL84-derived IT load for Site 1], run() -> hourly supply DataFrame
  demand.py                     shapes(), required_supply_temp(), nycha_apartments(), offtakers_from_ll84() [Site 1],
                                hourly_matrix(), validate_against_nycha_steam(), fuel_mix_for_tracts(),
                                offtakers_synthetic() [Site 2, UNTESTED]
  heatpump.py                   CoolProp R1234ze(E) cycle(); CopTable (1 K grid, bilinear)
  matcher.py                    score(): 7 dims in [0,1], total score, rank, rationale
  fuels.py                      (uncommitted) FUELS=(gas,oil,steam,propane,elecheat); price/efficiency/emission helpers
  network.py                    street_graph(), building_value(), optimize() [MILP], network_supply_temp(), pick_dn(),
                                crf(), _explain_rejections()
  economics.py                  run(design, a, site, cop_avg, grid_t) -> capex/annual/energy/kpis; npv(); payback_years()
  simulate.py                   run(site_id, scenario) -> Result (the full chain)
  export.py                     export_result() [per scenario], export_site() [manifest + layers],
                                export_compare() [uncommitted; compare.json], _clean() JSON sanitizer
  cli.py                        python -m heattwin.cli {data|simulate} <sites...>
  data/cache.py                 fetch() with cache, manifest (sha256), payload validation, Range resume; record_derived()
  data/sources.py               one function per source (see §5)
  data/fetch_all.py             fetch_site(site): required vs optional sources per adapter
  data/prepare.py               raw -> data/processed/<site>/{buildings,streets,context,tracts,hourly}.parquet + hourly_meta.json
tests/                          test_assumptions, test_cache, test_data_integrity, test_heatpump, test_network (synthetic
                                grid with known answers), test_economics (NPV vs annuity formula), test_simulation (real Site 1
                                run: energy balance, COP bounds, validation R², MILP gap, cooling-independence)
web/
  index.html                    #map + #overlay (brand, #kpis, #side, #evidence, #legend) + #loading
  vite.config.ts                worker format "es" (MapLibre worker bundled locally)
  scripts/check.mjs             headless render/offline check (see §2)
  src/main.ts                   boot: loadSite + loadScenario, MapLibre (background-only style), MapboxOverlay(deck.gl),
                                lighting, tooltips, click->select, ui store subscription, flyTo, ?select deep link
  src/data.ts                   Manifest/BuildingProps types, loadSite()
  src/results.ts                Results/Offtaker/ScenarioBundle types, DIMS + labels/help text, loadScenario()
  src/state.ts                  tiny store: ui {selectedId, tab}
  src/format.ts                 fmtInt/fmtUsd/fmtPct/fmtNum/esc/nice (title-cases ALL-CAPS LL84 names)
  src/map/layers.ts             COLORS, indexByBin(), siteLayers() [context, streets, dc-glow, pipes-glow, pipes, buildings],
                                tooltipHtml()
  src/ui/kpis.ts                6 KPI tiles (community first)
  src/ui/ranking.ts             "Who gets the heat — and why": tabs Connected / Not chosen / All ranked; rows with mini bars
  src/ui/detail.ts              building detail: facts, status box (reason), 7 dim bars, rationale, $/MWh value breakdown
  src/ui/dimbars.ts             miniBars(), fullBars()
  src/ui/evidence.ts            "How we know" card: Demand (validation SVG line chart + hover), Supply (IT-load steps),
                                Optimizer (MILP stats)
  src/style.css                 dark design tokens (:root), layout, all component styles
  public/data/                  ENGINE OUTPUT (committed, ~3 MB): sites.json, site1_chelsea/{manifest.json,
                                buildings.geojson, streets.geojson, context.geojson, air_g0_eq15/{results.json,
                                offtakers.json, network.geojson}}
docs/
  DECISIONS.md                  D1–D15 modeling/engineering decisions (pitch material)
  DATA_SOURCES.md               every source, status and fallback; notable facts
  RUBRIC_CHECK.md               self-scores M0 (6/20) -> M3 (15/20)
  screenshots/                  m1_site1_real_data.png, m3_overview.png, m3_detail_fulton.png, m3_detail_elliott.png
data/raw/ (gitignored)          cached downloads + manifest.json
data/processed/ (gitignored)    prepared per-site tables
```

---

## 4. Engine: how it works (with formulas)

### Data flow

```
config/sites/<id>.yaml + config/assumptions.yaml
   │
   ├─ data: fetch_site() → data/raw/…   then prepare() → data/processed/<id>/{buildings,streets,context,tracts,hourly}.parquet
   │
   └─ simulate.run(site_id, Scenario):
        supply.derive_it_load  → it (MW, with steps for UI)
        supply.run             → hourly it_load_mw, q_src_mw (recoverable), q_total_heat_mw, t_src_in/out
        demand.offtakers_*     → offtakers (one row per LL84 property / cluster) + screened_out (with reasons)
        demand.hourly_matrix   → M (n_offtakers × 8760, MW_th)
        matcher.score          → ranked (s_<dim>, total_score, rank, rationale, eligible)
        network_supply_temp    → t_net[h] (outdoor reset 65→80 °C) ; cop_h = CopTable(t_src_out, t_net+approach)
        cop_avg = demand-weighted mean(cop_h) ; cop_design = COP at 80 °C
        cands = top 50 by score ∪ top 20 by heat (eligible only)
        network.building_value → per-building $/MWh value stack
        network.optimize       → Design(connected, rejected+reasons, pipes, hp_mw, stats incl. mip_gap)
        economics.run          → capex / annual flows / energy balance / KPIs
        demand.validate_against_nycha_steam (Site 1 only)
   └─ export_result / export_site / export_compare → web/public/data/
```

### Key models

- **IT load, Site 1 (D7).** Taken from LL84 2023 for BBL 1007390001.
  - 505.3 GWh/yr of electricity, a **57.7 MW** average.
  - Minus an office baseline: the median of 255 Manhattan offices >500k ft² (**37.7 kWh/ft²** × 2.33M ft²), which is **10.0 MW**.
  - That leaves **47.7 MW** of DC load. Dividing by PUE 1.5 gives **31.8 MW IT** (range 24.5–36.7, from the p50/p90 baseline and PUE 1.3–1.7).
- **IT load, Site 2.** From config: 115 MW IT (138 MW Phase I ÷ PUE 1.2), up to 333 (400 MW ÷ 1.2). Source: TeraWulf SEC 8-K, ex. 99.1.
- **Supply.**
  - IT load: `it = it_mw·(1+growth)·(1+0.04·sin(2π(h−9)/24))`.
  - Recoverable heat: `q_src = it·capture`, with capture 0.85 for air cooling and 0.75 for liquid.
  - Return temperature: 30 °C for air, 50 °C for liquid. The HP evaporator cools it by 8 K.
- **Heat pump.** A single-stage CoolProp cycle on R1234ze(E), with η_is 0.70, 3 K approach, 5 K superheat and 2 K subcool.
  - Source 22 °C to sink 75 °C: COP 3.20, 54% of Carnot.
  - Source 42 °C to sink 75 °C: COP 5.10.
- **Demand, Site 1 (measured).**
  - Starts from LL84 fuel per footprint. Footprints get a volume-weighted share of their lot or campus, and **each BBL is assigned to at most one LL84 property (largest GFA first)**, so campus umbrella rows aren't double counted.
  - Useful heat = fossil × fraction-to-heat (0.92 residential / 0.95 commercial) × boiler efficiency (gas 0.80, oil 0.78), plus steam × 0.85.
  - DHW share is 0.28 for residential and 0.08 for commercial.
  - Hourly space heat follows a degree-hour shape with a 16 °C balance point; commercial gets a 0.6 night and weekend setback. DHW follows an ASHRAE-style diurnal profile.
  - **Validated against Fulton Houses' metered Con Ed steam bills: monthly R² 0.975, annual 23,502 vs 22,827 MWh.**
- **Screening (D11).** Every excluded building is kept with its reason:
  - named exclusions: Penn South CHP, NYU CoGen, and the DC itself;
  - a fossil-intensity cap of 200 kBtu/ft²;
  - a **cogeneration signature**: grid electricity <30% of the peer median *and* fossil fuel >2× the peer median (this catches PENN 1);
  - a minimum of 300 MWh/yr.
- **NYCHA apartment counts** come from the NYCHA Development Data Book: Fulton 944, Elliott 608, Chelsea 425, Chelsea Addition 96. PLUTO undercounts these.
- **Matcher.** Seven dimensions, each in [0, 1]:

  | Dimension | How it's scored |
  |---|---|
  | temperature | COP at the demand-weighted required supply temperature, normalized between 85 °C and 50 °C sinks; ×0.85 if the building needs a steam conversion |
  | capacity | `log(heat/300)/log(20000/300)` |
  | timing | min–max normalized load factor |
  | seasonality | summer/annual ratio relative to the max |
  | continuity | occupant-type rubric |
  | proximity | `1 − d/1500 m` |
  | equity | NYCHA = 1, else tract SVI |

  Weights are 1 each, except equity at 1.5 (the scenario's `equity_weight`).
- **Value per MWh delivered (`network.building_value`).**
  - Plus: avoided fuel cost (each fuel's price ÷ efficiency, blended by fuel mix).
  - Minus: HP electricity (`price / cop_avg / (1−0.06 loss)`).
  - Plus: **DC cooling avoided** (`(1−1/COP)/(1−loss)·elec/4.0`).
  - Plus: LL97 (avoided tCO2e × $268 × 0.75 capture; **0 for NYCHA** because of its separate compliance path; only where the site has `policy.ll97`).
  - Plus: carbon value (default $0/t).
  - Plus: an **equity shadow price** (`equity_weight × $10/MWh × s_equity`). This shapes the design but is **excluded from cash NPV**.
  - Delivered heat = 0.92 × building heat (`hp_energy_coverage`). The interface is sized at 0.6 × peak (`hp_peak_coverage`); existing boilers and steam remain as peak and backup supply.
- **MILP (`network.optimize`, D14).** A fixed-charge, single-commodity flow on the street graph. Snapped nodes are within 1 m, and only the largest connected component is used.
  - **Variables:** y_k (connect building k), x_e (build pipe on edge e), flows on both directions of each edge, and hp ≤ HP_max.
  - **HP_max** = `q_src_firm·cop_design/(cop_design−1)`.
  - **Pipe cost** is a linear fit of the DN table: `3600 + 90·MW` $/m, × the site multiplier.
  - **Objective (maximize):** `Σ y_k(V_k − CRF·conn_capex_k) − Σ_e CRF·len·(fixed·x_e + var·flow) − (CRF+O&M)·c_hp·hp`.
  - **Big-M** is `min(DN500 capacity, HP_max)`. A valid inequality requires `y_k ≤ Σ incident x`.
  - Solved with HiGHS at a 0.5% relative gap and a 120 s time limit. Site 1 takes about 70 s on 731 binaries.
  - Pipes are then re-costed using the actual DN table.
  - **Rejection reasons** price the full marginal cost of each skipped building: new main from the *built* network (multi-source Dijkstra), trunk upsizing from the source, HP capacity, and connection.
- **Economics.**
  - Capex adds 25% soft costs. Discounting uses the 6% design rate over 25 years.
  - LCOH = `(CRF·capex + elec + O&M − DC savings)/E`.
  - CO2 is computed with physical EPA factors and the annual-mean NY grid intensity from EIA-930.
  - Water saved = recovered heat × 1.47 m³/MWh, assuming evaporative heat rejection. **That assumption is unverified for 111 8th Ave**, so label it.

### Site 1 base results (committed scenario `air_g0_eq15`)

| | |
|---|---|
| Buildings / homes | 14 buildings, **3,157 homes**, of which **944 NYCHA** (Fulton) |
| Heat to high-vulnerability homes | **80–82%** |
| CO2e avoided | **13,127 t/yr** |
| LL97 penalties avoided | $1.34M/yr |
| HP / COP | 26.2 MW HP, COP avg 3.28 (range 2.7–3.7) |
| Network | 2.2 km of pipe |
| DC heat reused | 23% |
| Capex | **$56.2M** (pipes $12.6M, HP $29.5M, connections $14.1M) |
| System economics | net **$3.48M/yr**; **System NPV −$11.7M** (6%, 25 yr); payback 16 yr; LCOH $94/MWh |

- The negative NPV is an honest result: NYC gas is cheap and retail electricity is 18¢/kWh.
- **Pitch framing:** the system is socially positive (13 kt CO2e/yr, at about $190/t SCC worth +$2.5M/yr) but needs public or community capital. The deal room (M5) must show which ownership model or policy makes it bankable.
- **Elliott-Chelsea (704 NYCHA homes) is NOT connected.** Its cost to serve is about $473k/yr against $303k/yr of value. The ~$170k/yr gap is the deal-room climax: show it getting connected under municipal financing or a higher equity weight.

---

## 5. Data sources

| Source | Function | Status |
|---|---|---|
| NYC Building Footprints `5zhs-2jue` | `nyc_footprints` | ✅ cached |
| MapPLUTO `64uk-42ks` | `nyc_pluto` | ✅ |
| LL84 2023 `5zyy-y8am` | `nyc_ll84` (Manhattan) | ✅ |
| NYC CSCL streets `inkn-q76z` | `nyc_cscl` | ✅ |
| NYC Parks `enfh-gkve` | `nyc_parks` | ✅ |
| NYCHA Data Book `evjd-dqpz` | `nycha_databook` | ✅ |
| NYCHA steam bills `smdw-73pj` | `nycha_steam(2023)` | ✅ |
| CDC SVI 2022 NY | `cdc_svi_ny` | ✅ |
| Census tracts | `census_tracts_ny` | ✅ |
| TIGER roads / area water | `tiger_roads(fips)` / `tiger_areawater(fips)` | ✅ (061, 109) |
| Open-Meteo 2023 | `open_meteo` | ✅ Site 1. ⚠️ Site 2 file not fetched yet (`make data` will fetch it) |
| EIA-930 NYIS 2023 | `eia930_nyis` | ✅ |
| NYISO DAM LBMP 2023 | `nyiso_dam_lbmp` | ✅ cached (server flaky) |
| Overture places (Site 2) | `overture(...,'places','place',bbox)` | ✅ |
| Overture buildings (Site 2) | `overture(...,'buildings','building',bbox)` | ⏳ in progress / 0-byte file |
| DOE LEAD NY | `doe_lead_ny_tract` | ❌ not downloaded (see §2) |

### Verified facts, with sources
These are also in `assumptions.yaml`.

- **Prices (2023):**
  - NY commercial gas $9.59/Mcf, residential $16.90/Mcf (EIA).
  - NY commercial electricity 18.01¢/kWh, residential 22.24¢/kWh (EIA EPA Table 2.10).
  - Fulton's real steam price $21.3/MMBtu (NYCHA bills).
  - Propane $3.35/gal and heating oil $4.685/gal, averaging the two winters bracketing 2023 (EIA weekly XLS series).
  - 2023 day-ahead LBMP: Zone J $35.43/MWh, Central $28.30/MWh (Potomac Economics SOM report, Fig. A-2).
- **RECS 2020 CE3.2, Northeast** (verified from the PDF): single-family detached homes use 68.6 MMBtu/yr for space heating and 18.3 for water heating; apartments in 2–4 unit buildings use 32.2 and 16.7.
- **TeraWulf (SEC 8-K, Aug 2025):** "up to 400 MW", 138 MW in 2026, power "below $0.05/kWh", 183 acres.
- **[Ithaca Voice, Sep 2025](https://ithacavoice.org/2025/09/environmentalists-sound-alarm-as-plan-to-convert-cayuga-power-plant-to-data-center-advances/):** evaporative cooling using Cayuga Lake water; noise concerns; "Lansing will get far more costs than benefits." That last line is the community-acceptance hook for Site 2.
- **Penn South** has run its own cogeneration since 1986 (pennsouth.coop). A NYSERDA community heat-pump study of Penn South exists and is worth citing.

### Not yet verified (marked low confidence)
School heating intensity (45 kBtu/ft²), greenhouse intensity (400 kWh/m²), the upstate commercial electricity price (13¢), the rural pipe multiplier (0.40), and the rural fuel-mix fallback shares.

---

## 6. Frontend: how it works

- **Map:** MapLibre with a **background-only style**, so there's no tile server. A deck.gl `MapboxOverlay` (non-interleaved) carries the GeoJSON layers.
  - The MapLibre worker is bundled through `?worker&url` plus `setWorkerUrl`. **Don't remove this.** Without it the production build tries to load a 404 worker.
  - `#overlay` has `z-index: 10`. Without that, the deck canvas draws over the panels; that was a real bug.
- **Colors (validated with the dataviz skill's validator):**
  - DC orange `#ff6b35`, connected amber `#f2b134`, not chosen violet `#9d6bd8`, NYCHA teal `#40c4aa`, other slate.
  - Chart series: blue `#3987e5` (metered), orange `#d95926` (modeled).
  - Value bars: positive `#3987e5`, negative `#e66767`.
  - These hues failed only the lightness-band check, which targets flat marks; they fill shaded 3D extrusions. Identity is never carried by color alone (there's a legend, tooltips and chips).
- **State:** `ui` store `{selectedId, tab}`. When `selectedId` changes, the side panel switches to the detail view, the buildings layer recolors (selected = white), and the map flies to the building.
- **Everything is driven by `results.json` and `offtakers.json`.** No numbers are hardcoded in the UI, except some explanatory copy in `detail.ts`:
  - "18.0¢/kWh…" and "$268/tCO₂e × 75%…" **must become data-driven or site-aware** for Site 2 (§9).
- **Site 2 in the UI hasn't been tested.** Expect Site 1 assumptions in the copy: NYCHA/LL97 KPI tiles and the "Fulton" validation claim. The evidence tab already handles missing validation and missing IT-load steps.

---

## 7. Milestone plan and status

| # | Planned hours | Deliverable | Status |
|---|---|---|---|
| M0 | 0–2 | Scaffold, offline map, check script | ✅ `5e416ae` |
| M1 | 2–7 | Site 1 data pipeline and 3D map | ✅ `ff32ec4` |
| M2 | 7–12 | Tier 1 engine | ✅ `1b58a22` |
| M3 | 12–16 | Tier 1 demo UI | ✅ `a1fb69b` |
| M4 | 16–21 | Site 2 lite, comparison, **decision gate (user confirms the site)** | 🟡 WIP, uncommitted |
| — | ~21–27 | Sleep / buffer | |
| M5 | 27–33 | Tier 2: 8760 dispatch, time slider and presets, equity overlay, deal room | ⬜ |
| M6 | 33–38 | Demo Mode (8 scripted steps), then a polish pass | ⬜ |
| M7 | 38–43 | Tier 3: Monte Carlo reliability, what-if sliders, compare polish, terrain if Site 2 wins | ⬜ |
| M8 | 43–48 | **Feature freeze at H43.** RESULTS.md, final RUBRIC_CHECK, wifi-off rehearsal ×3, bug fixes only | ⬜ |

**Cut order if behind** (polish beats features):
1. what-if sliders
2. Monte Carlo (fall back to 3 deterministic stress scenarios)
3. the losing site's 3D view (keep the comparison table)
4. the ambient-loop topology option

**Demo Mode and the deal room are never cut.**

Rubric self-score after M3: **15/20** (Technology 3, Presentation 3, Innovation 3, Execution 3, Theme 3). The planned lift to 4s comes from: the comparison plus deal room (Innovation and Theme), Demo Mode (Presentation), the time slider with visibly changing COP (Technology), and zero-defect polish (Execution).

---

## 8. Remaining work, step by step

### M4: finish (start here)

**Uncommitted WIP already written (tests pass):**
- `fuels.py`, a shared fuel table.
- Generalized `building_value` and `economics.run`, which now take `site`.
- Per-site `prices`, `policy.ll97` and `network.pipe_cost_multiplier_key`.
- Site 2 config.
- Site 2 adapter code:
  - `prepare.build_upstate_buildings`, `build_tiger_streets` and `build_water_context`;
  - `demand.offtakers_synthetic` and `fuel_mix_for_tracts`.
- An `overture()` source (DuckDB), with the atomic `.part` write.
- New assumptions: verified propane, oil and residential prices; propane emission factor; `synthetic_demand.*`; `rural.*`; and `heat_pump`/network updates.
- `export_compare()` and `COMPARE_KPIS`, plus manifest labels `demand_source`/`data_quality` and `default_scenario` derived from the cooling type.
- CLI changes: `simulate` picks the scenario from the site's cooling type and writes `compare.json`.
- Matcher continuity now recognizes "Residential/Civic/School".

**Steps:**
1. **Commit the WIP first**, as e.g. "M4 WIP: site-agnostic fuels/prices + Site 2 adapter (untested)", once you've confirmed tests are green. Respect the git rules in §1.
2. **Get the Overture buildings** (§2). Fix `overture()` to treat 0-byte files as missing. **Inspect the real schema** before running the adapter:
   `uv run python -c "import pandas as pd; d=pd.read_parquet('data/raw/overture/site2_lansing_building.parquet'); print(d.columns.tolist()); print(d['class'].value_counts().head(30)); print(d['subtype'].value_counts())"`
   The adapter *guesses* the columns `id, names, class, subtype, height, num_floors`. Adjust `RES_CLASSES`, `SCHOOL_CLASSES`, `CIVIC_CLASSES` and `UNHEATED` in `prepare.py` to the actual values.
3. **Fix the across-the-lake problem before running.** Cayuga Lake separates the plant (east shore) from Trumansburg and Interlaken (west shore, Seneca County 099).
   - The bounding box includes the west shore, but roads come only from Tompkins (109). West-shore buildings would snap to an east-shore road node with an enormous service line.
   - **Fix:** keep only buildings whose centroid falls in a Tompkins tract (`GEOID.notna()` after `_attach_tracts`, which only loads county-109 tracts), and/or narrow the bounding box to about `[-76.66, 42.50, -76.48, 42.66]`.
   - Also, `network._nearest_nodes` builds a dense n×m distance matrix, which is fine at Site 1 scale. With thousands of rural nodes and clusters it may be heavy; use a KD-tree (`scipy.spatial.cKDTree` or shapely STRtree) if needed.
4. `make data SITES=site2_lansing` fetches Open-Meteo for Site 2, the TIGER roads and Overture, then prepares. Then run `make simulate SITES="site1_chelsea site2_lansing"`. **Expected issues to check:**
   - The TIGER road graph might be large or disconnected; `street_graph` keeps only the largest component. Check that the DC node is near the plant: the CRF/MILP needs `src` near the DC.
   - The MILP may get large with many cluster candidates. The candidate cap is 50 + 20, but the graph size drives solve time. Consider pruning the graph to roads within about 6 km of the DC.
   - `offtakers_synthetic` defines `MWH_PER_MMBTU_` at the **bottom** of `demand.py`. That works at call time but is ugly; move it to the top or import `fuels.MWH_PER_MMBTU`.
   - Site 2 has no LL84/NYCHA validation, so `validation` is `{}` and the frontend handles that.
   - The hypothetical greenhouse must stay **labeled** in data and UI. It sets `ll84_type = "HYPOTHETICAL anchor"` and carries a `note`; export the note and show a badge.
   - The capacity score caps at 20,000 MWh; the greenhouse is about 16 GWh.
   - Liquid cooling gives a 50 °C return and 42 °C at the evaporator outlet, so COP should be around 5.
   - Check sanity: homes served, $/MWh value (avoided costs are propane and oil heavy, around $45/MWh useful), the 0.40 pipe multiplier.
5. **Add the Site 2 KPI**: the water-saved story. Lake water not evaporated is already in KPIs as `water_saved_m3_per_yr`; show it on both sites, labeled. Add Site 2 hourly via `prepare.build_hourly`; it uses EIA-930 statewide carbon, which you should note.
6. **Frontend site support:**
   - **A site switcher** in the header (Site 1 / Site 2), which reloads with `?site=`.
   - **A "Compare sites" view.** Use a modal or full-panel overlay that reads `/data/compare.json`.
     - Show the same KPIs side by side, grouped community → climate → technical → economic, with a "better" marker per row.
     - Show a data-quality badge per site: measured vs synthetic.
     - Show a recommendation sentence. **Write it only after the user confirms the site.**
     - Use the dataviz skill for any chart (paired bars per KPI, one axis per KPI; never dual-axis).
   - **Site-aware copy:**
     - KPI tiles: hide the LL97 tile when the site has no LL97 (add `policy.ll97` to the manifest) and replace it with "Lake water saved".
     - The NYCHA sub-label should become generic: "public housing" vs none.
     - `detail.ts` value-row hover sources must come from data, not hardcoded "18.0¢/kWh"/LL97 text.
     - Add a **"SYNTHETIC DATA"** badge when `manifest.labels.data_quality === "synthetic"`.
7. **DECISION GATE.**
   - Present both sites' numbers to the user in chat: homes, high-vulnerability share, tCO2e, water, DC heat reused, NPV, LCOH and data quality, with your recommendation and reasoning.
   - **Wait for the user to confirm.** Record the choice in DECISIONS.md.
   - Expected, though verify with the numbers: Site 1 wins on community value (NYCHA, measured data, validation) and data quality. Site 2 has far more heat but sparse demand, and its best use may be co-located agriculture. Site 2's community-acceptance story (lake water, opposition) is strong.
8. Run `make check` for both sites (`QUERY="?site=site2_lansing"`), add the RUBRIC_CHECK M4 entry and DECISIONS entries (Site 2 synthetic method, the lake-crossing filter, etc.), and commit.

### M5: Tier 2

1. **`engine/heattwin/dispatch.py`: an 8760-hour LP** (PuLP + HiGHS, about 9 variables per hour, solves in seconds) on the fixed design:
   - Per hour: `hp_q[h] ≤ hp_mw`; `hp_q[h]·(1−1/COP_h) ≤ q_src[h]`; storage `soc[h+1] = soc[h]·(1−self_loss) + ch[h] − dis[h]` with `soc ≤ cap`; `hp_q + dis − ch + boiler[h] + unmet[h] = D[h]/(1−loss)` (D = sum of connected buildings' hourly demand × coverage logic); and `boiler[h] ≤` the buildings' existing capacity (≈ peak).
   - **Cooling independence:** `dc_reject[h] = q_total[h] − hp_q[h]·(1−1/COP_h) ≥ 0`. Dry coolers or towers stay 100% sized; assert it in a test.
   - Objective: minimize `Σ elec_price[h]·hp_q/COP_h + boiler fuel cost + big·unmet`.
   - Hourly electricity price = `LBMP[h] + (retail_avg − mean LBMP)`. Hourly carbon comes from `hourly.grid_tco2_per_mwh`.
   - Thermal storage size: sweep 0/50/100/200 MWh and pick the best, or add it as an LP variable with linear capex. Add assumptions (tank capex $/MWh, self-loss) with sources.
   - **Replace `network.hp_energy_coverage`** (0.92, an assumption) with the dispatch result, then re-run economics.
   - Tests: the energy balance closes every hour; COP stays within bounds; all flows ≥ 0; `dc_reject ≥ 0` every hour.
2. **Export hourly arrays** compactly: Float32 `.bin` files or rounded JSON per scenario. Include `t_out, cop, t_net, hp_q, boiler, soc, unmet, served_frac` per connected building (14 × 8760 is fine), plus price and carbon. Also export a per-hour DC heat output.
3. **Time slider UI:**
   - an 8760-hour scrubber with play/pause and a speed control;
   - presets: **coldest week** (early Feb 2023, when NYC hit −16.5 °C on Feb 4), **summer night**, **outage event**;
   - buildings colored by the % of demand met that hour (amber → gray), pipes colored by supply temperature, DC glow scaled by output;
   - a small readout: hour, outdoor temperature, COP (visibly varying, which is the Technology rubric), and the HP/boiler split.
4. **Equity overlay:** export the tracts GeoJSON with SVI and energy burden, as a toggleable choropleth (sequential single hue) under the buildings.
5. **Deal room (`ui/dealroom.ts` and `engine/heattwin/dealroom.py`):** four ownership models (data-center-owned, utility/ESCO, community co-op, municipal).
   - Per model: who pays capex, discount rate (private 8%, public 4%, co-op?), electricity price (Site 2 DC-owned can use TeraWulf's <5¢/kWh, sourced; Site 1 commercial), heat-price discount to customers (0–30%), and risk allocation (demand risk, price risk, DC outage risk), as text plus a matrix.
   - Per stakeholder (DC, operator, customers, NYCHA/community, city): capex, opex, revenue, NPV, payback; plus LCOH, tCO2e, LL97 avoided, and households in high-vulnerability tracts.
   - Precompute in Python, or recompute in TS from exported annual cash flows; both are cheap and linear.
   - **Climax:** show the Elliott-Chelsea gap of ~$170k/yr closing under municipal financing or a higher equity weight. Precompute scenarios `equity_weight` ∈ {0, 1.5, 3.0} and check whether Elliott connects; if not, compute the subsidy needed.
6. Run the RUBRIC_CHECK, update DECISIONS, and commit.

### M6: Demo Mode and polish

- A **Demo Mode** button giving a scripted 3–4 minute walkthrough. It's button-driven, with Next/Prev controls and keyboard arrows, camera `flyTo`, and short captions. It must work offline and never depend on timing races.
- Eight steps:
  1. The problem (DC heat wasted; Chelsea's carbon and energy burden).
  2. The site comparison: same engine, both sites, and why we picked the winner.
  3. The chosen site (fly to the DC; IT-load derivation).
  4. Who gets the heat and why (ranking, Fulton detail, Elliott "not chosen" reason).
  5. Cold-week playback (time slider preset; COP drops, boilers back up).
  6. Outage stress test (heat continuity from storage and boilers; DC cooling never depends on offtake).
  7. The deal room (ownership toggle; the NYCHA gap closes).
  8. KPIs and the ask.
- Each step sets `ui` state, the map camera, panel visibility and the slider hour. Put the script in `web/src/demo/script.ts` as data.
- Polish: loading states everywhere, consistent tokens, empty states, no layout shifts, keyboard focus, responsive down to about 1280 px wide, and the presenter's screen resolution (ask the user).

### M7: Tier 3

- **Monte Carlo (`reliability.py`)**, with about 2,000 draws and a fixed seed. Use a fast rule-based dispatch, not the LP.
  - Failure modes: DC outage/derate (MTBF/MTTR assumptions with sources), HP trip with N+1 modules, pipe break, and summer demand collapse (dry coolers reject 100%).
  - Report: the distribution of unmet heat hours, P(any cooling impact) = 0 by construction (verified), and per-mode statistics. Show it as a panel with a histogram (dataviz skill).
- **What-if sliders:**
  - Structural scenarios are precomputed: cooling {air, liquid} × IT growth {0, 0.5, 1.0} × equity {0, 1.5, 3.0} for the chosen site. That's about 18 MILP runs at ~70 s, roughly 20 minutes offline.
  - Carbon price and grid decarbonization are recomputed client-side; they're linear in the exported arrays.
- Polish the comparison view. If Site 2 wins, add 3D terrain from a USGS 3DEP DEM (TNM API reachable) via a local terrain PNG and deck.gl `TerrainLayer`.

### M8: Freeze

- `docs/RESULTS.md`: KPIs for both sites, the recommendation with justification, and the assumptions table generated from `assumptions.yaml` (write a small script).
- Final RUBRIC_CHECK.
- A clean-clone test of `make data && make simulate && make web` using cached raw data.
- Rehearse Demo Mode three times with **wifi off**.

---

## 9. Known issues and tech debt

1. `sources.overture()` treats a 0-byte file as cached. Check the size.
2. `demand.MWH_PER_MMBTU_` is defined at the bottom of the module. Consolidate on `fuels.MWH_PER_MMBTU`.
3. `network._nearest_nodes` builds a dense matrix (O(n·m) memory). Use a KD-tree for Site 2.
4. UI copy hardcodes Site 1 specifics: `detail.ts` value-row tooltips (18.0¢/kWh, the LL97 75% text), `kpis.ts` (LL97 tile, NYCHA sub-label) and `evidence.ts` (Fulton wording; this one is data-driven but phrased for NYCHA).
5. The water-saved KPI assumes evaporative heat rejection at Site 1. Not verified for 111 8th Ave; label it or turn it off for Site 1.
6. Grid carbon is the statewide annual mean (EIA-930 NYIS) in economics. M5 should use hourly values. Upstate is cleaner than the statewide mix, which is conservative for Site 2's HP emissions but overstates them.
7. `matcher` timing and seasonality are near-identical for all residential buildings, because every building shares the same two shapes. They mainly separate residential from commercial. Acceptable, but don't oversell it.
8. `RUBRIC_CHECK`/`DECISIONS` haven't been updated for the M4 WIP. Add D16+: fuels refactor, Site 2 synthetic method, TeraWulf capacity sourcing, the lake-crossing filter, and the propane/oil price verification that **corrected heating oil from an unverified $30 to a verified $33.8/MMBtu**.
9. `pyproject.toml` still lists `osmnx`, which is unused. Harmless; remove if desired.
10. The deprecation warnings from PuLP 3.3 (`LpVariable.dicts`) are filtered in pytest config. Harmless.
11. `docs/screenshots/latest.png` is overwritten by every `make check`. Copy milestone screenshots to named files.
12. Memory notes for future agent sessions live at `/Users/vayunmalik/.claude/projects/-Users-vayunmalik-iMasonsHackathon-waste-heat-reuse/memory/` (project status and network quirks). Update the status line there after milestones.

---

## 10. Pitch storyline (so far)

1. **Problem:** 111 8th Ave dumps about 27 MW of heat. One block away, Fulton Houses (944 NYCHA homes, 1,809 residents) buys **$2.1M/yr** of Con Ed steam.
2. **We know the numbers:**
   - IT load derived from the building's own disclosure.
   - Demand validated against real bills (R² 0.975).
   - Every assumption sourced.
3. **The optimizer chooses** 14 buildings, and 80% of the heat goes to high-vulnerability homes. It also explains every building it skips.
4. **Honest economics:** 13 kt CO2e/yr avoided and $1.3M/yr of LL97 penalties avoided, but a −$11.7M NPV on private capital. The deal room shows the ownership model and policy that make it work, and connects Elliott-Chelsea too.
5. **Reliability:** the DC's cooling never depends on offtake; existing boilers and steam back up the heat. To be quantified with Monte Carlo.
6. **Why this site and not Lake Hawkeye:** the same engine run on both (M4). Site 2 has 4× the heat but sparse rural demand, synthetic data, and a lake-water and community-acceptance story.
