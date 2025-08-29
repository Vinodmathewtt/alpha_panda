"""
Strategy protocols for composition-based architecture
Replaces inheritance with protocol-based contracts
"""

from typing import Protocol, List, Dict, Any, Optional
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

from core.schemas.events import MarketTick as MarketData, TradingSignal


@dataclass(frozen=True, slots=True)
class SignalResult:
    """Immutable signal result value object"""
    signal_type: str  # BUY, SELL, HOLD
    confidence: float
    quantity: int
    price: Decimal
    reasoning: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class StrategyProcessor(Protocol):
    """Protocol defining pure strategy processing contract"""
    
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """Process single tick and return signal if generated"""
        ...
    
    def get_required_history_length(self) -> int:
        """Return required historical data length"""
        ...
    
    def supports_instrument(self, token: int) -> bool:
        """Check if strategy supports given instrument"""
        ...
    
    def get_strategy_name(self) -> str:
        """Return strategy identifier"""
        ...


class StrategyValidator(Protocol):
    """Protocol for strategy validation"""
    
    def validate_signal(self, signal: SignalResult, market_data: MarketData) -> bool:
        """Validate generated signal"""
        ...
    
    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        """Validate strategy configuration"""
        ...