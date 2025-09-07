"""
Rule-based momentum strategy implementation
Pure technical indicator approach without ML dependencies
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal
from core.schemas.events import MarketTick as MarketData
from strategies.core.protocols import StrategyProcessor, SignalResult
from core.logging import get_trading_logger_safe

logger = get_trading_logger_safe("momentum_strategy")


class RulesMomentumProcessor:
    """
    Pure rule-based momentum strategy using price change thresholds
    No ML dependencies - uses only technical indicators
    """
    
    def __init__(self, lookback_periods: int = 20, threshold: float = 0.01, position_size: int = 100):
        """
        Initialize momentum strategy with configurable parameters
        
        Args:
            lookback_periods: Number of periods to calculate momentum
            threshold: Minimum price change percentage to trigger signal
            position_size: Base quantity for orders
        """
        self.lookback = lookback_periods
        self.threshold = threshold
        self.qty = position_size
        
        logger.info("Initialized rules-based momentum strategy", 
                   lookback=self.lookback, threshold=self.threshold, position_size=self.qty)
    
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """
        Process market tick and generate momentum-based signals
        
        Strategy Logic:
        1. Calculate price change over lookback period
        2. Generate BUY signal if momentum > threshold
        3. Generate SELL signal if momentum < -threshold
        4. Return None for sideways movement
        """
        if len(history) < self.lookback:
            return None
            
        try:
            # Calculate momentum as percentage change over lookback period
            start_price = float(history[-self.lookback].last_price)
            current_price = float(tick.last_price)
            
            if start_price == 0:
                return None
                
            momentum = (current_price - start_price) / start_price
            
            # Generate signals based on momentum thresholds
            if momentum > self.threshold:
                confidence = min(1.0, abs(momentum) * 5.0)  # Scale confidence with momentum strength
                return SignalResult(
                    signal_type="BUY",
                    confidence=confidence,
                    quantity=self.qty,
                    price=Decimal(str(current_price)),
                    reasoning=f"Positive momentum: {momentum:.2%} over {self.lookback} periods"
                )
            elif momentum < -self.threshold:
                confidence = min(1.0, abs(momentum) * 5.0)
                return SignalResult(
                    signal_type="SELL", 
                    confidence=confidence,
                    quantity=self.qty,
                    price=Decimal(str(current_price)),
                    reasoning=f"Negative momentum: {momentum:.2%} over {self.lookback} periods"
                )
            
            # No signal for sideways movement
            return None
            
        except (ValueError, IndexError, AttributeError) as e:
            logger.warning("Error processing momentum signal", error=str(e))
            return None
    
    def get_required_history_length(self) -> int:
        """Return required historical data length"""
        return self.lookback
    
    def supports_instrument(self, token: int) -> bool:
        """Momentum strategy supports all liquid instruments"""
        return True
    
    def get_strategy_name(self) -> str:
        """Return strategy identifier"""
        return "momentum"


def create_momentum_processor(config: Dict[str, Any]) -> RulesMomentumProcessor:
    """
    Factory function to create momentum strategy processor
    
    Configuration parameters:
    - lookback_periods: Number of periods for momentum calculation (default: 20)
    - threshold: Minimum momentum threshold for signals (default: 0.01 = 1%)
    - position_size: Order quantity (default: 100)
    """
    return RulesMomentumProcessor(
        lookback_periods=config.get("lookback_periods", 20),
        threshold=config.get("threshold", 0.01),
        position_size=config.get("position_size", 100)
    )
