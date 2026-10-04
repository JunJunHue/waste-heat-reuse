"""Fetch every raw source a site needs (idempotent). Required sources raise; optional ones log and continue.

The ~550 MB DOE LEAD archive is fetched separately (`make data-large`) so the main pipeline never blocks on it;
prepare uses it when cached and otherwise shows energy burden as n/a.
"""
from __future__ import annotations

from ..site import Site
from . import sources as S
from .cache import FetchError


def fetch_site(site: Site) -> None:
    bb, sid, y = site.study_area.bbox, site.id, site.weather.year
    required = [
        ("CDC SVI 2022", S.cdc_svi_ny),
        ("Census tracts", S.census_tracts_ny),
        ("Open-Meteo weather", lambda: S.open_meteo(sid, site.weather.lat, site.weather.lon, y)),
        ("EIA-930 NYIS", lambda: S.eia930_nyis(y)),
        ("TIGER area water", lambda: S.tiger_areawater(site.county_fips)),
    ]
    optional = [
        ("NYISO DAM LBMP", lambda: S.nyiso_dam_lbmp(y)),       # fallback: labeled proxy price
    ]
    if site.adapter == "nyc":
        required += [
            ("NYC footprints", lambda: S.nyc_footprints(sid, bb)),
            ("NYC PLUTO", lambda: S.nyc_pluto(sid, bb)),
            ("NYC LL84 2023", lambda: S.nyc_ll84(2023)),
            ("NYC CSCL streets", lambda: S.nyc_cscl(sid, bb)),
        ]
        optional += [("NYC parks", lambda: S.nyc_parks(sid, bb))]
    else:
        required += [("TIGER roads", lambda: S.tiger_roads(site.county_fips))]

    for name, fn in required:
        p = fn()
        print(f"  ok   {name:24s} {p.relative_to(p.parents[2])}")
    for name, fn in optional:
        try:
            p = fn()
            print(f"  ok   {name:24s} {p.relative_to(p.parents[2])}")
        except FetchError as e:
            print(f"  WARN {name:24s} unavailable -> fallback will be used and labeled ({str(e)[:120]})")
