"""Provider contract, shared helpers, and normalized result builders.

A provider is a class with:
  name          short id used in CLI/config ("okx", "yfinance", ...)
  markets       which symbol classes it serves: {"crypto"} / {"equity"} / both
  capabilities  subset of ASSETS it implements
  available()   -> (ok, reason) — deps installed + credentials present
  quote/option/chain/kline(...) -> dict (see build_result)

Anything a provider does not implement raises NotSupported so the router
can fall through to the next provider instead of crashing.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import SKILL_NAME

ASSETS = ("quote", "option", "chain", "kline")
MARKETS = ("crypto", "equity")


class ProviderError(RuntimeError):
    """Provider ran but could not produce data (bad symbol, upstream error)."""


class NotSupported(ProviderError):
    """Provider does not implement this asset / market."""


class NotAvailable(ProviderError):
    """Provider cannot run here (missing dependency or credentials)."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def f(v: Any) -> Optional[float]:
    """float or None. NaN/inf become None so JSON output stays valid."""
    try:
        if v is None:
            return None
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def i(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        x = float(v)
        return int(x) if math.isfinite(x) else None
    except Exception:
        return None


def g(obj: Any, *names: str) -> Any:
    """First existing attribute (or dict key) among names, else None."""
    for n in names:
        if isinstance(obj, dict):
            if n in obj:
                return obj[n]
        elif hasattr(obj, n):
            return getattr(obj, n)
    return None


def s(v: Any) -> Optional[str]:
    return None if v is None else str(v)


def build_result(provider: str, asset: str, symbol: str, provider_symbol: str, **fields: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "skill": SKILL_NAME,
        "provider": provider,
        "asset": asset,
        "symbol": symbol,
        "provider_symbol": provider_symbol,
    }
    out.update(fields)
    out["fetched_at"] = now_iso()
    return out


def classify_symbol(symbol: str) -> str:
    """crypto for OKX-style pairs (BTC-USDT, BTC-USDT-SWAP, ETH/USDC); else equity."""
    sym = (symbol or "").strip().upper().replace("/", "-")
    parts = sym.split("-")
    if len(parts) >= 2 and parts[0].isalnum() and parts[1] in ("USDT", "USDC", "USD", "BTC", "ETH"):
        return "crypto"
    return "equity"


class Provider:
    name: str = ""
    markets: frozenset = frozenset()
    capabilities: frozenset = frozenset()
    description: str = ""

    # --- lifecycle -------------------------------------------------------
    def available(self):
        """Return (True, "") or (False, reason). Must not raise."""
        return True, ""

    def normalize_symbol(self, symbol: str) -> str:
        return symbol.strip()

    def _check(self, asset: str) -> None:
        if asset not in self.capabilities:
            raise NotSupported(f"{self.name} does not support '{asset}'")
        ok, why = self.available()
        if not ok:
            raise NotAvailable(f"{self.name}: {why}")

    # --- data -------------------------------------------------------------
    def quote(self, symbol: str) -> Dict[str, Any]:
        raise NotSupported(f"{self.name} does not support 'quote'")

    def option(self, symbol: str, expiry: str, strike: float, right: str) -> Dict[str, Any]:
        raise NotSupported(f"{self.name} does not support 'option'")

    def chain(self, symbol: str, expiry: Optional[str]) -> Dict[str, Any]:
        raise NotSupported(f"{self.name} does not support 'chain'")

    def kline(self, symbol: str, period: str, count: int) -> Dict[str, Any]:
        raise NotSupported(f"{self.name} does not support 'kline'")
