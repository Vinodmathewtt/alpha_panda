"""Risk management API endpoints."""

from typing import List, Dict, Any, Optional
from decimal import Decimal
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from risk_manager import risk_manager
from core.logging.logger import get_logger
from ..middleware import get_current_user, require_admin_permission

logger = get_logger(__name__)

router = APIRouter()


class RiskProfile(BaseModel):
    strategy_name: str
    position_limits: List[Dict[str, Any]]
    loss_limits: List[Dict[str, Any]]
    exposure_limits: List[Dict[str, Any]]
    enabled: bool


class RiskStatus(BaseModel):
    strategy_name: str
    overall_status: str
    risk_utilization: float
    violations: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]


class RiskMetrics(BaseModel):
    strategy_name: str
    current_exposure: Decimal
    max_exposure: Decimal
    current_loss: Decimal
    max_loss: Decimal
    position_count: int
    max_positions: int


@router.get("/profiles", response_model=List[RiskProfile])
async def get_risk_profiles(user=Depends(get_current_user)):
    """Get all risk profiles."""
    try:
        profiles = await risk_manager.get_all_risk_profiles()
        
        return [
            RiskProfile(
                strategy_name=name,
                position_limits=profile.get("position_limits", []),
                loss_limits=profile.get("loss_limits", []),
                exposure_limits=profile.get("exposure_limits", []),
                enabled=profile.get("enabled", True)
            )
            for name, profile in profiles.items()
        ]
        
    except Exception as e:
        logger.error(f"Failed to get risk profiles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/profiles/{strategy_name}", response_model=RiskProfile)
async def get_risk_profile(
    strategy_name: str,
    user=Depends(get_current_user)
):
    """Get risk profile for a specific strategy."""
    try:
        profile = await risk_manager.get_risk_profile(strategy_name)
        if not profile:
            raise HTTPException(status_code=404, detail="Risk profile not found")
        
        return RiskProfile(
            strategy_name=strategy_name,
            position_limits=profile.get("position_limits", []),
            loss_limits=profile.get("loss_limits", []),
            exposure_limits=profile.get("exposure_limits", []),
            enabled=profile.get("enabled", True)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get risk profile for {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profiles/{strategy_name}")
async def create_or_update_risk_profile(
    strategy_name: str,
    profile: RiskProfile,
    user=Depends(get_current_user),
    _=Depends(require_admin_permission)
):
    """Create or update risk profile for a strategy."""
    try:
        success = await risk_manager.create_risk_profile(
            strategy_name=strategy_name,
            position_limits=profile.position_limits,
            loss_limits=profile.loss_limits,
            exposure_limits=profile.exposure_limits
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to create/update risk profile")
        
        return {
            "success": True,
            "message": f"Risk profile created/updated for {strategy_name}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create/update risk profile for {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=List[RiskStatus])
async def get_risk_status_all(user=Depends(get_current_user)):
    """Get risk status for all strategies."""
    try:
        statuses = await risk_manager.get_all_risk_status()
        
        return [
            RiskStatus(
                strategy_name=name,
                overall_status=status.get("overall_status", "unknown"),
                risk_utilization=status.get("risk_utilization", 0.0),
                violations=status.get("violations", []),
                warnings=status.get("warnings", [])
            )
            for name, status in statuses.items()
        ]
        
    except Exception as e:
        logger.error(f"Failed to get risk status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{strategy_name}", response_model=RiskStatus)
async def get_risk_status(
    strategy_name: str,
    user=Depends(get_current_user)
):
    """Get risk status for a specific strategy."""
    try:
        status = await risk_manager.get_risk_status(strategy_name)
        if not status:
            raise HTTPException(status_code=404, detail="Risk status not found")
        
        return RiskStatus(
            strategy_name=strategy_name,
            overall_status=status.get("overall_status", "unknown"),
            risk_utilization=status.get("risk_utilization", 0.0),
            violations=status.get("violations", []),
            warnings=status.get("warnings", [])
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get risk status for {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{strategy_name}", response_model=RiskMetrics)
async def get_risk_metrics(
    strategy_name: str,
    user=Depends(get_current_user)
):
    """Get risk metrics for a specific strategy."""
    try:
        metrics = await risk_manager.get_risk_metrics(strategy_name)
        if not metrics:
            raise HTTPException(status_code=404, detail="Risk metrics not found")
        
        return RiskMetrics(
            strategy_name=strategy_name,
            current_exposure=metrics.get("current_exposure", Decimal("0")),
            max_exposure=metrics.get("max_exposure", Decimal("0")),
            current_loss=metrics.get("current_loss", Decimal("0")),
            max_loss=metrics.get("max_loss", Decimal("0")),
            position_count=metrics.get("position_count", 0),
            max_positions=metrics.get("max_positions", 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get risk metrics for {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check")
async def check_order_risk(
    strategy_name: str,
    instrument_token: int,
    action: str,
    quantity: int,
    price: Decimal,
    user=Depends(get_current_user)
):
    """Check risk for a potential order."""
    try:
        risk_check = await risk_manager.check_order_risk(
            strategy_name=strategy_name,
            instrument_token=instrument_token,
            action=action,
            quantity=quantity,
            price=price
        )
        
        return {
            "passed": risk_check.passed,
            "violations": [
                {
                    "type": violation.violation_type,
                    "message": violation.message,
                    "current_value": str(violation.current_value),
                    "limit_value": str(violation.limit_value)
                }
                for violation in risk_check.violations
            ],
            "warnings": [
                {
                    "type": warning.violation_type,
                    "message": warning.message,
                    "current_value": str(warning.current_value),
                    "limit_value": str(warning.limit_value)
                }
                for warning in risk_check.warnings
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to check order risk: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset/{strategy_name}")
async def reset_risk_metrics(
    strategy_name: str,
    user=Depends(get_current_user),
    _=Depends(require_admin_permission)
):
    """Reset risk metrics for a strategy."""
    try:
        success = await risk_manager.reset_risk_metrics(strategy_name)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to reset risk metrics")
        
        return {
            "success": True,
            "message": f"Risk metrics reset for {strategy_name}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset risk metrics for {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/violations")
async def get_recent_violations(
    limit: int = 50,
    user=Depends(get_current_user)
):
    """Get recent risk violations."""
    try:
        violations = await risk_manager.get_recent_violations(limit)
        
        return {
            "violations": violations,
            "total_count": len(violations)
        }
        
    except Exception as e:
        logger.error(f"Failed to get recent violations: {e}")
        raise HTTPException(status_code=500, detail=str(e))