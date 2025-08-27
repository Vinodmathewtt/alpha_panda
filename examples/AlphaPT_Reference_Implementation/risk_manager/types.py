"""Risk management type definitions."""

from enum import Enum
from typing import Union
from decimal import Decimal


class RiskLimitType(str, Enum):
    """Types of risk limits."""
    POSITION_LIMIT = "position_limit"
    LOSS_LIMIT = "loss_limit"
    EXPOSURE_LIMIT = "exposure_limit"
    CONCENTRATION_LIMIT = "concentration_limit"
    LEVERAGE_LIMIT = "leverage_limit"
    DRAWDOWN_LIMIT = "drawdown_limit"
    VAR_LIMIT = "var_limit"


class RiskSeverity(str, Enum):
    """Risk violation severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskStatus(str, Enum):
    """Risk status indicators."""
    SAFE = "safe"
    WARNING = "warning"
    BREACHED = "breached"
    RECOVERED = "recovered"


class ViolationType(str, Enum):
    """Types of risk violations."""
    SOFT_LIMIT = "soft_limit"  # Warning level
    HARD_LIMIT = "hard_limit"  # Blocking level
    ABSOLUTE_LIMIT = "absolute_limit"  # System shutdown level


class RiskAction(str, Enum):
    """Actions to take on risk violations."""
    ALERT = "alert"
    REDUCE_POSITION = "reduce_position"
    CLOSE_POSITION = "close_position"
    BLOCK_NEW_ORDERS = "block_new_orders"
    EMERGENCY_STOP = "emergency_stop"


# Type aliases for better readability
MoneyAmount = Union[int, float, Decimal]
PercentageAmount = Union[int, float]
QuantityAmount = Union[int, float]