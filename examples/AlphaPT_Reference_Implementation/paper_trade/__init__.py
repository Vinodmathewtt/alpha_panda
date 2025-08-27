"""Paper trading module for AlphaPT.

This module provides simulated trading capabilities for strategy development and testing:
- Realistic order simulation with market impact
- Virtual portfolio management
- Performance tracking and analytics
- Risk-free strategy validation
- Backtesting capabilities
"""

from .engine import PaperTradingEngine
from .portfolio import PaperPortfolio
from .orders import PaperOrderManager

# Global instance for API access
# This will be initialized by the application
paper_trading_engine: PaperTradingEngine = None
from .models import (
    PaperOrder,
    PaperPosition,
    PaperTrade,
    OrderFill,
    PaperAccount
)
from .types import (
    OrderType,
    OrderStatus,
    OrderSide,
    TimeInForce,
    FillType
)

__all__ = [
    "PaperTradingEngine",
    "PaperPortfolio", 
    "PaperOrderManager",
    "paper_trading_engine",
    "PaperOrder",
    "PaperPosition",
    "PaperTrade",
    "OrderFill",
    "PaperAccount",
    "OrderType",
    "OrderStatus",
    "OrderSide",
    "TimeInForce",
    "FillType"
]