# Alpha Panda Trading API

A comprehensive monitoring and management API for the Alpha Panda algorithmic trading system. This enhanced API provides real-time monitoring, service management, log streaming, alert management, and dashboard integration capabilities.

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Virtual environment activated
- Alpha Panda dependencies installed
- Redis and PostgreSQL running
- Redpanda/Kafka cluster available

### Running the API

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the API server
python -m api.main

# Or using the CLI
python cli.py api

# Development mode (with auto-reload)
uvicorn api.main:create_app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at:
- **API Endpoints**: http://localhost:8000/api/v1/
- **Interactive Documentation**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 📊 API Overview

### Version
**2.1.0** - Enhanced monitoring and management API

### Base URL
```
http://localhost:8000/api/v1/
```

### Authentication
Most endpoints require valid Zerodha authentication. Some monitoring endpoints support optional authentication for development environments.

### Response Format
All API responses follow a standardized format:

```json
{
  "status": "success|error", 
  "message": "Human readable message",
  "data": "Response payload",
  "timestamp": "2024-01-01T12:00:00Z",
  "broker": "paper|zerodha"
}
```

## 🌐 API Endpoints

### Core System

#### Health & Status
```http
GET /health                    # API health check
GET /                         # API information and features
GET /api/v1/system/info       # System information
GET /api/v1/system/metrics    # Real-time system metrics
GET /api/v1/system/processes  # Process information
GET /api/v1/system/environment # Environment configuration
```

### 📱 Dashboard Integration

#### Dashboard Endpoints
```http
GET /api/v1/dashboard/summary   # Comprehensive dashboard overview
GET /api/v1/dashboard/health    # System health summary
GET /api/v1/dashboard/pipeline  # Pipeline status overview
GET /api/v1/dashboard/activity  # Recent system activity
```

**Example Response:**
```json
{
  "status": "success",
  "data": {
    "system_health": { "status": "healthy", "checks": {...} },
    "pipeline_status": { "overall_healthy": true, "stages": {...} },
    "active_services": 6,
    "total_services": 7,
    "recent_activity": [...],
    "alert_summary": { "active_alerts": 2, "critical_alerts": 0 }
  }
}
```

### 🔄 Real-time Streaming

#### Server-Sent Events (SSE)
```http
GET /api/v1/realtime/events/health     # Health monitoring stream
GET /api/v1/realtime/events/pipeline   # Pipeline monitoring stream  
GET /api/v1/realtime/events/logs       # Log entries stream
GET /api/v1/realtime/events/activity   # Activity feed stream
GET /api/v1/realtime/status            # Streaming status
```

#### WebSocket Endpoints
```http
WS /api/v1/realtime/ws/monitoring      # Monitoring data WebSocket
WS /api/v1/realtime/ws/logs            # Log streaming WebSocket
```

**SSE Usage Example:**
```javascript
const eventSource = new EventSource('/api/v1/realtime/events/health');
eventSource.onmessage = function(event) {
  const healthData = JSON.parse(event.data);
  console.log('Health update:', healthData);
};
```

### 🛠️ Service Management

#### Service Operations
```http
GET /api/v1/services/                    # List all services
GET /api/v1/services/{service_name}      # Service details
GET /api/v1/services/{service_name}/metrics # Service metrics
GET /api/v1/services/{service_name}/health  # Service health
GET /api/v1/services/{service_name}/logs    # Service logs
POST /api/v1/services/{service_name}/restart # Restart service
GET /api/v1/services/{service_name}/status/history # Status history
```

**Available Services:**
- `auth_service` - Authentication service
- `market_feed_service` - Market data feed
- `strategy_runner_service` - Strategy execution
- `risk_manager_service` - Risk management
- `trading_engine_service` - Order execution
- `portfolio_manager_service` - Portfolio tracking
- `pipeline_monitor` - Pipeline monitoring

### 📝 Log Management

#### Log Operations
```http
GET /api/v1/logs/                        # Paginated logs
GET /api/v1/logs/statistics              # Log statistics
GET /api/v1/logs/search                  # Full-text search
GET /api/v1/logs/services               # Available log services
GET /api/v1/logs/channels               # Available log channels
GET /api/v1/logs/levels                 # Available log levels
GET /api/v1/logs/tail/{service_name}    # Tail service logs
POST /api/v1/logs/export                # Export logs
GET /api/v1/logs/export/{id}/status     # Export status
```

**Query Parameters:**
```http
GET /api/v1/logs/?level=ERROR&service=trading_engine_service&page=1&size=50
GET /api/v1/logs/search?query=order&page=1&size=20
```

### 🚨 Alert Management

