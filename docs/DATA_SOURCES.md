# Data sources

Every raw file is cached in `data/raw/<source>/`. `data/raw/manifest.json` records each file's URL, query parameters, fetch time, size and SHA-256. The frontend reads only files bundled under `web/public/data/` and makes no network calls at demo time.

| Source | Used for | Site | Status (2026-10-03) | Fallback |
|---|---|---|---|---|
| NYC Building Footprints `5zhs-2jue` | 3D footprints, roof heights | 1 | ✅ 5,532 footprints | — |
| NYC MapPLUTO `64uk-42ks` | Residential units, owner (NYCHA), building class, floor area | 1 | ✅ | — |
| NYC LL84 Benchmarking 2023 `5zyy-y8am` | Annual gas, steam, oil and electricity per property, plus the DC's IT-load derivation | 1 | ✅ 12,083 Manhattan rows → 1,304 footprints matched | — |
| NYC Street Centerline (CSCL) `inkn-q76z` | Pipe routing graph | 1 | ✅ 807 segments | — |
| NYC Parks Properties `enfh-gkve` | Map context | 1 | ✅ | Omitted |
| Census TIGER/Line 2022 (tracts, area water, roads) | Tract geometry, water, Site 2 roads | 1, 2 | ✅ | — |
| CDC/ATSDR SVI 2022 (NY tracts) | Social vulnerability, households, poverty, housing-cost burden | 1, 2 | ✅ | — |
| DOE LEAD 2022 (NY, AMI × tract) | Energy burden, average income | 1, 2 | ⏳ ~550 MB, slow link, `make data-large` | Energy burden shown as "n/a" |
| Open-Meteo archive (ERA5) 2023 | Hourly weather | 1, 2 | ✅ | — |
| EIA-930 BALANCE 2023 (NYIS) | Hourly generation by fuel → grid carbon intensity | 1, 2 | ✅ 8,760 h | — |
| NYISO DAM zonal LBMP 2023 | Hourly electricity price | 1, 2 | ✅ (server intermittently unreachable) | Labeled proxy: EIA-930 load shape scaled to the Potomac Economics 2023 SOM zonal average |
| Potomac Economics 2023 NYISO SOM report | Published zonal average prices, used for the proxy calibration and as a cross-check | 1, 2 | ✅ | — |
| ~~OSM via Overpass~~ | ~~Streets~~ | — | ❌ connections refused or hung from the build host | Replaced by CSCL and TIGER (D5) |
| ~~Census ACS API~~ | ~~Tract demographics~~ | — | ❌ now requires an API key | Replaced by SVI's embedded ACS fields (D6) |

## Notable facts pulled from the data (pitch material)
- **111 8th Ave** (LL84 2023, BBL 1007390001): 505.3 GWh/yr of electricity, a 57.7 MW average, and a site EUI of 233 kBtu/ft². From this we derive 24–37 MW of IT load (D7).
- **Fulton Houses (NYCHA)**, about one block from the DC: 932k ft² and 94.3 billion Btu/yr of Con Ed district steam, about 27.6 GWh_th. That's roughly 4,240 tCO2e/yr at the LL97 steam coefficient.
- **Elliott / Chelsea Addition (NYCHA):** 51.9 billion Btu/yr of gas. **Chelsea (NYCHA):** 19.8 billion Btu/yr of gas.
- 2023 NYC Zone J day-ahead LBMP averaged $33.95/MWh (simple mean of the fetched data), consistent with the SOM report's load-weighted $35.43/MWh.
