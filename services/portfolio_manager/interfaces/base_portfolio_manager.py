from abc import ABC, abstractmethod
from typing import Dict, Any


class BasePortfolioManager(ABC):
    """Abstract base class for all portfolio managers."""
    
    @abstractmethod
    async def handle_fill(self, fill_data: Dict[str, Any]) -> None:
        """Process an order fill event."""
        pass
    
    @abstractmethod  
    async def handle_tick(self, tick_data: Dict[str, Any]) -> None:
        """Process market tick for unrealized P&L updates."""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Initialize the portfolio manager."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Shutdown and cleanup portfolio manager."""
        pass
    
    @abstractmethod
    async def get_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Retrieve portfolio state."""
        pass
    
    @abstractmethod
    async def reconcile_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Reconcile portfolio state with external sources."""
        pass