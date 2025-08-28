# Risk Manager API Schemas
from typing import Optional, Dict, Any, List
from datetime import datetime
from decimal import Decimal
from core.schemas.events import AlphaPandaBaseModel
from .models import RiskLevel, RiskCheckResult, RiskViolation


class RiskCheckRequest(AlphaPandaBaseModel):
    """Request schema for risk checking"""
    strategy_id: str
    instrument_token: int
    signal_type: str  # BUY, SELL
    quantity: int
    price: Decimal
    

class RiskCheckResponse(AlphaPandaBaseModel):
    """Response schema for risk checking"""
    approved: bool
    results: List[RiskCheckResult]
    overall_risk_level: RiskLevel
    message: Optional[str] = None
    

class RiskSummaryResponse(AlphaPandaBaseModel):
    """Risk summary for API responses"""
    portfolio_risk_level: RiskLevel
    active_violations: int
    total_exposure: Decimal
    risk_utilization_percent: float
    last_updated: datetime
    

class RiskViolationResponse(AlphaPandaBaseModel):
    """Risk violation details for API"""
    violations: List[RiskViolation]
    total_count: int
    unresolved_count: int