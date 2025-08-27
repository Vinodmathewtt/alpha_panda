import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dependency_injector.wiring import inject
from contextlib import asynccontextmanager
import structlog
from datetime import datetime

from app.containers import AppContainer
from api.middleware.auth import AuthenticationMiddleware
from api.middleware.error_handling import ErrorHandlingMiddleware
from api.middleware.rate_limiting import RateLimitingMiddleware
from api.routers import (
    auth, portfolios, monitoring, dashboard, services, 
    logs, alerts, realtime, system
)
from dashboard.routers import main as dashboard_main, realtime as dashboard_realtime
from dashboard.middleware.basic import SecurityMiddleware
from dashboard.middleware.metrics import PerformanceMiddleware

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting Alpha Panda API server")
    container = app.state.container
    
    # Initialize services
    try:
        await container.auth_service().start()
        await container.pipeline_monitor().start()
        logger.info("API services initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize API services", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Alpha Panda API server")
    try:
        await container.auth_service().stop()
        await container.pipeline_monitor().stop()
        logger.info("API services stopped successfully")
    except Exception as e:
        logger.error("Error during API shutdown", error=str(e))

def create_app() -> FastAPI:
    """Creates and configures the FastAPI application"""
    app = FastAPI(
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
        - **Dashboard Integration**: Comprehensive dashboard data aggregation
        - **Portfolio Analytics**: Real-time portfolio and position tracking
        
        ## Authentication
        Most endpoints require valid Zerodha authentication unless specified otherwise.
        
        ## Real-time Updates
        - Server-Sent Events (SSE) for live data streaming
        - WebSocket fallback for browsers with limited SSE support
        
        ## Broker Namespaces
        API supports both paper trading (`paper`) and Zerodha (`zerodha`) broker namespaces.
        """,
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
        "api.routers.realtime",
        "api.routers.system",
        "dashboard.routers.main",
        "dashboard.routers.realtime"
    ])

    # Add middleware (order matters - first added is outermost, executed first)
    app.add_middleware(ErrorHandlingMiddleware)
    
    # Add dashboard-specific middleware
    app.add_middleware(PerformanceMiddleware)
    app.add_middleware(SecurityMiddleware)
    
    # Add authentication middleware
    auth_service = container.auth_service()
    app.add_middleware(AuthenticationMiddleware, auth_service=auth_service)
    
    app.add_middleware(RateLimitingMiddleware, calls=100, period=60)
    
    # Get CORS settings from configuration
    settings = container.settings()
    
    # Environment-specific CORS configuration
    cors_origins = settings.api.cors_origins
    
    # Security check for production
    if settings.environment == "production" and "*" in cors_origins:
        raise ValueError(
            "CORS wildcard (*) not allowed in production. "
            "Specify exact origins in API__CORS_ORIGINS environment variable."
        )
    
    # Add CORS middleware with configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=settings.api.cors_credentials,
        allow_methods=settings.api.cors_methods,
        allow_headers=settings.api.cors_headers,
    )

    # Include routers with updated structure
    app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
    app.include_router(portfolios.router, prefix="/api/v1", tags=["Portfolios"])
    app.include_router(monitoring.router, prefix="/api/v1", tags=["Monitoring"])
    app.include_router(dashboard.router, prefix="/api/v1", tags=["Dashboard"])
    app.include_router(services.router, prefix="/api/v1", tags=["Services"])
    app.include_router(logs.router, prefix="/api/v1", tags=["Logs"])
    app.include_router(alerts.router, prefix="/api/v1", tags=["Alerts"])
    app.include_router(realtime.router, prefix="/api/v1", tags=["Real-time"])
    app.include_router(system.router, prefix="/api/v1", tags=["System"])
    
    # Include dashboard UI routers
    app.include_router(dashboard_main.router, tags=["Dashboard UI"])
    app.include_router(dashboard_realtime.router, tags=["Dashboard Real-time"])


    # Health check endpoint
    @app.get("/health", tags=["Health"])
    def health_check():
        return {
            "status": "healthy",
            "service": "alpha-panda-api",
            "version": "2.1.0",
            "timestamp": datetime.utcnow().isoformat(),
            "features": {
                "real_time_streaming": True,
                "websocket_support": True,
                "sse_support": True,
                "log_management": True,
                "alert_management": True,
                "service_management": True,
                "dashboard": True
            }
        }

    # Root endpoint
    @app.get("/", tags=["Root"])
    def root():
        return {
            "service": "Alpha Panda Trading API",
            "version": "2.1.0",
            "description": "Enhanced monitoring and management API",
            "docs": "/docs",
            "health": "/health",
            "api_prefix": "/api/v1",
            "features": [
                "Real-time monitoring",
                "Service management", 
                "Log streaming",
                "Alert management",
                "Dashboard integration",
                "Portfolio analytics"
            ],
            "endpoints": {
                "dashboard_ui": "/dashboard",
                "dashboard_api": "/api/v1/dashboard",
                "monitoring": "/api/v1/monitoring",
                "services": "/api/v1/services",
                "logs": "/api/v1/logs",
                "alerts": "/api/v1/alerts",
                "realtime": "/api/v1/realtime",
                "system": "/api/v1/system"
            }
        }

    return app

def run():
    """Main function to run the API server"""
    # Create the FastAPI app
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