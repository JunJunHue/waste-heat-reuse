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
