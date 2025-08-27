"""
Trading Engine Service

This module implements the Strategy Pattern for trading execution, providing
clean separation between routing decisions and execution implementations.
"""

from .service import TradingEngineService
from .interfaces.trader_interface import Trader
from .traders.trader_factory import TraderFactory
from .traders.paper_trader import PaperTrader
from .traders.zerodha_trader import ZerodhaTrader
from .routing.execution_router import ExecutionRouter

__all__ = [
    "TradingEngineService",
    "Trader",
    "TraderFactory", 
    "PaperTrader",
    "ZerodhaTrader",
    "ExecutionRouter"
]