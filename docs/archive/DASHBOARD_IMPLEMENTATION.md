# Alpha Panda Dashboard Implementation Guide

## Overview

This document provides a comprehensive implementation guide for the Alpha Panda monitoring dashboard, built using FastAPI + HTMX + Alpine.js + TailwindCSS + DaisyUI. The dashboard leverages existing API infrastructure to provide real-time monitoring and observability for the trading system.

## Architecture

### Enhanced Tech Stack
- **Backend**: FastAPI with Jinja2 templates + security middleware
- **Frontend**: HTMX for dynamic interactions with security headers
- **JavaScript**: Alpine.js for reactive components (CSP-compliant)
- **Styling**: TailwindCSS + DaisyUI component library
- **Real-time**: Server-Sent Events (SSE) with secure WebSocket fallback
- **Authentication**: JWT + RBAC + session management
- **Security**: CSP headers, CSRF protection, rate limiting
- **Performance**: Redis caching, connection pooling, CDN integration
- **Charts**: Plotly.js for advanced financial charts
- **Monitoring**: Structured logging, metrics collection, health checks

### Directory Structure
```
dashboard/
├── __init__.py
├── main.py                    # Dashboard application entry point
├── routers/
│   ├── __init__.py
│   ├── main.py               # Main dashboard routes
│   ├── health.py             # Health monitoring routes
│   ├── pipeline.py           # Pipeline monitoring routes
│   ├── portfolios.py         # Portfolio dashboard routes
│   ├── logs.py               # Log viewer routes
│   └── realtime.py           # SSE and WebSocket endpoints
├── templates/
│   ├── base.html             # Base template
│   ├── dashboard/
│   │   ├── index.html        # System overview
│   │   ├── health.html       # Health monitoring
│   │   ├── pipeline.html     # Pipeline monitoring
│   │   ├── portfolios.html   # Portfolio analytics
│   │   ├── logs.html         # Log viewer
│   │   └── settings.html     # Configuration
│   └── components/           # Reusable HTMX components
├── static/
│   ├── css/
│   ├── js/
│   └── assets/
├── services/
│   ├── __init__.py
│   ├── dashboard.py          # Dashboard business logic
│   ├── realtime.py           # Real-time data services
│   ├── metrics.py            # Metrics aggregation
│   └── caching.py            # Performance caching layer
├── middleware/
│   ├── __init__.py
│   ├── basic.py              # Basic middleware
│   └── metrics.py            # Performance metrics
# Optional (Phase 4):
# ├── security.py               # Advanced security middleware
# ├── rate_limit.py             # Rate limiting
# └── rbac.py                   # Role-based access control
└── config.py                 # Dashboard configuration
```

## Implementation Phases

### Phase 1: Secure Foundation & Core Infrastructure (Week 1-2)

#### 1.0 Security Foundation Setup

**Security Middleware Implementation**:

```python
# dashboard/middleware/security.py
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
import hashlib
from typing import Dict

class SecurityMiddleware(BaseHTTPMiddleware):
    """Comprehensive security middleware for dashboard"""
    
    def __init__(self, app, nonce_store: Dict[str, float] = None):
        super().__init__(app)
        self.nonce_store = nonce_store or {}
        self.nonce_ttl = 300  # 5 minutes
    
    async def dispatch(self, request: Request, call_next):
        # Generate CSP nonce for inline scripts
        nonce = self.generate_nonce()
        request.state.csp_nonce = nonce
        
        response = await call_next(request)
        
        # Security headers
        security_headers = {
            "Content-Security-Policy": f"""default-src 'self'; 
                script-src 'self' 'nonce-{nonce}' https://unpkg.com https://cdn.jsdelivr.net https://cdn.tailwindcss.com; 
                style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; 
                connect-src 'self' wss: ws:; 
                img-src 'self' data: https:; 
                font-src 'self' https://fonts.gstatic.com""".replace('\n', ''),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
        }
        
        for header, value in security_headers.items():
            response.headers[header] = value
            
        return response
    
    def generate_nonce(self) -> str:
        """Generate cryptographically secure nonce"""
        current_time = str(time.time())
        nonce = hashlib.sha256(current_time.encode()).hexdigest()[:16]
        self.nonce_store[nonce] = time.time()
        
        # Cleanup old nonces
        current = time.time()
        expired = [k for k, v in self.nonce_store.items() if current - v > self.nonce_ttl]
        for k in expired:
            del self.nonce_store[k]
            
        return nonce
```

**Rate Limiting Middleware**:

```python
# dashboard/middleware/rate_limit.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import time
from collections import defaultdict
from typing import Dict, DefaultDict

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiting for dashboard endpoints"""
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_second = requests_per_minute / 60
        self.buckets: DefaultDict[str, Dict] = defaultdict(lambda: {
            'tokens': self.requests_per_minute,
            'last_update': time.time()
        })
    
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        user_id = getattr(request.state, 'user_id', None)
        key = f"{client_ip}:{user_id}" if user_id else client_ip
        
        if not self.allow_request(key):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later."
            )
        
        return await call_next(request)
    
    def allow_request(self, key: str) -> bool:
        """Token bucket algorithm implementation"""
        bucket = self.buckets[key]
        now = time.time()
        elapsed = now - bucket['last_update']
        
        # Add tokens based on elapsed time
        bucket['tokens'] = min(
            self.requests_per_minute,
            bucket['tokens'] + elapsed * self.requests_per_second
        )
        bucket['last_update'] = now
        
        if bucket['tokens'] >= 1:
            bucket['tokens'] -= 1
            return True
        return False
```

#### 1.1 Dashboard Router Setup

Create the main dashboard router:

