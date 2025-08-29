"""
Composition-based strategy executor - no inheritance
Composes strategy processing and validation logic
"""

from typing import List, Optional, Dict, Any
from collections import deque
from .protocols import StrategyProcessor, StrategyValidator, SignalResult
from .config import StrategyConfig, ExecutionContext
from core.schemas.events import MarketTick as MarketData


class StrategyExecutor:
    """Composition-based strategy executor - no inheritance"""
    
    def __init__(
        self,
        processor: StrategyProcessor,  # Composed strategy logic
        validator: StrategyValidator,  # Composed validation logic  
        config: StrategyConfig,        # Immutable configuration
        context: ExecutionContext      # Execution context
    ):
        self._processor = processor
        self._validator = validator
        self.config = config
        self.context = context
        
        # Efficient history management
        max_history = processor.get_required_history_length()
        self._history: deque[MarketData] = deque(maxlen=max_history)
        
        # Performance optimization: O(1) instrument lookup
        self._supported_instruments = set(config.instrument_tokens)
    
    def can_process_tick(self, tick: MarketData) -> bool:
        """O(1) check if this executor should process tick"""
        return (
            tick.instrument_token in self._supported_instruments and
            self.config.enabled and
            self.context.broker in self.config.active_brokers
        )
    
    def process_tick(self, tick: MarketData) -> Optional[SignalResult]:
        """Process tick using composed strategy"""
        if not self.can_process_tick(tick):
            return None
        
        # Update history efficiently
        self._history.append(tick)
        
        # Delegate to composed processor (pure strategy logic)
        signal = self._processor.process_tick(tick, list(self._history))
        
        # Validate using composed validator
        if signal and self._validator.validate_signal(signal, tick):
            return signal
        
        return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Return execution metrics"""
        return {
            "strategy_id": self.config.strategy_id,
            "broker": self.context.broker,
            "history_length": len(self._history),
            "supported_instruments": len(self._supported_instruments)
        }