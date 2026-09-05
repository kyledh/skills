#!/usr/bin/env python3
"""market-quote CLI — read-only market data across OKX / Longbridge / Yahoo / IBKR.

  market_quote.py quote  SYMBOL [--provider P]
  market_quote.py option SYMBOL --expiry YYYY-MM-DD --strike N [--right call|put] [--provider P]
  market_quote.py chain  SYMBOL [--expiry YYYY-MM-DD] [--provider P]
  market_quote.py kline  SYMBOL [--period 1m] [--count 20] [--provider P]
  market_quote.py compare SYMBOL [--providers a,b,c]
  market_quote.py providers

Output: one JSON document on stdout (add --pretty). Errors: JSON on stderr, exit 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from mq import SKILL_NAME, providers, routing
from mq.base import ASSETS, NotAvailable, NotSupported, ProviderError, classify_symbol, f, now_iso


def _call(p, asset: str, a) -> Dict[str, Any]:
    if asset == "quote":
        return p.quote(a.symbol)
    if asset == "option":
        return p.option(a.symbol, a.expiry, float(a.strike), a.right)
    if asset == "chain":
        return p.chain(a.symbol, a.expiry)
    if asset == "kline":
        return p.kline(a.symbol, a.period, int(a.count))
    raise ValueError(asset)


def run_with_fallback(asset: str, a) -> Dict[str, Any]:
    chain, mode = routing.plan(a.symbol, asset, a.provider)
    if not chain:
        raise ProviderError(f"no provider supports '{asset}' for {classify_symbol(a.symbol)} symbol {a.symbol}")
    errors: Dict[str, str] = {}
    for name in chain:
        try:
            out = _call(providers.get(name), asset, a)
        except KeyError as e:
            raise ProviderError(str(e))
        except (NotSupported, NotAvailable, ProviderError) as e:
            errors[name] = str(e)
            continue
        except Exception as e:  # SDK / network surprises
            errors[name] = f"{type(e).__name__}: {e}"
            continue
        out["route"] = {"mode": mode, "tried": list(errors) + [name], "errors": errors or None}
        return out
    raise ProviderError(f"all providers failed for {asset} {a.symbol}: {json.dumps(errors, ensure_ascii=False)}")


def cmd_compare(a) -> Dict[str, Any]:
    market = classify_symbol(a.symbol)
    names = [x.strip() for x in a.providers.split(",")] if a.providers else routing.candidates(market, "quote")
    results: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    for n in names:
        try:
            r = providers.get(n).quote(a.symbol)
            results[n] = {k: r.get(k) for k in ("last", "bid", "ask", "prev_close", "source_ts", "source_ts_ms", "provider_symbol")}
        except Exception as e:
            errors[n] = str(e)
    lasts = {n: r["last"] for n, r in results.items() if f(r.get("last")) is not None}
    stats = None
    if len(lasts) >= 2:
        hi, lo = max(lasts.values()), min(lasts.values())
        ref = sum(lasts.values()) / len(lasts)
        stats = {"min": lo, "max": hi, "spread_abs": hi - lo, "spread_pct": (hi - lo) / ref * 100 if ref else None,
                 "consistent": ((hi - lo) / ref * 100 if ref else 0) <= a.tolerance}
    return {"skill": SKILL_NAME, "asset": "compare", "symbol": a.symbol, "providers": results,
            "errors": errors or None, "stats": stats, "tolerance_pct": a.tolerance, "fetched_at": now_iso()}


def cmd_providers(_a) -> Dict[str, Any]:
    rows = []
    for p in providers.all_providers():
        ok, why = p.available()
        rows.append({"name": p.name, "markets": sorted(p.markets), "capabilities": [x for x in ASSETS if x in p.capabilities],
                     "available": ok, "reason": why or None, "description": p.description})
    return {"skill": SKILL_NAME, "providers": rows, "routes_config": routing.load_routes() or None}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="market_quote.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    base = argparse.ArgumentParser(add_help=False)
    base.add_argument("--pretty", action="store_true", help="indent JSON output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, help_, symbol=True, provider=True):
        sp = sub.add_parser(name, help=help_, parents=[base])
        if symbol:
            sp.add_argument("symbol", help="e.g. BTC-USDT, AAPL, AAPL.US, 700.HK")
        if provider:
            sp.add_argument("--provider", choices=providers.names(), help="force a provider (default: auto-route)")
        return sp

    add("quote", "latest price / bid / ask")
    sp = add("option", "single option contract quote (nearest expiry + strike)")
    sp.add_argument("--expiry", required=True, help="YYYY-MM-DD (nearest listed expiry is used)")
    sp.add_argument("--strike", required=True, type=float)
    sp.add_argument("--right", choices=["call", "put"], default="call")
    sp = add("chain", "option expiries + strikes for one expiry")
    sp.add_argument("--expiry", help="YYYY-MM-DD; default nearest expiry")
    sp = add("kline", "candles")
    sp.add_argument("--period", default="1d", help="1m 5m 15m 30m 1h 4h 1d 1w 1mo (provider-dependent)")
    sp.add_argument("--count", type=int, default=20)
    sp = add("compare", "same quote from several providers + spread check", provider=False)
    sp.add_argument("--providers", help="comma list; default: all available for this market")
    sp.add_argument("--tolerance", type=float, default=1.0, help="max spread %% to call sources consistent")
    add("providers", "list providers, capabilities, availability", symbol=False, provider=False)
    return ap


def main() -> int:
    a = build_parser().parse_args()
    if a.cmd == "providers":
        out = cmd_providers(a)
    elif a.cmd == "compare":
        out = cmd_compare(a)
    else:
        out = run_with_fallback(a.cmd, a)
    print(json.dumps(out, ensure_ascii=False, indent=2 if a.pretty else None))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ProviderError as e:
        print(json.dumps({"skill": SKILL_NAME, "error": str(e), "ts": now_iso()}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
