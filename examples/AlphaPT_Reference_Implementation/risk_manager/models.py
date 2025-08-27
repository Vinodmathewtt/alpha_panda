"""Risk management data models."""

from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from decimal import Decimal

from .types import (
    RiskLimitType,
    RiskSeverity,
    RiskStatus,
    ViolationType,
    RiskAction,
    MoneyAmount,
    PercentageAmount,
    QuantityAmount
)


@dataclass
class PositionLimit:
    """Position size limits."""
    strategy_name: str
    instrument_token: Optional[int] = None
    instrument_type: Optional[str] = None  # EQ, FUT, CE, PE
    max_quantity: Optional[QuantityAmount] = None
    max_value: Optional[MoneyAmount] = None
    max_percentage: Optional[PercentageAmount] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class LossLimit:
    """Loss control limits."""
    strategy_name: str
    max_daily_loss: Optional[MoneyAmount] = None
    max_total_loss: Optional[MoneyAmount] = None
    max_drawdown_pct: Optional[PercentageAmount] = None
    stop_loss_pct: Optional[PercentageAmount] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExposureLimit:
    """Exposure concentration limits."""
    strategy_name: str
    sector: Optional[str] = None
    instrument_type: Optional[str] = None
    exchange: Optional[str] = None
    max_exposure_value: Optional[MoneyAmount] = None
    max_exposure_pct: Optional[PercentageAmount] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RiskMetric:
    """Current risk metric value."""
    strategy_name: str
    metric_type: RiskLimitType
    metric_name: str
    current_value: MoneyAmount
    limit_value: MoneyAmount
    utilization_pct: float
    status: RiskStatus
    last_checked: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskViolation:
    """Risk limit violation."""
    violation_id: str
    strategy_name: str
    risk_type: RiskLimitType
    violation_type: ViolationType
    severity: RiskSeverity
    current_value: MoneyAmount
    limit_value: MoneyAmount
    utilization_pct: float
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    acknowledged: bool = False
    resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskCheck:
    """Pre-trade risk check result."""
    check_id: str
    strategy_name: str
    instrument_token: int
    action: str  # BUY, SELL
    quantity: QuantityAmount
    price: MoneyAmount
    passed: bool
    violations: List[RiskViolation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskAlert:
    """Risk management alert."""
    alert_id: str
    strategy_name: str
    alert_type: str
    severity: RiskSeverity
    message: str
    action_required: RiskAction
    violation: Optional[RiskViolation] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sent: bool = False
    acknowledged: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskProfile:
    """Complete risk profile for a strategy."""
    strategy_name: str
    position_limits: List[PositionLimit] = field(default_factory=list)
    loss_limits: List[LossLimit] = field(default_factory=list)
    exposure_limits: List[ExposureLimit] = field(default_factory=list)
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "position_limits": [
                {
                    "instrument_token": pl.instrument_token,
                    "instrument_type": pl.instrument_type,
                    "max_quantity": pl.max_quantity,
                    "max_value": float(pl.max_value) if pl.max_value else None,
                    "max_percentage": pl.max_percentage
                }
                for pl in self.position_limits
            ],
            "loss_limits": [
                {
                    "max_daily_loss": float(ll.max_daily_loss) if ll.max_daily_loss else None,
                    "max_total_loss": float(ll.max_total_loss) if ll.max_total_loss else None,
                    "max_drawdown_pct": ll.max_drawdown_pct,
                    "stop_loss_pct": ll.stop_loss_pct
                }
                for ll in self.loss_limits
            ],
            "exposure_limits": [
                {
                    "sector": el.sector,
                    "instrument_type": el.instrument_type,
                    "exchange": el.exchange,
                    "max_exposure_value": float(el.max_exposure_value) if el.max_exposure_value else None,
                    "max_exposure_pct": el.max_exposure_pct
                }
                for el in self.exposure_limits
            ],
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }