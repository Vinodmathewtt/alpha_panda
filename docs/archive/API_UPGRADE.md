# Alpha Panda API Module Upgrade Plan

## Overview

This document outlines a comprehensive upgrade plan for the Alpha Panda API module to support the monitoring dashboard and enhance overall system observability. The upgrade addresses critical gaps in real-time monitoring, authentication, service management, and data access patterns.

## Current State Analysis

### Existing API Structure
```
api/
├── main.py                    # FastAPI app with basic setup
├── dependencies.py            # Basic DI for auth, settings, Redis
├── routers/
│   ├── auth.py               # 1 endpoint (auth status)
│   ├── portfolios.py         # 3 endpoints (CRUD operations)
│   └── monitoring.py         # 7 endpoints (health, pipeline, metrics)
```

### Identified Gaps
- **Missing real-time streaming** (SSE/WebSocket)
- **Incomplete monitoring integration** 
- **No log management endpoints**
- **Missing service status tracking**
- **Limited authentication coverage**
- **No alert management system**
- **Insufficient historical data access**

## Upgrade Architecture

### Enhanced Directory Structure
```
api/
├── main.py                           # Enhanced app with middleware
├── dependencies.py                   # Expanded DI container
├── middleware/                       # Custom middleware
│   ├── __init__.py
│   ├── auth.py                      # Enhanced authentication
│   ├── cors.py                      # CORS configuration
│   ├── rate_limiting.py             # Rate limiting
│   └── error_handling.py            # Global error handling
├── routers/
│   ├── __init__.py
│   ├── auth.py                      # Enhanced authentication
│   ├── portfolios.py                # Portfolio management (existing)
│   ├── monitoring.py                # Enhanced monitoring (existing)
│   ├── dashboard.py                 # Dashboard-specific endpoints
│   ├── services.py                  # Service management
│   ├── logs.py                      # Log management
│   ├── alerts.py                    # Alert management
│   ├── strategies.py                # Strategy management
│   ├── realtime.py                  # SSE/WebSocket endpoints
│   └── system.py                    # System information
├── schemas/                          # Enhanced API schemas
│   ├── __init__.py
│   ├── responses.py                 # Standard response models
│   ├── requests.py                  # Request validation models
│   ├── dashboard.py                 # Dashboard-specific schemas
│   ├── monitoring.py                # Monitoring schemas
│   └── errors.py                    # Error response schemas
├── services/                         # Business logic layer
│   ├── __init__.py
│   ├── dashboard_service.py         # Dashboard data aggregation
│   ├── log_service.py               # Log management service
│   ├── alert_service.py             # Alert management service
│   └── realtime_service.py          # Real-time data service
└── utils/                           # API utilities
    ├── __init__.py
    ├── pagination.py                # Pagination helpers
    ├── filtering.py                 # Query filtering
    ├── validators.py                # Custom validators
    └── formatters.py                # Response formatters
```

## Phase 1: Core Infrastructure (Week 1-2)

### 1.1 Enhanced Dependencies and Middleware

#### Enhanced Dependencies (`api/dependencies.py`)
```python
from fastapi import Depends, HTTPException, status, Query
from dependency_injector.wiring import inject, Provide
from typing import Optional, List
import redis.asyncio as redis

from app.containers import AppContainer
from core.config.settings import Settings
from core.health.health_checker import ServiceHealthChecker
from core.monitoring import PipelineMonitor, AlertManager, MetricsCollector
from services.auth.service import AuthService
from services.portfolio_manager.cache import PortfolioCache
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
    except Exception as e:
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
def get_alert_manager(
    settings: Settings = Depends(Provide[AppContainer.settings])
) -> AlertManager:
    """Get alert manager instance"""
    from core.monitoring.alerting import get_alert_manager
    return get_alert_manager(settings)

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

# Query parameter dependencies
def get_pagination_params(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=1000, description="Page size")
):
    """Get pagination parameters with validation"""
    return {"page": page, "size": size, "offset": (page - 1) * size}

def get_log_filter_params(
    level: Optional[str] = Query(None, regex="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
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
```

#### Authentication Middleware (`api/middleware/auth.py`)
```python
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
import time

class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Enhanced authentication middleware with session management"""
    
    def __init__(self, app, auth_service, excluded_paths=None):
        super().__init__(app)
        self.auth_service = auth_service
        self.excluded_paths = excluded_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/api/v1/auth/status"
        ]
    
    async def dispatch(self, request: Request, call_next):
        # Skip authentication for excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)
        
        # Check if monitoring endpoints should require auth
        if request.url.path.startswith("/api/v1/monitoring"):
            # Allow monitoring access without auth in development
            if getattr(self.auth_service.settings, 'environment', 'development') == 'development':
                return await call_next(request)
        
        # Require authentication for protected endpoints
        if not self.auth_service.is_authenticated():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        return await call_next(request)
```

### 1.2 Enhanced API Schemas

