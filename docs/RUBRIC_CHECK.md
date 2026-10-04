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