#### Alert Operations
```http
GET /api/v1/alerts/                     # List alerts
GET /api/v1/alerts/summary              # Alert summary
GET /api/v1/alerts/{alert_id}           # Alert details
POST /api/v1/alerts/{alert_id}/acknowledge # Acknowledge alert
POST /api/v1/alerts/{alert_id}/resolve     # Resolve alert
GET /api/v1/alerts/categories           # Alert categories
GET /api/v1/alerts/severities           # Alert severities
POST /api/v1/alerts/test                # Create test alert
```

**Alert Filtering:**
```http
GET /api/v1/alerts/?status=active&severity=critical&category=trading
```

### 📊 Legacy Endpoints

#### Authentication
```http
GET /api/v1/auth/status                 # Authentication status
```

#### Portfolio Management
```http
GET /api/v1/portfolios/                 # Portfolio data
GET /api/v1/portfolios/summary          # Portfolio summary
GET /api/v1/portfolios/positions        # Current positions
```

#### System Monitoring
```http
GET /api/v1/monitoring/health           # System health
GET /api/v1/monitoring/pipeline         # Pipeline status
GET /api/v1/monitoring/pipeline/history # Pipeline history
GET /api/v1/monitoring/pipeline/stages/{stage} # Stage details
GET /api/v1/monitoring/logs/statistics  # Log statistics
GET /api/v1/monitoring/metrics          # Metrics summary
POST /api/v1/monitoring/pipeline/reset  # Reset metrics
```

## 🔧 Configuration

### Environment Variables

```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=false

# Authentication
API_REQUIRE_AUTH=true
API_SESSION_TIMEOUT=3600

# Rate Limiting
API_RATE_LIMIT_CALLS=100
API_RATE_LIMIT_PERIOD=60

# Real-time Features
API_SSE_ENABLED=true
API_WEBSOCKET_ENABLED=true
API_MAX_SSE_CONNECTIONS=100

# Monitoring
API_HEALTH_CHECK_INTERVAL=30
API_METRICS_RETENTION_HOURS=24
```

### Broker Namespace

The API supports dual broker architecture:

```bash
# Paper trading
BROKER_NAMESPACE=paper

# Live trading
BROKER_NAMESPACE=zerodha
```

## 📚 Usage Examples

### Python Client Example

```python
import httpx
import asyncio

async def monitor_system():
    async with httpx.AsyncClient() as client:
        # Get dashboard summary
        response = await client.get("http://localhost:8000/api/v1/dashboard/summary")
        dashboard = response.json()
        print(f"System health: {dashboard['data']['system_health']['status']}")
        
        # Get service status
        response = await client.get("http://localhost:8000/api/v1/services/")
        services = response.json()
        print(f"Active services: {services['data']['summary']['running']}")
        
        # Search logs
        response = await client.get("http://localhost:8000/api/v1/logs/search?query=error")
        logs = response.json()
        print(f"Found {logs['total']} log entries")

asyncio.run(monitor_system())
```

### JavaScript/Frontend Example

```javascript
// Dashboard data fetching
async function getDashboardData() {
    const response = await fetch('/api/v1/dashboard/summary');
    const dashboard = await response.json();
    return dashboard.data;
}

// Real-time health monitoring
function startHealthMonitoring() {
    const eventSource = new EventSource('/api/v1/realtime/events/health');
    
    eventSource.onmessage = function(event) {
        const healthData = JSON.parse(event.data);
        updateHealthDisplay(healthData);
    };
    
    eventSource.onerror = function(event) {
        console.error('SSE connection error:', event);
        // Fallback to WebSocket or polling
    };
}

// Service management
async function restartService(serviceName) {
    const response = await fetch(`/api/v1/services/${serviceName}/restart`, {
        method: 'POST',
        headers: {
            'Authorization': 'Bearer ' + authToken
        }
    });
    
    if (response.ok) {
        const result = await response.json();
        console.log(`Service restart initiated: ${result.message}`);
    }
}
```

### cURL Examples