```python
# dashboard/routers/main.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from api.dependencies import get_current_user, get_settings, get_redis_client
from core.config.settings import Settings
import redis.asyncio as redis

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="dashboard/templates")

@router.get("/", response_class=HTMLResponse)
async def dashboard_home(
    request: Request,
    current_user: dict = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """Main dashboard page with system overview"""
    context = {
        "request": request,
        "user": current_user,
        "broker": settings.broker_namespace,
        "title": "Alpha Panda Dashboard"
    }
    return templates.TemplateResponse("dashboard/index.html", context)

@router.get("/health", response_class=HTMLResponse)
async def health_dashboard(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Health monitoring dashboard"""
    context = {
        "request": request,
        "user": current_user,
        "title": "Health Monitoring"
    }
    return templates.TemplateResponse("dashboard/health.html", context)

# Helper functions
async def get_system_health():
    """Fetch system health data"""
    # Implementation here
    return {"status": "healthy", "uptime": "24h"}

async def get_pipeline_status():
    """Fetch pipeline status"""
    return {"active_pipelines": 5, "messages_processed": 10000}

async def get_recent_activity():
    """Fetch recent activity feed"""
    return [{"type": "info", "message": "System started", "timestamp": time.time()}]

async def log_dashboard_access(user_id: str, page: str, timestamp: float):
    """Log dashboard access for audit"""
    # Implementation for audit logging
    pass
```

**Security Service for RBAC**:

```python
# dashboard/services/security.py
from typing import Dict, List, Set
from enum import Enum

class Permission(Enum):
    """Dashboard permissions"""
    DASHBOARD_VIEW = "dashboard.view"
    DASHBOARD_ADMIN = "dashboard.admin"
    HEALTH_VIEW = "dashboard.health.view"
    PIPELINE_VIEW = "dashboard.pipeline.view"
    PORTFOLIO_VIEW = "dashboard.portfolio.view"
    LOGS_VIEW = "dashboard.logs.view"
    SETTINGS_MANAGE = "dashboard.settings.manage"
    EXPORT_DATA = "dashboard.export.data"

class Role(Enum):
    """User roles with permission mappings"""
    ADMIN = "admin"
    TRADER = "trader"
    ANALYST = "analyst"
    VIEWER = "viewer"

class SecurityService:
    """Role-based access control for dashboard"""
    
    def __init__(self):
        self.role_permissions = {
            Role.ADMIN: {
                Permission.DASHBOARD_VIEW,
                Permission.DASHBOARD_ADMIN,
                Permission.HEALTH_VIEW,
                Permission.PIPELINE_VIEW,
                Permission.PORTFOLIO_VIEW,
                Permission.LOGS_VIEW,
                Permission.SETTINGS_MANAGE,
                Permission.EXPORT_DATA
            },
            Role.TRADER: {
                Permission.DASHBOARD_VIEW,
                Permission.HEALTH_VIEW,
                Permission.PIPELINE_VIEW,
                Permission.PORTFOLIO_VIEW,
                Permission.EXPORT_DATA
            },
            Role.ANALYST: {
                Permission.DASHBOARD_VIEW,
                Permission.HEALTH_VIEW,
                Permission.PORTFOLIO_VIEW,
                Permission.EXPORT_DATA
            },
            Role.VIEWER: {
                Permission.DASHBOARD_VIEW,
                Permission.HEALTH_VIEW
            }
        }
    
    def has_permission(self, user: Dict, permission: str) -> bool:
        """Check if user has specific permission"""
        user_role = Role(user.get("role", "viewer"))
        permission_enum = Permission(permission)
        return permission_enum in self.role_permissions.get(user_role, set())
    
    def get_user_permissions(self, user: Dict) -> Set[str]:
        """Get all permissions for user"""
        user_role = Role(user.get("role", "viewer"))
        permissions = self.role_permissions.get(user_role, set())
        return {perm.value for perm in permissions}
```

#### 1.2 Secure Base Template with Performance Optimizations

