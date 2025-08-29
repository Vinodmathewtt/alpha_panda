"""
Modern momentum strategy implementation using composition
Pure function approach - no inheritance
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal
from ..core.protocols import StrategyProcessor, SignalResult
from core.schemas.events import MarketTick as MarketData


class MomentumProcessor:
    """Pure momentum strategy logic - no inheritance"""
    
    def __init__(self, momentum_threshold: Decimal, lookback_periods: int, position_size: int = 100):
        self.momentum_threshold = momentum_threshold
        self.lookback_periods = lookback_periods
        self.position_size = position_size
        self._strategy_name = "momentum"
    
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """Pure function - no side effects"""
        if len(history) < self.lookback_periods:
            return None
        
        # Calculate momentum using pure calculations
        current_price = tick.last_price
        lookback_price = history[-self.lookback_periods].last_price
        
        if lookback_price == 0:
            return None
        
        momentum = (current_price - lookback_price) / lookback_price
        confidence = min(float(abs(momentum) * 100), 100.0)
        
        if momentum > self.momentum_threshold:
            return SignalResult(
                signal_type="BUY",
                confidence=confidence,
                quantity=self.position_size,
                price=current_price,
                reasoning=f"Momentum {momentum:.2%} > threshold {self.momentum_threshold:.2%}",
                metadata={
                    "momentum": float(momentum),
                    "lookback_periods": self.lookback_periods,
                    "current_price": float(current_price),
                    "lookback_price": float(lookback_price)
                }
            )
        elif momentum < -self.momentum_threshold:
            return SignalResult(
                signal_type="SELL", 
                confidence=confidence,
                quantity=self.position_size,
                price=current_price,
                reasoning=f"Momentum {momentum:.2%} < threshold {-self.momentum_threshold:.2%}",
                metadata={
                    "momentum": float(momentum),
                    "lookback_periods": self.lookback_periods,
                    "current_price": float(current_price),
                    "lookback_price": float(lookback_price)
                }
            )
        
        return None
    
    def get_required_history_length(self) -> int:
        return self.lookback_periods
    
    def supports_instrument(self, token: int) -> bool:
        return True  # Momentum can work on any instrument
    
    def get_strategy_name(self) -> str:
        return self._strategy_name


def create_momentum_processor(config: Dict[str, Any]) -> MomentumProcessor:
    """Module-level factory function"""
    # Support both legacy and new parameter names
    lookback = config.get("lookback_periods") or config.get("lookback_period", 10)
    position_size = config.get("position_size") or config.get("max_position_size", 100)
    
    return MomentumProcessor(
        momentum_threshold=Decimal(str(config.get("momentum_threshold", "0.02"))),
        lookback_periods=lookback,
        position_size=position_size
    )