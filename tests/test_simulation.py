"""End-to-end invariants on the real Site 1 run (slow: solves the MILP). Skipped until `make data` has run."""
import numpy as np
import pytest

from heattwin.scenario import BASE
from heattwin.site import Site

pytestmark = pytest.mark.skipif(not (Site.load("site1_chelsea").processed_dir / "buildings.parquet").exists(),
                                reason="run `make data` first")


@pytest.fixture(scope="module")
def result():
    from heattwin.simulate import run
    return run("site1_chelsea", BASE)


def test_energy_balance_closes(result):
    e = result.econ["energy_mwh"]
    assert e["produced"] == pytest.approx(e["hp_electricity"] + e["dc_heat_recovered"], rel=1e-9)
    assert e["delivered"] == pytest.approx(e["produced"] * (1 - 0.06), rel=1e-9)


def test_heat_pump_never_exceeds_firm_source(result):
    d = result.design
    assert d.hp_mw <= d.hp_max_mw + 1e-6
    assert result.econ["energy_mwh"]["dc_heat_recovered"] <= result.supply.q_src_mw.sum()


def test_cooling_never_depends_on_offtake(result):
    """Design rule: the existing DC heat rejection stays 100% sized, so recovered heat is always <= total DC heat."""
    assert (result.supply.q_src_mw <= result.supply.q_total_heat_mw).all()


def test_scores_bounded_and_explained(result):
    r = result.ranked
    for d in ("temperature", "capacity", "timing", "seasonality", "continuity", "proximity", "equity"):
        assert r[f"s_{d}"].between(0, 1).all(), d
    assert r.rationale.str.len().gt(10).all()
    assert (r[r.is_nycha].s_equity == 1).all()


def test_cop_physical(result):
    assert np.all(result.cop_hourly > 1) and np.all(result.cop_hourly < 8)


def test_demand_model_validates_against_metered_steam(result):
    v = result.validation
    assert v["r2"] > 0.9
    assert v["annual_modeled_mwh"] == pytest.approx(v["annual_metered_mwh"], rel=0.10)


def test_milp_solved_to_tolerance(result):
    assert result.design.stats["mip_gap"] <= 0.01