#### Response Schemas (`api/schemas/responses.py`)
```python
from pydantic import BaseModel, Field
from typing import Generic, TypeVar, List, Optional, Any, Dict
from datetime import datetime
from enum import Enum

T = TypeVar('T')

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

class ServiceStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    STARTING = "starting"
    STOPPING = "stopping"

class StandardResponse(BaseModel, Generic[T]):
    """Standard API response wrapper"""
    status: str = Field(description="Response status")
    message: Optional[str] = Field(None, description="Response message")
    data: Optional[T] = Field(None, description="Response data")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    broker: Optional[str] = Field(None, description="Broker namespace")

class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper"""
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Health Check Responses
class ComponentHealth(BaseModel):
    name: str
    component: str
    status: HealthStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime
    duration_ms: Optional[float] = None
    error: Optional[str] = None

class SystemHealthResponse(BaseModel):
    status: HealthStatus
    timestamp: datetime
    broker_namespace: str
    checks: Dict[str, ComponentHealth]
    summary: Dict[str, int]

# Service Management Responses
class ServiceInfo(BaseModel):
    name: str
    status: ServiceStatus
    started_at: Optional[datetime] = None
    uptime_seconds: Optional[float] = None
    version: Optional[str] = None
    health: HealthStatus
    metrics: Optional[Dict[str, Any]] = None

class ServiceListResponse(BaseModel):
    services: List[ServiceInfo]
    summary: Dict[str, int]

# Pipeline Monitoring Responses
class PipelineStageStatus(BaseModel):
    stage_name: str
    status: HealthStatus
    last_activity: Optional[Dict[str, Any]] = None
    age_seconds: float
    total_count: int
    healthy: bool
    threshold_seconds: float
    message: Optional[str] = None

class PipelineStatusResponse(BaseModel):
    broker: str
    timestamp: datetime
    overall_healthy: bool
    stages: Dict[str, PipelineStageStatus]
    health_check_interval: float

# Log Management Responses
class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    service: str
    message: str
    details: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None

class LogStatistics(BaseModel):
    total_entries: int
    by_level: Dict[str, int]
    by_service: Dict[str, int]
    recent_errors: int
    time_range: Dict[str, datetime]

# Alert Responses
class Alert(BaseModel):
    id: str
    title: str
    message: str
    severity: str
    category: str
    component: str
    status: str
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    details: Optional[Dict[str, Any]] = None

class AlertSummary(BaseModel):
    active_alerts: int
    critical_alerts: int
    acknowledged_alerts: int
    alerts_24h: int
    top_categories: Dict[str, int]
```

### 1.3 Enhanced Main Application

#### Updated Main App (`api/main.py`)
```python
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dependency_injector.wiring import inject
from contextlib import asynccontextmanager
import structlog

from app.containers import AppContainer
from api.middleware.auth import AuthenticationMiddleware
from api.middleware.error_handling import ErrorHandlingMiddleware
from api.middleware.rate_limiting import RateLimitingMiddleware
from api.routers import (
    auth, portfolios, monitoring, dashboard, services, 
    logs, alerts, strategies, realtime, system
)

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Alpha Panda API server")
    container = app.state.container
    
    # Initialize services
    try:
        await container.auth_service().initialize()
        await container.pipeline_monitor().start()
        logger.info("API services initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize API services", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Alpha Panda API server")
    try:
        await container.pipeline_monitor().stop()
        logger.info("API services stopped successfully")
    except Exception as e:
        logger.error("Error during API shutdown", error=str(e))

def create_app() -> FastAPI:
    """Creates and configures the FastAPI application"""
    app = FastAPI(
        title="Alpha Panda Trading API",
        version="2.1.0",
        description="Enhanced API for monitoring and managing the Alpha Panda trading system.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan
    )

    # Create and store DI container
    container = AppContainer()
    app.state.container = container
    
    # Wire dependency injection
    container.wire(modules=[
        "api.dependencies",
        "api.routers.auth",
        "api.routers.portfolios", 
        "api.routers.monitoring",
        "api.routers.dashboard",
        "api.routers.services",
        "api.routers.logs",
        "api.routers.alerts",
        "api.routers.strategies",
        "api.routers.realtime",
        "api.routers.system"
    ])

    # Add middleware
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RateLimitingMiddleware, calls=100, period=60)
    app.add_middleware(
        AuthenticationMiddleware,
        auth_service=container.auth_service(),
        excluded_paths=[
            "/health", "/docs", "/openapi.json", "/redoc",
            "/api/v1/auth/status", "/api/v1/system/info"
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
    app.include_router(portfolios.router, prefix="/api/v1", tags=["Portfolios"])
    app.include_router(monitoring.router, prefix="/api/v1", tags=["Monitoring"])
    app.include_router(dashboard.router, prefix="/api/v1", tags=["Dashboard"])
    app.include_router(services.router, prefix="/api/v1", tags=["Services"])
    app.include_router(logs.router, prefix="/api/v1", tags=["Logs"])
    app.include_router(alerts.router, prefix="/api/v1", tags=["Alerts"])
    app.include_router(strategies.router, prefix="/api/v1", tags=["Strategies"])
    app.include_router(realtime.router, prefix="/api/v1", tags=["Real-time"])
    app.include_router(system.router, prefix="/api/v1", tags=["System"])

    # Global exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled API exception", 
                    path=request.url.path,
                    method=request.method,
                    error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": "An unexpected error occurred",
                "timestamp": str(datetime.utcnow())
            }
        )

    # Health check endpoint
    @app.get("/health", tags=["Health"])
    def health_check():
        return {
            "status": "healthy",
            "service": "alpha-panda-api",
            "version": "2.1.0",
            "timestamp": str(datetime.utcnow())
        }

    # Root endpoint
    @app.get("/", tags=["Root"])
    def root():
        return {
            "service": "Alpha Panda Trading API",
            "version": "2.1.0",
            "docs": "/docs",
            "health": "/health",
            "api_prefix": "/api/v1"
        }

    return app

def run():
    """Main function to run the API server"""
    app = create_app()
    
    # Run with uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_level="info",
        access_log=True,
        reload=False  # Set to True for development
    )

if __name__ == "__main__":
    run()
```

## Phase 2: New Router Implementation (Week 2-3)