```html
<!-- dashboard/templates/base.html -->
<!DOCTYPE html>
<html lang="en" data-theme="corporate">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Alpha Panda Dashboard{% endblock %}</title>
    
    <!-- Performance optimizations -->
    <link rel="preconnect" href="https://unpkg.com">
    <link rel="preconnect" href="https://cdn.jsdelivr.net">
    <link rel="dns-prefetch" href="https://cdn.tailwindcss.com">
    
    <!-- Critical CSS inline for performance -->
    <style>
        /* Critical path CSS */
        .loading { opacity: 0.7; pointer-events: none; }
        .error-boundary { border: 2px solid #ef4444; background: #fef2f2; padding: 1rem; }
    </style>
    
    <!-- HTMX with integrity -->
    <script src="https://unpkg.com/htmx.org@1.9.2" 
            integrity="sha384-L6OqL9pRWyyFU3+/bjdSri+iIphTN/ckddFhRJpNIXDuYILIEpZnN4TFy4TL8hEP" 
            crossorigin="anonymous" nonce="{{ csp_nonce }}"></script>
    <script src="https://unpkg.com/htmx.org/dist/ext/sse.js" 
            crossorigin="anonymous" nonce="{{ csp_nonce }}"></script>
    
    <!-- Alpine.js with integrity -->
    <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js" 
            crossorigin="anonymous" nonce="{{ csp_nonce }}"></script>
    
    <!-- TailwindCSS + DaisyUI -->
    <script src="https://cdn.tailwindcss.com" nonce="{{ csp_nonce }}"></script>
    <link href="https://cdn.jsdelivr.net/npm/daisyui@3.5.0/dist/full.css" rel="stylesheet">
    
    <!-- Plotly.js for advanced financial charts -->
    <script src="https://cdn.jsdelivr.net/npm/plotly.js-dist@2.26.0/plotly.min.js" 
            crossorigin="anonymous" nonce="{{ csp_nonce }}"></script>
    
    <!-- CSRF protection moved to Phase 4 (optional security enhancements) -->
    
    {% block head %}{% endblock %}
</head>
<body class="min-h-screen bg-base-200" x-data="dashboardGlobal()">
    <!-- Navigation -->
    <div class="navbar bg-base-100 shadow-lg">
        <div class="navbar-start">
            <div class="dropdown">
                <label tabindex="0" class="btn btn-ghost lg:hidden">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h8m-8 6h16"></path>
                    </svg>
                </label>
                <ul tabindex="0" class="menu menu-compact dropdown-content mt-3 p-2 shadow bg-base-100 rounded-box w-52">
                    <li><a href="/dashboard/">Overview</a></li>
                    <li><a href="/dashboard/health">Health</a></li>
                    <li><a href="/dashboard/pipeline">Pipeline</a></li>
                    <li><a href="/dashboard/portfolios">Portfolios</a></li>
                    <li><a href="/dashboard/logs">Logs</a></li>
                </ul>
            </div>
            <a class="btn btn-ghost normal-case text-xl" href="/dashboard/">Alpha Panda</a>
        </div>
        
        <div class="navbar-center hidden lg:flex">
            <ul class="menu menu-horizontal px-1">
                <li><a href="/dashboard/">Overview</a></li>
                <li><a href="/dashboard/health">Health</a></li>
                <li><a href="/dashboard/pipeline">Pipeline</a></li>
                <li><a href="/dashboard/portfolios">Portfolios</a></li>
                <li><a href="/dashboard/logs">Logs</a></li>
            </ul>
        </div>
        
        <div class="navbar-end">
            <div class="dropdown dropdown-end">
                <label tabindex="0" class="btn btn-ghost btn-circle avatar">
                    <div class="w-10 rounded-full bg-primary text-primary-content flex items-center justify-center">
                        {{ user.username[0].upper() if user else "?" }}
                    </div>
                </label>
                <ul tabindex="0" class="mt-3 p-2 shadow menu menu-compact dropdown-content bg-base-100 rounded-box w-52">
                    <li><a href="/dashboard/settings">Settings</a></li>
                    <li><a href="/dashboard/profile">Profile</a></li>
                    <li><a href="/api/v1/auth/logout">Logout</a></li>
                </ul>
            </div>
        </div>
    </div>

    <!-- Main Content -->
    <main class="container mx-auto px-4 py-8">
        {% block content %}{% endblock %}
    </main>

    <!-- Footer -->
    <footer class="footer footer-center p-4 bg-base-300 text-base-content mt-auto">
        <div>
            <p>Alpha Panda Trading System - Broker: <span class="badge badge-primary">{{ broker }}</span></p>
        </div>
    </footer>

    <!-- Global dashboard functionality -->
    <script nonce="{{ csp_nonce }}">
    function dashboardGlobal() {
        return {
            connectionStatus: 'connected',
            lastHeartbeat: null,
            
            init() {
                this.initializeErrorHandling();
                this.startHeartbeat();
                this.setupCSRFProtection();
            },
            
            initializeErrorHandling() {
                // Global HTMX error handling
                document.body.addEventListener('htmx:responseError', (event) => {
                    this.handleError(event.detail);
                });
                
                document.body.addEventListener('htmx:timeout', (event) => {
                    this.handleTimeout(event.detail);
                });
            },
            
            startHeartbeat() {
                setInterval(() => {
                    fetch('/dashboard/api/heartbeat', {
                        method: 'GET',
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest'
                        }
                    })
                    .then(response => {
                        this.connectionStatus = response.ok ? 'connected' : 'error';
                        this.lastHeartbeat = new Date();
                    })
                    .catch(() => {
                        this.connectionStatus = 'disconnected';
                    });
                }, 30000); // 30 second heartbeat
            },
            
            // CSRF protection moved to Phase 4 (optional security enhancements)
            
            handleError(detail) {
                console.error('Dashboard Error:', detail);
                this.showNotification('error', 'Connection error. Please refresh the page.');
            },
            
            handleTimeout(detail) {
                console.warn('Dashboard Timeout:', detail);
                this.showNotification('warning', 'Request timed out. Retrying...');
            },
            
            showNotification(type, message) {
                // Create toast notification
                const toast = document.createElement('div');
                toast.className = `alert alert-${type} fixed top-4 right-4 w-auto z-50 shadow-lg`;
                toast.innerHTML = `
                    <span>${message}</span>
                    <button class="btn btn-sm btn-ghost" onclick="this.parentElement.remove()">×</button>
                `;
                document.body.appendChild(toast);
                
                // Auto-remove after 5 seconds
                setTimeout(() => {
                    if (toast.parentElement) {
                        toast.remove();
                    }
                }, 5000);
            }
        }
    }
    </script>
    
    <!-- Performance monitoring -->
    <script nonce="{{ csp_nonce }}">
    // Monitor page performance
    window.addEventListener('load', function() {
        if ('performance' in window) {
            const perfData = performance.getEntriesByType('navigation')[0];
            if (perfData.loadEventEnd - perfData.loadEventStart > 3000) {
                console.warn('Dashboard load time exceeded 3 seconds');
            }
        }
    });
    </script>
    
    {% block scripts %}{% endblock %}
</body>
</html>
```

#### 1.3 Enhanced Real-time Data Integration with Security

```python
# dashboard/routers/realtime.py
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from api.dependencies import get_settings, get_redis_client
from core.config.settings import Settings
import asyncio
import json
import redis.asyncio as redis

router = APIRouter(prefix="/dashboard/events", tags=["realtime"])

@router.get("/health")
async def health_stream(
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """Server-Sent Events for health monitoring"""
    async def event_generator():
        while True:
            try:
                # Get health data from monitoring API
                from api.routers.monitoring import health_check
                health_data = await health_check(settings, redis_client)
                
                yield {
                    "event": "health_update",
                    "data": json.dumps(health_data)
                }
                
                await asyncio.sleep(10)  # Update every 10 seconds
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e)})
                }
                await asyncio.sleep(10)
    
    return EventSourceResponse(event_generator())

@router.get("/pipeline")
async def pipeline_stream(
    settings: Settings = Depends(get_settings),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """Server-Sent Events for pipeline monitoring"""
    async def event_generator():
        while True:
            try:
                from api.routers.monitoring import pipeline_status
                pipeline_data = await pipeline_status(settings, redis_client)
                
                yield {
                    "event": "pipeline_update",
                    "data": json.dumps(pipeline_data)
                }
                
                await asyncio.sleep(5)  # Update every 5 seconds
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({"error": str(e)})
                }
                await asyncio.sleep(5)
    
    return EventSourceResponse(event_generator())

# Helper functions
async def fetch_health_data():
    """Fetch health data for real-time streaming"""
    # Implementation here
    return {"status": "healthy", "components": []}
```

