# API Services

## Overview

The API services module provides business logic services for the Alpha Panda REST API. These services act as an abstraction layer between the API routers and the core system components, handling data aggregation, transformation, and caching for API responses.

## Components

### `dashboard_service.py`
Dashboard data aggregation and presentation service:

- **Portfolio Aggregation**: Aggregates portfolio data across multiple brokers
- **Performance Metrics**: Calculates performance statistics and analytics
- **Chart Data**: Prepares data for dashboard charts and visualizations
- **Real-time Updates**: Manages real-time data updates for dashboard
- **Data Caching**: Caches frequently accessed dashboard data

### `log_service.py`
Log management and retrieval service:

- **Log Aggregation**: Aggregates logs from different services and components
- **Log Filtering**: Provides filtering capabilities by service, level, timeframe
- **Log Search**: Implements log search functionality
- **Real-time Streaming**: Supports real-time log streaming
- **Log Archival**: Manages log archival and retention policies

### `realtime_service.py`
Real-time data streaming service for WebSocket endpoints:

- **WebSocket Management**: Manages WebSocket connections and lifecycle
- **Data Broadcasting**: Broadcasts real-time updates to connected clients
- **Subscription Management**: Handles client subscriptions to different data streams
- **Connection Pooling**: Manages connection pools for scalability
- **Message Filtering**: Filters messages based on client subscriptions

## Service Architecture

### Dashboard Service
```python
class DashboardService:
    """Service for dashboard data aggregation and presentation"""
    
    def __init__(self, redis_client, settings):
        self.redis_client = redis_client
        self.settings = settings
    
    async def get_portfolio_summary(self, broker: str = "all"):
        """Get aggregated portfolio summary"""
        # Aggregate data from Redis cache
        # Calculate performance metrics
        # Return formatted dashboard data
    
    async def get_performance_analytics(self, timeframe: str):
        """Get performance analytics for specified timeframe"""
        # Calculate returns, drawdown, Sharpe ratio
        # Prepare chart data
        # Return analytics summary
```

### Log Service  
```python
class LogService:
    """Service for log management and retrieval"""
    
    def __init__(self, log_directory: Path):
        self.log_directory = log_directory
    
    async def get_logs(self, filters: LogFilters):
        """Retrieve logs with filtering"""
        # Apply filters (service, level, timeframe)
        # Parse and format log entries
        # Return paginated results
    
    async def stream_logs(self, websocket: WebSocket, filters: LogFilters):
        """Stream real-time logs via WebSocket"""
        # Set up log file watching
        # Stream new log entries to WebSocket
        # Handle connection lifecycle
```

### Realtime Service
```python
class RealtimeService:
    """Service for real-time data streaming"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.connections: Dict[str, WebSocket] = {}
    
    async def subscribe_portfolio_updates(self, websocket: WebSocket, broker: str):
        """Subscribe to real-time portfolio updates"""
        # Register WebSocket connection
        # Set up Redis subscription
        # Forward updates to WebSocket
    
    async def broadcast_market_data(self, market_data: Dict):
        """Broadcast market data to subscribed clients"""
        # Send data to all subscribed connections
        # Handle disconnected clients
```

## Usage

### Dashboard Service Integration
```python
from api.services.dashboard_service import DashboardService
from api.dependencies import get_redis_client

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    broker: str = "all",
    dashboard_service: DashboardService = Depends(get_dashboard_service)
):
    return await dashboard_service.get_portfolio_summary(broker)
```

### Log Service Integration
```python
from api.services.log_service import LogService, LogFilters

@router.get("/logs")
async def get_logs(
    service: Optional[str] = None,
    level: Optional[str] = None,
    since: Optional[datetime] = None,
    log_service: LogService = Depends(get_log_service)
):
    filters = LogFilters(service=service, level=level, since=since)
    return await log_service.get_logs(filters)
```

### WebSocket Real-time Streaming
```python
from api.services.realtime_service import RealtimeService

@router.websocket("/realtime/portfolio")
async def portfolio_websocket(
    websocket: WebSocket,
    broker: str,
    realtime_service: RealtimeService = Depends(get_realtime_service)
):
    await realtime_service.subscribe_portfolio_updates(websocket, broker)
```

## Data Processing Patterns

### Portfolio Data Aggregation
```python
async def aggregate_portfolio_data(self, brokers: List[str]) -> PortfolioSummary:
    """Aggregate portfolio data across multiple brokers"""
    summaries = []
    
    for broker in brokers:
        # Get broker-specific data from Redis
        broker_data = await self.redis_client.hgetall(f"{broker}:portfolio:summary")
        summaries.append(self.parse_broker_data(broker_data))
    
    # Aggregate totals
    return self.calculate_aggregated_summary(summaries)
```

### Real-time Data Broadcasting
```python
async def broadcast_update(self, topic: str, data: Dict):
    """Broadcast update to all subscribers of a topic"""
    subscribers = self.get_topic_subscribers(topic)
    
    for websocket in subscribers:
        try:
            await websocket.send_json({
                "topic": topic,
                "data": data,
                "timestamp": datetime.now().isoformat()
            })
        except WebSocketDisconnect:
            self.remove_subscriber(websocket, topic)
```

## Caching Strategy

### Redis Integration
```python
class CacheManager:
    """Manages caching for API services"""
    
    async def get_cached_data(self, key: str, ttl: int = 300):
        """Get data from cache with TTL"""
        data = await self.redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    
    async def cache_data(self, key: str, data: Any, ttl: int = 300):
        """Cache data with expiration"""
        await self.redis_client.setex(
            key, 
            ttl, 
            json.dumps(data, default=str)
        )
```

## Architecture Patterns

- **Service Layer**: Clear separation between API routing and business logic
- **Dependency Injection**: Services injected via FastAPI dependency system
- **Data Aggregation**: Aggregates data from multiple sources and brokers
- **Real-time Streaming**: WebSocket-based real-time data streaming
- **Caching**: Redis-based caching for performance optimization
- **Error Handling**: Comprehensive error handling and logging

## Configuration

Service configuration through settings:

```python
class APIServiceSettings(BaseModel):
    cache_ttl_seconds: int = 300
    max_log_entries: int = 1000
    websocket_timeout: int = 30
    dashboard_refresh_interval: int = 5
    realtime_buffer_size: int = 100
```

## Best Practices

1. **Async Operations**: Use async/await for all I/O operations
2. **Error Handling**: Handle errors gracefully with proper logging
3. **Caching**: Cache frequently accessed data to improve performance
4. **Resource Management**: Properly manage WebSocket connections and resources
5. **Data Validation**: Validate data before processing and caching
6. **Monitoring**: Include metrics and monitoring in service operations

## Dependencies

- **Redis**: Caching and real-time data storage
- **WebSockets**: Real-time streaming capabilities
- **FastAPI**: Dependency injection and WebSocket support
- **Pydantic**: Data validation and serialization
- **core.logging**: Service logging and correlation tracking