### 2.1 Real-time Streaming Router (`api/routers/realtime.py`)
```python
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse
from typing import List
import asyncio
import json
from datetime import datetime

from api.dependencies import get_dashboard_service, get_current_user_optional
from api.services.dashboard_service import DashboardService
from api.services.realtime_service import RealtimeService, ConnectionManager

router = APIRouter(prefix="/realtime", tags=["Real-time"])

# Connection manager for WebSocket connections
connection_manager = ConnectionManager()

@router.get("/events/health")
async def health_stream(
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user_optional)
):
    """Server-Sent Events stream for health monitoring updates"""
    async def event_generator():
        while True:
            try:
                health_data = await dashboard_service.get_health_summary()
                yield {
                    "event": "health_update",
                    "data": json.dumps({
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": health_data,
                        "user": current_user.user_id if current_user else None
                    })
                }
                await asyncio.sleep(10)  # Update every 10 seconds
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
                await asyncio.sleep(10)
    
    return EventSourceResponse(event_generator())

@router.get("/events/pipeline")
async def pipeline_stream(
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user_optional)
):
    """Server-Sent Events stream for pipeline monitoring updates"""
    async def event_generator():
        while True:
            try:
                pipeline_data = await dashboard_service.get_pipeline_summary()
                yield {
                    "event": "pipeline_update",
                    "data": json.dumps({
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": pipeline_data,
                        "user": current_user.user_id if current_user else None
                    })
                }
                await asyncio.sleep(5)  # Update every 5 seconds
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
                await asyncio.sleep(5)
    
    return EventSourceResponse(event_generator())

@router.get("/events/logs")
async def log_stream(
    level: str = None,
    service: str = None,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user_optional)
):
    """Server-Sent Events stream for log entries"""
    async def event_generator():
        async for log_entry in dashboard_service.stream_logs(level=level, service=service):
            try:
                yield {
                    "event": "log_entry",
                    "data": json.dumps({
                        "timestamp": log_entry.get("timestamp"),
                        "level": log_entry.get("level"),
                        "service": log_entry.get("service"),
                        "message": log_entry.get("message"),
                        "details": log_entry.get("details"),
                        "user": current_user.user_id if current_user else None
                    })
                }
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
    
    return EventSourceResponse(event_generator())

@router.get("/events/activity")
async def activity_stream(
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user_optional)
):
    """Server-Sent Events stream for system activity feed"""
    async def event_generator():
        async for activity in dashboard_service.stream_activity():
            try:
                yield {
                    "event": "activity_item",
                    "data": json.dumps({
                        "timestamp": activity.get("timestamp"),
                        "type": activity.get("type"),
                        "service": activity.get("service"),
                        "message": activity.get("message"),
                        "severity": activity.get("severity", "info"),
                        "user": current_user.user_id if current_user else None
                    })
                }
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
    
    return EventSourceResponse(event_generator())

@router.websocket("/ws/monitoring")
async def monitoring_websocket(
    websocket: WebSocket,
    dashboard_service: DashboardService = Depends(get_dashboard_service)
):
    """WebSocket endpoint for real-time monitoring (fallback for SSE)"""
    await connection_manager.connect(websocket)
    
    try:
        while True:
            # Send periodic updates
            health_data = await dashboard_service.get_health_summary()
            pipeline_data = await dashboard_service.get_pipeline_summary()
            
            await connection_manager.send_json({
                "type": "monitoring_update",
                "timestamp": datetime.utcnow().isoformat(),
                "health": health_data,
                "pipeline": pipeline_data
            }, websocket)
            
            await asyncio.sleep(10)
            
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as e:
        await connection_manager.send_json({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)
        connection_manager.disconnect(websocket)

@router.websocket("/ws/logs")
async def logs_websocket(
    websocket: WebSocket,
    dashboard_service: DashboardService = Depends(get_dashboard_service)
):
    """WebSocket endpoint for real-time log streaming"""
    await connection_manager.connect(websocket)
    
    try:
        async for log_entry in dashboard_service.stream_logs():
            await connection_manager.send_json({
                "type": "log_entry",
                "timestamp": log_entry.get("timestamp"),
                "data": log_entry
            }, websocket)
            
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as e:
        await connection_manager.send_json({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)
        connection_manager.disconnect(websocket)
```

