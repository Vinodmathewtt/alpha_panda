from fastapi import Depends, HTTPException, status, Query
from dependency_injector.wiring import inject, Provide
from typing import Optional, List
import redis.asyncio as redis

from app.containers import AppContainer
from core.config.settings import Settings
from core.health.health_checker import ServiceHealthChecker
from core.monitoring import PipelineMonitor, PipelineMetricsCollector
from services.auth.service import AuthService
from core.trading.portfolio_cache import PortfolioCache
from api.services.log_service import LogService
from api.services.dashboard_service import DashboardService

# Enhanced Authentication Dependencies
@inject
async def get_current_user(
    auth_service: AuthService = Depends(Provide[AppContainer.auth_service])
):
    """Get current authenticated user with enhanced error handling"""
    if not auth_service.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please authenticate with Zerodha.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        user_profile = await auth_service.get_current_user_profile()
        if not user_profile:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to retrieve user profile. Please re-authenticate.",
            )
        return user_profile
    except HTTPException as http_exc:
        # FIXED: Re-raise HTTP exceptions (like 401) directly
        raise http_exc
    except Exception as e:
        # FIXED: Only catch non-HTTP exceptions as service unavailable
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Authentication service unavailable: {str(e)}"
        )

# Optional authentication for monitoring endpoints
@inject
async def get_current_user_optional(
    auth_service: AuthService = Depends(Provide[AppContainer.auth_service])
):
    """Optional authentication for monitoring endpoints"""
    try:
        if auth_service.is_authenticated():
            return await auth_service.get_current_user_profile()
        return None
    except Exception:
        return None

# Enhanced monitoring dependencies
@inject
def get_health_checker(
    settings: Settings = Depends(Provide[AppContainer.settings]),
    redis_client: redis.Redis = Depends(Provide[AppContainer.redis_client]),
    auth_service: AuthService = Depends(Provide[AppContainer.auth_service])
) -> ServiceHealthChecker:
    """Get configured health checker instance"""
    return ServiceHealthChecker(
        settings=settings,
        redis_client=redis_client,
        auth_service=auth_service
    )

@inject
def get_pipeline_monitor(
    pipeline_monitor: PipelineMonitor = Depends(Provide[AppContainer.pipeline_monitor])
) -> PipelineMonitor:
    """Get pipeline monitor instance"""
    return pipeline_monitor

@inject
def get_pipeline_metrics_collector(
    settings: Settings = Depends(Provide[AppContainer.settings]),
    redis_client: redis.Redis = Depends(Provide[AppContainer.redis_client]),
) -> PipelineMetricsCollector:
    """Get pipeline metrics collector via DI for API endpoints"""
    return PipelineMetricsCollector(redis_client, settings)

@inject
def get_log_service(
    settings: Settings = Depends(Provide[AppContainer.settings])
) -> LogService:
    """Get log service instance"""
    return LogService(settings)

@inject
def get_dashboard_service(
    settings: Settings = Depends(Provide[AppContainer.settings]),
    redis_client: redis.Redis = Depends(Provide[AppContainer.redis_client]),
    health_checker: ServiceHealthChecker = Depends(get_health_checker),
    pipeline_monitor: PipelineMonitor = Depends(get_pipeline_monitor)
) -> DashboardService:
    """Get dashboard service instance"""
    return DashboardService(settings, redis_client, health_checker, pipeline_monitor)

# Legacy dependencies for backward compatibility
@inject
def get_portfolio_cache(
    settings: Settings = Depends(Provide[AppContainer.settings])
) -> PortfolioCache:
    """Get portfolio cache instance for API endpoints"""
    return PortfolioCache(settings)

@inject
def get_settings(
    settings: Settings = Depends(Provide[AppContainer.settings])
) -> Settings:
    """Get application settings for API endpoints"""
    return settings

@inject
def get_redis_client(
    redis_client: redis.Redis = Depends(Provide[AppContainer.redis_client])
) -> redis.Redis:
    """Get Redis client for API endpoints"""
    return redis_client

# Query parameter dependencies
def get_pagination_params(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=1000, description="Page size")
):
    """Get pagination parameters with validation"""
    return {"page": page, "size": size, "offset": (page - 1) * size}

def get_log_filter_params(
    level: Optional[str] = Query(None, pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    service: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    search: Optional[str] = Query(None, max_length=500)
):
    """Get log filtering parameters"""
    return {
        "level": level,
        "service": service,
        "start_time": start_time,
        "end_time": end_time,
        "search": search
    }
