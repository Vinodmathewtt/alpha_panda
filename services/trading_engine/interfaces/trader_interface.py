from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from core.schemas.events import TradingSignal

class Trader(ABC):
    """Abstract base class for all trading execution engines."""
    
    @abstractmethod
    async def execute_order(self, signal: TradingSignal, last_price: Optional[float]) -> Dict[str, Any]:
        """Execute a trading signal and return result payload."""
        pass
    
    @abstractmethod
    def get_execution_mode(self) -> str:
        """Return the execution mode identifier (e.g., 'paper', 'zerodha')."""
        pass
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the trader. Returns True if successful."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup trader resources."""
        pass