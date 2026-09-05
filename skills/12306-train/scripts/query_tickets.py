#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query 12306 remaining tickets (leftTicket).

Low-frequency query helper:
- resolves station names to codes via cached mapping
- caches identical queries briefly to reduce load
- retries with backoff

No login/captcha/purchase.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from datetime import date as Date
from dataclasses import dataclass
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

# Station resolving + date helpers are shared via stations.py
from stations import load_stations, resolve_station, normalize_date, validate_query_date  # noqa: E402


QUERY_ENDPOINTS = [
    "https://kyfw.12306.cn/otn/leftTicket/query",
    "https://kyfw.12306.cn/otn/leftTicket/queryZ",
    "https://kyfw.12306.cn/otn/leftTicket/queryX",
    "https://kyfw.12306.cn/otn/leftTicket/queryY",
]


@dataclass
class QueryArgs:
    date: str
    from_station: str
    to_station: str
    purpose: str = "ADULT"


# Cookie-enabled opener (some 12306 endpoints behave better after a preflight page view).
CJ = http.cookiejar.CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    "Referer": "https://kyfw.12306.cn/otn/leftTicket/init",
    "X-Requested-With": "XMLHttpRequest",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "close",
}


def get_cookie(timeout: int = 15) -> str:
    """Fetch /otn/leftTicket/init and return a Cookie header value.

    12306's JSON endpoints often return HTML unless a small set of cookies are present.
    We keep this minimal (no login).
    """
    req = urllib.request.Request(
        "https://kyfw.12306.cn/otn/leftTicket/init",
        headers={
            "User-Agent": COMMON_HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": COMMON_HEADERS["Accept-Language"],
        },
        method="GET",
    )
    with OPENER.open(req, timeout=timeout) as resp:
        resp.read(2000)
        set_cookies = []
        try:
            set_cookies = resp.headers.get_all("Set-Cookie") or []
        except Exception:
            pass

    # turn "a=b; Path=/; ..." into "a=b"
    kv = []
    for c in set_cookies:
        part = c.split(";", 1)[0].strip()
        if part and "=" in part:
            kv.append(part)
    return "; ".join(kv)


def http_get_json(url: str, timeout: int = 15) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers=COMMON_HEADERS, method="GET")
    with OPENER.open(req, timeout=timeout) as resp:
        b = resp.read()
        ctype = resp.headers.get('content-type')

    txt = b.decode("utf-8-sig", errors="replace")
    if os.environ.get("DEBUG_12306") == "1":
        head = txt[:160].replace("\n", "\\n")
        print(f"[debug] ctype={ctype} head={head}")

    if txt.lstrip().startswith("<"):
        # dump HTML for debugging
        ts = int(time.time())
        dump = CACHE_DIR / f"last_nonjson_{ts}.html"
        try:
            dump.write_text(txt, encoding="utf-8")
        except Exception:
            pass
        raise ValueError(f"Non-JSON response (HTML). dump={dump}")
    return json.loads(txt)


def cache_key(q: QueryArgs, from_code: str, to_code: str) -> str:
    safe = f"{q.date}_{from_code}_{to_code}_{q.purpose}".replace("/", "_")
    return safe


def read_cache(key: str, ttl_seconds: int) -> Optional[Dict[str, Any]]:
    p = CACHE_DIR / f"{key}.json"
    if not p.exists():
        return None
    age = time.time() - p.stat().st_mtime
    if age > ttl_seconds:
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_cache(key: str, data: Dict[str, Any]) -> None:
    p = CACHE_DIR / f"{key}.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_url(endpoint: str, q: QueryArgs, from_code: str, to_code: str) -> str:
    params = {
        "leftTicketDTO.train_date": q.date,
        "leftTicketDTO.from_station": from_code,
        "leftTicketDTO.to_station": to_code,
        "purpose_codes": q.purpose,
    }
    return endpoint + "?" + urllib.parse.urlencode(params)


