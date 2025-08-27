"""Health check and system status API endpoints."""

from typing import Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from monitoring import health_checker
from core.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    overall_status: str
    components: Dict[str, Any]
    timestamp: str
    version: str = "1.0.0"


class ComponentHealth(BaseModel):
    status: str
    details: Dict[str, Any]
    last_check: str


@router.get("/", response_model=HealthResponse)
async def get_health_status():
    """Get overall system health status."""
    try:
        health_data = await health_checker.get_health_status()
        return HealthResponse(**health_data)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Health check unavailable")


@router.get("/components", response_model=Dict[str, ComponentHealth])
async def get_component_health():
    """Get detailed health status for all components."""
    try:
        components = await health_checker.get_component_health()
        return {
            name: ComponentHealth(**details)
            for name, details in components.items()
        }
    except Exception as e:
        logger.error(f"Component health check failed: {e}")
        raise HTTPException(status_code=503, detail="Component health check unavailable")


@router.get("/components/{component_name}")
async def get_component_health_detail(component_name: str):
    """Get detailed health status for a specific component."""
    try:
        component_health = await health_checker.get_component_health(component_name)
        if not component_health:
            raise HTTPException(status_code=404, detail=f"Component '{component_name}' not found")
        
        return ComponentHealth(**component_health)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Component health check failed for {component_name}: {e}")
        raise HTTPException(status_code=503, detail=f"Health check unavailable for {component_name}")


@router.get("/readiness")
async def readiness_check():
    """Kubernetes-style readiness probe."""
    try:
        health_data = await health_checker.get_health_status()
        if health_data["overall_status"] == "healthy":
            return {"status": "ready"}
        else:
            raise HTTPException(status_code=503, detail="Service not ready")
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")


@router.get("/liveness")
async def liveness_check():
    """Kubernetes-style liveness probe."""
    try:
        # Simple check that the application is running
        return {"status": "alive", "timestamp": health_checker.get_current_timestamp()}
    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not alive")


@router.get("/strategies")
async def get_strategies_health():
    """Get health status for all strategies."""
    try:
        # Try to get strategy manager from global context
        from strategy_manager.strategy_health_monitor import get_strategy_health_monitor
        
        monitor = get_strategy_health_monitor()
        health_data = await monitor.get_all_strategies_health()
        summary = await monitor.get_health_summary()
        
        return {
            "summary": summary,
            "strategies": health_data,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Strategy health check failed: {e}")
        raise HTTPException(status_code=503, detail="Strategy health check unavailable")


@router.get("/strategies/{strategy_name}")
async def get_strategy_health_detail(strategy_name: str):
    """Get detailed health status for a specific strategy."""
    try:
        from strategy_manager.strategy_health_monitor import get_strategy_health_monitor
        
        monitor = get_strategy_health_monitor()
        health_metrics = await monitor.get_strategy_health(strategy_name)
        
        if not health_metrics:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")
        
        return {
            "strategy_name": health_metrics.strategy_name,
            "health_level": health_metrics.health_level.value,
            "health_score": health_metrics.health_score,
            "is_active": health_metrics.is_active,
            "market_data_received": health_metrics.market_data_received,
            "last_market_data_time": health_metrics.last_market_data_time.isoformat() if health_metrics.last_market_data_time else None,
            "market_data_lag_seconds": health_metrics.market_data_lag_seconds,
            "signals_generated": health_metrics.signals_generated,
            "signals_executed": health_metrics.signals_executed,
            "execution_success_rate": health_metrics.execution_success_rate,
            "error_count": health_metrics.error_count,
            "error_rate": health_metrics.error_rate,
            "uptime_percentage": health_metrics.uptime_percentage,
            "issues": [
                {
                    "type": issue.check_type.value,
                    "severity": issue.severity,
                    "description": issue.description,
                    "timestamp": issue.timestamp.isoformat(),
                    "auto_recoverable": issue.auto_recoverable
                }
                for issue in health_metrics.issues
            ],
            "last_health_check": health_metrics.last_health_check.isoformat() if health_metrics.last_health_check else None,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Strategy health detail check failed for {strategy_name}: {e}")
        raise HTTPException(status_code=503, detail=f"Health check unavailable for {strategy_name}")


@router.get("/strategies/unhealthy")
async def get_unhealthy_strategies():
    """Get list of strategies with health issues."""
    try:
        from strategy_manager.strategy_health_monitor import get_strategy_health_monitor
        
        monitor = get_strategy_health_monitor()
        unhealthy_strategies = await monitor.get_unhealthy_strategies()
        
        # Get details for each unhealthy strategy
        unhealthy_details = {}
        for strategy_name in unhealthy_strategies:
            health_metrics = await monitor.get_strategy_health(strategy_name)
            if health_metrics:
                unhealthy_details[strategy_name] = {
                    "health_level": health_metrics.health_level.value,
                    "health_score": health_metrics.health_score,
                    "issues_count": len(health_metrics.issues),
                    "critical_issues": [
                        issue.description for issue in health_metrics.issues 
                        if issue.severity == "critical"
                    ]
                }
        
        return {
            "unhealthy_strategies": unhealthy_strategies,
            "details": unhealthy_details,
            "count": len(unhealthy_strategies),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Unhealthy strategies check failed: {e}")
        raise HTTPException(status_code=503, detail="Unhealthy strategies check unavailable")