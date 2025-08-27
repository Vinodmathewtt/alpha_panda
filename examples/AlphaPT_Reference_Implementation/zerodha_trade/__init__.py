"""Zerodha live trading module for AlphaPT.

This module provides real trading capabilities with Zerodha KiteConnect:
- Live order management and execution
- Real-time position tracking
- Trade execution with proper error handling
- Integration with risk management
- Compliance and audit trail
"""

from .engine import ZerodhaTradeEngine
from .orders import ZerodhaOrderManager
from .positions import ZerodhaPositionManager

# Global instance for API access
# This will be initialized by the application
zerodha_trading_engine: ZerodhaTradeEngine = None
from .models import (
    ZerodhaOrder,
    ZerodhaPosition,
    ZerodhaAccount,
    ZerodhaTrade
)
from .types import (
    ZerodhaOrderType,
    ZerodhaOrderStatus,
    ZerodhaProductType,
    ZerodhaValidityType,
    ZerodhaVarietyType
)

__all__ = [
    "ZerodhaTradeEngine",
    "ZerodhaOrderManager",
    "ZerodhaPositionManager",
    "zerodha_trading_engine",
    "ZerodhaOrder",
    "ZerodhaPosition", 
    "ZerodhaAccount",
    "ZerodhaTrade",
    "ZerodhaOrderType",
    "ZerodhaOrderStatus",
    "ZerodhaProductType",
    "ZerodhaValidityType",
    "ZerodhaVarietyType"
]