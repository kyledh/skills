#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch and cache 12306 station name -> code mapping.

It downloads station_name.js from 12306 and parses the mapping.
Stores a simple JSON mapping at references/stations.json.

This is used for low-frequency ticket queries.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Dict

import urllib.request

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
REF_DIR = SKILL_ROOT / "references"
STATIONS_JSON = REF_DIR / "stations.json"
META_JSON = REF_DIR / "stations.meta.json"


STATION_JS_CANDIDATES = [
    # common paths seen historically
    "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js",
    "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js?station_version=1",
]


def fetch(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
            "Accept": "*/*",
            "Referer": "https://kyfw.12306.cn/otn/leftTicket/init",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        b = resp.read()
    return b.decode("utf-8", errors="replace")


def parse_station_js(js: str) -> Dict[str, str]:
    # station_name.js contains a big string like: var station_names ='@bji|北京|BJP|beijing|bj|2@...'
    m = re.search(r"station_names\s*=\s*'([^']+)'", js)
    if not m:
        # sometimes double quotes
        m = re.search(r'station_names\s*=\s*"([^"]+)"', js)
    if not m:
        raise ValueError("Could not find station_names string in station_name.js")

    s = m.group(1)
    # entries separated by '@'
    stations: Dict[str, str] = {}
    for entry in s.split("@"):  # first is empty
        if not entry:
            continue
        parts = entry.split("|")
        if len(parts) < 3:
            continue
        name_cn = parts[1].strip()
        code = parts[2].strip().upper()
        if name_cn and code:
            stations[name_cn] = code
    if len(stations) < 1000:
        # sanity check; China railway stations > 2000 typically
        raise ValueError(f"Parsed too few stations: {len(stations)}")
    return stations


def update_stations(quiet: bool = False) -> int:
    """Download station_name.js, write references/stations.json (+ meta). Returns station count."""
    REF_DIR.mkdir(parents=True, exist_ok=True)
    last_err = None
    for url in STATION_JS_CANDIDATES:
        try:
            js = fetch(url)
            stations = parse_station_js(js)
            STATIONS_JSON.write_text(json.dumps(stations, ensure_ascii=False, indent=2), encoding="utf-8")
            META_JSON.write_text(
                json.dumps({"source": url, "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "count": len(stations)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if not quiet:
                print(f"OK: wrote {len(stations)} stations to {STATIONS_JSON}")
            return len(stations)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Failed to update stations. Last error: {last_err}")


def main():
    try:
        update_stations()
    except RuntimeError as e:
        raise SystemExit(str(e))


if __name__ == "__main__":
    main()
