"""API route registration and organization."""

from fastapi import FastAPI

from .routers import (
    health,
    trading,
    market_data,
    strategies,
    risk,
    monitoring,
    auth,
    system,
    logs
)


def register_routes(app: FastAPI):
    """Register all API routes with the FastAPI application."""
    
    # Health and system routes
    app.include_router(
        health.router,
        prefix="/api/v1/health",
        tags=["health"]
    )
    
    app.include_router(
        system.router,
        prefix="/api/v1/system",
        tags=["system"]
    )
    
    # Authentication routes
    app.include_router(
        auth.router,
        prefix="/api/v1/auth",
        tags=["authentication"]
    )
    
    # Trading routes
    app.include_router(
        trading.router,
        prefix="/api/v1/trading",
        tags=["trading"]
    )
    
    # Market data routes
    app.include_router(
        market_data.router,
        prefix="/api/v1/market",
        tags=["market-data"]
    )
    
    # Strategy routes
    app.include_router(
        strategies.router,
        prefix="/api/v1/strategies",
        tags=["strategies"]
    )
    
    # Risk management routes
    app.include_router(
        risk.router,
        prefix="/api/v1/risk",
        tags=["risk-management"]
    )
    
    # Monitoring and metrics routes
    app.include_router(
        monitoring.router,
        prefix="/api/v1/monitoring",
        tags=["monitoring"]
    )
    
    # Log management routes
    app.include_router(
        logs.router,
        prefix="/api/v1/logs",
        tags=["logs"]
    )