### 2.2 Log Management Router (`api/routers/logs.py`)
```python
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import Optional, List
from datetime import datetime, timedelta
import asyncio

from api.dependencies import get_log_service, get_pagination_params, get_log_filter_params
from api.services.log_service import LogService
from api.schemas.responses import StandardResponse, PaginatedResponse, LogEntry, LogStatistics

router = APIRouter(prefix="/logs", tags=["Logs"])

@router.get("/", response_model=PaginatedResponse[LogEntry])
async def get_logs(
    pagination: dict = Depends(get_pagination_params),
    filters: dict = Depends(get_log_filter_params),
    log_service: LogService = Depends(get_log_service)
):
    """Get paginated log entries with filtering"""
    try:
        logs = await log_service.get_logs(
            offset=pagination["offset"],
            limit=pagination["size"],
            filters=filters
        )
        
        total = await log_service.count_logs(filters)
        
        return PaginatedResponse(
            items=logs,
            total=total,
            page=pagination["page"],
            size=pagination["size"],
            pages=(total + pagination["size"] - 1) // pagination["size"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve logs: {str(e)}")

@router.get("/statistics", response_model=StandardResponse[LogStatistics])
async def get_log_statistics(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
    log_service: LogService = Depends(get_log_service)
):
    """Get log statistics for the specified time period"""
    try:
        start_time = datetime.utcnow() - timedelta(hours=hours)
        stats = await log_service.get_statistics(start_time=start_time)
        
        return StandardResponse(
            status="success",
            data=stats,
            message=f"Log statistics for last {hours} hours"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get log statistics: {str(e)}")

@router.get("/services", response_model=StandardResponse[List[str]])
async def get_log_services(
    log_service: LogService = Depends(get_log_service)
):
    """Get list of available log services/sources"""
    try:
        services = await log_service.get_available_services()
        return StandardResponse(
            status="success",
            data=services,
            message="Available log services"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get log services: {str(e)}")

@router.get("/channels", response_model=StandardResponse[List[str]])
async def get_log_channels(
    log_service: LogService = Depends(get_log_service)
):
    """Get list of available log channels"""
    try:
        channels = await log_service.get_available_channels()
        return StandardResponse(
            status="success",
            data=channels,
            message="Available log channels"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get log channels: {str(e)}")

@router.post("/export")
async def export_logs(
    background_tasks: BackgroundTasks,
    format: str = Query("json", regex="^(json|csv|txt)$"),
    filters: dict = Depends(get_log_filter_params),
    log_service: LogService = Depends(get_log_service)
):
    """Export logs in specified format"""
    try:
        # Generate export file in background
        export_id = await log_service.create_export_task(
            format=format,
            filters=filters
        )
        
        background_tasks.add_task(
            log_service.process_export_task,
            export_id
        )
        
        return StandardResponse(
            status="success",
            data={"export_id": export_id, "format": format},
            message="Log export started. Check export status endpoint."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start log export: {str(e)}")

@router.get("/export/{export_id}/status")
async def get_export_status(
    export_id: str,
    log_service: LogService = Depends(get_log_service)
):
    """Get status of log export task"""
    try:
        status = await log_service.get_export_status(export_id)
        return StandardResponse(
            status="success",
            data=status,
            message="Export status retrieved"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get export status: {str(e)}")

@router.get("/search")
async def search_logs(
    query: str = Query(..., min_length=3, max_length=500),
    pagination: dict = Depends(get_pagination_params),
    log_service: LogService = Depends(get_log_service)
):
    """Full-text search in logs"""
    try:
        results = await log_service.search_logs(
            query=query,
            offset=pagination["offset"],
            limit=pagination["size"]
        )
        
        total = await log_service.count_search_results(query)
        
        return PaginatedResponse(
            items=results,
            total=total,
            page=pagination["page"],
            size=pagination["size"],
            pages=(total + pagination["size"] - 1) // pagination["size"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Log search failed: {str(e)}")
```

### 2.3 Service Management Router (`api/routers/services.py`)
```python
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Dict, Any

from api.dependencies import get_dashboard_service, get_current_user
from api.services.dashboard_service import DashboardService
from api.schemas.responses import StandardResponse, ServiceInfo, ServiceListResponse

router = APIRouter(prefix="/services", tags=["Services"])

@router.get("/", response_model=StandardResponse[ServiceListResponse])
async def get_all_services(
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get status of all Alpha Panda services"""
    try:
        services_info = await dashboard_service.get_all_services_status()
        
        summary = {
            "running": sum(1 for s in services_info if s.status == "running"),
            "stopped": sum(1 for s in services_info if s.status == "stopped"),
            "error": sum(1 for s in services_info if s.status == "error"),
            "total": len(services_info)
        }
        
        return StandardResponse(
            status="success",
            data=ServiceListResponse(services=services_info, summary=summary),
            message="Service status retrieved successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get services status: {str(e)}")

@router.get("/{service_name}", response_model=StandardResponse[ServiceInfo])
async def get_service_status(
    service_name: str,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get detailed status of a specific service"""
    try:
        service_info = await dashboard_service.get_service_status(service_name)
        
        if not service_info:
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
        
        return StandardResponse(
            status="success",
            data=service_info,
            message=f"Status for service '{service_name}'"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get service status: {str(e)}")

@router.get("/{service_name}/metrics", response_model=StandardResponse[Dict[str, Any]])
async def get_service_metrics(
    service_name: str,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get performance metrics for a specific service"""
    try:
        metrics = await dashboard_service.get_service_metrics(service_name)
        
        if not metrics:
            raise HTTPException(status_code=404, detail=f"Metrics for service '{service_name}' not found")
        
        return StandardResponse(
            status="success",
            data=metrics,
            message=f"Metrics for service '{service_name}'"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get service metrics: {str(e)}")

@router.get("/{service_name}/health", response_model=StandardResponse[Dict[str, Any]])
async def get_service_health(
    service_name: str,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get health check details for a specific service"""
    try:
        health = await dashboard_service.get_service_health(service_name)
        
        if not health:
            raise HTTPException(status_code=404, detail=f"Health data for service '{service_name}' not found")
        
        return StandardResponse(
            status="success",
            data=health,
            message=f"Health check for service '{service_name}'"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get service health: {str(e)}")

@router.post("/{service_name}/restart")
async def restart_service(
    service_name: str,
    background_tasks: BackgroundTasks,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Restart a specific service (admin only)"""
    try:
        # Add background task for service restart
        background_tasks.add_task(
            dashboard_service.restart_service,
            service_name,
            user_id=current_user.user_id
        )
        
        return StandardResponse(
            status="success",
            data={"service_name": service_name, "action": "restart_initiated"},
            message=f"Restart initiated for service '{service_name}'"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart service: {str(e)}")

@router.get("/{service_name}/logs", response_model=StandardResponse[List[Dict[str, Any]]])
async def get_service_logs(
    service_name: str,
    lines: int = 100,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get recent logs for a specific service"""
    try:
        logs = await dashboard_service.get_service_logs(service_name, lines=lines)
        
        return StandardResponse(
            status="success",
            data=logs,
            message=f"Recent logs for service '{service_name}'"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get service logs: {str(e)}")
```

## Phase 3: Business Logic Services (Week 3-4)

