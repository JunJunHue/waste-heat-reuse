# Rubric self-check

Rubric: 5 equal categories × 1–4 points (max 20). Updated at every milestone.

## M0 — scaffold (2026-10-03)
| Category | Score | Reasoning |
|---|---|---|
| Technology | 1 | Toolchain proven (HiGHS MILP, CoolProp, deck.gl), but nothing modeled yet |
| Presentation | 1 | Dark map with a placeholder DC marker |
| Innovation | 1 | Approach is designed but not visible yet |
| Execution | 2 | Builds cleanly. Headless check enforces no external requests and no console errors |
| Theme | 1 | No community outcomes yet |
| **Total** | **6/20** | |

**Weakest:** Theme, Technology and Presentation are tied, because nothing is built yet.
**Highest-leverage next fix:** M1–M3. Get real Site 1 buildings, NYCHA and SVI on the map fast, so community value shows up from the first demoable build.

## M1 — Site 1 real data on the map (2026-10-03)
| Category | Score | Reasoning |
|---|---|---|
| Technology | 2 | Reproducible, provenance-tracked pipeline joining 10 public datasets, with volume-weighted apportionment and campus-level de-duplication. Still no modeling |
| Presentation | 2 | Real 3D Chelsea with the DC glowing and the NYCHA campuses highlighted. There's no narrative or panels yet |
| Innovation | 2 | IT load derived from the building's own LL84 disclosure is a creative, defensible move. It isn't visible in the UI yet |
| Execution | 3 | Pipeline is idempotent with fallbacks, 9 tests pass, and the headless check is clean (no external requests, no errors). Payload validation guards against cached error pages |
| Theme | 2 | NYCHA highlighted and SVI attached to every building, but no community outcome is quantified yet |
| **Total** | **11/20** | |

**Weakest:** Technology and Theme are tied, because nothing is simulated yet.
**Highest-leverage fix:** M2. The matcher must make the equity weighting explicit (NYCHA campuses ranked with per-dimension reasons), and the MILP must select buildings visibly. That moves Technology and Theme together.

## M2 — Tier 1 engine (2026-10-04)
Base result (Site 1, air-cooled, today's IT load, equity weight 1.5):
- 14 buildings, 3,157 homes (944 NYCHA)
- 82% of heat goes to high-vulnerability households
- 13,100 tCO2e/yr avoided; $1.34M/yr LL97 penalties avoided
- System NPV −$11.7M at 6%; LCOH $94/MWh

| Category | Score | Reasoning |
|---|---|---|
| Technology | 3 | CoolProp cycle model, MILP on the real street graph (0.5% gap), demand validated against metered bills (R² 0.975), data-derived IT load. Not yet visible in the UI, which caps the score at 3 |
| Presentation | 2 | Results exist only as JSON. The map has no panels yet |
| Innovation | 3 | Cogeneration-signature screening, the DC-cooling value stream, and the equity shadow price as an explicit lever are all distinctive |
| Execution | 3 | 34 tests pass (energy balance, flow conservation, hand-checked NPV, COP bounds, validation). The pipeline is reproducible |
| Theme | 3 | Equity is built into both matcher and MILP; 82% of heat reaches high-vulnerability households. Not visible yet |
| **Total** | **14/20** | |

**Weakest:** Presentation.
**Highest-leverage fix:** M3. Put the ranking (per-dimension bars), the chosen-vs-rejected-with-reasons view, pipes and the KPI strip on screen. Make the negative-NPV finding a story ("what it takes to make this bankable") rather than something to hide.

## M3 — Tier 1 demo (2026-10-04)
| Category | Score | Reasoning |
|---|---|---|
| Technology | 3 | The sophistication is now visible: 7-dimension fit fingerprints, MILP stats (731 binaries, 0.5% proven gap), the COP range, the IT-load derivation steps, and the validation chart against metered bills. Still missing is anything time-varying (no 8760 playback yet) |
| Presentation | 3 | A clear and professional layout, with community KPIs first and a "How we know" evidence card. Every building is explained by fit bars, a $/MWh value breakdown, and a quantified reason when it isn't chosen. No guided narrative yet |
| Innovation | 3 | The data-derived IT load, the validation against real bills, and quantified rejection reasons are all visible. The site comparison and deal room aren't built yet |
| Execution | 3 | Offline, no console errors, loading and error states, deep links. 34 tests pass |
| Theme | 3 | NYCHA is visible on the map and in the KPIs (944 NYCHA homes; 80% of heat to high-vulnerability homes). The Elliott-Chelsea gap (704 NYCHA homes, ~$170k/yr short) is quantified but not yet acted on |
| **Total** | **15/20** | |

**Weakest:** Presentation, Innovation and Theme are tied at 3. The single highest-leverage fix serves all three:
**Highest-leverage fix:** M4 + M5. Build the site comparison (the innovation hook), then the deal room plus an equity-weight sweep that shows Elliott-Chelsea getting connected under a community or municipal ownership model. That turns the negative-NPV finding into the pitch's climax.
