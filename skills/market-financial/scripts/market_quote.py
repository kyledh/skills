#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _f(v):
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _i(v):
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _g(obj, *names):
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    return None


def http_get_json(url, headers=None, timeout=10):
    h = {"User-Agent": "Mozilla/5.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read().decode("utf-8")
        return json.loads(data)


def fetch_okx(symbol: str):
    inst = symbol.upper()
    url = f"https://www.okx.com/api/v5/market/ticker?instId={urllib.parse.quote(inst)}"
    j = http_get_json(url)
    row = (j.get("data") or [{}])[0]
    return {
        "skill": "market-financial",
        "provider": "okx",
        "symbol": inst,
        "last": _f(row.get("last")),
        "bid": _f(row.get("bidPx")),
        "ask": _f(row.get("askPx")),
        "vol24h": _f(row.get("vol24h")),
        "source_ts_ms": row.get("ts"),
        "fetched_at": now_iso(),
    }



def fetch_yfinance_stock(symbol: str):
    try:
        import yfinance as yf
    except Exception:
        raise RuntimeError("yfinance not installed. Run: source .venv/bin/activate && pip install yfinance")

    t = yf.Ticker(symbol)
    fi = getattr(t, "fast_info", None) or {}
    hist = t.history(period="1d", interval="1m")
    last = None
    source_ts = None
    if hist is not None and len(hist) > 0:
        last = float(hist["Close"].iloc[-1])
        try:
            ts = hist.index[-1]
            source_ts = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        except Exception:
            source_ts = None

    return {
        "skill": "market-financial",
        "provider": "yfinance",
        "symbol": symbol.upper(),
        "asset": "stock",
        "last": last if last is not None else _f(fi.get("lastPrice")),
        "open": _f(fi.get("open")),
        "high": _f(fi.get("dayHigh")),
        "low": _f(fi.get("dayLow")),
        "prev_close": _f(fi.get("previousClose")),
        "market_cap": _f(fi.get("marketCap")),
        "source_ts": source_ts,
        "fetched_at": now_iso(),
    }


def fetch_yfinance_option(symbol: str, expiry: str, strike: float, right: str):
    try:
        import yfinance as yf
    except Exception:
        raise RuntimeError("yfinance not installed. Run: source .venv/bin/activate && pip install yfinance")

    t = yf.Ticker(symbol)
    chain = t.option_chain(expiry)
    table = chain.calls if right == "call" else chain.puts

    if table is None or table.empty:
        raise RuntimeError(f"No option data: {symbol} {expiry} {right}")

    row = table.loc[(table["strike"] - float(strike)).abs().idxmin()].to_dict()

    return {
        "skill": "market-financial",
        "provider": "yfinance",
        "symbol": symbol.upper(),
        "asset": "option",
        "expiry": expiry,
        "right": right,
        "target_strike": strike,
        "matched_strike": _f(row.get("strike")),
        "contract_symbol": row.get("contractSymbol"),
        "last": _f(row.get("lastPrice")),
        "bid": _f(row.get("bid")),
        "ask": _f(row.get("ask")),
        "volume": _i(row.get("volume")),
        "open_interest": _i(row.get("openInterest")),
        "implied_volatility": _f(row.get("impliedVolatility")),
        "in_the_money": bool(row.get("inTheMoney")) if row.get("inTheMoney") is not None else None,
        "fetched_at": now_iso(),
    }

def fetch_ibkr_stock(symbol: str):
    try:
        from ib_insync import IB, Stock
    except Exception:
        raise RuntimeError("ib-insync not installed. Run: pip install ib-insync")

    host = os.getenv("IBKR_HOST", "127.0.0.1")
    port = int(os.getenv("IBKR_PORT", "7497"))
    cid = int(os.getenv("IBKR_CLIENT_ID", "77"))

    ib = IB()
    ib.connect(host, port, clientId=cid, readonly=True, timeout=5)
    try:
        c = Stock(symbol.upper(), "SMART", "USD")
        cds = ib.qualifyContracts(c)
        if not cds:
            raise RuntimeError(f"Contract not found: {symbol}")
        ticker = ib.reqMktData(cds[0], "", False, False)
        ib.sleep(1.2)
        last = ticker.last if ticker.last is not None else ticker.marketPrice()

        return {
            "skill": "market-financial",
            "provider": "ibkr",
            "symbol": symbol.upper(),
            "asset": "stock",
            "last": _f(last),
            "bid": _f(ticker.bid),
            "ask": _f(ticker.ask),
            "close": _f(ticker.close),
            "fetched_at": now_iso(),
            "note": f"from TWS/Gateway {host}:{port} clientId={cid}",
        }
    finally:
        ib.disconnect()


def _longbridge_context():
    try:
        from longport.openapi import Config, QuoteContext
    except Exception:
        raise RuntimeError("longport not installed. Run: pip install longport")

    app_key = os.getenv("LONGPORT_APP_KEY", "").strip()
    app_secret = os.getenv("LONGPORT_APP_SECRET", "").strip()
    access_token = os.getenv("LONGPORT_ACCESS_TOKEN", "").strip()
    if not (app_key and app_secret and access_token):
        raise RuntimeError("LONGPORT_APP_KEY/LONGPORT_APP_SECRET/LONGPORT_ACCESS_TOKEN are required")

    http_url = os.getenv("LONGPORT_HTTP_URL", "").strip() or None
    cfg = Config(app_key=app_key, app_secret=app_secret, access_token=access_token, http_url=http_url)
    return QuoteContext(cfg)


def fetch_longbridge_stock(symbol: str):
    qc = _longbridge_context()
    resp = qc.quote([symbol])
    if not resp:
        raise RuntimeError(f"No longbridge quote for {symbol}")

    q = resp[0]
    pre = _g(q, "pre_market_quote")
    post = _g(q, "post_market_quote")
    return {
        "skill": "market-financial",
        "provider": "longbridge",
        "symbol": symbol,
        "asset": "stock",
        "last": _f(_g(q, "last_done", "last")),
        "open": _f(_g(q, "open")),
        "high": _f(_g(q, "high")),
        "low": _f(_g(q, "low")),
        "prev_close": _f(_g(q, "prev_close", "pre_close")),
        "volume": _i(_g(q, "volume")),
        "turnover": _f(_g(q, "turnover")),
        "trade_status": str(_g(q, "trade_status")) if _g(q, "trade_status") is not None else None,
        "source_ts": str(_g(q, "timestamp")) if _g(q, "timestamp") is not None else None,
        "pre_market": {
            "last": _f(_g(pre, "last_done")) if pre else None,
            "high": _f(_g(pre, "high")) if pre else None,
            "low": _f(_g(pre, "low")) if pre else None,
            "volume": _i(_g(pre, "volume")) if pre else None,
            "turnover": _f(_g(pre, "turnover")) if pre else None,
            "ts": str(_g(pre, "timestamp")) if pre and _g(pre, "timestamp") is not None else None,
        },
        "post_market": {
            "last": _f(_g(post, "last_done")) if post else None,
            "high": _f(_g(post, "high")) if post else None,
            "low": _f(_g(post, "low")) if post else None,
            "volume": _i(_g(post, "volume")) if post else None,
            "turnover": _f(_g(post, "turnover")) if post else None,
            "ts": str(_g(post, "timestamp")) if post and _g(post, "timestamp") is not None else None,
        },
        "fetched_at": now_iso(),
    }



def _map_longbridge_period(period: str):
    from longport.openapi import Period
    m = {
        "1m": Period.Min_1,
        "2m": Period.Min_2,
        "3m": Period.Min_3,
        "5m": Period.Min_5,
        "10m": Period.Min_10,
        "15m": Period.Min_15,
        "20m": Period.Min_20,
        "30m": Period.Min_30,
        "45m": Period.Min_45,
        "60m": Period.Min_60,
        "120m": Period.Min_120,
        "180m": Period.Min_180,
        "240m": Period.Min_240,
        "1d": Period.Day,
        "1w": Period.Week,
        "1mo": Period.Month,
        "1q": Period.Quarter,
        "1y": Period.Year,
    }
    key = period.strip().lower()
    if key not in m:
        raise RuntimeError(f"Unsupported kline period: {period}")
    return m[key]


def fetch_longbridge_kline(symbol: str, period: str, count: int):
    from longport.openapi import AdjustType
    qc = _longbridge_context()
    p = _map_longbridge_period(period)
    bars = qc.candlesticks(symbol, p, int(count), AdjustType.NoAdjust)
    out = []
    for b in bars:
        out.append({
            "ts": str(_g(b, "timestamp")),
            "open": _f(_g(b, "open")),
            "high": _f(_g(b, "high")),
            "low": _f(_g(b, "low")),
            "close": _f(_g(b, "close")),
            "volume": _i(_g(b, "volume")),
            "turnover": _f(_g(b, "turnover")),
            "session": str(_g(b, "trade_session")) if _g(b, "trade_session") is not None else None,
        })
    return {
        "skill": "market-financial",
        "provider": "longbridge",
        "symbol": symbol,
        "asset": "kline",
        "period": period,
        "count": len(out),
        "bars": out,
        "fetched_at": now_iso(),
    }

def fetch_longbridge_option(symbol: str, expiry: str, strike: float, right: str):
    qc = _longbridge_context()

    try:
        exp_list = qc.option_chain_expiry_date_list(symbol)
    except Exception as e:
        raise RuntimeError(f"longbridge option expiry list failed: {e}")

    if not exp_list:
        raise RuntimeError(f"No option expiry list for {symbol}")

    target_date = date.fromisoformat(expiry)
    if target_date not in exp_list:
        nearest = min(exp_list, key=lambda d: abs((d - target_date).days))
    else:
        nearest = target_date

    chain = qc.option_chain_info_by_date(symbol, nearest)
    if not chain:
        raise RuntimeError(f"No option chain info for {symbol} @ {nearest}")

    best = min(chain, key=lambda x: abs((_f(_g(x, "strike_price", "strike")) or 0.0) - strike))
    call_sym = _g(best, "call_symbol", "call")
    put_sym = _g(best, "put_symbol", "put")
    option_symbol = call_sym if right == "call" else put_sym
    if not option_symbol:
        raise RuntimeError(f"No {right} contract symbol found at strike {strike}")

    q = qc.option_quote([option_symbol])
    if not q:
        raise RuntimeError(f"No option quote for {option_symbol}")
    oq = q[0]

    return {
        "skill": "market-financial",
        "provider": "longbridge",
        "symbol": symbol,
        "asset": "option",
        "expiry": str(nearest),
        "right": right,
        "target_strike": strike,
        "matched_strike": _f(_g(best, "strike_price", "strike")),
        "contract_symbol": option_symbol,
        "last": _f(_g(oq, "last_done", "last")),
        "prev_close": _f(_g(oq, "prev_close", "pre_close")),
        "open": _f(_g(oq, "open")),
        "high": _f(_g(oq, "high")),
        "low": _f(_g(oq, "low")),
        "volume": _i(_g(oq, "volume")),
        "turnover": _f(_g(oq, "turnover")),
        "open_interest": _i(_g(oq, "open_interest")),
        "implied_volatility": _f(_g(oq, "implied_volatility")),
        "source_ts": str(_g(oq, "timestamp")) if _g(oq, "timestamp") is not None else None,
        "fetched_at": now_iso(),
    }



def _load_routes_from_openclaw():
    paths = [
        os.path.expanduser("~/.openclaw/openclaw.json"),
        "/Users/kyle/.openclaw/openclaw.json",
    ]
    for fp in paths:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                obj = json.load(f)
            return (((obj.get("skills") or {}).get("entries") or {}).get("market-financial") or {}).get("config", {}).get("routes", {})
        except Exception:
            continue
    return {}


def _route_provider(symbol: str, asset: str):
    routes = _load_routes_from_openclaw()
    sym = (symbol or "").upper()
    is_crypto = "-" in sym and (sym.endswith("USDT") or sym.endswith("USDC") or "SWAP" in sym)

    if is_crypto:
        chosen = ((routes.get("crypto") or {}).get(asset)) or ((routes.get("crypto") or {}).get("spot")) or "okx"
    else:
        chosen = ((routes.get("equity") or {}).get(asset)) or ((routes.get("equity") or {}).get("stock")) or "longbridge"

    fall = []
    fobj = routes.get("fallback") or {}
    if isinstance(fobj.get(asset), list):
        fall = [x for x in fobj.get(asset) if x != chosen]
    return chosen, fall


def _symbol_for_yfinance(symbol: str):
    s = (symbol or "").upper()
    if s.endswith(".US"):
        return s[:-3]
    return symbol


def _execute_provider(provider: str, args):
    if provider == "okx":
        return fetch_okx(args.symbol)
    if provider == "ibkr":
        if args.asset == "option":
            raise RuntimeError("ibkr option query not implemented yet in this script")
        if args.asset == "kline":
            raise RuntimeError("ibkr kline query not implemented yet in this script")
        return fetch_ibkr_stock(args.symbol)
    if provider == "yfinance":
        if args.asset == "option":
            if not args.expiry or args.strike is None:
                raise RuntimeError("yfinance option requires --expiry and --strike")
            return fetch_yfinance_option(_symbol_for_yfinance(args.symbol), args.expiry, args.strike, args.right)
        if args.asset == "kline":
            raise RuntimeError("yfinance kline query not implemented yet in this script")
        return fetch_yfinance_stock(_symbol_for_yfinance(args.symbol))
    if provider == "longbridge":
        if args.asset == "option":
            if not args.expiry or args.strike is None:
                raise RuntimeError("longbridge option requires --expiry and --strike")
            return fetch_longbridge_option(args.symbol, args.expiry, args.strike, args.right)
        if args.asset == "kline":
            return fetch_longbridge_kline(args.symbol, args.period, args.count)
        return fetch_longbridge_stock(args.symbol)
    raise RuntimeError(f"Unknown provider: {provider}")

def main():
    p = argparse.ArgumentParser(description="Unified market quote tool")
    p.add_argument("--provider", choices=["okx", "ibkr", "longbridge", "yfinance"], help="optional; omit to use configured routes")
    p.add_argument("--symbol", required=True)
    p.add_argument("--asset", default="spot", choices=["spot", "stock", "option", "kline"])
    p.add_argument("--expiry")
    p.add_argument("--strike", type=float)
    p.add_argument("--right", choices=["call", "put"], default="call")
    p.add_argument("--period", default="1m", help="kline period: 1m,5m,15m,30m,60m,1d,1w,1mo")
    p.add_argument("--count", type=int, default=20, help="kline bars count")
    p.add_argument("--pretty", action="store_true")
    args = p.parse_args()
    provider = args.provider
    if not provider:
        provider, fallbacks = _route_provider(args.symbol, args.asset)
    else:
        fallbacks = []

    tried = []
    last_err = None
    for pvd in [provider] + fallbacks:
        tried.append(pvd)
        try:
            out = _execute_provider(pvd, args)
            out["routed_provider"] = pvd
            out["route_mode"] = "configured" if args.provider is None else "explicit"
            out["tried_providers"] = tried
            break
        except Exception as e:
            last_err = e
            continue
    else:
        raise RuntimeError(f"all providers failed: {tried}; last_error={last_err}")

    if args.pretty:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e), "ts": now_iso()}), file=sys.stderr)
        sys.exit(1)
