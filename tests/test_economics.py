import pytest

from heattwin.economics import npv, payback_years
from heattwin.network import crf


def test_npv_matches_annuity_formula():
    rate, years, capex, annual = 0.06, 25, 1_000_000.0, 100_000.0
    annuity_pv = annual * (1 - (1 + rate) ** -years) / rate
    assert npv(rate, [-capex] + [annual] * years) == pytest.approx(annuity_pv - capex, rel=1e-12)


def test_crf_is_inverse_of_annuity_factor():
    rate, years = 0.04, 25
    assert crf(rate, years) * (1 - (1 + rate) ** -years) / rate == pytest.approx(1.0)


def test_payback():
    assert payback_years(100, 25) == 4
    assert payback_years(100, 0) == float("inf")