### Phase 2: Secure Dashboard Components with Advanced Features (Week 3-4)

#### 2.1 System Overview Dashboard

```html
<!-- dashboard/templates/dashboard/index.html -->
{% extends "base.html" %}

{% block title %}System Overview - Alpha Panda{% endblock %}

{% block content %}
<div x-data="dashboardOverview()" class="space-y-6">
    <!-- System Status Cards -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div class="stats shadow">
            <div class="stat" 
                 hx-get="/api/v1/monitoring/health" 
                 hx-trigger="every 10s"
                 hx-target="#system-health">
                <div id="system-health" class="stat-title">System Health</div>
                <div class="stat-value text-success">Loading...</div>
            </div>
        </div>
        
        <div class="stats shadow">
            <div class="stat"
                 hx-get="/api/v1/monitoring/metrics"
                 hx-trigger="every 5s"
                 hx-target="#event-count">
                <div class="stat-title">Events Processed</div>
                <div id="event-count" class="stat-value">Loading...</div>
            </div>
        </div>
        
        <div class="stats shadow">
            <div class="stat"
                 hx-get="/api/v1/portfolios/summary/stats"
                 hx-trigger="every 30s"
                 hx-target="#portfolio-pnl">
                <div class="stat-title">Total P&L</div>
                <div id="portfolio-pnl" class="stat-value text-success">Loading...</div>
            </div>
        </div>
        
        <div class="stats shadow">
            <div class="stat">
                <div class="stat-title">Broker</div>
                <div class="stat-value badge badge-primary">{{ broker }}</div>
            </div>
        </div>
    </div>

    <!-- Pipeline Flow Diagram -->
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">Pipeline Flow</h2>
            <div class="pipeline-diagram" 
                 hx-get="/dashboard/components/pipeline-diagram" 
                 hx-trigger="every 10s">
                Loading pipeline status...
            </div>
        </div>
    </div>

    <!-- Real-time Activity Feed -->
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">Activity Feed</h2>
            <div id="activity-feed" 
                 hx-ext="sse" 
                 sse-connect="/dashboard/events/activity" 
                 sse-swap="activity_item" 
                 hx-swap="beforeend"
                 class="max-h-96 overflow-y-auto">
                <!-- Activity items will appear here -->
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
function dashboardOverview() {
    return {
        systemStatus: 'loading',
        lastUpdate: null,
        
        init() {
            this.startRealTimeUpdates();
        },
        
        startRealTimeUpdates() {
            // Connect to SSE for real-time updates
            const eventSource = new EventSource('/dashboard/events/health');
            
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.updateSystemStatus(data);
                this.lastUpdate = new Date().toLocaleTimeString();
            };
            
            eventSource.onerror = () => {
                this.systemStatus = 'error';
            };
        },
        
        updateSystemStatus(data) {
            this.systemStatus = data.status;
            // Update UI elements based on status
        }
    }
}
</script>
{% endblock %}
```

#### 2.2 Health Monitoring Dashboard

```html
<!-- dashboard/templates/dashboard/health.html -->
{% extends "base.html" %}

{% block title %}Health Monitoring - Alpha Panda{% endblock %}

{% block content %}
<div x-data="healthDashboard()" class="space-y-6">
    <!-- Health Status Matrix -->
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">Component Health Status</h2>
            <div class="overflow-x-auto">
                <table class="table table-zebra w-full"
                       hx-get="/dashboard/components/health-matrix"
                       hx-trigger="every 15s">
                    <thead>
                        <tr>
                            <th>Component</th>
                            <th>Status</th>
                            <th>Last Check</th>
                            <th>Duration</th>
                            <th>Details</th>
                        </tr>
                    </thead>
                    <tbody id="health-matrix">
                        <tr><td colspan="5">Loading health data...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- System Resources -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h3 class="card-title">CPU Usage</h3>
                <div class="radial-progress text-primary" :style="`--value:${cpuUsage}`">
                    <span x-text="`${cpuUsage}%`"></span>
                </div>
            </div>
        </div>
        
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h3 class="card-title">Memory Usage</h3>
                <div class="radial-progress text-secondary" :style="`--value:${memoryUsage}`">
                    <span x-text="`${memoryUsage}%`"></span>
                </div>
            </div>
        </div>
        
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h3 class="card-title">Disk Usage</h3>
                <div class="radial-progress text-accent" :style="`--value:${diskUsage}`">
                    <span x-text="`${diskUsage}%`"></span>
                </div>
            </div>
        </div>
    </div>

    <!-- Health History Chart -->
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">Health History</h2>
            <canvas id="healthChart" width="400" height="200"></canvas>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script>
function healthDashboard() {
    return {
        cpuUsage: 0,
        memoryUsage: 0,
        diskUsage: 0,
        healthChart: null,
        
        init() {
            this.initHealthChart();
            this.startHealthMonitoring();
        },
        
        initHealthChart() {
            const ctx = document.getElementById('healthChart').getContext('2d');
            this.healthChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'System Health Score',
                        data: [],
                        borderColor: 'rgb(75, 192, 192)',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 100
                        }
                    }
                }
            });
        },
        
        startHealthMonitoring() {
            // Connect to SSE for real-time health updates
            const eventSource = new EventSource('/dashboard/events/health');
            
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.updateHealthMetrics(data);
            };
        },
        
        updateHealthMetrics(data) {
            // Update system resource usage
            if (data.data && data.data.checks) {
                const checks = data.data.checks;
                
                if (checks.cpu_usage && checks.cpu_usage.details) {
                    this.cpuUsage = Math.round(checks.cpu_usage.details.cpu_percent);
                }
                
                if (checks.memory_usage && checks.memory_usage.details) {
                    this.memoryUsage = Math.round(checks.memory_usage.details.used_percent);
                }
                
                if (checks.disk_space && checks.disk_space.details) {
                    this.diskUsage = Math.round(checks.disk_space.details.used_percent);
                }
            }
            
            // Update health chart
            this.updateHealthChart(data);
        },
        
        updateHealthChart(data) {
            if (!this.healthChart) return;
            
            const now = new Date().toLocaleTimeString();
            const healthScore = this.calculateHealthScore(data);
            
            this.healthChart.data.labels.push(now);
            this.healthChart.data.datasets[0].data.push(healthScore);
            
            // Keep only last 20 data points
            if (this.healthChart.data.labels.length > 20) {
                this.healthChart.data.labels.shift();
                this.healthChart.data.datasets[0].data.shift();
            }
            
            this.healthChart.update();
        },
        
        calculateHealthScore(data) {
            // Calculate overall health score based on component status
            if (!data.data || !data.data.summary) return 0;
            
            const summary = data.data.summary;
            const totalChecks = summary.total_checks || 1;
            const healthyChecks = summary.healthy || 0;
            
            return Math.round((healthyChecks / totalChecks) * 100);
        }
    }
}
</script>
{% endblock %}
```

