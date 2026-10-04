"""Download cache: every raw file lands in data/raw/<source>/ and is recorded in data/raw/manifest.json.

Fetches are idempotent: if the file exists it is reused, so `make data` is fast and works offline once
the cache is warm. Each manifest entry records url, params, timestamp, size and sha256 for provenance.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
MANIFEST = RAW / "manifest.json"
USER_AGENT = "HeatTwin/0.1 (NYU Data Center Heat Reuse hackathon; research use)"


class FetchError(RuntimeError):
    pass


def _load_manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


def _record(key: str, entry: dict) -> None:
    m = _load_manifest()
    m[key] = entry
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2, sort_keys=True))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record_derived(source: str, path: Path, note: str, url: str | None = None) -> None:
    """Record a file produced locally (e.g. extracted from an archive, or a labeled proxy)."""
    _record(f"{source}/{path.name}", {
        "source": source, "file": str(path.relative_to(ROOT)), "url": url, "note": note,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bytes": path.stat().st_size, "sha256": sha256(path),
    })


def fetch(source: str, filename: str, url: str, params: dict | None = None, *,
          refresh: bool = False, timeout: int = 120, retries: int = 3, stream: bool = False,
          expect: str | None = None) -> Path:
    """Download url (with params) to data/raw/<source>/<filename> unless already cached.

    expect: "json" | "csv" | "zip" — validate the payload before caching, so an HTML error page served
    with HTTP 200 (e.g. an API demanding a key) is never cached as data. Defaults from the file extension.
    """
    expect = expect or {".json": "json", ".geojson": "json", ".csv": "csv", ".zip": "zip"}.get(dest_suffix(filename))
    dest = RAW / source / filename
    if dest.exists() and dest.stat().st_size > 0 and not refresh:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            # Resume a partial download (large files stall on slow links) via an HTTP Range request.
            have = tmp.stat().st_size if tmp.exists() else 0
            headers = {"User-Agent": USER_AGENT, **({"Range": f"bytes={have}-"} if have else {})}
            with requests.get(url, params=params, timeout=timeout, stream=True, headers=headers) as r:
                r.raise_for_status()
                mode = "ab" if have and r.status_code == 206 else "wb"
                with tmp.open(mode) as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            _validate(tmp, expect, url)
            tmp.rename(dest)
            _record(f"{source}/{filename}", {
                "source": source, "file": str(dest.relative_to(ROOT)), "url": url, "params": params,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "bytes": dest.stat().st_size, "sha256": sha256(dest),
            })
            return dest
        except FetchError:
            tmp.unlink(missing_ok=True)
            raise
        except Exception as e:  # network errors, HTTP errors
            last_err = e
            time.sleep(2 * (attempt + 1))
    tmp.unlink(missing_ok=True)
    raise FetchError(f"{source}: failed to fetch {url}: {last_err}")


def dest_suffix(filename: str) -> str:
    return Path(filename).suffix.lower()


def _validate(path: Path, expect: str | None, url: str) -> None:
    head = path.open("rb").read(512).lstrip()
    looks_html = head[:15].lower().startswith((b"<!doctype html", b"<html"))
    ok = {
        "json": head[:1] in (b"{", b"["),
        "csv": not looks_html and len(head) > 0,
        "zip": head[:2] == b"PK",
        None: True,
    }[expect]
    if not ok:
        raise FetchError(f"payload from {url} is not valid {expect} (starts with {head[:60]!r})")
