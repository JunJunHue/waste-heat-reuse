"""Network MILP on a tiny synthetic street grid where the right answer is known by hand."""
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString

from heattwin import network as N
from heattwin.assumptions import Assumptions

A = Assumptions.load()
# A straight street running east from the data center: nodes every ~100 m (in lon at 40.74 N).
DLON = 100 / (111_320 * np.cos(np.radians(40.74)))
LON0, LAT = -74.0, 40.74


def _streets(n=5):
    return gpd.GeoDataFrame({"geometry": [LineString([(LON0 + i * DLON, LAT), (LON0 + (i + 1) * DLON, LAT)])
                                          for i in range(n)]}, crs="EPSG:4326")


def _cand(idx, node_i, value, peak=1.0):
    return {"id": f"c{idx}", "name": f"c{idx}", "lon": LON0 + node_i * DLON, "lat": LAT, "annual_value_usd": value,
            "peak_net_mw": peak, "interface_capex_usd": 0.0}


def test_connects_valuable_and_skips_worthless():
    c = pd.DataFrame([_cand(0, 2, 5e6), _cand(1, 5, -1e5)])
    d = N.optimize(c, _streets(), (LON0, LAT), q_src_firm_mw=10, cop_design=3.0, a=A, time_limit=30)
    assert set(d.connected.id) == {"c0"}
    assert d.rejected.set_index("id").loc["c1", "reason"]
    assert d.pipes.length_m.sum() == pytest.approx(200, rel=0.02)    # pipe only as far as c0
    assert (d.pipes.flow_mw >= 0).all()                               # no negative flows
    assert d.hp_mw == pytest.approx(1.0, abs=1e-6)                    # HP sized exactly to connected peak


def test_supply_limit_is_respected():
    # 3 valuable buildings of 4 MW each, but the source only supports ~6 MW of heat-pump output
    c = pd.DataFrame([_cand(i, i + 1, 5e6, peak=4.0) for i in range(3)])
    cop = 3.0
    q_firm = 6.0 * (cop - 1) / cop
    d = N.optimize(c, _streets(), (LON0, LAT), q_src_firm_mw=q_firm, cop_design=cop, a=A, time_limit=30)
    assert d.connected.peak_net_mw.sum() <= 6.0 + 1e-6
    assert len(d.connected) == 1


def test_flow_conservation_on_trunk():
    c = pd.DataFrame([_cand(0, 2, 5e6, 1.0), _cand(1, 4, 5e6, 2.0)])
    d = N.optimize(c, _streets(), (LON0, LAT), q_src_firm_mw=10, cop_design=3.0, a=A, time_limit=30)
    flows = sorted(d.pipes.flow_mw.round(6))
    # first two segments carry both loads (3 MW); the last two carry only the far building (2 MW)
    assert flows == pytest.approx([2.0, 2.0, 3.0, 3.0])


def test_pipe_sizes_and_linear_fit():
    caps = [N.pipe_capacity_mw(d, A) for d in N.PIPES.values()]
    assert caps == sorted(caps)
    assert N.pick_dn(0.5, A)[0] == "dn100"
    for dn, d in N.PIPES.items():   # the MILP's linear cost fit stays within 20% of the DN table
        fit = A.v("network.pipe_cost_fixed_per_m") + A.v("network.pipe_cost_per_mw_m") * N.pipe_capacity_mw(d, A)
        assert fit == pytest.approx(A.v(f"pipes.{dn}"), rel=0.20), dn


def test_crf():
    assert N.crf(0.06, 25) == pytest.approx(0.0782267, rel=1e-5)