### Phase 3: Advanced Features (Week 5-6)

#### 3.1 Pipeline Monitoring Dashboard

```html
<!-- dashboard/templates/dashboard/pipeline.html -->
{% extends "base.html" %}

{% block title %}Pipeline Monitoring - Alpha Panda{% endblock %}

{% block content %}
<div x-data="pipelineMonitor()" class="space-y-6">
    <!-- Pipeline Flow Diagram -->
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">End-to-End Pipeline Flow</h2>
            <div class="pipeline-flow">
                <div class="flex items-center justify-between p-4">
                    <!-- Market Feed -->
                    <div class="pipeline-stage" :class="getStageClass('market_ticks')">
                        <div class="stage-icon">📊</div>
                        <div class="stage-name">Market Feed</div>
                        <div class="stage-count" x-text="stageMetrics.market_ticks?.count || 0"></div>
                    </div>
                    
                    <div class="pipeline-arrow">→</div>
                    
                    <!-- Strategy Runner -->
                    <div class="pipeline-stage" :class="getStageClass('signals')">
                        <div class="stage-icon">🧠</div>
                        <div class="stage-name">Strategy Runner</div>
                        <div class="stage-count" x-text="stageMetrics.signals?.count || 0"></div>
                    </div>
                    
                    <div class="pipeline-arrow">→</div>
                    
                    <!-- Risk Manager -->
                    <div class="pipeline-stage" :class="getStageClass('signals_validated')">
                        <div class="stage-icon">🛡️</div>
                        <div class="stage-name">Risk Manager</div>
                        <div class="stage-count" x-text="stageMetrics.signals_validated?.count || 0"></div>
                    </div>
                    
                    <div class="pipeline-arrow">→</div>
                    
                    <!-- Trading Engine -->
                    <div class="pipeline-stage" :class="getStageClass('orders')">
                        <div class="stage-icon">⚡</div>
                        <div class="stage-name">Trading Engine</div>
                        <div class="stage-count" x-text="stageMetrics.orders?.count || 0"></div>
                    </div>
                    
                    <div class="pipeline-arrow">→</div>
                    
                    <!-- Portfolio Manager -->
                    <div class="pipeline-stage" :class="getStageClass('portfolio_updates')">
                        <div class="stage-icon">💼</div>
                        <div class="stage-name">Portfolio Manager</div>
                        <div class="stage-count" x-text="stageMetrics.portfolio_updates?.count || 0"></div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Stage Details -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h3 class="card-title">Throughput Metrics</h3>
                <canvas id="throughputChart" width="400" height="200"></canvas>
            </div>
        </div>
        
        <div class="card bg-base-100 shadow-xl">
            <div class="card-body">
                <h3 class="card-title">Latency Metrics</h3>
                <canvas id="latencyChart" width="400" height="200"></canvas>
            </div>
        </div>
    </div>

    <!-- Consumer Lag Monitoring -->
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <h2 class="card-title">Consumer Lag Monitoring</h2>
            <div class="overflow-x-auto">
                <table class="table table-zebra w-full"
                       hx-get="/dashboard/components/consumer-lag"
                       hx-trigger="every 10s">
                    <thead>
                        <tr>
                            <th>Consumer Group</th>
                            <th>Topic</th>
                            <th>Partition</th>
                            <th>Current Offset</th>
                            <th>End Offset</th>
                            <th>Lag</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="consumer-lag-table">
                        <tr><td colspan="7">Loading consumer lag data...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</div>

<style>
.pipeline-stage {
    @apply flex flex-col items-center p-4 rounded-lg border-2 min-w-32;
}

.pipeline-stage.healthy {
    @apply border-success bg-success bg-opacity-10;
}

.pipeline-stage.degraded {
    @apply border-warning bg-warning bg-opacity-10;
}

.pipeline-stage.unhealthy {
    @apply border-error bg-error bg-opacity-10;
}

.pipeline-arrow {
    @apply text-2xl text-base-content opacity-50;
}

.stage-icon {
    @apply text-2xl mb-2;
}

.stage-name {
    @apply text-sm font-semibold text-center mb-1;
}

.stage-count {
    @apply text-xs text-base-content opacity-75;
}
</style>
{% endblock %}

{% block scripts %}
<script>
function pipelineMonitor() {
    return {
        stageMetrics: {},
        throughputChart: null,
        latencyChart: null,
        
        init() {
            this.initCharts();
            this.startPipelineMonitoring();
        },
        
        initCharts() {
            // Initialize throughput chart
            const throughputCtx = document.getElementById('throughputChart').getContext('2d');
            this.throughputChart = new Chart(throughputCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Messages/sec',
                        data: [],
                        borderColor: 'rgb(54, 162, 235)',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            });
            
            // Initialize latency chart
            const latencyCtx = document.getElementById('latencyChart').getContext('2d');
            this.latencyChart = new Chart(latencyCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Latency (ms)',
                        data: [],
                        borderColor: 'rgb(255, 99, 132)',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        y: { beginAtZero: true }
                    }
                }
            });
        },
        
        startPipelineMonitoring() {
            const eventSource = new EventSource('/dashboard/events/pipeline');
            
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.updatePipelineMetrics(data);
            };
        },
        
        updatePipelineMetrics(data) {
            if (data.data && data.data.health && data.data.health.stages) {
                this.stageMetrics = data.data.health.stages;
            }
            
            // Update charts
            this.updateCharts(data);
        },
        
        getStageClass(stageName) {
            const stage = this.stageMetrics[stageName];
            if (!stage) return '';
            
            if (stage.healthy) return 'healthy';
            if (stage.status === 'degraded') return 'degraded';
            return 'unhealthy';
        },
        
        updateCharts(data) {
            // Update throughput chart
            const now = new Date().toLocaleTimeString();
            const throughput = this.calculateThroughput(data);
            
            this.throughputChart.data.labels.push(now);
            this.throughputChart.data.datasets[0].data.push(throughput);
            
            if (this.throughputChart.data.labels.length > 20) {
                this.throughputChart.data.labels.shift();
                this.throughputChart.data.datasets[0].data.shift();
            }
            
            this.throughputChart.update();
            
            // Update latency chart similarly
            const latency = this.calculateLatency(data);
            
            this.latencyChart.data.labels.push(now);
            this.latencyChart.data.datasets[0].data.push(latency);
            
            if (this.latencyChart.data.labels.length > 20) {
                this.latencyChart.data.labels.shift();
                this.latencyChart.data.datasets[0].data.shift();
            }
            
            this.latencyChart.update();
        },
        
        calculateThroughput(data) {
            // Calculate messages per second based on pipeline data
            // Implementation depends on data structure
            return Math.floor(Math.random() * 100); // Placeholder
        },
        
        calculateLatency(data) {
            // Calculate average latency across pipeline stages
            // Implementation depends on data structure
            return Math.floor(Math.random() * 50); // Placeholder
        }
    }
}
</script>
{% endblock %}
```

