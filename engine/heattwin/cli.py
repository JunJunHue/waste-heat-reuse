"""Pipeline entry point: `python -m heattwin.cli {data|simulate} <site> ...`."""
from __future__ import annotations

import argparse
import sys

from .site import Site


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="heattwin")
    p.add_argument("command", choices=["data", "simulate"])
    p.add_argument("sites", nargs="+")
    args = p.parse_args(argv)
    for site_id in args.sites:
        site = Site.load(site_id)
        print(f"[{args.command}] {site.name}")
        if args.command == "data":
            if site.adapter != "nyc":
                print("  skip: Site 2 adapter lands in M4")
                continue
            from .data.fetch_all import fetch_site
            from .data.prepare import prepare
            fetch_site(site)
            print(f"  prepared -> {prepare(site_id)}")
        else:
            if site.adapter != "nyc":
                print("  skip: Site 2 adapter lands in M4")
                continue
            from .export import export_result, export_site
            from .scenario import BASE
            from .simulate import run
            res = run(site_id, BASE)
            k = res.econ["kpis"]
            print(f"  {BASE.id}: {k['buildings_connected']} buildings, {k['homes_served']:.0f} homes, "
                  f"{k['tco2e_avoided_per_yr']:,.0f} tCO2e/yr, MILP {res.timings['milp']:.0f}s gap {res.design.stats['mip_gap']:.3%}")
            print(f"  results -> {export_result(res)}")
            print(f"  site    -> {export_site(site)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