def query(q: QueryArgs, from_code: str, to_code: str, retries: int = 3) -> Dict[str, Any]:
    last_err: Optional[Exception] = None

    # "compromise" cookie strategy:
    # - obtain cookie once, reuse for a short TTL
    # - on HTML/non-JSON errors, refresh cookie and retry
    cookie = ""
    cookie_at = 0.0
    COOKIE_TTL = 30.0

    def ensure_cookie(force: bool = False) -> str:
        nonlocal cookie, cookie_at
        now = time.time()
        if force or (not cookie) or (now - cookie_at > COOKIE_TTL):
            try:
                cookie = get_cookie()
            except Exception:
                cookie = ""
            cookie_at = now
        if cookie:
            COMMON_HEADERS["Cookie"] = cookie
        else:
            COMMON_HEADERS.pop("Cookie", None)
        return cookie

    ensure_cookie(force=True)

    for attempt in range(retries):
        if attempt > 0:
            time.sleep((1.1 * attempt) + random.random() * 0.9)

        if os.environ.get("DEBUG_12306") == "1":
            print(f"[debug] attempt={attempt+1}/{retries} cookie={'(empty)' if not cookie else cookie}")

        for ep in QUERY_ENDPOINTS:
            url = build_url(ep, q, from_code, to_code)
            try:
                # refresh cookie if stale
                ensure_cookie(force=False)
                data = http_get_json(url)
                if isinstance(data, dict) and data.get("status") is True and isinstance(data.get("data"), dict):
                    return {"endpoint": ep, "url": url, "response": data}
                # JSON but not a success payload (e.g. {"status":false,"messages":[...]}): try next endpoint
                msgs = data.get("messages") if isinstance(data, dict) else None
                raise ValueError(f"12306 returned non-success JSON: messages={msgs} keys={list(data)[:6] if isinstance(data, dict) else type(data).__name__}")
            except Exception as e:
                last_err = e
                # If we got HTML/non-JSON, refresh cookie and try again.
                if "Non-JSON" in str(e) or "HTML" in str(e):
                    ensure_cookie(force=True)
                time.sleep(0.35 + random.random() * 0.5)
                continue

    raise RuntimeError(f"Query failed after retries. Last error: {last_err}")


# Keys aligned with common 12306 leftTicket result format (see Joooook/12306-mcp types.ts).
TICKET_KEYS = [
    "secret_Sstr",
    "button_text_info",
    "train_no",
    "station_train_code",
    "start_station_telecode",
    "end_station_telecode",
    "from_station_telecode",
    "to_station_telecode",
    "start_time",
    "arrive_time",
    "lishi",
    "canWebBuy",
    "yp_info",
    "start_train_date",
    "train_seat_feature",
    "location_code",
    "from_station_no",
    "to_station_no",
    "is_support_card",
    "controlled_train_flag",
    "gg_num",
    "gr_num",
    "qt_num",
    "rw_num",
    "rz_num",
    "tz_num",
    "wz_num",
    "yb_num",
    "yw_num",
    "yz_num",
    "ze_num",
    "zy_num",
    "swz_num",
    "srrb_num",
    "yp_ex",
    "seat_types",
    "exchange_train_flag",
    "houbu_train_flag",
    "houbu_seat_limit",
    "yp_info_new",
    "40",
    "41",
    "42",
    "43",
    "44",
    "45",
    "dw_flag",
    "47",
    "stopcheckTime",
    "country_flag",
    "local_arrive_time",
    "local_start_time",
    "52",
    "bed_level_info",
    "seat_discount_info",
    "sale_time",
    "56",
]

SEAT_LABELS = [
    ("swz_num", "商务"),
    ("tz_num", "特等"),
    ("zy_num", "一等"),
    ("ze_num", "二等"),
    ("gr_num", "高级软卧/动卧"),
    ("rw_num", "软卧"),
    ("yw_num", "硬卧"),
    ("rz_num", "软座"),
    ("yz_num", "硬座"),
    ("wz_num", "无座"),
]

SEAT_TYPES = {
    "9": {"name": "商务座", "short": "swz"},
    "P": {"name": "特等座", "short": "tz"},
    "M": {"name": "一等座", "short": "zy"},
    "D": {"name": "优选一等座", "short": "zy"},
    "O": {"name": "二等座", "short": "ze"},
    "S": {"name": "二等包座", "short": "ze"},
    "6": {"name": "高级软卧", "short": "gr"},
    "A": {"name": "高级动卧", "short": "gr"},
    "4": {"name": "软卧", "short": "rw"},
    "I": {"name": "一等卧", "short": "rw"},
    "F": {"name": "动卧", "short": "rw"},
    "3": {"name": "硬卧", "short": "yw"},
    "J": {"name": "二等卧", "short": "yw"},
    "2": {"name": "软座", "short": "rz"},
    "1": {"name": "硬座", "short": "yz"},
    "W": {"name": "无座", "short": "wz"},
    "H": {"name": "其他", "short": "qt"},
}


