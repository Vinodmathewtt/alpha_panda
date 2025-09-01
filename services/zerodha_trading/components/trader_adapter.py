from __future__ import annotations

from typing import Any, Dict

from core.trading.interfaces import BrokerOrderClient


class ZerodhaTraderAdapter(BrokerOrderClient):
    """Thin adapter placeholder that will wrap the existing Zerodha trader.

    Phase 2: compiles/imports. Implementation will be completed in Phase 3.
    """

    def __init__(self, trader_factory: Any) -> None:
        self._trader_factory = trader_factory

    async def place_order(self, order: Dict[str, Any]) -> Dict[str, Any]:
        # Phase 2 placeholder
        return {"status": "noop", "broker": "zerodha"}

    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        # Phase 2 placeholder
        return {"status": "noop", "broker": "zerodha", "order_id": order_id}