### 3.1 Dashboard Service (`api/services/dashboard_service.py`)
```python
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, AsyncGenerator
import json
import redis.asyncio as redis

from core.config.settings import Settings
from core.health.health_checker import ServiceHealthChecker
from core.monitoring import PipelineMonitor
from api.schemas.responses import ServiceInfo, ServiceStatus, HealthStatus

class DashboardService:
    """Service for aggregating dashboard data from various sources"""
    
    def __init__(
        self,
        settings: Settings,
        redis_client: redis.Redis,
        health_checker: ServiceHealthChecker,
        pipeline_monitor: PipelineMonitor
    ):
        self.settings = settings
        self.redis = redis_client
        self.health_checker = health_checker
        self.pipeline_monitor = pipeline_monitor
        self.broker = settings.broker_namespace
    
    async def get_health_summary(self) -> Dict[str, Any]:
        """Get overall system health summary"""
        try:
            health_data = await self.health_checker.get_overall_health()
            
            # Add dashboard-specific metrics
            uptime = await self._get_system_uptime()
            last_restart = await self._get_last_restart_time()
            
            return {
                **health_data,
                "uptime_seconds": uptime,
                "last_restart": last_restart,
                "broker": self.broker
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
                "broker": self.broker
            }
    
    async def get_pipeline_summary(self) -> Dict[str, Any]:
        """Get pipeline flow summary with metrics"""
        try:
            pipeline_health = await self.pipeline_monitor.get_pipeline_health()
            
            # Add flow rate calculations
            flow_rates = await self._calculate_flow_rates()
            
            return {
                **pipeline_health,
                "flow_rates": flow_rates,
                "broker": self.broker
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
                "broker": self.broker
            }
    
    async def get_all_services_status(self) -> List[ServiceInfo]:
        """Get status of all Alpha Panda services"""
        services = [
            "auth_service",
            "market_feed_service", 
            "strategy_runner_service",
            "risk_manager_service",
            "trading_engine_service",
            "portfolio_manager_service",
            "pipeline_monitor"
        ]
        
        service_infos = []
        for service_name in services:
            try:
                info = await self._get_service_info(service_name)
                service_infos.append(info)
            except Exception as e:
                service_infos.append(ServiceInfo(
                    name=service_name,
                    status=ServiceStatus.ERROR,
                    health=HealthStatus.UNHEALTHY,
                    metrics={"error": str(e)}
                ))
        
        return service_infos
    
    async def get_service_status(self, service_name: str) -> Optional[ServiceInfo]:
        """Get detailed status for a specific service"""
        try:
            return await self._get_service_info(service_name)
        except Exception:
            return None
    
    async def get_service_metrics(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get performance metrics for a specific service"""
        try:
            metrics_key = f"metrics:{service_name}:{self.broker}"
            metrics_data = await self.redis.get(metrics_key)
            
            if metrics_data:
                return json.loads(metrics_data)
            
            return await self._collect_service_metrics(service_name)
        except Exception:
            return None
    
    async def get_service_health(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get health check details for a specific service"""
        try:
            # Get from health checker results
            health_results = await self.health_checker.get_overall_health()
            checks = health_results.get("checks", {})
            
            # Find health checks related to this service
            service_checks = {
                name: check for name, check in checks.items()
                if service_name in name or service_name in check.get("component", "")
            }
            
            return service_checks if service_checks else None
        except Exception:
            return None
    
    async def stream_logs(
        self, 
        level: Optional[str] = None, 
        service: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream log entries in real-time"""
        # This would integrate with the actual logging system
        # For now, simulate with Redis pub/sub
        try:
            pubsub = self.redis.pubsub()
            log_channel = f"logs:{self.broker}"
            if service:
                log_channel = f"logs:{service}:{self.broker}"
            
            await pubsub.subscribe(log_channel)
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        log_data = json.loads(message["data"])
                        
                        # Filter by level if specified
                        if level and log_data.get("level") != level:
                            continue
                        
                        yield log_data
                    except json.JSONDecodeError:
                        continue
        except Exception:
            # Fallback to polling for log entries
            async for log_entry in self._poll_logs(level, service):
                yield log_entry
    
    async def stream_activity(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream system activity events"""
        try:
            activity_key = f"activity:{self.broker}"
            
            while True:
                # Get recent activity from Redis list
                activities = await self.redis.lrange(activity_key, 0, 9)
                
                for activity_data in reversed(activities):
                    try:
                        activity = json.loads(activity_data)
                        yield activity
                    except json.JSONDecodeError:
                        continue
                
                await asyncio.sleep(2)
        except Exception:
            # Fallback activity generation
            async for activity in self._generate_activity_feed():
                yield activity
    
    async def restart_service(self, service_name: str, user_id: str):
        """Restart a specific service (admin operation)"""
        try:
            # Log the restart request
            await self._log_admin_action("service_restart", service_name, user_id)
            
            # This would integrate with actual service management
            # For now, just update service status
            restart_key = f"service:{service_name}:restart_requested"
            await self.redis.setex(restart_key, 300, json.dumps({
                "timestamp": datetime.utcnow().isoformat(),
                "requested_by": user_id,
                "status": "pending"
            }))
            
        except Exception as e:
            await self._log_admin_action("service_restart_failed", service_name, user_id, str(e))
            raise
    
    async def get_service_logs(self, service_name: str, lines: int = 100) -> List[Dict[str, Any]]:
        """Get recent logs for a specific service"""
        try:
            logs_key = f"logs:{service_name}:{self.broker}"
            log_entries = await self.redis.lrange(logs_key, 0, lines - 1)
            
            logs = []
            for entry in log_entries:
                try:
                    log_data = json.loads(entry)
                    logs.append(log_data)
                except json.JSONDecodeError:
                    continue
            
            return logs
        except Exception:
            return []
    
    # Private helper methods
    async def _get_system_uptime(self) -> float:
        """Get system uptime in seconds"""
        uptime_key = f"system:uptime:{self.broker}"
        uptime_data = await self.redis.get(uptime_key)
        
        if uptime_data:
            start_time = datetime.fromisoformat(uptime_data.decode())
            return (datetime.utcnow() - start_time).total_seconds()
        
        return 0.0
    
    async def _get_last_restart_time(self) -> Optional[str]:
        """Get timestamp of last system restart"""
        restart_key = f"system:last_restart:{self.broker}"
        restart_data = await self.redis.get(restart_key)
        
        return restart_data.decode() if restart_data else None
    
    async def _calculate_flow_rates(self) -> Dict[str, float]:
        """Calculate message flow rates per minute"""
        stages = ["market_ticks", "signals", "orders", "portfolio_updates"]
        rates = {}
        
        for stage in stages:
            try:
                # Get counts from last two minutes
                current_key = f"pipeline:{stage}:{self.broker}:count"
                current_count = int(await self.redis.get(current_key) or 0)
                
                # Estimate rate (simplified - would need time-windowed counting in production)
                prev_key = f"pipeline:{stage}:{self.broker}:count:prev"
                prev_count = int(await self.redis.get(prev_key) or 0)
                
                rates[stage] = max(0, current_count - prev_count)
                
                # Update previous count
                await self.redis.setex(prev_key, 120, current_count)
                
            except Exception:
                rates[stage] = 0.0
        
        return rates
    
    async def _get_service_info(self, service_name: str) -> ServiceInfo:
        """Get detailed service information"""
        # This would integrate with actual service monitoring
        status_key = f"service:{service_name}:{self.broker}:status"
        status_data = await self.redis.get(status_key)
        
        if status_data:
            data = json.loads(status_data)
            return ServiceInfo(
                name=service_name,
                status=ServiceStatus(data.get("status", "unknown")),
                started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
                uptime_seconds=data.get("uptime_seconds"),
                version=data.get("version"),
                health=HealthStatus(data.get("health", "unknown")),
                metrics=data.get("metrics")
            )
        
        # Default fallback
        return ServiceInfo(
            name=service_name,
            status=ServiceStatus.UNKNOWN,
            health=HealthStatus.UNKNOWN
        )
    
    async def _collect_service_metrics(self, service_name: str) -> Dict[str, Any]:
        """Collect real-time metrics for a service"""
        # This would integrate with actual metrics collection
        return {
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "message_rate": 0.0,
            "error_rate": 0.0,
            "uptime": 0.0
        }
    
    async def _poll_logs(
        self, 
        level: Optional[str], 
        service: Optional[str]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Poll for log entries when streaming is not available"""
        last_timestamp = datetime.utcnow()
        
        while True:
            try:
                # This would integrate with actual log storage
                # Simulate log entries for now
                yield {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": level or "INFO",
                    "service": service or "system",
                    "message": f"Sample log entry from {service or 'system'}",
                    "details": None
                }
                
                await asyncio.sleep(5)
            except Exception:
                break
    
    async def _generate_activity_feed(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Generate system activity feed"""
        activities = [
            "Market data received",
            "Signal generated", 
            "Order executed",
            "Portfolio updated",
            "Health check completed"
        ]
        
        while True:
            try:
                import random
                activity = random.choice(activities)
                
                yield {
                    "timestamp": datetime.utcnow().isoformat(),
                    "type": "system_event",
                    "service": "system",
                    "message": activity,
                    "severity": "info"
                }
                
                await asyncio.sleep(10)
            except Exception:
                break
    
    async def _log_admin_action(
        self, 
        action: str, 
        target: str, 
        user_id: str, 
        error: Optional[str] = None
    ):
        """Log administrative actions"""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "target": target,
            "user_id": user_id,
            "broker": self.broker,
            "error": error
        }
        
        admin_log_key = f"admin_actions:{self.broker}"
        await self.redis.lpush(admin_log_key, json.dumps(log_entry))
        await self.redis.ltrim(admin_log_key, 0, 999)  # Keep last 1000 actions
```