#### 3.2 Log Viewer Component

```html
<!-- dashboard/templates/dashboard/logs.html -->
{% extends "base.html" %}

{% block title %}Log Viewer - Alpha Panda{% endblock %}

{% block content %}
<div x-data="logViewer()" class="space-y-6">
    <!-- Log Controls -->
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body">
            <div class="flex flex-wrap gap-4 items-center">
                <!-- Log Level Filter -->
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Log Level</span>
                    </label>
                    <select class="select select-bordered" x-model="selectedLevel" @change="filterLogs()">
                        <option value="">All Levels</option>
                        <option value="DEBUG">Debug</option>
                        <option value="INFO">Info</option>
                        <option value="WARNING">Warning</option>
                        <option value="ERROR">Error</option>
                        <option value="CRITICAL">Critical</option>
                    </select>
                </div>
                
                <!-- Service Filter -->
                <div class="form-control">
                    <label class="label">
                        <span class="label-text">Service</span>
                    </label>
                    <select class="select select-bordered" x-model="selectedService" @change="filterLogs()">
                        <option value="">All Services</option>
                        <option value="market_feed">Market Feed</option>
                        <option value="strategy_runner">Strategy Runner</option>
                        <option value="risk_manager">Risk Manager</option>
                        <option value="trading_engine">Trading Engine</option>
                        <option value="portfolio_manager">Portfolio Manager</option>
                        <option value="api">API</option>
                    </select>
                </div>
                
                <!-- Search -->
                <div class="form-control flex-1">
                    <label class="label">
                        <span class="label-text">Search</span>
                    </label>
                    <input type="text" 
                           class="input input-bordered" 
                           placeholder="Search logs..." 
                           x-model="searchQuery"
                           @input.debounce.500ms="filterLogs()">
                </div>
                
                <!-- Controls -->
                <div class="flex gap-2">
                    <button class="btn btn-primary" @click="toggleAutoScroll()">
                        <span x-text="autoScroll ? 'Pause' : 'Resume'"></span>
                    </button>
                    <button class="btn btn-secondary" @click="clearLogs()">Clear</button>
                    <button class="btn btn-accent" @click="exportLogs()">Export</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Log Stream -->
    <div class="card bg-base-100 shadow-xl">
        <div class="card-body p-0">
            <div class="bg-black text-green-400 font-mono text-sm p-4 h-96 overflow-y-auto" 
                 id="log-container"
                 :class="{ 'auto-scroll': autoScroll }">
                
                <!-- SSE Log Stream -->
                <div id="log-stream" 
                     hx-ext="sse" 
                     sse-connect="/dashboard/events/logs" 
                     sse-swap="log_entry" 
                     hx-swap="beforeend">
                    <div class="text-yellow-400">Connecting to log stream...</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Log Statistics -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div class="stats shadow">
            <div class="stat">
                <div class="stat-title">Total Entries</div>
                <div class="stat-value" x-text="logStats.total"></div>
            </div>
        </div>
        
        <div class="stats shadow">
            <div class="stat">
                <div class="stat-title">Errors</div>
                <div class="stat-value text-error" x-text="logStats.errors"></div>
            </div>
        </div>
        
        <div class="stats shadow">
            <div class="stat">
                <div class="stat-title">Warnings</div>
                <div class="stat-value text-warning" x-text="logStats.warnings"></div>
            </div>
        </div>
        
        <div class="stats shadow">
            <div class="stat">
                <div class="stat-title">Last Minute</div>
                <div class="stat-value" x-text="logStats.lastMinute"></div>
            </div>
        </div>
    </div>
</div>

<style>
.log-entry {
    @apply mb-1 whitespace-pre-wrap break-words;
}

.log-level-DEBUG { @apply text-gray-400; }
.log-level-INFO { @apply text-green-400; }
.log-level-WARNING { @apply text-yellow-400; }
.log-level-ERROR { @apply text-red-400; }
.log-level-CRITICAL { @apply text-red-600 font-bold; }

.auto-scroll {
    scroll-behavior: smooth;
}
</style>
{% endblock %}

{% block scripts %}
<script>
function logViewer() {
    return {
        selectedLevel: '',
        selectedService: '',
        searchQuery: '',
        autoScroll: true,
        logStats: {
            total: 0,
            errors: 0,
            warnings: 0,
            lastMinute: 0
        },
        logs: [],
        
        init() {
            this.startLogStream();
            this.updateLogStats();
        },
        
        startLogStream() {
            // The SSE connection is handled by HTMX
            // Listen for new log entries
            document.body.addEventListener('htmx:sseMessage', (event) => {
                if (event.detail.type === 'log_entry') {
                    this.handleNewLogEntry(JSON.parse(event.detail.data));
                }
            });
        },
        
        handleNewLogEntry(logEntry) {
            this.logs.push(logEntry);
            this.updateLogStats();
            
            if (this.autoScroll) {
                this.$nextTick(() => {
                    const container = document.getElementById('log-container');
                    container.scrollTop = container.scrollHeight;
                });
            }
        },
        
        filterLogs() {
            // Send filter parameters to server via HTMX
            const params = new URLSearchParams({
                level: this.selectedLevel,
                service: this.selectedService,
                search: this.searchQuery
            });
            
            htmx.trigger('#log-stream', 'refresh', {
                values: Object.fromEntries(params)
            });
        },
        
        toggleAutoScroll() {
            this.autoScroll = !this.autoScroll;
        },
        
        clearLogs() {
            document.getElementById('log-stream').innerHTML = '';
            this.logs = [];
            this.logStats = { total: 0, errors: 0, warnings: 0, lastMinute: 0 };
        },
        
        exportLogs() {
            // Create downloadable log file
            const logData = this.logs.map(log => 
                `${log.timestamp} [${log.level}] ${log.service}: ${log.message}`
            ).join('\n');
            
            const blob = new Blob([logData], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `alpha-panda-logs-${new Date().toISOString().split('T')[0]}.txt`;
            a.click();
            URL.revokeObjectURL(url);
        },
        
        updateLogStats() {
            this.logStats.total = this.logs.length;
            this.logStats.errors = this.logs.filter(log => log.level === 'ERROR').length;
            this.logStats.warnings = this.logs.filter(log => log.level === 'WARNING').length;
            
            // Count logs in the last minute
            const oneMinuteAgo = Date.now() - 60000;
            this.logStats.lastMinute = this.logs.filter(log => 
                new Date(log.timestamp).getTime() > oneMinuteAgo
            ).length;
        }
    }
}
</script>
{% endblock %}
```

