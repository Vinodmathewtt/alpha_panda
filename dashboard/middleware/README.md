# Dashboard Middleware

## Overview

The dashboard middleware provides specific middleware functionality for the Alpha Panda dashboard application, including basic authentication, metrics collection, and dashboard-specific cross-cutting concerns.

## Components

### `basic.py`
Basic authentication middleware for dashboard access:

- **Simple Authentication**: Basic HTTP authentication for dashboard access
- **Session Management**: Simple session handling for dashboard users
- **Access Control**: Controls access to dashboard endpoints
- **Security Headers**: Adds security headers for dashboard pages

### `metrics.py`
Dashboard-specific metrics collection middleware:

- **Page View Tracking**: Tracks dashboard page views and usage
- **Performance Metrics**: Collects client-side performance metrics
- **User Activity**: Tracks user interactions and activity patterns
- **Dashboard Analytics**: Collects analytics data for dashboard optimization

## Usage

### Middleware Registration
```python
from dashboard.middleware.basic import BasicAuthMiddleware
from dashboard.middleware.metrics import MetricsMiddleware

# Register dashboard middleware
dashboard_app.add_middleware(MetricsMiddleware)
dashboard_app.add_middleware(BasicAuthMiddleware)
```

### Basic Authentication
```python
from dashboard.middleware.basic import require_auth

@dashboard_app.get("/dashboard")
@require_auth
async def dashboard_home(request: Request):
    return templates.TemplateResponse("dashboard/index.html", {"request": request})
```

## Configuration

Dashboard middleware configuration:

```python
class DashboardMiddlewareSettings(BaseModel):
    auth_enabled: bool = True
    metrics_enabled: bool = True
    session_timeout: int = 3600
    basic_auth_username: str = "admin"
    basic_auth_password: str = "secure_password"
```

## Dependencies

- **FastAPI**: Web framework and middleware system
- **dashboard.services**: Dashboard service integration
- **core.monitoring**: Metrics collection and reporting