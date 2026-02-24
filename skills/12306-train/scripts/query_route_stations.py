#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query route (stops) for a specific train on 12306.

Uses endpoint:
  /otn/czxx/queryByTrainNo

This typically requires:
- train_no (not just the visible train code)
- from_station_telecode, to_station_telecode
- depart_date (YYYY-MM-DD)

Workflow supported:
1) If you already have train_no: call czxx directly.
2) If you only have a visible train code (e.g. K4409):
   - run leftTicket query for the given date/from/to
   - find the row with matching station_train_code and extract train_no
   - call czxx

Low-frequency only. No login/captcha/purchase.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import urllib.parse
import urllib.request
import http.cookiejar

# Reuse station resolving + cookie strategy from query_tickets.py
from query_tickets import (  # type: ignore
    load_stations,
    resolve_station,
    get_cookie,
    http_get_json,
    build_url,
    QueryArgs,
    QUERY_ENDPOINTS,
    COMMON_HEADERS,
)

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
CACHE_DIR = SKILL_ROOT / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://kyfw.12306.cn"
CZXX_URL = f"{API_BASE}/otn/czxx/queryByTrainNo"


def find_train_no(
    date: str,
    from_code: str,
    to_code: str,
    train_code: str,
    purpose: str = "ADULT",
) -> Tuple[str, Dict[str, Any]]:
    """Find train_no by running a leftTicket query and matching station_train_code."""
    q = QueryArgs(date=date, from_station="", to_station="", purpose=purpose)
    train_code = train_code.strip().upper()

    last_err: Optional[Exception] = None
    for attempt in range(3):
        if attempt > 0:
            time.sleep((1.1 * attempt) + random.random() * 0.8)

        cookie = ""
        try:
            cookie = get_cookie()
        except Exception:
            cookie = ""
        if cookie:
            COMMON_HEADERS["Cookie"] = cookie
        else:
            COMMON_HEADERS.pop("Cookie", None)

        for ep in QUERY_ENDPOINTS:
            url = build_url(ep, q, from_code, to_code)
            try:
                data = http_get_json(url)
                d = data.get("data") if isinstance(data, dict) else None
                rows = d.get("result") if isinstance(d, dict) else None
                if not isinstance(rows, list):
                    continue
                for r in rows:
                    if not isinstance(r, str):
                        continue
                    parts = r.split("|")
                    # station_train_code is commonly at index 3 per our mapping
                    if len(parts) > 3 and str(parts[3]).upper() == train_code:
                        # train_no commonly at index 2
                        if len(parts) > 2 and parts[2]:
                            return str(parts[2]), {"endpoint": ep, "url": url}
                return "", {"endpoint": ep, "url": url}
            except Exception as e:
                last_err = e
                continue

    raise RuntimeError(f"Failed to find train_no. Last error: {last_err}")


def query_route(date: str, train_no: str, from_code: str, to_code: str) -> Dict[str, Any]:
    cookie = ""
    try:
        cookie = get_cookie()
    except Exception:
        cookie = ""
    if cookie:
        COMMON_HEADERS["Cookie"] = cookie
    else:
        COMMON_HEADERS.pop("Cookie", None)

    params = {
        "train_no": train_no,
        "from_station_telecode": from_code,
        "to_station_telecode": to_code,
        "depart_date": date,
    }
    url = CZXX_URL + "?" + urllib.parse.urlencode(params)
    data = http_get_json(url)
    return {"url": url, "response": data}


def format_stops(stops: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for s in stops:
        name = s.get("station_name") or s.get("stationName") or ""
        arr = s.get("arrive_time") or s.get("arriveTime") or ""
        dep = s.get("start_time") or s.get("startTime") or ""
        stay = s.get("stopover_time") or s.get("stopoverTime") or ""
        seq = s.get("station_no") or s.get("stationNo") or ""
        lines.append(f"{seq}. {name} 到{arr} 发{dep} 停{stay}")
    return "\n".join([l for l in lines if l.strip()])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--from", dest="from_station", required=True, help="Chinese station name or code")
    ap.add_argument("--to", dest="to_station", required=True, help="Chinese station name or code")
    ap.add_argument("--train-code", default="", help="Visible train code, e.g. K4409/G175")
    ap.add_argument("--train-no", default="", help="Internal train_no (if already known)")
    ap.add_argument("--purpose", default="ADULT")
    args = ap.parse_args()

    stations = load_stations()
    from_name, from_code = resolve_station(stations, args.from_station)
    to_name, to_code = resolve_station(stations, args.to_station)

    train_no = args.train_no.strip()
    meta: Dict[str, Any] = {}

    if not train_no:
        if not args.train_code:
            raise SystemExit("Provide --train-code or --train-no")
        train_no, meta = find_train_no(args.date, from_code, to_code, args.train_code, purpose=args.purpose)
        if not train_no:
            raise SystemExit(f"Train {args.train_code} not found in leftTicket results for this route/date")

    resp = query_route(args.date, train_no, from_code, to_code)
    data = resp.get("response")
    d = data.get("data") if isinstance(data, dict) else None
    stops = d.get("data") if isinstance(d, dict) else None
    if not isinstance(stops, list):
        # try alternative key
        stops = d.get("data") if isinstance(d, dict) else []

    print(f"{args.date} {from_name}({from_code}) → {to_name}({to_code})")
    if args.train_code:
        print(f"车次: {args.train_code}  train_no: {train_no}")
    else:
        print(f"train_no: {train_no}")

    if isinstance(stops, list) and stops:
        print(format_stops(stops))
    else:
        msg = data.get("messages") if isinstance(data, dict) else None
        print(f"未获取到经停信息。messages={msg}")

    # dump JSON only when DEBUG_12306=1
    if os.environ.get("DEBUG_12306") == "1":
        out_path = CACHE_DIR / f"route_{args.date}_{from_code}_{to_code}_{train_no}.json"
        out_path.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON: {out_path}")


if __name__ == "__main__":
    main()
