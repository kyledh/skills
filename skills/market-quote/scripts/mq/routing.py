"""Pick which provider(s) serve a request.

Explicit --provider wins. Otherwise a routes config (optional) is consulted,
and finally a sensible default: the first *available* provider for the
symbol's market that supports the asset. Fallbacks come from the config or,
when unset, from the remaining available providers.

Config lookup order:
  1. $MARKET_ROUTES_JSON  (inline JSON)
  2. $MARKET_ROUTES_FILE  (path)
  3. ~/.config/market-quote/routes.json
Schema:
  {"crypto": {"quote": "okx", "kline": "okx"},
   "equity": {"quote": "longbridge", "option": "longbridge", "chain": "yfinance", "kline": "longbridge"},
   "fallback": {"quote": ["yfinance"], "option": ["yfinance"]}}
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

from . import providers
from .base import classify_symbol

ROUTES_JSON_ENV = "MARKET_ROUTES_JSON"
ROUTES_FILE_ENV = "MARKET_ROUTES_FILE"
DEFAULT_ROUTES_FILE = "~/.config/market-quote/routes.json"

# Preference order when nothing is configured (first available wins).
DEFAULT_ORDER = {"crypto": ["okx"], "equity": ["longbridge", "yfinance", "ibkr"]}


def load_routes() -> Dict:
    inline = os.getenv(ROUTES_JSON_ENV)
    if inline:
        try:
            obj = json.loads(inline)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    fp = os.path.expanduser(os.getenv(ROUTES_FILE_ENV) or DEFAULT_ROUTES_FILE)
    try:
        with open(fp, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def candidates(market: str, asset: str) -> List[str]:
    """Providers serving this market+asset, preferred order, available first."""
    ordered = [n for n in DEFAULT_ORDER.get(market, []) if n in providers.names()]
    ordered += [n for n in providers.names() if n not in ordered]
    ok, bad = [], []
    for n in ordered:
        p = providers.get(n)
        if market not in p.markets or asset not in p.capabilities:
            continue
        (ok if p.available()[0] else bad).append(n)
    return ok + bad


def plan(symbol: str, asset: str, explicit: str | None = None) -> Tuple[List[str], str]:
    """Return (ordered provider names to try, mode)."""
    if explicit:
        return [explicit], "explicit"
    market = classify_symbol(symbol)
    routes = load_routes()
    primary = (routes.get(market) or {}).get(asset)
    fall = (routes.get("fallback") or {}).get(asset)
    cands = candidates(market, asset)
    if primary:
        chain = [primary] + [x for x in (fall if isinstance(fall, list) else cands) if x != primary]
        return chain, "configured"
    return cands, "auto"
