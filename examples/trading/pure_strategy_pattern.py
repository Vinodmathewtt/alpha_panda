"""
Pure Strategy Pattern Example

Demonstrates how to implement pure trading strategies that are
completely decoupled from infrastructure dependencies.
"""

from typing import Generator
from strategies.base import BaseStrategy

class MomentumStrategy(BaseStrategy):
    def on_market_data(self, data, context) -> Generator:
        # Pure business logic - no infrastructure dependencies
        if self._should_buy(data):
            yield TradingSignal(
                strategy_id=self.strategy_id,
                instrument_token=data.instrument_token,
                signal_type="BUY",
                quantity=100
            )