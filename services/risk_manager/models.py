# Risk Manager Service Models
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCheckResult(BaseModel):
    """Result of a risk check evaluation"""
    passed: bool
    risk_level: RiskLevel
    rule_name: str
    reason: Optional[str] = None
    current_value: Optional[float] = None
    limit_value: Optional[float] = None
    

class PortfolioRisk(BaseModel):
    """Portfolio-level risk metrics"""
    portfolio_id: str
    total_exposure: Decimal
    max_exposure_limit: Decimal
    position_count: int
    max_positions_limit: int
    concentration_risk: float = 0.0  # 0-1 scale
    

class InstrumentRisk(BaseModel):
    """Instrument-specific risk metrics"""
    instrument_token: int
    current_position: int
    max_position_limit: int
    daily_loss: Decimal = Decimal('0')
    max_daily_loss_limit: Decimal
    

class RiskViolation(BaseModel):
    """Record of risk rule violations"""
    violation_id: str
    rule_name: str
    strategy_id: str
    instrument_token: int
    violation_type: str
    severity: RiskLevel
    description: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    resolved: bool = False