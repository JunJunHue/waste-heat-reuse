"""A scenario = one point in the what-if space. Structural knobs need an engine run; the rest are client-side."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Scenario:
    cooling: str = "air"          # "air" | "liquid"  (structural: changes source temperature and network design)
    it_growth: float = 0.0        # fractional IT load growth vs today (structural)
    equity_weight: float = 1.5    # matcher + MILP equity weight (structural)

    @property
    def id(self) -> str:
        return f"{self.cooling}_g{int(round(self.it_growth * 100))}_eq{int(round(self.equity_weight * 10))}"

    def to_dict(self) -> dict:
        return {**asdict(self), "id": self.id}


BASE = Scenario()