```bash
# Get system health
curl -X GET "http://localhost:8000/api/v1/dashboard/health"

# Stream health updates (SSE)
curl -N "http://localhost:8000/api/v1/realtime/events/health"

# Search logs with authentication
curl -X GET "http://localhost:8000/api/v1/logs/search?query=trading" \
     -H "Authorization: Bearer YOUR_TOKEN"

# Acknowledge an alert
curl -X POST "http://localhost:8000/api/v1/alerts/alert-123/acknowledge" \
     -H "Authorization: Bearer YOUR_TOKEN"

# Export logs
curl -X POST "http://localhost:8000/api/v1/logs/export?format=json" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

## 🔒 Authentication

### Requirements
- Zerodha authentication is required for most endpoints
- Some monitoring endpoints support optional authentication in development
- Authentication is handled via JWT tokens or session-based authentication

### Protected Endpoints
- Service management (`/services/*`)
- Alert management (`/alerts/*`)
- Log export and management
- Administrative operations

### Public Endpoints
- Health checks (`/health`, `/api/v1/system/*`)
- API documentation (`/docs`, `/redoc`)
- Real-time streaming status
- Some monitoring endpoints (configurable)

## 🚨 Error Handling

### Standard Error Response

```json
{
  "status": "error",
  "message": "Human readable error message",
  "timestamp": "2024-01-01T12:00:00Z",
  "path": "/api/v1/endpoint"
}
```

### Common HTTP Status Codes

- **200 OK** - Successful request
- **400 Bad Request** - Invalid request parameters
- **401 Unauthorized** - Authentication required
- **403 Forbidden** - Insufficient permissions
- **404 Not Found** - Resource not found
- **422 Unprocessable Entity** - Validation error
- **429 Too Many Requests** - Rate limit exceeded
- **500 Internal Server Error** - Server error

### Rate Limiting

- **Default Limit**: 100 requests per 60 seconds per IP
- **Headers**: Rate limit info included in response headers
- **Override**: Configure via `API_RATE_LIMIT_CALLS` and `API_RATE_LIMIT_PERIOD`

## 🔧 Development

### Project Structure

```
api/
├── __init__.py
├── main.py                 # FastAPI application
├── dependencies.py         # Dependency injection
├── middleware/            # Custom middleware
│   ├── auth.py           # Authentication middleware
│   ├── error_handling.py # Global error handling
│   └── rate_limiting.py  # Rate limiting middleware
├── routers/              # API route handlers
│   ├── alerts.py         # Alert management
│   ├── auth.py          # Authentication
│   ├── dashboard.py     # Dashboard endpoints
│   ├── logs.py          # Log management
│   ├── monitoring.py    # System monitoring
│   ├── portfolios.py    # Portfolio management
│   ├── realtime.py      # Real-time streaming
│   ├── services.py      # Service management
│   └── system.py        # System information
├── schemas/             # API response models
│   └── responses.py     # Pydantic response schemas
└── services/           # Business logic services
    ├── dashboard_service.py  # Dashboard data aggregation
    ├── log_service.py       # Log management service
    └── realtime_service.py  # Real-time streaming service
```

### Adding New Endpoints

1. **Create Router** in `api/routers/`
2. **Add Business Logic** in `api/services/`
3. **Define Schemas** in `api/schemas/`
4. **Register Router** in `api/main.py`
5. **Add Dependencies** in `api/dependencies.py`
6. **Update Container** in `app/containers.py`

### Testing

```bash
# Run API tests
python -m pytest api/tests/

# Test specific endpoint
curl -X GET "http://localhost:8000/api/v1/health"

# Load testing
ab -n 1000 -c 10 http://localhost:8000/api/v1/health
```

## 📈 Monitoring & Observability

### Health Checks
- **Application Health**: `/health`
- **System Health**: `/api/v1/system/metrics`
- **Service Health**: `/api/v1/services/{service}/health`

### Metrics
- Request/response metrics via FastAPI
- System resource monitoring
- Service-specific metrics
- Pipeline flow metrics

### Logging
- Structured logging with `structlog`
- Request/response logging
- Error tracking and alerting
- Log aggregation and search

### Real-time Monitoring
- Server-Sent Events for live updates
- WebSocket fallback support
- Health status streaming
- Log streaming with filters

## 🚀 Production Deployment

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "-m", "api.main"]
```

### Docker Compose

```yaml
version: '3.8'
services:
  alpha-panda-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - BROKER_NAMESPACE=zerodha
      - API_REQUIRE_AUTH=true
      - API_RATE_LIMIT_CALLS=1000
    depends_on:
      - redis
      - postgres
      - redpanda
```

### Production Considerations

1. **Security**
   - Configure CORS origins properly
   - Use HTTPS in production
   - Implement proper authentication
   - Rate limiting configuration

2. **Performance**
   - Use production ASGI server (Gunicorn + Uvicorn)
   - Configure connection pooling
   - Implement caching strategies
   - Monitor resource usage

3. **Reliability**
   - Health check endpoints for load balancers
   - Graceful shutdown handling
   - Error monitoring and alerting
   - Backup and recovery procedures

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Implement changes with tests
4. Update documentation
5. Submit pull request

## 📄 License

This project is part of the Alpha Panda trading system. See the main project license for details.

## 📞 Support

For issues and questions:
- Check the interactive API documentation at `/docs`
- Review the implementation summary in `API_IMPLEMENTATION_SUMMARY.md`
- Refer to the main project documentation in the root `README.md`