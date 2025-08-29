# Simple Momentum Strategy
from typing import Generator, List
from decimal import Decimal
from datetime import datetime
from .base import BaseStrategy, MarketData
from core.schemas.events import SignalType, TradingSignal


class SimpleMomentumStrategy(BaseStrategy):
    """Simple momentum strategy based on price change over lookback period"""
    
    def __init__(self, strategy_id: str, parameters: dict, brokers: List[str] = None, 
                 instrument_tokens: List[int] = None):
        super().__init__(strategy_id, parameters, brokers, instrument_tokens)
        self.lookback_period = parameters.get("lookback_period", 20)
        self.momentum_threshold = parameters.get("momentum_threshold", 0.02)  # 2%
        self.position_size = parameters.get("position_size", 100)

    def on_market_data(self, data: MarketData) -> Generator[TradingSignal, None, None]:
        """Generate momentum-based trading signals"""
        
        # Add to history
        self._add_market_data(data)
        
        # Need enough history for momentum calculation
        if len(self._market_data_history) < self.lookback_period:
            return
            
        # Calculate momentum
        current_price = data.last_price
        lookback_price = self._market_data_history[-self.lookback_period].last_price
        
        if lookback_price == 0:
            return
            
        momentum = (current_price - lookback_price) / lookback_price
        
        # Generate signals based on momentum
        if momentum > self.momentum_threshold:
            # Strong upward momentum - BUY signal
            yield TradingSignal(
                strategy_id=self.strategy_id,
                instrument_token=data.instrument_token,
                signal_type=SignalType.BUY,
                quantity=self.position_size,
                price=current_price,
                timestamp=data.timestamp,
                confidence=float(abs(momentum)),
                metadata={
                    "momentum": float(momentum),
                    "lookback_period": self.lookback_period,
                    "current_price": float(current_price),
                    "lookback_price": float(lookback_price)
                }
            )
            
        elif momentum < -self.momentum_threshold:
            # Strong downward momentum - SELL signal
            yield TradingSignal(
                strategy_id=self.strategy_id,
                instrument_token=data.instrument_token,
                signal_type=SignalType.SELL,
                quantity=self.position_size,
                price=current_price,
                timestamp=data.timestamp,
                confidence=float(abs(momentum)),
                metadata={
                    "momentum": float(momentum),
                    "lookback_period": self.lookback_period,
                    "current_price": float(current_price),
                    "lookback_price": float(lookback_price)
                }
            )


# Alias for backward compatibility and YAML configuration
class MomentumStrategy(SimpleMomentumStrategy):
    """Alias for SimpleMomentumStrategy to support YAML configuration"""
    pass