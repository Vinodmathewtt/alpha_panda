# API Routers

## Overview

The API routers module contains FastAPI router implementations that define the REST API endpoints for Alpha Panda. Each router is organized by domain and provides specific functionality for different aspects of the trading system.

## Router Components

### `auth.py`
Authentication endpoints:

- **POST /auth/login**: User authentication and JWT token generation
- **POST /auth/logout**: User logout and token invalidation
- **GET /auth/me**: Get current user information
- **POST /auth/refresh**: JWT token refresh

### `portfolios.py`
Portfolio and trading data endpoints:

- **GET /api/v1/portfolios/{broker}/summary**: Portfolio summary for specific broker
- **GET /api/v1/portfolios/{broker}/positions**: Current positions for broker
- **GET /api/v1/portfolios/{broker}/orders**: Order history for broker
- **GET /api/v1/portfolios/all/summary**: Aggregated portfolio data across all brokers

### `monitoring.py`
System monitoring and metrics endpoints:

- **GET /api/v1/monitoring/health**: System health status
- **GET /api/v1/monitoring/metrics**: System performance metrics
- **GET /api/v1/monitoring/pipeline**: Pipeline health and throughput
- **GET /api/v1/monitoring/services**: Individual service status
- **GET /api/v1/monitoring/broker/{broker}**: Broker-specific health

### `system.py`
System information and configuration endpoints:

- **GET /api/v1/system/info**: System information and version
- **GET /api/v1/system/config**: System configuration status
- **GET /api/v1/system/brokers**: Active brokers configuration
- **POST /api/v1/system/config/reload**: Reload system configuration

### `logs.py`
Log management endpoints:

- **GET /api/v1/logs**: Retrieve system logs with filtering
- **GET /api/v1/logs/{service}**: Service-specific logs
- **GET /api/v1/logs/tail**: Real-time log streaming
- **POST /api/v1/logs/level**: Change log level at runtime

### `alerts.py`
Alert and notification endpoints:

- **GET /api/v1/alerts**: Get active alerts
- **POST /api/v1/alerts/{id}/acknowledge**: Acknowledge alert
- **GET /api/v1/alerts/history**: Alert history
- **POST /api/v1/alerts/config**: Configure alert rules

### `realtime.py`
Real-time data streaming endpoints:

- **GET /realtime/portfolio**: WebSocket for real-time portfolio updates
- **GET /realtime/market**: WebSocket for real-time market data
- **GET /realtime/orders**: WebSocket for real-time order updates
- **GET /realtime/system**: WebSocket for real-time system status

### `dashboard.py`
Dashboard-specific data endpoints:

- **GET /api/v1/dashboard/summary**: Dashboard summary data
- **GET /api/v1/dashboard/charts**: Chart data for visualization
- **GET /api/v1/dashboard/statistics**: Statistical summaries
- **GET /api/v1/dashboard/performance**: Performance analytics

### `services.py`
Service management endpoints:

- **GET /api/v1/services**: List all services and their status
- **GET /api/v1/services/{service}/health**: Individual service health
- **POST /api/v1/services/{service}/restart**: Restart service (if supported)
- **GET /api/v1/services/{service}/metrics**: Service-specific metrics

## Usage

### Router Registration
```python
from api.routers import (
    auth, portfolios, monitoring, system, 
    logs, alerts, realtime, dashboard, services
)

# Register routers with FastAPI app
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(portfolios.router, prefix="/api/v1", tags=["portfolios"])
app.include_router(monitoring.router, prefix="/api/v1", tags=["monitoring"])
app.include_router(system.router, prefix="/api/v1", tags=["system"])
```

### Authentication Protected Routes
```python
from api.middleware.auth import get_current_user
from fastapi import Depends

@router.get("/protected")
async def protected_endpoint(user: User = Depends(get_current_user)):
    return {"data": "protected content"}
```

### Broker-Specific Endpoints
```python
@router.get("/portfolios/{broker}/summary")
async def get_portfolio_summary(
    broker: str,
    portfolio_service: PortfolioService = Depends(get_portfolio_service)
):
    if broker not in ["paper", "zerodha", "all"]:
        raise HTTPException(status_code=400, detail="Invalid broker")
    
    return await portfolio_service.get_summary(broker)
```

## Architecture Patterns

- **Domain Separation**: Each router handles a specific domain area
- **Dependency Injection**: Uses FastAPI's dependency injection system
- **Error Handling**: Consistent error handling and HTTP status codes
- **Authentication**: Protected routes using middleware authentication
- **Validation**: Request/response validation using Pydantic models
- **Documentation**: Automatic OpenAPI documentation generation

## Response Patterns

### Standard Response Format
```python
{
    "success": true,
    "data": {...},
    "message": "Operation completed successfully",
    "timestamp": "2024-08-30T12:00:00Z"
}
```

### Error Response Format
```python
{
    "success": false,
    "error": {
        "code": "INVALID_REQUEST",
        "message": "Invalid broker specified",
        "details": {...}
    },
    "timestamp": "2024-08-30T12:00:00Z"
}
```

## Best Practices

1. **Consistent Naming**: Use consistent URL patterns and naming conventions
2. **HTTP Methods**: Use appropriate HTTP methods (GET, POST, PUT, DELETE)
3. **Status Codes**: Return appropriate HTTP status codes
4. **Input Validation**: Validate all input parameters and request bodies
5. **Error Handling**: Provide meaningful error messages and codes
6. **Documentation**: Use docstrings and FastAPI documentation features

## Dependencies

- **FastAPI**: Web framework for API implementation
- **Pydantic**: Data validation and serialization
- **api.schemas**: Request/response models
- **api.services**: Business logic services
- **api.middleware**: Authentication and cross-cutting concerns