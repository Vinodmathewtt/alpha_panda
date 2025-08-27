"""Strategy management system for AlphaPT.

This module provides a comprehensive framework for strategy development,
execution, and monitoring in the AlphaPT algorithmic trading platform.

Key Components:
- BaseStrategy: Abstract base class for all strategies
- StrategyManager: Central orchestrator for strategy lifecycle
- StrategyFactory: Factory for creating strategy instances
- SignalTypes: Trading signal definitions and types
- StrategyConfig: Configuration management for strategies

Features:
- Event-driven strategy execution
- Multi-asset strategy support
- Risk integration with pre-trade validation
- Performance monitoring and analytics
- Hot-reloading of strategy configurations
- Strategy isolation and error handling
"""

from .base_strategy import BaseStrategy
from .strategy_manager import StrategyManager

# Global instance for API access
# This will be initialized by the application
strategy_manager: StrategyManager = None
from .signal_types import TradingSignal, SignalType, SignalStrength
from .strategy_factory import StrategyFactory

__all__ = [
    'BaseStrategy',
    'StrategyManager',
    'strategy_manager',
    'TradingSignal',
    'SignalType',
    'SignalStrength',
    'StrategyFactory'
]

__version__ = '1.0.0'