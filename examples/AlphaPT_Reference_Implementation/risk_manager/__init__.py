"""Risk management module for AlphaPT.

This module provides comprehensive risk management capabilities including:
- Position limits and controls
- Loss limits and stop-loss mechanisms
- Exposure limits across instruments and sectors
- Real-time risk monitoring and alerts
- Pre-trade and post-trade risk validation
"""

from .risk_manager import RiskManager

# Global instance for API access
# This will be initialized by the application
risk_manager: RiskManager = None
from .models import (
    RiskProfile,
    RiskMetric,
    RiskViolation,
    PositionLimit,
    LossLimit,
    ExposureLimit,
    RiskCheck,
    RiskAlert
)
from .types import (
    RiskLimitType,
    RiskSeverity,
    RiskStatus,
    ViolationType
)

__all__ = [
    "RiskManager",
    "risk_manager",
    "RiskProfile",
    "RiskMetric", 
    "RiskViolation",
    "PositionLimit",
    "LossLimit",
    "ExposureLimit",
    "RiskCheck",
    "RiskAlert",
    "RiskLimitType",
    "RiskSeverity",
    "RiskStatus",
    "ViolationType"
]