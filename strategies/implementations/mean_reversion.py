"""
Modern mean reversion strategy implementation using composition
Pure function approach - no inheritance
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal
from statistics import mean, stdev
from ..core.protocols import StrategyProcessor, SignalResult
from core.schemas.events import MarketTick as MarketData


class MeanReversionProcessor:
    """Pure mean reversion strategy logic - no inheritance"""
    
    def __init__(self, std_dev_threshold: Decimal, lookback_periods: int, position_size: int = 100):
        self.std_dev_threshold = float(std_dev_threshold)
        self.lookback_periods = lookback_periods
        self.position_size = position_size
        self._strategy_name = "mean_reversion"
    
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """Pure function - no side effects"""
        if len(history) < self.lookback_periods:
            return None
        
        # Get recent prices for calculation
        recent_prices = [float(tick.last_price) for tick in history[-self.lookback_periods:]]
        
        if len(recent_prices) < 2:
            return None
        
        # Calculate mean and standard deviation
        price_mean = mean(recent_prices)
        price_std = stdev(recent_prices)
        
        if price_std == 0:
            return None
        
        current_price = tick.last_price
        current_price_float = float(current_price)
        
        # Calculate z-score (how many standard deviations from mean)
        z_score = (current_price_float - price_mean) / price_std
        confidence = min(float(abs(z_score) * 25), 100.0)  # Scale confidence
        
        if z_score > self.std_dev_threshold:
            # Price too high - expect reversion down - SELL
            return SignalResult(
                signal_type="SELL",
                confidence=confidence,
                quantity=self.position_size,
                price=current_price,
                reasoning=f"Price {z_score:.2f} std devs above mean, expect reversion",
                metadata={
                    "z_score": z_score,
                    "price_mean": price_mean,
                    "price_std": price_std,
                    "lookback_periods": self.lookback_periods,
                    "current_price": current_price_float
                }
            )
        elif z_score < -self.std_dev_threshold:
            # Price too low - expect reversion up - BUY
            return SignalResult(
                signal_type="BUY",
                confidence=confidence,
                quantity=self.position_size,
                price=current_price,
                reasoning=f"Price {abs(z_score):.2f} std devs below mean, expect reversion",
                metadata={
                    "z_score": z_score,
                    "price_mean": price_mean,
                    "price_std": price_std,
                    "lookback_periods": self.lookback_periods,
                    "current_price": current_price_float
                }
            )
        
        return None
    
    def get_required_history_length(self) -> int:
        return self.lookback_periods
    
    def supports_instrument(self, token: int) -> bool:
        return True  # Mean reversion can work on any instrument
    
    def get_strategy_name(self) -> str:
        return self._strategy_name


def create_mean_reversion_processor(config: Dict[str, Any]) -> MeanReversionProcessor:
    """Module-level factory function"""
    # Support both legacy and new parameter names
    std_threshold = (config.get("std_deviation_threshold") or 
                     config.get("std_dev_threshold") or 
                     config.get("entry_threshold", "2.0"))
    
    lookback = (config.get("lookback_periods") or 
                config.get("lookback_period") or 
                config.get("window_size", 20))
    
    position_size = config.get("position_size") or config.get("max_position_size", 100)
    
    return MeanReversionProcessor(
        std_dev_threshold=Decimal(str(std_threshold)),
        lookback_periods=lookback,
        position_size=position_size
    )