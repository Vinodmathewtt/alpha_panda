# Dashboard Services

## Overview

The dashboard services module provides business logic services specific to the Alpha Panda web dashboard. These services handle data aggregation, formatting, and presentation for the dashboard interface.

## Service Architecture

Dashboard services are designed to:
- **Aggregate Data**: Combine data from multiple sources for dashboard display
- **Format Presentation**: Format data appropriately for web display
- **Cache Results**: Cache frequently accessed dashboard data
- **Handle Real-time Updates**: Manage real-time data streaming to dashboard
- **Provide Analytics**: Calculate dashboard-specific analytics and metrics

## Service Integration Pattern

```python
class DashboardDataService:
    """Service for dashboard data aggregation and presentation"""
    
    def __init__(self, redis_client, api_service):
        self.redis_client = redis_client
        self.api_service = api_service
    
    async def get_dashboard_overview(self):
        """Get comprehensive dashboard overview data"""
        return {
            "portfolio_summary": await self.get_portfolio_summary(),
            "system_health": await self.get_system_health(),
            "recent_activity": await self.get_recent_activity(),
            "performance_metrics": await self.get_performance_metrics()
        }
    
    async def stream_updates(self, websocket: WebSocket):
        """Stream real-time updates to dashboard WebSocket"""
        while True:
            # Get latest data updates
            updates = await self.get_latest_updates()
            await websocket.send_json(updates)
            await asyncio.sleep(self.refresh_interval)
```

## Data Processing

### Portfolio Data Aggregation
```python
async def aggregate_portfolio_data(self):
    """Aggregate portfolio data across all brokers"""
    portfolios = {}
    
    for broker in self.active_brokers:
        portfolio_data = await self.api_service.get_portfolio_summary(broker)
        portfolios[broker] = self.format_for_dashboard(portfolio_data)
    
    return {
        "individual": portfolios,
        "aggregate": self.calculate_aggregate_metrics(portfolios)
    }
```

### Chart Data Preparation
```python
async def prepare_chart_data(self, chart_type: str, timeframe: str):
    """Prepare data for dashboard charts"""
    raw_data = await self.get_time_series_data(timeframe)
    
    if chart_type == "portfolio_value":
        return self.format_portfolio_chart_data(raw_data)
    elif chart_type == "pnl_timeline":
        return self.format_pnl_chart_data(raw_data)
    elif chart_type == "trading_volume":
        return self.format_volume_chart_data(raw_data)
```

### Real-time Updates
```python
async def handle_real_time_update(self, update_type: str, data: dict):
    """Handle real-time data updates for dashboard"""
    formatted_update = {
        "type": update_type,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    
    # Broadcast to all connected dashboard clients
    await self.broadcast_to_dashboard_clients(formatted_update)
```

## Architecture Patterns

- **Data Aggregation**: Combines data from multiple API services
- **Caching Strategy**: Caches dashboard data for performance
- **Real-time Streaming**: WebSocket-based real-time updates
- **Template Integration**: Provides data formatted for dashboard templates
- **Error Handling**: Graceful handling of data service errors
- **Performance Optimization**: Optimized data queries and caching

## Usage Examples

### Service Dependency Injection
```python
from dashboard.services import get_dashboard_service

@router.get("/dashboard-data")
async def get_dashboard_data(
    dashboard_service = Depends(get_dashboard_service)
):
    return await dashboard_service.get_dashboard_overview()
```

### WebSocket Integration
```python
@router.websocket("/ws/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
    dashboard_service = Depends(get_dashboard_service)
):
    await websocket.accept()
    await dashboard_service.stream_dashboard_updates(websocket)
```

## Configuration

Dashboard service configuration:

```python
class DashboardServiceSettings(BaseModel):
    refresh_interval: int = 5  # seconds
    cache_ttl: int = 30  # seconds
    max_data_points: int = 1000
    websocket_timeout: int = 30
```

## Dependencies

- **Redis**: Data caching and real-time updates
- **WebSockets**: Real-time streaming to dashboard clients
- **api.services**: API service layer integration
- **core.monitoring**: System monitoring and health data