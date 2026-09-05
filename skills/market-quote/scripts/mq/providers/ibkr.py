"""Interactive Brokers via ib_insync (TWS / IB Gateway must be running with API
enabled). Read-only connection. Quote only for now; option/chain/kline are
future work — add them here and extend `capabilities`."""
from __future__ import annotations

import os
from typing import Any, Dict

from ..base import Provider, ProviderError, build_result, f


class IBKR(Provider):
    name = "ibkr"
    markets = frozenset({"equity"})
    capabilities = frozenset({"quote"})
    description = "Interactive Brokers (ib_insync) via local TWS/Gateway; US stock quote only (read-only)"

    def available(self):
        try:
            import ib_insync  # noqa: F401
            return True, ""
        except Exception:
            return False, "ib-insync not installed (pip install ib-insync)"

    def normalize_symbol(self, symbol: str) -> str:
        sym = symbol.strip().upper()
        return sym[:-3] if sym.endswith(".US") else sym

    def quote(self, symbol: str) -> Dict[str, Any]:
        self._check("quote")
        from ib_insync import IB, Stock
        host = os.getenv("IBKR_HOST", "127.0.0.1")
        port = int(os.getenv("IBKR_PORT", "7497"))
        cid = int(os.getenv("IBKR_CLIENT_ID", "77"))
        ps = self.normalize_symbol(symbol)
        ib = IB()
        try:
            ib.connect(host, port, clientId=cid, readonly=True, timeout=5)
        except Exception as e:
            raise ProviderError(f"ibkr: cannot connect {host}:{port} ({e}); is TWS/Gateway running with API enabled?")
        try:
            cds = ib.qualifyContracts(Stock(ps, "SMART", "USD"))
            if not cds:
                raise ProviderError(f"ibkr: contract not found: {ps}")
            t = ib.reqMktData(cds[0], "", False, False)
            ib.sleep(1.2)
            last = t.last if f(t.last) is not None else t.marketPrice()
            return build_result(
                self.name, "quote", symbol, ps,
                last=f(last), bid=f(t.bid), ask=f(t.ask), close=f(t.close),
                note=f"TWS/Gateway {host}:{port} clientId={cid}",
            )
        finally:
            ib.disconnect()


PROVIDER = IBKR()
