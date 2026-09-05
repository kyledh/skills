#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Station code utilities for 12306.

- Maintains a cached station mapping JSON in references/stations.json
- Can search stations by keyword

This intentionally stays simple and low-risk.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date as Date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
REF_DIR = SKILL_ROOT / "references"
STATIONS_JSON = REF_DIR / "stations.json"


def load_stations() -> Dict[str, str]:
    if not STATIONS_JSON.exists():
        raise FileNotFoundError(
            f"Missing station cache: {STATIONS_JSON}. Run update_stations.py first."
        )
    with STATIONS_JSON.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # data: {"name": "CODE"}
    return {str(k): str(v) for k, v in data.items()}


def invert(stations: Dict[str, str]) -> Dict[str, List[str]]:
    inv: Dict[str, List[str]] = {}
    for name, code in stations.items():
        inv.setdefault(code.upper(), []).append(name)
    return inv


def resolve_station(stations: Dict[str, str], s: str) -> Tuple[str, str]:
    """Return (name_or_code_input, code). Accepts Chinese station name or CODE."""
    s2 = s.strip()
    if not s2:
        raise ValueError("Empty station")
    # If looks like 12306 telecode (ASCII letters)
    if len(s2) in (3, 4) and s2.isascii() and s2.isalpha():
        code = s2.upper()
        inv = invert(stations)
        # If we know a canonical name, return first
        if code in inv:
            return inv[code][0], code
        return s2, code

    # Exact match by name
    if s2 in stations:
        return s2, stations[s2].upper()

    # Fuzzy: contains keyword
    hits = [(name, code) for name, code in stations.items() if s2 in name]
    if len(hits) == 1:
        name, code = hits[0]
        return name, code.upper()
    if len(hits) > 1:
        raise ValueError(
            f"Ambiguous station '{s2}'. Candidates: "
            + ", ".join([f"{n}({c})" for n, c in hits[:12]])
            + (" ..." if len(hits) > 12 else "")
        )

    raise ValueError(f"Unknown station '{s2}'. Run update_stations.py and try again.")


# 12306 only sells tickets inside a near-term window; commonly "15 days including today".
QUERY_WINDOW_DAYS = 14


def normalize_date(s: str, today: Date | None = None) -> str:
    """Accept YYYY-MM-DD or M-D / M.D / M/D (current year). Empty -> tomorrow."""
    today = today or Date.today()
    s = (s or "").strip()
    if not s:
        return (today + timedelta(days=1)).isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    m = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})", s)
    if m:
        return f"{today.year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return s


def validate_query_date(s: str, today: Date | None = None) -> Date:
    """Parse a normalized date and enforce the 12306 query window. Raises ValueError."""
    today = today or Date.today()
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        raise ValueError(f"Invalid date '{s}'. Expected YYYY-MM-DD (or M-D / M.D / M/D)")
    if d < today:
        raise ValueError(f"Date {s} is in the past (today={today.isoformat()})")
    latest = today + timedelta(days=QUERY_WINDOW_DAYS)
    if d > latest:
        raise ValueError(f"Date {s} is beyond the 12306 query window (latest={latest.isoformat()})")
    return d


def cmd_search(keyword: str) -> None:
    stations = load_stations()
    kw = keyword.strip()
    hits = [(n, c) for n, c in stations.items() if kw in n]
    hits = sorted(hits, key=lambda x: (len(x[0]), x[0]))
    for n, c in hits[:50]:
        print(f"{n}\t{c}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--search", help="Search station names by substring")
    ap.add_argument("--resolve", help="Resolve a station name/code to code")
    args = ap.parse_args()

    if args.search:
        cmd_search(args.search)
        return

    if args.resolve:
        stations = load_stations()
        name, code = resolve_station(stations, args.resolve)
        print(json.dumps({"input": args.resolve, "name": name, "code": code}, ensure_ascii=False))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
