# Dashboard Routers

## Overview

The dashboard routers module contains FastAPI router implementations for the Alpha Panda web dashboard. These routers serve HTML pages and provide dashboard-specific endpoints for the web interface.

## Components

### `main.py`
Main dashboard routes and page serving:

- **Dashboard Home**: Main dashboard page with overview
- **Portfolio Views**: Portfolio summary and detailed views
- **Trading Views**: Trading activity and order management pages
- **System Status**: System health and monitoring dashboard
- **Settings**: Dashboard configuration and preferences

### `realtime.py`
Real-time dashboard data endpoints:

- **WebSocket Endpoints**: Real-time data streaming for dashboard
- **Live Updates**: Live portfolio and market data updates
- **System Monitoring**: Real-time system status updates
- **Event Streaming**: Real-time trading events and notifications

## Route Categories

### Dashboard Pages
```python
@router.get("/")
async def dashboard_home(request: Request):
    """Main dashboard homepage"""
    return templates.TemplateResponse("dashboard/index.html", {
        "request": request,
        "portfolio_data": await get_portfolio_summary(),
        "system_status": await get_system_status()
    })

@router.get("/portfolio")
async def portfolio_page(request: Request):
    """Portfolio management dashboard"""
    return templates.TemplateResponse("dashboard/portfolio.html", {
        "request": request,
        "portfolios": await get_all_portfolios()
    })
```

### API Endpoints for Dashboard
```python
@router.get("/api/portfolio/{broker}")
async def get_portfolio_data(broker: str):
    """Get portfolio data for dashboard charts"""
    return await dashboard_service.get_portfolio_data(broker)

@router.get("/api/system/metrics")
async def get_system_metrics():
    """Get system metrics for dashboard monitoring"""
    return await dashboard_service.get_system_metrics()
```

### Real-time Streaming
```python
@router.websocket("/ws/portfolio")
async def portfolio_websocket(websocket: WebSocket):
    """WebSocket for real-time portfolio updates"""
    await websocket.accept()
    await dashboard_service.stream_portfolio_updates(websocket)

@router.websocket("/ws/system")
async def system_websocket(websocket: WebSocket):
    """WebSocket for real-time system status updates"""
    await websocket.accept()
    await dashboard_service.stream_system_updates(websocket)
```

## Template Integration

### Template Context
```python
async def get_dashboard_context(request: Request) -> dict:
    """Get common dashboard template context"""
    return {
        "request": request,
        "user": get_current_user(request),
        "system_info": await get_system_info(),
        "active_brokers": settings.active_brokers,
        "timestamp": datetime.now()
    }
```

### Page Rendering
```python
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="dashboard/templates")

@router.get("/trading")
async def trading_page(request: Request):
    context = await get_dashboard_context(request)
    context.update({
        "recent_trades": await get_recent_trades(),
        "active_orders": await get_active_orders()
    })
    return templates.TemplateResponse("dashboard/trading.html", context)
```

## Architecture Patterns

- **Template Rendering**: Server-side HTML template rendering
- **WebSocket Integration**: Real-time updates via WebSocket connections
- **API Integration**: Dashboard-specific API endpoints
- **Context Management**: Consistent template context across pages
- **Authentication**: Dashboard authentication integration
- **Error Handling**: User-friendly error pages and handling

## Configuration

Dashboard router configuration:

```python
class DashboardRouterSettings(BaseModel):
    template_directory: str = "dashboard/templates"
    static_directory: str = "dashboard/static"
    websocket_timeout: int = 30
    refresh_interval: int = 5
    max_chart_data_points: int = 1000
```

## Dependencies

- **FastAPI**: Web framework and routing
- **Jinja2**: Template engine for HTML rendering
- **WebSockets**: Real-time data streaming
- **dashboard.services**: Dashboard business logic
- **api.services**: API service integration