### Phase 4: Integration & Configuration

#### 4.1 Dashboard Configuration

```python
# dashboard/config.py
from pydantic import BaseModel
from typing import Optional

class DashboardSettings(BaseModel):
    """Dashboard-specific configuration"""
    
    # General settings
    enabled: bool = True
    title: str = "Alpha Panda Dashboard"
    theme: str = "corporate"  # DaisyUI theme
    
    # Update intervals (seconds)
    health_update_interval: int = 10
    pipeline_update_interval: int = 5
    log_update_interval: int = 1
    portfolio_update_interval: int = 30
    
    # Display settings
    max_log_entries: int = 1000
    chart_data_points: int = 20
    activity_feed_items: int = 50
    
    # Real-time settings
    enable_sse: bool = True
    enable_websocket_fallback: bool = True
    
    # Security
    require_authentication: bool = True
    session_timeout_minutes: int = 60
```

#### 4.2 Integration with Main Application

```python
# Update api/main.py
from dashboard.routers import main as dashboard_main
from dashboard.routers import realtime as dashboard_realtime

def create_app() -> FastAPI:
    app = FastAPI(
        title="Alpha Panda Trading API",
        version="2.0.0",
        description="API for monitoring and managing the Alpha Panda trading system."
    )

    # Existing middleware and routers...
    
    # Dashboard routes
    app.include_router(dashboard_main.router)
    app.include_router(dashboard_realtime.router)
    
    return app
```

#### 4.3 Docker Integration

```dockerfile
# Add to existing Dockerfile
COPY dashboard/ /app/dashboard/

# Install additional dependencies
RUN pip install jinja2 sse-starlette python-multipart
```

## Security Considerations

### Core Security (Phase 1-3)
- **Basic Authentication**: JWT token validation for all dashboard routes
- **HTTPS Enforcement**: All dashboard traffic over HTTPS in production
- **Basic Input Validation**: Sanitization of user inputs
- **Session Management**: Secure session handling with existing auth system

### Optional Advanced Security (Phase 4 - Future Implementation)
The following security features are **optional** and can be implemented in Phase 4 or future iterations:

#### Advanced Authentication & Authorization
- **RBAC**: Role-based access control with fine-grained permissions
- **Multi-factor Auth**: Optional 2FA for admin accounts
- **API Key Management**: Secure API keys for service-to-service communication

#### Network Security Enhancements
- **CSP Headers**: Content Security Policy with nonces for inline scripts
- **Rate Limiting**: Token bucket algorithm with per-user limits
- **Advanced CORS**: Strict origin validation

#### Data Protection Enhancements
- **Sensitive Data Masking**: PII and trading secrets masked in UI
- **CSRF Protection**: Cross-site request forgery protection
- **XSS Prevention**: Advanced XSS protection with CSP

#### Audit & Compliance (Optional)
- **Security Event Logging**: All access attempts logged with correlation IDs
- **Anomaly Detection**: Unusual access patterns flagged
- **Compliance Logging**: GDPR/SOX compliance audit trails

**Note**: These advanced security features add complexity and can be implemented later based on specific security requirements.

## Advanced Performance Framework

### Multi-Tier Caching Strategy

#### 1. Application-Level Caching
- **Redis Cache**: Multi-level caching with TTL optimization
- **User-Specific Cache**: Personalized data caching per user role
- **Query Result Cache**: Database query results cached with smart invalidation
- **Computed Metrics Cache**: Expensive calculations cached with background refresh

#### 2. Client-Side Performance
- **CDN Integration**: Static assets served via CDN with edge caching
- **Resource Bundling**: CSS/JS bundling with tree shaking
- **Image Optimization**: WebP format with lazy loading
- **Critical Path CSS**: Inline critical styles, defer non-critical

