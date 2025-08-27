# Pure, decoupled strategy logic - no I/O dependencies
from abc import ABC, abstractmethod
from typing import Generator, Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel
from core.schemas.events import SignalType


class MarketData(BaseModel):
    """Market data input for strategies"""
    instrument_token: int
    last_price: Decimal
    volume: int
    timestamp: datetime
    ohlc: Optional[Dict[str, Decimal]] = None


class TradingSignal(BaseModel):
    """Trading signal output from strategies"""
    strategy_id: str
    instrument_token: int
    signal_type: SignalType
    quantity: int
    price: Optional[Decimal] = None
    timestamp: datetime
    confidence: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


class BaseStrategy(ABC):
    """Base class for all trading strategies - pure logic, no I/O"""
    
    def __init__(self, strategy_id: str, parameters: Dict[str, Any], 
                 brokers: List[str] = None, instrument_tokens: List[int] = None):
        self.strategy_id = strategy_id
        self.parameters = parameters
        self.brokers = brokers or ["paper"]  # Default to paper trading
        self.instrument_tokens = instrument_tokens or []
        self._market_data_history: List[MarketData] = []
        
    @abstractmethod
    def on_market_data(self, data: MarketData) -> Generator[TradingSignal, None, None]:
        """
        Process market data and yield trading signals
        
        Args:
            data: New market data point
            
        Yields:
            TradingSignal: Generated trading signals
        """
        pass
    
    def _add_market_data(self, data: MarketData):
        """Add market data to history (helper method)"""
        self._market_data_history.append(data)
        
        # Keep only required history based on strategy needs
        max_history = self.parameters.get("max_history", 100)
        if len(self._market_data_history) > max_history:
            self._market_data_history = self._market_data_history[-max_history:]
    
    def get_history(self, lookback: int = None) -> List[MarketData]:
        """Get market data history"""
        if lookback is None:
            return self._market_data_history.copy()
        return self._market_data_history[-lookback:]
    
    def get_latest_price(self) -> Optional[Decimal]:
        """Get the latest price from history"""
        if self._market_data_history:
            return self._market_data_history[-1].last_price
        return None
    
    def is_subscribed(self, instrument_token: int) -> bool:
        """Check if strategy is subscribed to given instrument"""
        return instrument_token in self.instrument_tokens
    
    def supports_broker(self, broker: str) -> bool:
        """Check if strategy supports given broker"""
        return broker in self.brokers