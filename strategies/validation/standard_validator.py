"""
Standard validation logic - composition, not inheritance
"""

from decimal import Decimal
from typing import Dict, Any
from ..core.protocols import StrategyValidator, SignalResult
from core.schemas.events import MarketTick as MarketData


class StandardStrategyValidator:
    """Standard validation logic - composition, not inheritance"""
    
    def __init__(self, max_signal_confidence: float = 100.0, min_quantity: int = 1):
        self.max_signal_confidence = max_signal_confidence
        self.min_quantity = min_quantity
    
    def validate_signal(self, signal: SignalResult, market_data: MarketData) -> bool:
        """Validate signal using business rules"""
        if signal.confidence < 0 or signal.confidence > self.max_signal_confidence:
            return False
        
        if signal.quantity < self.min_quantity:
            return False
        
        if signal.signal_type not in ["BUY", "SELL", "HOLD"]:
            return False
        
        # Market data validation
        if market_data.last_price <= 0:
            return False
        
        # Signal price should be positive
        if signal.price <= 0:
            return False
        
        return True
    
    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        """Validate strategy configuration"""
        required_fields = ["strategy_id", "strategy_type", "parameters"]
        return all(field in config for field in required_fields)


def create_standard_validator(config: Dict[str, Any]) -> StandardStrategyValidator:
    """Factory function for validator"""
    return StandardStrategyValidator(
        max_signal_confidence=config.get("max_confidence", 100.0),
        min_quantity=config.get("min_quantity", 1)
    )