#### 3. Real-Time Optimization
- **Connection Pooling**: Persistent SSE connections with health checks
- **Data Deduplication**: Client-side dedup using event IDs
- **Selective Updates**: Only changed data transmitted
- **Compression**: gzip/brotli compression for all responses
- **WebSocket Fallback**: Intelligent fallback for unreliable connections

#### 4. Database Performance
- **Query Optimization**: Indexed queries with execution plan analysis
- **Connection Pooling**: Async connection pools with overflow handling
- **Read Replicas**: Read-heavy operations routed to replicas
- **Materialized Views**: Pre-computed dashboard aggregations

#### 5. Memory Management
- **Lazy Loading**: Components loaded on demand
- **Virtual Scrolling**: Large datasets with virtualized rendering
- **Memory Leak Prevention**: Proper cleanup of SSE connections
- **Background Tasks**: Heavy processing moved to background workers

```python
# Performance monitoring implementation
class PerformanceMonitor:
    def __init__(self):
        self.metrics = defaultdict(list)
    
    async def track_request_time(self, endpoint: str, duration: float):
        self.metrics[f"{endpoint}_response_time"].append(duration)
        
        # Alert if response time > 2 seconds
        if duration > 2.0:
            await self.alert_slow_response(endpoint, duration)
    
    async def track_cache_hit_rate(self, cache_key: str, hit: bool):
        metric_key = f"{cache_key}_cache_hits"
        self.metrics[metric_key].append(1 if hit else 0)
        
        # Calculate hit rate over last 100 requests
        recent_hits = self.metrics[metric_key][-100:]
        hit_rate = sum(recent_hits) / len(recent_hits) if recent_hits else 0
        
        if hit_rate < 0.8:  # Alert if hit rate < 80%
            await self.alert_low_cache_performance(cache_key, hit_rate)
```

## Testing Strategy

### Unit Tests
- Component functionality testing
- API endpoint testing
- Real-time data flow testing

### Integration Tests
- Dashboard UI automation tests
- End-to-end pipeline monitoring tests
- Authentication flow tests

### Performance Tests
- Load testing for concurrent users
- Memory usage monitoring
- Real-time update performance

## Deployment Guidelines

### Environment Configuration
```bash
# Dashboard-specific environment variables
DASHBOARD_ENABLED=true
DASHBOARD_THEME=corporate
DASHBOARD_REQUIRE_AUTH=true
SSE_ENABLED=true
```

### Production Deployment Framework

#### 1. Infrastructure Security
- **HTTPS Enforcement**: TLS 1.3 with perfect forward secrecy
- **Certificate Management**: Automated cert renewal with Let's Encrypt
- **WAF Integration**: Web Application Firewall for DDoS protection
- **Load Balancer Security**: SSL termination at load balancer level

#### 2. Configuration Management
- **Environment Separation**: Strict dev/staging/prod isolation
- **Secret Management**: HashiCorp Vault or AWS Secrets Manager
- **Configuration Validation**: Schema validation for all configs
- **Hot Reloading**: Configuration updates without downtime

#### 3. Monitoring & Observability
```python
# Production monitoring setup
MONITORING_CONFIG = {
    'metrics': {
        'dashboard_response_time': {'threshold': 2.0, 'alert': 'slack'},
        'sse_connection_count': {'threshold': 1000, 'alert': 'pagerduty'},
        'cache_hit_rate': {'threshold': 0.8, 'alert': 'email'},
        'error_rate': {'threshold': 0.01, 'alert': 'pagerduty'}
    },
    'health_checks': {
        'database_connectivity': {'interval': 30, 'timeout': 5},
        'redis_connectivity': {'interval': 30, 'timeout': 5},
        'external_api_health': {'interval': 60, 'timeout': 10}
    },
    'log_aggregation': {
        'structured_logging': True,
        'correlation_ids': True,
        'sensitive_data_scrubbing': True
    }
}
```

#### 4. Disaster Recovery
- **Automated Backups**: Daily encrypted backups to multiple regions
- **Recovery Testing**: Monthly disaster recovery drills
- **Failover Procedures**: Automated failover with health checks
- **Data Consistency**: ACID compliance for critical dashboard state

## Maintenance & Monitoring

### Health Monitoring
- Dashboard service health checks
- Real-time connection monitoring
- Performance metrics tracking

### Updates & Upgrades
- Version compatibility checking
- Graceful deployment strategies
- Rollback procedures

### Troubleshooting
- Common issues and solutions
- Debug mode configuration
- Log analysis procedures

## Simplified Implementation Timeline

### Phase 1: Core Foundation (Week 1-2)
- Basic middleware implementation
- Performance caching layer with Redis
- Base templates (simplified, no advanced security)
- JWT authentication integration

### Phase 2: Core Dashboard Features (Week 3-4)
- System overview with real-time updates
- Health monitoring dashboard
- Basic performance optimizations
- Server-Sent Events implementation

### Phase 3: Advanced Features (Week 5-6)
- Pipeline monitoring with visual flow
- Log viewer with filtering
- Financial charts with Plotly.js
- Basic export functionality

### Phase 4: Optional Security & Production Hardening (Future/Optional)
- **Advanced Security Features (Optional)**:
  - CSP headers and nonces
  - CSRF protection
  - Rate limiting middleware
  - RBAC with fine-grained permissions
  - Security audit logging
- **Production Hardening**:
  - Security testing and penetration testing
  - Advanced monitoring and alerting
  - Performance load testing
  - Documentation and training

## Success Metrics

- **Performance**: < 2s page load time, > 95% uptime
- **Security**: Zero XSS/CSRF vulnerabilities, comprehensive audit logs
- **Usability**: < 3 clicks to any information, mobile responsive
- **Reliability**: 99.9% real-time data accuracy, automatic error recovery

---

This enhanced implementation guide provides a production-ready, security-first approach to building a modern monitoring dashboard for the Alpha Panda trading system. The framework emphasizes defense-in-depth security, high-performance real-time capabilities, and enterprise-grade reliability while maintaining the simplicity of the HTMX + Alpine.js stack.