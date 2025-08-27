"""
Monitoring and health API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
import redis.asyncio as redis

from core.config.settings import Settings
from core.health import ServiceHealthChecker
from core.monitoring import PipelineMonitor, PipelineMetricsCollector
from api.dependencies import get_settings, get_redis_client

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/health")
async def health_check(
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """Get overall system health"""
    try:
        health_checker = ServiceHealthChecker(settings)
        await health_checker.start()
        
        health_status = await health_checker.get_overall_health()
        
        await health_checker.stop()
        
        return {
            "status": "success",
            "data": health_status,
            "broker": settings.broker_namespace
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Health check failed: {str(e)}",
            "broker": settings.broker_namespace
        }


@router.get("/pipeline")
async def pipeline_status(
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """Get pipeline flow status and metrics"""
    try:
        # Get current pipeline validation status
        validation_key = f"pipeline:validation:{settings.broker_namespace}"
        validation_data = await redis_client.get(validation_key)
        
        if validation_data:
            import json
            pipeline_status = json.loads(validation_data)
        else:
            pipeline_status = {
                "broker": settings.broker_namespace,
                "status": "no_recent_data",
                "message": "No recent pipeline validation data available"
            }
        
        # Get pipeline health metrics
        metrics_collector = PipelineMetricsCollector(redis_client, settings)
        health_data = await metrics_collector.get_pipeline_health()
        
        return {
            "status": "success",
            "data": {
                "validation": pipeline_status,
                "health": health_data
            },
            "broker": settings.broker_namespace
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get pipeline status: {str(e)}"
        )


@router.get("/pipeline/history")
async def pipeline_history(
    limit: int = 50,
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """Get pipeline health history"""
    try:
        # Get health history from Redis
        history_key = f"pipeline:health_history:{settings.broker_namespace}"
        history_data = await redis_client.lrange(history_key, 0, limit - 1)
        
        if history_data:
            import json
            history = [json.loads(record) for record in history_data]
        else:
            history = []
        
        return {
            "status": "success",
            "data": {
                "history": history,
                "count": len(history),
                "limit": limit
            },
            "broker": settings.broker_namespace
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get pipeline history: {str(e)}"
        )


@router.get("/pipeline/stages/{stage_name}")
async def pipeline_stage_status(
    stage_name: str,
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """Get detailed status for a specific pipeline stage"""
    try:
        # Validate stage name
        valid_stages = [
            "market_ticks",
            "signals", 
            "signals_validated",
            "orders",
            "portfolio_updates"
        ]
        
        if stage_name not in valid_stages:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid stage name. Valid stages: {valid_stages}"
            )
        
        # Get stage-specific data
        last_key = f"pipeline:{stage_name}:{settings.broker_namespace}:last"
        count_key = f"pipeline:{stage_name}:{settings.broker_namespace}:count"
        
        last_data_str = await redis_client.get(last_key)
        total_count = await redis_client.get(count_key) or 0
        
        stage_data = {
            "stage_name": stage_name,
            "total_count": int(total_count),
            "broker": settings.broker_namespace
        }
        
        if last_data_str:
            import json
            from datetime import datetime
            
            last_activity = json.loads(last_data_str)
            last_time = datetime.fromisoformat(last_activity["timestamp"])
            age_seconds = (datetime.utcnow() - last_time).total_seconds()
            
            stage_data.update({
                "last_activity": last_activity,
                "age_seconds": age_seconds,
                "healthy": age_seconds < 60,  # Basic threshold
            })
        else:
            stage_data.update({
                "last_activity": None,
                "age_seconds": float('inf'),
                "healthy": False,
                "message": "No recent activity"
            })
        
        return {
            "status": "success",
            "data": stage_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stage status: {str(e)}"
        )


@router.get("/logs/statistics")
async def log_statistics(
    settings: Settings = Depends(get_settings)
) -> Dict[str, Any]:
    """Get logging system statistics"""
    try:
        # This would integrate with the enhanced logging system
        # For now, return basic information
        return {
            "status": "success",
            "data": {
                "logging_enabled": True,
                "log_channels": [
                    "trading",
                    "market_data", 
                    "api",
                    "performance",
                    "monitoring",
                    "error"
                ],
                "json_format_enabled": getattr(settings.logging, 'json_format', True) if hasattr(settings, 'logging') else True,
                "multi_channel_enabled": getattr(settings.logging, 'multi_channel_enabled', True) if hasattr(settings, 'logging') else True,
                "logs_directory": getattr(settings.logging, 'logs_dir', 'logs') if hasattr(settings, 'logging') else 'logs'
            },
            "broker": settings.broker_namespace
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get log statistics: {str(e)}"
        )


@router.post("/pipeline/reset")
async def reset_pipeline_metrics(
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """Reset pipeline metrics (useful for testing)"""
    try:
        metrics_collector = PipelineMetricsCollector(redis_client, settings)
        await metrics_collector.reset_metrics()
        
        return {
            "status": "success",
            "message": "Pipeline metrics reset successfully",
            "broker": settings.broker_namespace
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset pipeline metrics: {str(e)}"
        )


@router.get("/metrics")
async def get_metrics_summary(
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """Get overall metrics summary"""
    try:
        metrics_collector = PipelineMetricsCollector(redis_client, settings)
        health_data = await metrics_collector.get_pipeline_health()
        
        # Calculate summary statistics
        stages = health_data.get("stages", {})
        healthy_stages = sum(1 for stage in stages.values() if stage.get("healthy", False))
        total_stages = len(stages)
        
        # Get total counts across all stages
        total_events = 0
        for stage_name in ["market_ticks", "signals", "orders", "portfolio_updates"]:
            count_key = f"pipeline:{stage_name}:{settings.broker_namespace}:count"
            count = await redis_client.get(count_key) or 0
            total_events += int(count)
        
        return {
            "status": "success",
            "data": {
                "overall_health": health_data.get("overall_healthy", False),
                "healthy_stages": healthy_stages,
                "total_stages": total_stages,
                "health_percentage": round((healthy_stages / total_stages * 100), 2) if total_stages > 0 else 0,
                "total_events_processed": total_events,
                "broker": settings.broker_namespace,
                "timestamp": health_data.get("timestamp")
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get metrics summary: {str(e)}"
        )