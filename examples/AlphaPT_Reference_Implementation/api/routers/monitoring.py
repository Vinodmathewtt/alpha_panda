"""Monitoring and metrics API endpoints."""

from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse

from monitoring import metrics_collector, health_checker
from core.logging.logger import get_logger
from ..middleware import get_current_user

logger = get_logger(__name__)

router = APIRouter()


@router.get("/metrics")
async def get_metrics(
    format: str = "json",
    user=Depends(get_current_user)
):
    """Get system metrics."""
    try:
        if format == "prometheus":
            # Return Prometheus-formatted metrics
            metrics_text = await metrics_collector.get_prometheus_metrics()
            return PlainTextResponse(
                content=metrics_text,
                media_type="text/plain"
            )
        else:
            # Return JSON-formatted metrics
            metrics = await metrics_collector.get_all_metrics()
            return metrics
        
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{metric_name}")
async def get_metric(
    metric_name: str,
    user=Depends(get_current_user)
):
    """Get specific metric value."""
    try:
        metric_value = await metrics_collector.get_metric(metric_name)
        if metric_value is None:
            raise HTTPException(status_code=404, detail="Metric not found")
        
        return {
            "metric_name": metric_name,
            "value": metric_value,
            "timestamp": metrics_collector.get_current_timestamp()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metric {metric_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system/performance")
async def get_system_performance(user=Depends(get_current_user)):
    """Get system performance metrics."""
    try:
        performance = await metrics_collector.get_system_performance()
        return performance
        
    except Exception as e:
        logger.error(f"Failed to get system performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trading/performance")
async def get_trading_performance(user=Depends(get_current_user)):
    """Get trading performance metrics."""
    try:
        performance = await metrics_collector.get_trading_performance()
        return performance
        
    except Exception as e:
        logger.error(f"Failed to get trading performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/performance")
async def get_market_data_performance(user=Depends(get_current_user)):
    """Get market data performance metrics."""
    try:
        performance = await metrics_collector.get_market_data_performance()
        return performance
        
    except Exception as e:
        logger.error(f"Failed to get market data performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/stats")
async def get_event_statistics(user=Depends(get_current_user)):
    """Get event system statistics."""
    try:
        stats = await metrics_collector.get_event_statistics()
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get event statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/summary")
async def get_dashboard_summary(user=Depends(get_current_user)):
    """Get summary data for monitoring dashboard."""
    try:
        # Aggregate key metrics for dashboard
        summary = {
            "system_health": await health_checker.get_health_status(),
            "performance": await metrics_collector.get_system_performance(),
            "trading": await metrics_collector.get_trading_performance(),
            "market_data": await metrics_collector.get_market_data_performance(),
            "events": await metrics_collector.get_event_statistics(),
            "timestamp": metrics_collector.get_current_timestamp()
        }
        
        return summary
        
    except Exception as e:
        logger.error(f"Failed to get dashboard summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_active_alerts(user=Depends(get_current_user)):
    """Get active system alerts."""
    try:
        alerts = await metrics_collector.get_active_alerts()
        return {
            "alerts": alerts,
            "total_count": len(alerts)
        }
        
    except Exception as e:
        logger.error(f"Failed to get active alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/recent")
async def get_recent_logs(
    level: str = "INFO",
    limit: int = 100,
    user=Depends(get_current_user)
):
    """Get recent log entries."""
    try:
        logs = await metrics_collector.get_recent_logs(level, limit)
        return {
            "logs": logs,
            "level": level,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Failed to get recent logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/errors/summary")
async def get_error_summary(user=Depends(get_current_user)):
    """Get error summary and statistics."""
    try:
        error_summary = await metrics_collector.get_error_summary()
        return error_summary
        
    except Exception as e:
        logger.error(f"Failed to get error summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))