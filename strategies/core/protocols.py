"""
Strategy protocols for composition-based architecture
Replaces inheritance with protocol-based contracts
"""

from typing import Protocol, List, Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime

# Conditional import for ML dependencies
if TYPE_CHECKING:
    import numpy as np
else:
    try:
        import numpy as np
    except ImportError:
        # Fallback for environments without numpy
        np = None

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


class MLStrategyProcessor(StrategyProcessor):
    """ML extension of existing StrategyProcessor - maintains compatibility"""
    
    def load_model(self) -> bool:
        """Load ML model - called once at startup"""
        ...
    
    def extract_features(self, tick: MarketData, history: List[MarketData]) -> Any:
        """Convert tick data to ML features - returns np.ndarray if numpy available"""
        ...
        
    def predict_signal(self, features: Any) -> Optional[SignalResult]:
        """ML inference method"""
        ...
    
    # KEEP ALL EXISTING StrategyProcessor METHODS UNCHANGED
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """Default implementation delegates to ML pipeline"""
        features = self.extract_features(tick, history) 
        return self.predict_signal(features)


class MLCapable(Protocol):
    """Optional ML capability mixin - strategies can implement this for ML features"""
    
    def load_model(self) -> bool:
        """Load ML model - returns True if successful"""
        ...
    
    def extract_features(self, tick: MarketData, history: List[MarketData]) -> Any:
        """Convert tick data to ML features"""
        ...
        
    def predict_signal(self, features: Any) -> Optional[SignalResult]:
        """ML inference method - returns signal or None"""
        ...


class DecisionPolicy(Protocol):
    """Policy for combining multiple signals in hybrid strategies"""
    
    def decide(self, rules_signal: Optional[SignalResult], ml_signal: Optional[SignalResult], 
               context: Optional[Dict[str, Any]] = None) -> Optional[SignalResult]:
        """Combine rules and ML signals into final decision"""
        ...


class StrategyValidator(Protocol):
    """Protocol for strategy validation"""
    
    def validate_signal(self, signal: SignalResult, market_data: MarketData) -> bool:
        """Validate generated signal"""
        ...
    
    def validate_configuration(self, config: Dict[str, Any]) -> bool:
        """Validate strategy configuration"""
        ...