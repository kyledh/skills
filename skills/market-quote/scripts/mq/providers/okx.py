"""OKX public market data (no credentials). Crypto spot & perpetual swaps."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Dict

from ..base import Provider, ProviderError, build_result, f, i

BASE = "https://www.okx.com/api/v5/market"
PERIODS = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "60m": "1H", "1h": "1H", "2h": "2H", "4h": "4H", "6h": "6H", "12h": "12H",
    "1d": "1D", "1w": "1W", "1mo": "1M",
}


def _get(path: str, params: Dict[str, Any], timeout: int = 10) -> Any:
    url = f"{BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        j = json.loads(r.read().decode("utf-8"))
    if str(j.get("code")) != "0" or not j.get("data"):
        raise ProviderError(f"okx {path}: code={j.get('code')} msg={j.get('msg')}")
    return j["data"]


class OKX(Provider):
    name = "okx"
    markets = frozenset({"crypto"})
    capabilities = frozenset({"quote", "kline"})
    description = "OKX public REST: crypto spot/perp ticker and candles (no API key)"

    def normalize_symbol(self, symbol: str) -> str:
        sym = symbol.strip().upper().replace("/", "-")
        if sym.endswith("-PERP"):
            sym = sym[:-5] + "-SWAP"
        return sym

    def quote(self, symbol: str) -> Dict[str, Any]:
        self._check("quote")
        inst = self.normalize_symbol(symbol)
        row = _get("ticker", {"instId": inst})[0]
        return build_result(
            self.name, "quote", symbol, inst,
            last=f(row.get("last")), bid=f(row.get("bidPx")), ask=f(row.get("askPx")),
            open_24h=f(row.get("open24h")), high_24h=f(row.get("high24h")), low_24h=f(row.get("low24h")),
            volume_24h=f(row.get("vol24h")), source_ts_ms=i(row.get("ts")),
        )

    def kline(self, symbol: str, period: str, count: int) -> Dict[str, Any]:
        self._check("kline")
        inst = self.normalize_symbol(symbol)
        bar = PERIODS.get(period.lower())
        if not bar:
            raise ProviderError(f"okx: unsupported period '{period}'. Use one of {', '.join(PERIODS)}")
        rows = _get("candles", {"instId": inst, "bar": bar, "limit": max(1, min(int(count), 300))})
        bars = [
            {"ts_ms": i(r[0]), "open": f(r[1]), "high": f(r[2]), "low": f(r[3]), "close": f(r[4]),
             "volume": f(r[5]), "confirmed": r[8] == "1" if len(r) > 8 else None}
            for r in reversed(rows)  # OKX returns newest first
        ]
        return build_result(self.name, "kline", symbol, inst, period=period, count=len(bars), bars=bars)


PROVIDER = OKX()