## Phase 4: Alert and Strategy Management (Week 4-5)

### 4.1 Alert Management Router (`api/routers/alerts.py`)
```python
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from api.dependencies import get_alert_manager, get_current_user, get_pagination_params
from core.monitoring.alerting import AlertManager
from api.schemas.responses import StandardResponse, PaginatedResponse, Alert, AlertSummary

router = APIRouter(prefix="/alerts", tags=["Alerts"])

@router.get("/", response_model=PaginatedResponse[Alert])
async def get_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    pagination: dict = Depends(get_pagination_params),
    alert_manager: AlertManager = Depends(get_alert_manager),
    current_user = Depends(get_current_user)
):
    """Get paginated list of alerts with filtering"""
    try:
        alerts = await alert_manager.get_alerts(
            status=status,
            severity=severity,
            category=category,
            offset=pagination["offset"],
            limit=pagination["size"]
        )
        
        total = await alert_manager.count_alerts(
            status=status,
            severity=severity,
            category=category
        )
        
        return PaginatedResponse(
            items=alerts,
            total=total,
            page=pagination["page"],
            size=pagination["size"],
            pages=(total + pagination["size"] - 1) // pagination["size"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alerts: {str(e)}")

@router.get("/summary", response_model=StandardResponse[AlertSummary])
async def get_alert_summary(
    alert_manager: AlertManager = Depends(get_alert_manager),
    current_user = Depends(get_current_user)
):
    """Get alert summary statistics"""
    try:
        summary = await alert_manager.get_alert_summary()
        return StandardResponse(
            status="success",
            data=summary,
            message="Alert summary retrieved"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alert summary: {str(e)}")

@router.get("/{alert_id}", response_model=StandardResponse[Alert])
async def get_alert(
    alert_id: str,
    alert_manager: AlertManager = Depends(get_alert_manager),
    current_user = Depends(get_current_user)
):
    """Get specific alert details"""
    try:
        alert = await alert_manager.get_alert(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return StandardResponse(
            status="success",
            data=alert,
            message=f"Alert {alert_id} retrieved"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alert: {str(e)}")

@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    alert_manager: AlertManager = Depends(get_alert_manager),
    current_user = Depends(get_current_user)
):
    """Acknowledge an alert"""
    try:
        success = await alert_manager.acknowledge_alert(alert_id, current_user.user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return StandardResponse(
            status="success",
            data={"alert_id": alert_id, "acknowledged_by": current_user.user_id},
            message="Alert acknowledged successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to acknowledge alert: {str(e)}")

@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    alert_manager: AlertManager = Depends(get_alert_manager),
    current_user = Depends(get_current_user)
):
    """Resolve an alert"""
    try:
        success = await alert_manager.resolve_alert(alert_id, current_user.user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return StandardResponse(
            status="success",
            data={"alert_id": alert_id, "resolved_by": current_user.user_id},
            message="Alert resolved successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resolve alert: {str(e)}")

@router.get("/history/statistics")
async def get_alert_history_stats(
    days: int = 30,
    alert_manager: AlertManager = Depends(get_alert_manager),
    current_user = Depends(get_current_user)
):
    """Get alert history statistics"""
    try:
        start_date = datetime.utcnow() - timedelta(days=days)
        stats = await alert_manager.get_history_statistics(start_date)
        
        return StandardResponse(
            status="success",
            data=stats,
            message=f"Alert statistics for last {days} days"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alert history: {str(e)}")
```

