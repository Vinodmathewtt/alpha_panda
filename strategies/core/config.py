"""
Strategy configuration value objects
Immutable configuration for composition-based strategies
"""

from dataclasses import dataclass
from typing import Dict, Any, List
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    """Immutable strategy configuration"""
    strategy_id: str
    strategy_type: str
    parameters: Dict[str, Any]
    active_brokers: List[str]
    instrument_tokens: List[int]
    max_position_size: Decimal
    risk_multiplier: Decimal
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Immutable execution context"""
    broker: str
    portfolio_state: Dict[str, Any]
    market_session: str  # "pre_market", "regular", "post_market"
    risk_limits: Dict[str, Decimal]