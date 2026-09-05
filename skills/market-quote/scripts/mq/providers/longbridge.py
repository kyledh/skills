"""Longbridge OpenAPI (longport SDK). Real-time HK/US/CN equities, option chains,
candles. Needs LONGPORT_APP_KEY / LONGPORT_APP_SECRET / LONGPORT_ACCESS_TOKEN."""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict, Optional

from ..base import Provider, ProviderError, build_result, f, g, i, s

ENV = ("LONGPORT_APP_KEY", "LONGPORT_APP_SECRET", "LONGPORT_ACCESS_TOKEN")
PERIODS = {
    "1m": "Min_1", "2m": "Min_2", "3m": "Min_3", "5m": "Min_5", "10m": "Min_10", "15m": "Min_15",
    "20m": "Min_20", "30m": "Min_30", "45m": "Min_45", "60m": "Min_60", "1h": "Min_60",
    "2h": "Min_120", "3h": "Min_180", "4h": "Min_240",
    "1d": "Day", "1w": "Week", "1mo": "Month", "1q": "Quarter", "1y": "Year",
}


def _session(pre_or_post):
    if not pre_or_post:
        return None
    return {
        "last": f(g(pre_or_post, "last_done")), "high": f(g(pre_or_post, "high")), "low": f(g(pre_or_post, "low")),
        "volume": i(g(pre_or_post, "volume")), "turnover": f(g(pre_or_post, "turnover")),
        "ts": s(g(pre_or_post, "timestamp")),
    }


class Longbridge(Provider):
    name = "longbridge"
    markets = frozenset({"equity"})
    capabilities = frozenset({"quote", "option", "chain", "kline"})
    description = "Longbridge OpenAPI: real-time HK/US equities, option chains, candles (needs LONGPORT_* keys)"

    def available(self):
        try:
            import longport  # noqa: F401
        except Exception:
            return False, "longport not installed (pip install longport)"
        missing = [k for k in ENV if not os.getenv(k, "").strip()]
        if missing:
            return False, f"missing env {', '.join(missing)}"
        return True, ""

    def normalize_symbol(self, symbol: str) -> str:
        sym = symbol.strip().upper()
        if "." not in sym and sym.isalpha():
            return f"{sym}.US"  # bare ticker -> US
        return sym

    def _ctx(self):
        from longport.openapi import Config, QuoteContext
        cfg = Config(
            app_key=os.getenv("LONGPORT_APP_KEY", "").strip(),
            app_secret=os.getenv("LONGPORT_APP_SECRET", "").strip(),
            access_token=os.getenv("LONGPORT_ACCESS_TOKEN", "").strip(),
            http_url=os.getenv("LONGPORT_HTTP_URL", "").strip() or None,
        )
        return QuoteContext(cfg)

    def quote(self, symbol: str) -> Dict[str, Any]:
        self._check("quote")
        ps = self.normalize_symbol(symbol)
        resp = self._ctx().quote([ps])
        if not resp:
            raise ProviderError(f"longbridge: no quote for {ps}")
        q = resp[0]
        return build_result(
            self.name, "quote", symbol, ps,
            last=f(g(q, "last_done", "last")), open=f(g(q, "open")), high=f(g(q, "high")), low=f(g(q, "low")),
            prev_close=f(g(q, "prev_close", "pre_close")), volume=i(g(q, "volume")), turnover=f(g(q, "turnover")),
            trade_status=s(g(q, "trade_status")), source_ts=s(g(q, "timestamp")),
            pre_market=_session(g(q, "pre_market_quote")), post_market=_session(g(q, "post_market_quote")),
        )

    def _expiry(self, qc, ps: str, expiry: Optional[str]):
        exp_list = qc.option_chain_expiry_date_list(ps)
        if not exp_list:
            raise ProviderError(f"longbridge: no option expiries for {ps}")
        if not expiry:
            return exp_list, exp_list[0]
        target = date.fromisoformat(expiry)
        return exp_list, (target if target in exp_list else min(exp_list, key=lambda d: abs((d - target).days)))

    def option(self, symbol: str, expiry: str, strike: float, right: str) -> Dict[str, Any]:
        self._check("option")
        ps = self.normalize_symbol(symbol)
        qc = self._ctx()
        _, chosen = self._expiry(qc, ps, expiry)
        chain = qc.option_chain_info_by_date(ps, chosen)
        if not chain:
            raise ProviderError(f"longbridge: empty chain for {ps} @ {chosen}")
        best = min(chain, key=lambda x: abs((f(g(x, "strike_price", "strike")) or 0.0) - strike))
        osym = g(best, "call_symbol", "call") if right == "call" else g(best, "put_symbol", "put")
        if not osym:
            raise ProviderError(f"longbridge: no {right} contract at strike {strike}")
        q = qc.option_quote([osym])
        if not q:
            raise ProviderError(f"longbridge: no quote for {osym}")
        oq = q[0]
        return build_result(
            self.name, "option", symbol, ps,
            expiry=str(chosen), requested_expiry=expiry, right=right,
            target_strike=strike, matched_strike=f(g(best, "strike_price", "strike")), contract_symbol=osym,
            last=f(g(oq, "last_done", "last")), prev_close=f(g(oq, "prev_close", "pre_close")),
            open=f(g(oq, "open")), high=f(g(oq, "high")), low=f(g(oq, "low")),
            volume=i(g(oq, "volume")), turnover=f(g(oq, "turnover")), open_interest=i(g(oq, "open_interest")),
            implied_volatility=f(g(oq, "implied_volatility")), source_ts=s(g(oq, "timestamp")),
        )

    def chain(self, symbol: str, expiry: Optional[str]) -> Dict[str, Any]:
        self._check("chain")
        ps = self.normalize_symbol(symbol)
        qc = self._ctx()
        exp_list, chosen = self._expiry(qc, ps, expiry)
        rows = qc.option_chain_info_by_date(ps, chosen) or []
        strikes = [
            {"strike": f(g(x, "strike_price", "strike")), "call_symbol": g(x, "call_symbol", "call"),
             "put_symbol": g(x, "put_symbol", "put"), "standard": g(x, "standard")}
            for x in rows
        ]
        return build_result(
            self.name, "chain", symbol, ps,
            expiries=[str(d) for d in exp_list], expiry=str(chosen), strikes=strikes,
            note="strike list only; use `option` for per-contract quotes",
        )

    def kline(self, symbol: str, period: str, count: int) -> Dict[str, Any]:
        self._check("kline")
        from longport.openapi import AdjustType, Period
        ps = self.normalize_symbol(symbol)
        key = PERIODS.get(period.lower())
        if not key:
            raise ProviderError(f"longbridge: unsupported period '{period}'. Use one of {', '.join(PERIODS)}")
        bars = self._ctx().candlesticks(ps, getattr(Period, key), max(1, int(count)), AdjustType.NoAdjust)
        out = [
            {"ts": s(g(b, "timestamp")), "open": f(g(b, "open")), "high": f(g(b, "high")), "low": f(g(b, "low")),
             "close": f(g(b, "close")), "volume": i(g(b, "volume")), "turnover": f(g(b, "turnover")),
             "session": s(g(b, "trade_session"))}
            for b in bars
        ]
        return build_result(self.name, "kline", symbol, ps, period=period, count=len(out), bars=out)


PROVIDER = Longbridge()