def extract_prices(yp_info_new: str, seat_discount_info: str, ticket: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract prices per seat from yp_info_new and seat_discount_info.

    Ported from Joooook/12306-mcp.
    - yp_info_new is a concatenation of 10-char chunks.
    - seat_discount_info is concatenation of 5-char chunks.
    """
    if not yp_info_new:
        return []

    PRICE_STR_LENGTH = 10
    DISCOUNT_STR_LENGTH = 5

    discounts: Dict[str, int] = {}
    if seat_discount_info:
        for i in range(0, len(seat_discount_info) // DISCOUNT_STR_LENGTH):
            s = seat_discount_info[i * DISCOUNT_STR_LENGTH : (i + 1) * DISCOUNT_STR_LENGTH]
            if len(s) == DISCOUNT_STR_LENGTH and s[0]:
                try:
                    discounts[s[0]] = int(s[1:])
                except Exception:
                    pass

    prices: List[Dict[str, Any]] = []
    for i in range(0, len(yp_info_new) // PRICE_STR_LENGTH):
        p = yp_info_new[i * PRICE_STR_LENGTH : (i + 1) * PRICE_STR_LENGTH]
        if len(p) != PRICE_STR_LENGTH:
            continue
        # seat type code
        try:
            tail = int(p[6:10])
        except Exception:
            tail = 0
        if tail >= 3000:
            seat_type_code = "W"
        elif p[0] not in SEAT_TYPES:
            seat_type_code = "H"
        else:
            seat_type_code = p[0]

        seat_type = SEAT_TYPES.get(seat_type_code, {"name": "其他", "short": "qt"})
        try:
            price = int(p[1:6]) / 10
        except Exception:
            price = None
        discount = discounts.get(seat_type_code)

        short = seat_type.get("short")
        num_key = f"{short}_num"
        num = ticket.get(num_key, "")

        prices.append(
            {
                "seat_name": seat_type.get("name"),
                "short": short,
                "seat_type_code": seat_type_code,
                "num": num,
                "price": price,
                "discount": discount,
            }
        )

    return prices



def parse_result_rows(resp: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse 12306 leftTicket results into structured rows.

    Note: seat fields are strings like '有', '无', '候补', '--', or numbers.
    """
    data = resp.get("response", {})
    d = data.get("data") if isinstance(data, dict) else None
    if not isinstance(d, dict):
        return []
    rows = d.get("result")
    if not isinstance(rows, list):
        return []

    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, str):
            continue
        parts = r.split("|")
        # map by index
        ticket: Dict[str, Any] = {}
        for i, key in enumerate(TICKET_KEYS):
            if i < len(parts):
                ticket[key] = parts[i]
            else:
                ticket[key] = ""

        seats = {k: str(ticket.get(k, "")) for k, _ in SEAT_LABELS}
        prices = extract_prices(str(ticket.get("yp_info_new", "")), str(ticket.get("seat_discount_info", "")), ticket)

        out.append(
            {
                "train_code": ticket.get("station_train_code", ""),
                "train_no": ticket.get("train_no", ""),
                "from_code": ticket.get("from_station_telecode", ""),
                "to_code": ticket.get("to_station_telecode", ""),
                "depart": ticket.get("start_time", ""),
                "arrive": ticket.get("arrive_time", ""),
                "duration": ticket.get("lishi", ""),
                "can_buy": ticket.get("canWebBuy", ""),
                "seats": seats,
                "prices": prices,
                "raw": r,
            }
        )
    return out


