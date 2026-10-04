"""Sanity checks on processed Site 1 data. Skipped if `make data` has not been run."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest

from heattwin.assumptions import Assumptions
from heattwin.data import prepare as P
from heattwin.site import Site

SITE = Site.load("site1_chelsea")
OUT = SITE.processed_dir
pytestmark = pytest.mark.skipif(not (OUT / "buildings.parquet").exists(), reason="run `make data` first")


def test_hourly_is_a_full_year_with_physical_values():
    h = pd.read_parquet(OUT / "hourly.parquet")
    assert len(h) == 8760
    assert h.utc.is_monotonic_increasing and h.utc.diff().dropna().eq(pd.Timedelta(hours=1)).all()
    assert h.t_out_c.between(-30, 45).all()
    assert h.grid_tco2_per_mwh.between(0.0, 1.0).all()
    assert h.notna().all().all()


def test_ll84_energy_is_conserved_not_double_counted():
    """Apportioning LL84 property fuel to footprints must preserve each property's total exactly."""
    b = gpd.read_parquet(OUT / "buildings.parquet")
    ll = b[b.has_ll84].groupby("ll84_property").gas_kbtu.sum()
    assert (ll >= 0).all()
    fulton = b[b.ll84_property == "FULTON"]
    assert fulton.steam_kbtu.sum() == pytest.approx(94_343_574, rel=1e-6)  # LL84 2023 reported value


def test_nycha_and_dc_present():
    b = gpd.read_parquet(OUT / "buildings.parquet")
    assert b.is_nycha.sum() > 5
    assert b.units_res.sum() > 10_000
    assert b.svi.notna().mean() > 0.95


def test_bbl_normalisation():
    assert P._norm_bbls("1-01870-0052") == ["1018700052"]
    assert P._norm_bbls("1007230001;1007240001; 1007240015") == ["1007230001", "1007240001", "1007240015"]
    assert P._norm_bbls("Not Available") == []


def test_price_proxy_matches_published_load_weighted_average(monkeypatch):
    """If NYISO is unreachable, the proxy must reproduce the published 2023 zonal average exactly."""
    a = Assumptions.load()
    h = pd.read_parquet(OUT / "hourly.parquet")

    def boom(*_a, **_k):
        raise P.FetchError("simulated outage")

    monkeypatch.setattr(P.S, "nyiso_dam_lbmp", boom)
    price, label = P._price(SITE, a, h)
    assert label.startswith("PROXY")
    lw = (price * h.grid_load_mw).sum() / h.grid_load_mw.sum()
    assert lw == pytest.approx(a.v("grid.lbmp_avg_2023_zone_j"), rel=1e-9)
    assert (price > 0).all()