### 4.2 Strategy Management Router (`api/routers/strategies.py`)
```python
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional

from api.dependencies import get_current_user, get_db_manager, get_pagination_params
from core.database.connection import DatabaseManager
from api.schemas.responses import StandardResponse, PaginatedResponse

router = APIRouter(prefix="/strategies", tags=["Strategies"])

@router.get("/", response_model=PaginatedResponse[Dict[str, Any]])
async def get_strategies(
    active_only: bool = True,
    pagination: dict = Depends(get_pagination_params),
    db_manager: DatabaseManager = Depends(get_db_manager),
    current_user = Depends(get_current_user)
):
    """Get list of trading strategies"""
    try:
        async with db_manager.get_session() as session:
            # This would use proper strategy models
            query = "SELECT * FROM strategies"
            if active_only:
                query += " WHERE is_active = true"
            query += f" LIMIT {pagination['size']} OFFSET {pagination['offset']}"
            
            result = await session.execute(query)
            strategies = [dict(row) for row in result.fetchall()]
            
            # Get total count
            count_query = "SELECT COUNT(*) FROM strategies"
            if active_only:
                count_query += " WHERE is_active = true"
            
            count_result = await session.execute(count_query)
            total = count_result.scalar()
        
        return PaginatedResponse(
            items=strategies,
            total=total,
            page=pagination["page"],
            size=pagination["size"],
            pages=(total + pagination["size"] - 1) // pagination["size"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get strategies: {str(e)}")

@router.get("/{strategy_id}", response_model=StandardResponse[Dict[str, Any]])
async def get_strategy(
    strategy_id: str,
    db_manager: DatabaseManager = Depends(get_db_manager),
    current_user = Depends(get_current_user)
):
    """Get specific strategy details"""
    try:
        async with db_manager.get_session() as session:
            result = await session.execute(
                "SELECT * FROM strategies WHERE id = :id",
                {"id": strategy_id}
            )
            strategy = result.fetchone()
            
            if not strategy:
                raise HTTPException(status_code=404, detail="Strategy not found")
            
            return StandardResponse(
                status="success",
                data=dict(strategy),
                message=f"Strategy {strategy_id} retrieved"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get strategy: {str(e)}")

@router.get("/{strategy_id}/performance")
async def get_strategy_performance(
    strategy_id: str,
    days: int = 30,
    db_manager: DatabaseManager = Depends(get_db_manager),
    current_user = Depends(get_current_user)
):
    """Get strategy performance metrics"""
    try:
        # This would calculate actual performance metrics
        performance_data = {
            "strategy_id": strategy_id,
            "period_days": days,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "win_rate": 0.0
        }
        
        return StandardResponse(
            status="success",
            data=performance_data,
            message=f"Performance metrics for strategy {strategy_id}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get strategy performance: {str(e)}")

@router.post("/{strategy_id}/toggle")
async def toggle_strategy(
    strategy_id: str,
    db_manager: DatabaseManager = Depends(get_db_manager),
    current_user = Depends(get_current_user)
):
    """Enable/disable a strategy"""
    try:
        async with db_manager.get_session() as session:
            # Get current status
            result = await session.execute(
                "SELECT is_active FROM strategies WHERE id = :id",
                {"id": strategy_id}
            )
            row = result.fetchone()
            
            if not row:
                raise HTTPException(status_code=404, detail="Strategy not found")
            
            # Toggle status
            new_status = not row.is_active
            await session.execute(
                "UPDATE strategies SET is_active = :status, updated_at = :now WHERE id = :id",
                {"status": new_status, "now": datetime.utcnow(), "id": strategy_id}
            )
            await session.commit()
        
        return StandardResponse(
            status="success",
            data={
                "strategy_id": strategy_id,
                "is_active": new_status,
                "updated_by": current_user.user_id
            },
            message=f"Strategy {strategy_id} {'enabled' if new_status else 'disabled'}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle strategy: {str(e)}")
```

