"""Yahoo Finance via the `yfinance` package. Free, delayed; good fallback for US
equities and options, and for anyone without a broker account."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..base import Provider, ProviderError, build_result, f, i

INTERVALS = {
    "1m": ("1m", "7d"), "2m": ("2m", "60d"), "5m": ("5m", "60d"), "15m": ("15m", "60d"),
    "30m": ("30m", "60d"), "60m": ("60m", "730d"), "1h": ("60m", "730d"),
    "1d": ("1d", "5y"), "1w": ("1wk", "max"), "1mo": ("1mo", "max"),
}


def _yf():
    try:
        import yfinance  # noqa: WPS433
        return yfinance
    except Exception:
        raise ProviderError("yfinance not installed: pip install yfinance")


class YFinance(Provider):
    name = "yfinance"
    markets = frozenset({"equity"})
    capabilities = frozenset({"quote", "option", "chain", "kline"})
    description = "Yahoo Finance (yfinance): equities, option chains, candles; free, may be delayed"

    def available(self):
        try:
            import yfinance  # noqa: F401
            return True, ""
        except Exception:
            return False, "yfinance not installed (pip install yfinance)"

    def normalize_symbol(self, symbol: str) -> str:
        sym = symbol.strip().upper()
        if sym.endswith(".US"):
            return sym[:-3]
        if sym.endswith(".HK"):  # Yahoo wants 4-digit HK codes: 700.HK -> 0700.HK
            code, _ = sym.rsplit(".", 1)
            if code.isdigit():
                return f"{int(code):04d}.HK"
        return sym

    def quote(self, symbol: str) -> Dict[str, Any]:
        self._check("quote")
        yf = _yf()
        ps = self.normalize_symbol(symbol)
        t = yf.Ticker(ps)
        fi = getattr(t, "fast_info", None) or {}
        hist = t.history(period="1d", interval="1m")
        last, source_ts = None, None
        if hist is not None and len(hist) > 0:
            last = f(hist["Close"].iloc[-1])
            ts = hist.index[-1]
            source_ts = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        if last is None:
            last = f(fi.get("lastPrice"))
        if last is None:
            raise ProviderError(f"yfinance: no data for {ps}")
        return build_result(
            self.name, "quote", symbol, ps,
            last=last, open=f(fi.get("open")), high=f(fi.get("dayHigh")), low=f(fi.get("dayLow")),
            prev_close=f(fi.get("previousClose")), volume=i(fi.get("lastVolume")),
            market_cap=f(fi.get("marketCap")), currency=fi.get("currency"), source_ts=source_ts,
        )

    def _chain_for(self, t, ps: str, expiry: Optional[str]):
        expiries = list(t.options or [])
        if not expiries:
            raise ProviderError(f"yfinance: no options listed for {ps}")
        if expiry and expiry in expiries:
            chosen = expiry
        elif expiry:
            from datetime import date
            target = date.fromisoformat(expiry)
            chosen = min(expiries, key=lambda d: abs((date.fromisoformat(d) - target).days))
        else:
            chosen = expiries[0]
        return expiries, chosen, t.option_chain(chosen)

    def option(self, symbol: str, expiry: str, strike: float, right: str) -> Dict[str, Any]:
        self._check("option")
        yf = _yf()
        ps = self.normalize_symbol(symbol)
        t = yf.Ticker(ps)
        _, chosen, ch = self._chain_for(t, ps, expiry)
        table = ch.calls if right == "call" else ch.puts
        if table is None or table.empty:
            raise ProviderError(f"yfinance: no {right} data for {ps} {chosen}")
        row = table.loc[(table["strike"] - float(strike)).abs().idxmin()].to_dict()
        return build_result(
            self.name, "option", symbol, ps,
            expiry=chosen, requested_expiry=expiry, right=right,
            target_strike=strike, matched_strike=f(row.get("strike")),
            contract_symbol=row.get("contractSymbol"),
            last=f(row.get("lastPrice")), bid=f(row.get("bid")), ask=f(row.get("ask")),
            volume=i(row.get("volume")), open_interest=i(row.get("openInterest")),
            implied_volatility=f(row.get("impliedVolatility")),
            in_the_money=bool(row.get("inTheMoney")) if row.get("inTheMoney") is not None else None,
        )

    def chain(self, symbol: str, expiry: Optional[str]) -> Dict[str, Any]:
        self._check("chain")
        yf = _yf()
        ps = self.normalize_symbol(symbol)
        t = yf.Ticker(ps)
        expiries, chosen, ch = self._chain_for(t, ps, expiry)

        def rows(table):
            out = []
            for r in table.to_dict("records"):
                out.append({
                    "strike": f(r.get("strike")), "contract_symbol": r.get("contractSymbol"),
                    "last": f(r.get("lastPrice")), "bid": f(r.get("bid")), "ask": f(r.get("ask")),
                    "volume": i(r.get("volume")), "open_interest": i(r.get("openInterest")),
                    "implied_volatility": f(r.get("impliedVolatility")),
                })
            return out

        return build_result(
            self.name, "chain", symbol, ps,
            expiries=expiries, expiry=chosen, calls=rows(ch.calls), puts=rows(ch.puts),
        )

    def kline(self, symbol: str, period: str, count: int) -> Dict[str, Any]:
        self._check("kline")
        yf = _yf()
        ps = self.normalize_symbol(symbol)
        iv = INTERVALS.get(period.lower())
        if not iv:
            raise ProviderError(f"yfinance: unsupported period '{period}'. Use one of {', '.join(INTERVALS)}")
        interval, span = iv
        hist = yf.Ticker(ps).history(period=span, interval=interval)
        if hist is None or len(hist) == 0:
            raise ProviderError(f"yfinance: no candles for {ps} @ {period}")
        hist = hist.tail(max(1, int(count)))
        bars = [
            {"ts": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
             "open": f(r.get("Open")), "high": f(r.get("High")), "low": f(r.get("Low")),
             "close": f(r.get("Close")), "volume": i(r.get("Volume"))}
            for idx, r in zip(hist.index, hist.to_dict("records"))
        ]
        return build_result(self.name, "kline", symbol, ps, period=period, count=len(bars), bars=bars)


PROVIDER = YFinance()
