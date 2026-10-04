import numpy as np
import pytest

from heattwin.heatpump import CopTable, cycle


@pytest.mark.parametrize("src,sink", [(22, 75), (42, 75), (22, 60), (30, 85), (50, 65)])
def test_cop_within_physical_bounds(src, sink):
    r = cycle(src, sink)
    assert 1.0 < r.cop_heating < r.cop_carnot          # second law
    assert 0.35 < r.carnot_fraction < 0.75              # realistic large-HP range


def test_cop_falls_as_lift_rises():
    cops = [cycle(22, s).cop_heating for s in (55, 65, 75, 85)]
    assert all(a > b for a, b in zip(cops, cops[1:]))


def test_liquid_cooling_beats_air_cooling():
    assert cycle(42, 75).cop_heating > cycle(22, 75).cop_heating + 1.0


def test_table_matches_direct_cycle():
    t = CopTable(0.70, 3.0)
    for src, sink in [(22.0, 75.0), (22.5, 74.3), (41.2, 68.8)]:
        assert float(t(src, sink)) == pytest.approx(cycle(round(src), round(sink)).cop_heating, rel=0.03)


def test_table_rejects_infeasible():
    with pytest.raises(ValueError):
        CopTable(0.70, 3.0)(np.array([60.0]), np.array([62.0]))