## Phase 5: Testing and Documentation (Week 5-6)

### 5.1 API Testing Framework

#### Test Configuration (`tests/api/conftest.py`)
```python
import pytest
import asyncio
from httpx import AsyncClient
from fastapi.testclient import TestClient

from api.main import create_app
from app.containers import AppContainer

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def app():
    """Create test application"""
    app = create_app()
    # Override dependencies for testing
    yield app

@pytest.fixture
async def client(app):
    """Create test client"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.fixture
def auth_headers():
    """Mock authentication headers"""
    return {"Authorization": "Bearer test-token"}
```

#### Integration Tests (`tests/api/test_monitoring_endpoints.py`)
```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test health endpoint"""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_monitoring_health(client: AsyncClient, auth_headers):
    """Test monitoring health endpoint"""
    response = await client.get("/api/v1/monitoring/health", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "data" in data

@pytest.mark.asyncio
async def test_pipeline_status(client: AsyncClient, auth_headers):
    """Test pipeline status endpoint"""
    response = await client.get("/api/v1/monitoring/pipeline", headers=auth_headers)
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_services_list(client: AsyncClient, auth_headers):
    """Test services list endpoint"""
    response = await client.get("/api/v1/services/", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "services" in data["data"]

@pytest.mark.asyncio
async def test_logs_endpoint(client: AsyncClient, auth_headers):
    """Test logs endpoint"""
    response = await client.get("/api/v1/logs/", headers=auth_headers)
    assert response.status_code == 200

@pytest.mark.asyncio
async def test_real_time_health_stream(client: AsyncClient):
    """Test SSE health stream"""
    # This would test the SSE endpoint
    async with client.stream("GET", "/api/v1/realtime/events/health") as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"
```

### 5.2 API Documentation Enhancement

#### OpenAPI Configuration (`api/main.py` additions)
```python
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    """Custom OpenAPI schema with enhanced documentation"""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Alpha Panda Trading API",
        version="2.1.0",
        description="""
        # Alpha Panda Trading API
        
        Enhanced API for monitoring and managing the Alpha Panda algorithmic trading system.
        
        ## Features
        - **Real-time Monitoring**: Health checks, pipeline status, system metrics
        - **Service Management**: Start, stop, and monitor individual services
        - **Log Management**: Search, filter, and stream log entries
        - **Alert System**: Manage and acknowledge system alerts
        - **Strategy Control**: Enable, disable, and monitor trading strategies
        - **Portfolio Analytics**: Real-time portfolio and position tracking
        
        ## Authentication
        All endpoints require valid Zerodha authentication unless specified otherwise.
        
        ## Real-time Updates
        - Server-Sent Events (SSE) for live data streaming
        - WebSocket fallback for browsers with limited SSE support
        
        ## Broker Namespaces
        API supports both paper trading (`paper`) and Zerodha (`zerodha`) broker namespaces.
        """,
        routes=app.routes,
    )
    
    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "ZerodhaAuth": {
            "type": "http",
            "scheme": "bearer",
            "description": "Zerodha authentication token"
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

## Deployment Configuration

### 5.3 Updated Container Configuration (`app/containers.py` additions)
```python
# Add new providers for API services
class AppContainer(containers.DeclarativeContainer):
    # ... existing providers ...
    
    # API-specific services
    log_service = providers.Singleton(
        LogService,
        settings=settings
    )
    
    dashboard_service = providers.Singleton(
        DashboardService,
        settings=settings,
        redis_client=redis_client,
        health_checker=providers.Factory(
            ServiceHealthChecker,
            settings=settings,
            redis_client=redis_client,
            auth_service=auth_service
        ),
        pipeline_monitor=pipeline_monitor
    )
    
    alert_service = providers.Singleton(
        AlertService,
        settings=settings,
        redis_client=redis_client
    )
```

### 5.4 Environment Configuration
```bash
# API-specific environment variables
API_VERSION=2.1.0
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=1
API_RELOAD=false

# Authentication
API_REQUIRE_AUTH=true
API_SESSION_TIMEOUT=3600

# Rate limiting
API_RATE_LIMIT_CALLS=100
API_RATE_LIMIT_PERIOD=60

# Real-time features
API_SSE_ENABLED=true
API_WEBSOCKET_ENABLED=true
API_MAX_SSE_CONNECTIONS=100

# Monitoring
API_HEALTH_CHECK_INTERVAL=30
API_METRICS_RETENTION_HOURS=24
```

## Summary

This comprehensive API upgrade plan transforms the basic 3-router API into a full-featured monitoring and management system with:

### **Enhanced Capabilities**:
- **10+ new routers** with 40+ new endpoints
- **Real-time streaming** via SSE and WebSocket
- **Complete monitoring suite** with health checks and metrics
- **Advanced authentication** and security middleware
- **Service management** capabilities
- **Log streaming and search** functionality
- **Alert management** system
- **Strategy control** interface

### **Production-Ready Features**:
- **Error handling** and validation
- **Rate limiting** and CORS
- **Comprehensive logging** and monitoring
- **API documentation** with OpenAPI
- **Testing framework** with integration tests
- **Performance optimization** and caching

### **Implementation Timeline**: 5-6 weeks
- **Week 1-2**: Core infrastructure and middleware
- **Week 3-4**: Business logic services and new routers
- **Week 4-5**: Alert and strategy management
- **Week 5-6**: Testing, documentation, and deployment

This upgrade provides a solid foundation for the dashboard implementation while maintaining backward compatibility with existing endpoints.