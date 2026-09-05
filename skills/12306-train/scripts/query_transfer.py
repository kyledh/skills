#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query 12306 transfer (interline) tickets via lcQuery.

This follows the same approach as Joooook/12306-mcp:
- GET /otn/lcQuery/init to discover lc_search_url path
- GET /otn/leftTicket/init to obtain cookies
- Call the discovered lc_search_url with required query params

Low-frequency only. No login/captcha/purchase.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import urllib.parse
import urllib.request
import http.cookiejar

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
REF_DIR = SKILL_ROOT / "references"
CACHE_DIR = SKILL_ROOT / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://kyfw.12306.cn"
LCQUERY_INIT_URL = f"{API_BASE}/otn/lcQuery/init"

CJ = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    "Connection": "close",
}


from stations import load_stations, resolve_station, normalize_date, validate_query_date  # noqa: E402


def fetch(url: str, headers: Dict[str, str], timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with OPENER.open(req, timeout=timeout) as resp:
        b = resp.read()
    return b.decode("utf-8-sig", errors="replace")


def get_cookie(timeout: int = 15) -> str:
    url = f"{API_BASE}/otn/leftTicket/init"
    headers = {
        "User-Agent": COMMON_HEADERS["User-Agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": COMMON_HEADERS["Accept-Language"],
    }
    req = urllib.request.Request(url, headers=headers, method="GET")
    with OPENER.open(req, timeout=timeout) as resp:
        resp.read(2000)
        set_cookies = resp.headers.get_all("Set-Cookie") or []
    kv = []
    for c in set_cookies:
        part = c.split(";", 1)[0].strip()
        if part and "=" in part:
            kv.append(part)
    return "; ".join(kv)


def get_lcquery_path(timeout: int = 15) -> str:
    html = fetch(
        LCQUERY_INIT_URL,
        headers={
            "User-Agent": COMMON_HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": COMMON_HEADERS["Accept-Language"],
            "Referer": f"{API_BASE}/",
        },
        timeout=timeout,
    )
    m = re.search(r"\svar\s+lc_search_url\s*=\s*'(.+?)'", html)
    if not m:
        raise ValueError("Failed to locate lc_search_url in lcQuery init page")
    return m.group(1)


def http_get_json(url: str, headers: Dict[str, str], timeout: int = 15) -> Dict[str, Any]:
    txt = fetch(url, headers=headers, timeout=timeout)
    if os.environ.get("DEBUG_12306") == "1":
        head = txt[:160].replace("\n", "\\n")
        print(f"[debug] head={head}")
    if txt.lstrip().startswith("<"):
        raise ValueError("Non-JSON response (可能被风控/返回HTML页面)")
    return json.loads(txt)


def summarize_interline(items: List[Dict[str, Any]], limit: int = 10) -> str:
    if not items:
        return "没查到中转方案。"

    def tkey(x: Dict[str, Any]) -> Tuple[int, str]:
        mins = x.get("all_lishi_minutes")
        try:
            mins_i = int(mins)
        except Exception:
            mins_i = 10**9
        return (mins_i, str(x.get("start_time") or "99:99"))

    items2 = sorted(items, key=tkey)[:limit]
    lines: List[str] = []
    for it in items2:
        from_name = it.get("from_station_name")
        mid_name = it.get("middle_station_name")
        end_name = it.get("end_station_name")
        st = it.get("start_time")
        at = it.get("arrive_time")
        dur = it.get("all_lishi") or it.get("use_time")
        wait = it.get("wait_time")
        lines.append(f"{from_name} → {mid_name} → {end_name} {st}→{at} 总历时{dur}  等待{wait}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD (or M-D/M.D/M/D; optional; defaults to tomorrow)")
    ap.add_argument("--from", dest="from_station", required=True, help="Chinese station name or code")
    ap.add_argument("--to", dest="to_station", required=True, help="Chinese station name or code")
    ap.add_argument("--middle", default="", help="Optional middle station (name or code)")
    ap.add_argument("--show-wz", action="store_true", help="Show no-seat (无座) options")
    ap.add_argument("--limit", type=int, default=10, help="Max transfer plans to show")
    ap.add_argument("--cache-ttl", type=int, default=120, help="Cache TTL seconds")
    args = ap.parse_args()

    used_default_date = not args.date
    args.date = normalize_date(args.date)
    try:
        validate_query_date(args.date)
    except ValueError as e:
        raise SystemExit(str(e))

    stations = load_stations()
    from_name, from_code = resolve_station(stations, args.from_station)
    to_name, to_code = resolve_station(stations, args.to_station)
    mid_name = ""
    mid_code = ""
    if args.middle:
        mid_name, mid_code = resolve_station(stations, args.middle)

    key = f"transfer_{args.date}_{from_code}_{to_code}_{mid_code}_{'WZ' if args.show_wz else 'NO'}.json"
    cache_path = CACHE_DIR / key
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) <= args.cache_ttl:
        out = json.loads(cache_path.read_text(encoding="utf-8"))
        out["meta"]["cached"] = True
        print(f"{args.date} {from_name}({from_code}) → {to_name}({to_code})" + ("  (默认查询明天)" if used_default_date else ""))
        if mid_code:
            print(f"指定中转：{mid_name}({mid_code})")
        print(out.get("summary", ""))
        # Only print JSON path when DEBUG_12306=1 (keep output clean)
        if os.environ.get("DEBUG_12306") == "1":
            print(f"\nJSON: {cache_path}")
        return

    # discover lcquery path
    lc_path = get_lcquery_path()
    query_url = f"{API_BASE}{lc_path}"

    cookie = get_cookie()
    headers = {
        **COMMON_HEADERS,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Referer": LCQUERY_INIT_URL,
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": cookie,
    }

    params = {
        "train_date": args.date,
        "from_station_telecode": from_code,
        "to_station_telecode": to_code,
        "middle_station": mid_code,
        "result_index": "0",
        "can_query": "Y",
        "isShowWZ": "Y" if args.show_wz else "N",
        "purpose_codes": "00",
        "channel": "E",
    }

    # paginate until enough
    interline: List[Dict[str, Any]] = []
    result_index = "0"
    for _page in range(6):  # hard cap
        params["result_index"] = result_index
        url = query_url + "?" + urllib.parse.urlencode(params)
        try:
            data = http_get_json(url, headers=headers)
        except Exception as e:
            raise SystemExit(f"Query failed: {e}")

        d = data.get("data") if isinstance(data, dict) else None
        if isinstance(d, str):
            # errorMsg may exist at top level
            em = data.get("errorMsg") if isinstance(data, dict) else ""
            raise SystemExit(f"No transfer results: {em or d}")
        if not isinstance(d, dict):
            break
        middle_list = d.get("middleList") or []
        if isinstance(middle_list, list):
            interline.extend([x for x in middle_list if isinstance(x, dict)])
        if len(interline) >= args.limit:
            break
        if d.get("can_query") == "N":
            break
        result_index = str(d.get("result_index") or result_index)
        time.sleep(0.4 + random.random() * 0.6)

    summary = summarize_interline(interline, limit=args.limit)
    out = {
        "query": {
            "date": args.date,
            "from": {"input": args.from_station, "name": from_name, "code": from_code},
            "to": {"input": args.to_station, "name": to_name, "code": to_code},
            "middle": ({"input": args.middle, "name": mid_name, "code": mid_code} if mid_code else None),
            "showWZ": bool(args.show_wz),
        },
        "meta": {
            "cached": False,
            "lcqueryPath": lc_path,
            "queryUrl": query_url,
            "count": len(interline),
        },
        "summary": summary,
        "items": interline,
    }
    cache_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{args.date} {from_name}({from_code}) → {to_name}({to_code})" + ("  (默认查询明天)" if used_default_date else ""))
    if mid_code:
        print(f"指定中转：{mid_name}({mid_code})")
    print(summary)
    # Only print JSON path when DEBUG_12306=1 (keep output clean)
    if os.environ.get("DEBUG_12306") == "1":
        print(f"\nJSON: {cache_path}")


if __name__ == "__main__":
    main()