def summarize(rows: List[Dict[str, Any]], limit: int = 10) -> str:
    if not rows:
        return "没查到车次（可能当天无直达/该站名应换成北站/接口返回空）。"
    # sort by depart time
    def key(r):
        t = r.get("depart") or "99:99"
        return t

    rows2 = sorted(rows, key=key)[:limit]
    lines = []
    for r in rows2:
        seats = r.get("seats", {})
        # Map prices by short code, keep only those we care about.
        price_map = {}
        for p in r.get("prices", []) or []:
            if isinstance(p, dict) and p.get("short"):
                price_map[p["short"]] = p

        def seat_cell(short: str, label: str, num_key: str) -> str:
            num = str(seats.get(num_key, ""))
            pr = price_map.get(short, {})
            price = pr.get("price")
            if price is None or price == "" or price == 0:
                return f"{label}:{num}"
            # keep 1 decimal if needed, otherwise int
            try:
                price_s = (str(int(price)) if float(price).is_integer() else f"{float(price):.1f}")
            except Exception:
                price_s = str(price)
            return f"{label}:{num}(¥{price_s})"

        seat_str = " ".join(
            [
                seat_cell("swz", "商务", "swz_num"),
                seat_cell("tz", "特等", "tz_num"),
                seat_cell("zy", "一等", "zy_num"),
                seat_cell("ze", "二等", "ze_num"),
                seat_cell("rw", "软卧", "rw_num"),
                seat_cell("yw", "硬卧", "yw_num"),
                seat_cell("yz", "硬座", "yz_num"),
                seat_cell("wz", "无座", "wz_num"),
            ]
        ).replace("  ", " ").strip()

        lines.append(
            f"{r.get('train_code','?')} {r.get('depart','?')}→{r.get('arrive','?')} 历时{r.get('duration','?')} 可购:{r.get('can_buy','?')} {seat_str}"
        )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="YYYY-MM-DD (or M-D/M.D/M/D; optional; defaults to tomorrow)")
    ap.add_argument("--from", dest="from_station", required=True, help="Chinese station name or code")
    ap.add_argument("--to", dest="to_station", required=True, help="Chinese station name or code")
    ap.add_argument("--purpose", default="ADULT", help="ADULT by default")
    ap.add_argument("--cache-ttl", type=int, default=60, help="Cache TTL seconds")
    ap.add_argument("--limit", type=int, default=10, help="Summary rows limit")
    ap.add_argument("--json-out", default="", help="Write full JSON to path")
    args = ap.parse_args()

    today = Date.today()
    used_default_date = not args.date
    args.date = normalize_date(args.date, today)
    try:
        validate_query_date(args.date, today)
    except ValueError as e:
        raise SystemExit(str(e))

    stations = load_stations()
    from_name, from_code = resolve_station(stations, args.from_station)
    to_name, to_code = resolve_station(stations, args.to_station)

    q = QueryArgs(date=args.date, from_station=from_name, to_station=to_name, purpose=args.purpose)
    key = cache_key(q, from_code, to_code)

    cached = read_cache(key, args.cache_ttl)
    if cached:
        resp = cached
        resp["cached"] = True
    else:
        resp = query(q, from_code, to_code)
        resp["cached"] = False
        write_cache(key, resp)

    rows = parse_result_rows(resp)
    summary = summarize(rows, limit=args.limit)

    out = {
        "query": {
            "date": q.date,
            "from": {"input": args.from_station, "name": from_name, "code": from_code},
            "to": {"input": args.to_station, "name": to_name, "code": to_code},
            "purpose": q.purpose,
        },
        "meta": {
            "cached": resp.get("cached", False),
            "endpoint": resp.get("endpoint"),
            "url": resp.get("url"),
            "rowCount": len(rows),
        },
        "rows": rows,
        "raw": resp.get("response"),
    }

    # write JSON output (optional to print path)
    if args.json_out:
        out_path = Path(args.json_out)
    else:
        out_path = CACHE_DIR / f"last_{key}.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    if used_default_date:
        print(f"{q.date} {from_name}({from_code}) → {to_name}({to_code})  (默认查询明天；不同日期车次/票价/余票可能不同)")
    else:
        print(f"{q.date} {from_name}({from_code}) → {to_name}({to_code})")
    print(summary)

    # Only print JSON path when explicitly requested (keeps skill output clean)
    if args.json_out:
        print(f"\nJSON: {out_path}")


if __name__ == "__main__":
    main()
