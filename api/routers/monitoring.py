"""
Monitoring and health API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Dict, Any, Optional
import redis.asyncio as redis
import time
from datetime import datetime, timezone

from core.config.settings import Settings
from core.health import ServiceHealthChecker
from api.dependencies import get_health_checker
from core.monitoring import PipelineMonitor
from api.dependencies import get_settings, get_redis_client, get_pipeline_metrics_collector
from core.logging import (
    get_api_logger_safe,
    get_performance_logger_safe,
    get_error_logger_safe,
)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# Initialize loggers
api_logger = get_api_logger_safe("monitoring_api")
performance_logger = get_performance_logger_safe("monitoring_performance")
error_logger = get_error_logger_safe("monitoring_errors")


@router.get("/health")
async def health_check(
    request: Request,
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client),
    health_checker: ServiceHealthChecker = Depends(get_health_checker),
) -> Dict[str, Any]:
    """Get overall system health"""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    api_logger.info("Health check requested",
                   client_ip=client_ip,
                   endpoint="/monitoring/health",
                   method="GET")
    
    try:
        await health_checker.start()
        
        health_status = await health_checker.get_overall_health()
        
        await health_checker.stop()
        
        processing_time = (time.time() - start_time) * 1000
        
        performance_logger.info("Health check completed",
                              processing_time_ms=processing_time,
                              checks_executed=len(health_status.get('checks', {})),
                              overall_status=health_status.get('status', 'unknown'),
                              client_ip=client_ip)
        
        api_logger.info("Health check API completed",
                       client_ip=client_ip,
                       processing_time_ms=processing_time,
                       response_code=200,
                       overall_health=health_status.get('status', 'unknown'))
        
        return {
            "status": "success",
            "data": health_status,
            "broker": settings.active_brokers[0] if settings.active_brokers else "unknown"
        }
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        error_logger.error("Health check failed",
                          client_ip=client_ip,
                          error=str(e),
                          processing_time_ms=processing_time,
                          exc_info=True)
        
        api_logger.error("Health check API error",
                        client_ip=client_ip,
                        error=str(e),
                        processing_time_ms=processing_time,
                        response_code=500)
        
        return {
            "status": "error",
            "message": f"Health check failed: {str(e)}",
            "broker": settings.active_brokers[0] if settings.active_brokers else "unknown"
        }


@router.get("/pipeline")
async def pipeline_status(
    request: Request,
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client),
    metrics_collector = Depends(get_pipeline_metrics_collector),
) -> Dict[str, Any]:
    """Get pipeline flow status and metrics"""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    api_logger.info("Pipeline status requested",
                   client_ip=client_ip,
                   endpoint="/monitoring/pipeline",
                   method="GET")
    
    try:
        # Get current pipeline validation status
        broker_ns = settings.active_brokers[0] if settings.active_brokers else "unknown"
        validation_key = f"pipeline:validation:{broker_ns}"
        validation_data = await redis_client.get(validation_key)
        
        if validation_data:
            import json
            pipeline_status = json.loads(validation_data)
        else:
            pipeline_status = {
                "broker": broker_ns,
                "status": "no_recent_data",
                "message": "No recent pipeline validation data available"
            }
        
        # Get pipeline health metrics via DI collector
        health_data = await metrics_collector.get_pipeline_health()
        
        processing_time = (time.time() - start_time) * 1000
        
        performance_logger.info("Pipeline status retrieved",
                              processing_time_ms=processing_time,
                              pipeline_status=pipeline_status.get('status', 'unknown'),
                              broker=broker_ns,
                              client_ip=client_ip)
        
        api_logger.info("Pipeline status API completed",
                       client_ip=client_ip,
                       processing_time_ms=processing_time,
                       response_code=200)
        
        return {
            "status": "success",
            "data": {
                "validation": pipeline_status,
                "health": health_data
            },
            "broker": broker_ns
        }
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        error_logger.error("Pipeline status retrieval failed",
                          client_ip=client_ip,
                          error=str(e),
                          processing_time_ms=processing_time,
                          exc_info=True)
        
        api_logger.error("Pipeline status API error",
                        client_ip=client_ip,
                        error=str(e),
                        processing_time_ms=processing_time,
                        response_code=500)
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get pipeline status: {str(e)}"
        )


@router.get("/pipeline/history")
async def pipeline_history(
    limit: int = 50,
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client),
    health_checker: ServiceHealthChecker = Depends(get_health_checker),
) -> Dict[str, Any]:
    """Get pipeline health history"""
    try:
        # Get health history from Redis
        broker_ns = settings.active_brokers[0] if settings.active_brokers else "unknown"
        history_key = f"pipeline:health_history:{broker_ns}"
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
            "broker": broker_ns
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
        broker_ns = settings.active_brokers[0] if settings.active_brokers else "unknown"
        last_key = f"pipeline:{stage_name}:{broker_ns}:last"
        count_key = f"pipeline:{stage_name}:{broker_ns}:count"
        
        last_data_str = await redis_client.get(last_key)
        total_count = await redis_client.get(count_key) or 0
        
        stage_data = {
            "stage_name": stage_name,
            "total_count": int(total_count),
            "broker": broker_ns
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
            "broker": settings.active_brokers[0] if settings.active_brokers else "unknown"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get log statistics: {str(e)}"
        )


@router.post("/pipeline/reset")
async def reset_pipeline_metrics(
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client),
    metrics_collector = Depends(get_pipeline_metrics_collector),
) -> Dict[str, Any]:
    """Reset pipeline metrics (useful for testing)"""
    try:
        await metrics_collector.reset_metrics()
        
        return {
            "status": "success",
            "message": "Pipeline metrics reset successfully",
            "broker": settings.active_brokers[0] if settings.active_brokers else "unknown"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset pipeline metrics: {str(e)}"
        )


@router.get("/metrics")
async def get_metrics_summary(
    request: Request,
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client),
    metrics_collector = Depends(get_pipeline_metrics_collector),
) -> Dict[str, Any]:
    """Get overall metrics summary"""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    api_logger.info("Metrics summary requested",
                   client_ip=client_ip,
                   endpoint="/monitoring/metrics",
                   method="GET")
    
    try:
        health_data = await metrics_collector.get_pipeline_health()
        
        # Calculate summary statistics
        stages = health_data.get("stages", {})
        healthy_stages = sum(1 for stage in stages.values() if stage.get("healthy", False))
        total_stages = len(stages)
        
        # Get total counts across all stages
        broker_ns = settings.active_brokers[0] if settings.active_brokers else "unknown"
        total_events = 0
        for stage_name in ["market_ticks", "signals", "orders", "portfolio_updates"]:
            count_key = f"pipeline:{stage_name}:{broker_ns}:count"
            count = await redis_client.get(count_key) or 0
            total_events += int(count)
        
        processing_time = (time.time() - start_time) * 1000
        
        performance_logger.info("Metrics summary generated",
                              processing_time_ms=processing_time,
                              total_events=total_events,
                              healthy_stages=healthy_stages,
                              total_stages=total_stages,
                              health_percentage=round((healthy_stages / total_stages * 100), 2) if total_stages > 0 else 0,
                              client_ip=client_ip)
        
        api_logger.info("Metrics summary API completed",
                       client_ip=client_ip,
                       processing_time_ms=processing_time,
                       response_code=200)
        
        return {
            "status": "success",
            "data": {
                "overall_health": health_data.get("overall_healthy", False),
                "healthy_stages": healthy_stages,
                "total_stages": total_stages,
                "health_percentage": round((healthy_stages / total_stages * 100), 2) if total_stages > 0 else 0,
                "total_events_processed": total_events,
                "broker": broker_ns,
                "timestamp": health_data.get("timestamp")
            }
        }
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        error_logger.error("Metrics summary generation failed",
                          client_ip=client_ip,
                          error=str(e),
                          processing_time_ms=processing_time,
                          exc_info=True)
        
        api_logger.error("Metrics summary API error",
                        client_ip=client_ip,
                        error=str(e),
                        processing_time_ms=processing_time,
                        response_code=500)
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get metrics summary: {str(e)}"
        )


@router.get("/health/history")
async def health_check_history(
    request: Request,
    component: Optional[str] = None,
    check_name: Optional[str] = None,
    limit: int = 50,
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client),
    health_checker: ServiceHealthChecker = Depends(get_health_checker),
) -> Dict[str, Any]:
    """Get health check history from Redis"""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    api_logger.info("Health check history requested",
                   client_ip=client_ip,
                   endpoint="/monitoring/health/history",
                   method="GET",
                   component=component,
                   check_name=check_name,
                   limit=limit)
    
    try:
        history = await health_checker.get_health_history(component, check_name, limit)
        
        processing_time = (time.time() - start_time) * 1000
        
        performance_logger.info("Health check history retrieved",
                              processing_time_ms=processing_time,
                              history_count=len(history),
                              component=component,
                              check_name=check_name,
                              client_ip=client_ip)
        
        api_logger.info("Health check history API completed",
                       client_ip=client_ip,
                       processing_time_ms=processing_time,
                       response_code=200,
                       history_count=len(history))
        
        return {
            "status": "success",
            "data": {
                "history": history,
                "count": len(history),
                "limit": limit,
                "component": component,
                "check_name": check_name
            }
        }
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        error_logger.error("Health check history retrieval failed",
                          client_ip=client_ip,
                          error=str(e),
                          processing_time_ms=processing_time,
                          component=component,
                          check_name=check_name,
                          exc_info=True)
        
        api_logger.error("Health check history API error",
                        client_ip=client_ip,
                        error=str(e),
                        processing_time_ms=processing_time,
                        response_code=500)
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get health check history: {str(e)}"
        )


@router.get("/health/service/{service_name}")
async def service_health_check(
    service_name: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client),
    health_checker: ServiceHealthChecker = Depends(get_health_checker),
) -> Dict[str, Any]:
    """Get health status for a specific service"""
    start_time = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    api_logger.info("Service-specific health check requested",
                   client_ip=client_ip,
                   endpoint=f"/monitoring/health/service/{service_name}",
                   method="GET",
                   service_name=service_name)
    
    try:
        # Validate service name
        valid_services = [
            "risk_manager", 
            "strategy_runner", "market_feed", "auth", "api",
            "paper_trading", "zerodha_trading",
        ]
        
        if service_name not in valid_services:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid service name. Valid services: {valid_services}"
            )
        
        # Run service-specific checks using DI-provided health checker
        await health_checker.start()
        
        # Filter health checks for specific service
        service_checks = []
        for check in health_checker.health_checks:
            if service_name in check.name or service_name in check.component:
                service_checks.append(check)
        
        # Run service-specific health checks
        results = {}
        for check in service_checks:
            if check.enabled:
                result = await health_checker.run_health_check(check)
                results[check.name] = result.to_dict()
        
        await health_checker.stop()
        
        # Calculate service health status
        if not results:
            service_status = "unknown"
            message = f"No health checks found for service: {service_name}"
        else:
            unhealthy_count = sum(1 for result in results.values() 
                                if result.get("status") == "unhealthy")
            degraded_count = sum(1 for result in results.values() 
                               if result.get("status") == "degraded")
            
            if unhealthy_count > 0:
                service_status = "unhealthy"
                message = f"Service has {unhealthy_count} unhealthy checks"
            elif degraded_count > 0:
                service_status = "degraded"
                message = f"Service has {degraded_count} degraded checks"
            else:
                service_status = "healthy"
                message = "All service health checks are healthy"
        
        processing_time = (time.time() - start_time) * 1000
        
        performance_logger.info("Service health check completed",
                              processing_time_ms=processing_time,
                              service_name=service_name,
                              service_status=service_status,
                              checks_count=len(results),
                              client_ip=client_ip)
        
        api_logger.info("Service health check API completed",
                       client_ip=client_ip,
                       processing_time_ms=processing_time,
                       response_code=200,
                       service_name=service_name,
                       service_status=service_status)
        
        return {
            "status": "success",
            "data": {
                "service_name": service_name,
                "service_status": service_status,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "checks": results,
                "summary": {
                    "total_checks": len(results),
                    "healthy": sum(1 for r in results.values() if r.get("status") == "healthy"),
                    "degraded": sum(1 for r in results.values() if r.get("status") == "degraded"), 
                    "unhealthy": sum(1 for r in results.values() if r.get("status") == "unhealthy")
                }
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        error_logger.error("Service health check failed",
                          client_ip=client_ip,
                          error=str(e),
                          processing_time_ms=processing_time,
                          service_name=service_name,
                          exc_info=True)
        
        api_logger.error("Service health check API error",
                        client_ip=client_ip,
                        error=str(e),
                        processing_time_ms=processing_time,
                        response_code=500,
                        service_name=service_name)
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get service health: {str(e)}"
        )
