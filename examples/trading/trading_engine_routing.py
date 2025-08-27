"""
Trading Engine Routing Pattern Example

Demonstrates how TradingEngineService routes validated signals
to appropriate traders based on configuration with topic segregation.
"""

from typing import Dict, Any

# TradingEngineService routes based on configuration
async def _handle_signal(self, signal: Dict[str, Any]):
    strategy_id = signal.get('strategy_id')
    
    # 1. ALWAYS execute paper trading (if enabled)
    if self.settings.paper_trading.enabled:
        last_price = self.last_prices.get(instrument_token)
        await self.paper_trader.execute_order(signal, last_price)
    
    # 2. Check strategy-specific zerodha trading configuration
    strategy_config = await self._get_strategy_config(strategy_id)
    if strategy_config.get("zerodha_trading_enabled", False):
        if self.settings.zerodha.enabled:
            await self.zerodha_trader.execute_order(signal)

# PaperTrader publishes to segregated topic
await self.producer.send(
    topic="orders.filled.paper",  # NEVER mix with zerodha topics
    key=fill_event["key"],
    value={
        "data": {
            "trading_mode": "paper",  # ALWAYS identify mode
            "fill_price": simulated_price,
            "commission": calculated_commission
        }
    }
)

# ZerodhaTrader publishes to segregated topic  
await self.producer.send(
    topic="orders.filled.zerodha",   # NEVER mix with paper topics
    key=fill_event["key"],
    value={
        "data": {
            "trading_mode": "zerodha",   # ALWAYS identify mode
            "broker_order_id": actual_id,
            "fill_price": broker_price
        }
    }
)