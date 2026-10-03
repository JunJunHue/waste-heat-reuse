"""Pipeline entry point: `python -m heattwin.cli {data|simulate} <site> ...`."""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="heattwin")
    p.add_argument("command", choices=["data", "simulate"])
    p.add_argument("sites", nargs="+")
    args = p.parse_args(argv)
    for site in args.sites:
        print(f"[{args.command}] {site}: not implemented yet (M0 scaffold)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
