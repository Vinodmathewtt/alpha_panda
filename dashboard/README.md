# Alpha Panda Dashboard

Modern web dashboard for monitoring the Alpha Panda trading system, built with FastAPI + HTMX + Alpine.js + TailwindCSS + DaisyUI.

## Implementation Status

### ✅ Phase 1 & 2 Complete (Weeks 1-4)

**Security Foundation & Core Infrastructure:**
- ✅ Security middleware with CSP headers and nonces
- ✅ Rate limiting middleware (token bucket algorithm)
- ✅ Performance monitoring middleware
- ✅ Base HTML template with modern tech stack
- ✅ Authentication integration with existing JWT system

**Dashboard Components:**
- ✅ System overview dashboard with real-time metrics
- ✅ Health monitoring dashboard with system resources
- ✅ Server-Sent Events (SSE) for real-time streaming
- ✅ Real-time activity feed
- ✅ Interactive charts with Chart.js
- ✅ Responsive design with DaisyUI components

**Real-time Features:**
- ✅ Health metrics streaming (`/dashboard/events/health`)
- ✅ Pipeline status streaming (`/dashboard/events/pipeline`) 
- ✅ Activity feed streaming (`/dashboard/events/activity`)
- ✅ Connection status monitoring

### 🔄 Phase 3 Implementation Next (Weeks 5-6)

**Advanced Features (Coming Next):**
- 🔄 Complete pipeline monitoring dashboard
- 🔄 Log viewer with filtering and search
- 🔄 Portfolio analytics with financial charts
- 🔄 Advanced charting with Plotly.js
- 🔄 Export functionality

## Tech Stack

- **Backend**: FastAPI with Jinja2 templates
- **Frontend**: HTMX for dynamic interactions
- **JavaScript**: Alpine.js for reactive components
- **Styling**: TailwindCSS + DaisyUI component library
- **Real-time**: Server-Sent Events (SSE) 
- **Charts**: Chart.js for dashboard charts
- **Security**: CSP headers, rate limiting, JWT authentication

## Project Structure

```
dashboard/
├── __init__.py
├── config.py                  # Dashboard configuration
├── routers/
│   ├── __init__.py
│   ├── main.py               # Main dashboard routes
│   └── realtime.py           # SSE endpoints
├── templates/
│   ├── base.html             # Base template with security
│   └── dashboard/
│       ├── index.html        # System overview
│       ├── health.html       # Health monitoring
│       ├── pipeline.html     # Pipeline monitoring (placeholder)
│       ├── portfolios.html   # Portfolio analytics (placeholder)
│       └── logs.html         # Log viewer (placeholder)
├── middleware/
│   ├── __init__.py
│   ├── basic.py              # Security middleware
│   └── metrics.py            # Performance & rate limiting
├── services/
│   └── __init__.py
└── static/                   # Static assets (CSS/JS/images)
```

## Usage

### Access URLs

- **Dashboard Home**: `http://localhost:8000/dashboard/`
- **Health Monitoring**: `http://localhost:8000/dashboard/health`
- **Pipeline Monitor**: `http://localhost:8000/dashboard/pipeline`
- **Portfolio Analytics**: `http://localhost:8000/dashboard/portfolios`
- **Log Viewer**: `http://localhost:8000/dashboard/logs`

### Real-time Endpoints

- **Health Stream**: `/dashboard/events/health`
- **Pipeline Stream**: `/dashboard/events/pipeline`
- **Activity Stream**: `/dashboard/events/activity`
- **Logs Stream**: `/dashboard/events/logs`

### API Integration

The dashboard consumes your existing Alpha Panda API endpoints:

- Authentication via existing JWT system
- Health data from `/api/v1/monitoring/health`
- Portfolio data from `/api/v1/portfolios/summary/stats`
- Real-time streaming via Server-Sent Events

## Features

### System Overview Dashboard

- **Real-time System Health**: Live status indicators
- **Pipeline Flow Diagram**: Visual representation of data flow
- **Performance Charts**: CPU, memory, throughput metrics
- **Activity Feed**: Live stream of system events
- **Status Cards**: Key metrics at a glance

### Health Monitoring Dashboard

- **Component Health Matrix**: Detailed status of all services
- **Resource Usage**: CPU, memory, disk usage with visual indicators
- **Health History Charts**: Time-series health metrics
- **Alert Management**: Health alerts and notifications
- **Export Functionality**: Export health data for analysis

### Security Features

- **CSP Headers**: Content Security Policy with nonces
- **Rate Limiting**: Token bucket algorithm (60 req/min)
- **JWT Authentication**: Integration with existing auth system
- **Performance Monitoring**: Response time tracking
- **Error Handling**: Global error boundaries

### Real-time Updates

- **Server-Sent Events**: Efficient real-time data streaming
- **Connection Monitoring**: Visual connection status indicators
- **Auto-reconnection**: Automatic reconnection on failures
- **Heartbeat System**: Regular connection health checks

## Development

### Dependencies

```bash
pip install fastapi jinja2 sse-starlette python-multipart uvicorn
```

### Integration

The dashboard is fully integrated into the main FastAPI application via `api/main.py`:

```python
# Dashboard UI routes
app.include_router(dashboard_main.router, tags=["Dashboard UI"])
app.include_router(dashboard_realtime.router, tags=["Dashboard Real-time"])
```

### Authentication

All dashboard routes require authentication via the existing `get_current_user` dependency injection.

## Next Steps

1. **Complete Phase 3** - Implement remaining dashboard pages
2. **Add Pipeline Monitoring** - Full pipeline visualization
3. **Enhance Log Viewer** - Advanced filtering and search
4. **Portfolio Analytics** - Financial charts and P&L tracking
5. **Performance Optimization** - Caching and CDN integration