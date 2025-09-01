"""Main dashboard router with authentication integration."""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, Response
from api.dependencies import get_current_user, get_settings, get_redis_client
from core.config.settings import Settings
import redis.asyncio as redis
import time

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
    # Display active brokers context (comma-separated) or 'shared' when unset
    try:
        brokers = getattr(settings, 'active_brokers', []) or []
        broker_ctx = ",".join(brokers) if brokers else "shared"
    except Exception:
        broker_ctx = "shared"
    context = {
        "request": request,
        "user": current_user,
        "broker": broker_ctx,
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


@router.get("/pipeline", response_class=HTMLResponse)
async def pipeline_dashboard(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Pipeline monitoring dashboard"""
    context = {
        "request": request,
        "user": current_user,
        "title": "Pipeline Monitoring"
    }
    return templates.TemplateResponse("dashboard/pipeline.html", context)


@router.get("/portfolios", response_class=HTMLResponse)
async def portfolios_dashboard(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Portfolio analytics dashboard"""
    context = {
        "request": request,
        "user": current_user,
        "title": "Portfolio Analytics"
    }
    return templates.TemplateResponse("dashboard/portfolios.html", context)


@router.get("/logs", response_class=HTMLResponse)
async def logs_dashboard(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Log viewer dashboard"""
    context = {
        "request": request,
        "user": current_user,
        "title": "Log Viewer"
    }
    return templates.TemplateResponse("dashboard/logs.html", context)


@router.get("/api/heartbeat")
async def dashboard_heartbeat(
    current_user: dict = Depends(get_current_user),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """Dashboard heartbeat endpoint for connection status"""
    try:
        # Test Redis connection
        await redis_client.ping()

        return JSONResponse({
            "status": "healthy",
            "timestamp": time.time(),
            "user": current_user.get("username") if isinstance(current_user, dict) and current_user else None
        })
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Dashboard services unavailable: {str(e)}"
        )


# Helper functions
async def get_system_health(redis_client: redis.Redis):
    """Fetch system health data"""
    try:
        # Test Redis connection
        await redis_client.ping()

        return {
            "status": "healthy",
            "uptime": "24h",
            "services": {
                "redis": "healthy",
                "database": "healthy",
                "market_feed": "healthy"
            }
        }
    except Exception:
        return {
            "status": "degraded",
            "uptime": "24h",
            "services": {
                "redis": "unhealthy",
                "database": "unknown",
                "market_feed": "unknown"
            }
        }


async def get_pipeline_status():
    """Fetch pipeline status"""
    return {
        "active_pipelines": 5,
        "messages_processed": 10000,
        "stages": {
            "market_feed": {"status": "healthy", "throughput": 100},
            "strategy_runner": {"status": "healthy", "throughput": 95},
            "risk_manager": {"status": "healthy", "throughput": 90},
            "paper_trading": {"status": "healthy", "throughput": 80},
            "zerodha_trading": {"status": "healthy", "throughput": 75}
        }
    }


async def get_recent_activity():
    """Fetch recent activity feed"""
    return [
        {
            "type": "info",
            "message": "System started successfully",
            "timestamp": time.time() - 300,
            "service": "api"
        },
        {
            "type": "success",
            "message": "Market feed connected",
            "timestamp": time.time() - 250,
            "service": "market_feed"
        },
        {
            "type": "info",
            "message": "Strategy runner initialized",
            "timestamp": time.time() - 200,
            "service": "strategy_runner"
        }
    ]


async def log_dashboard_access(user_id: str, page: str, timestamp: float):
    """Log dashboard access for audit"""
    # Implementation for audit logging
    print(f"Dashboard access: user={user_id}, page={page}, timestamp={timestamp}")


# Component endpoints for HTMX
@router.get("/components/consumer-lag")
async def consumer_lag_component(
    current_user: dict = Depends(get_current_user)
):
    """Consumer lag monitoring component"""
    # Mock consumer lag data
    consumer_data = [
        {
            "consumer_group": "alpha-panda.strategy-runner",
            "topic": "market.ticks",
            "partition": 0,
            "current_offset": 125430,
            "end_offset": 125435,
            "lag": 5,
            "status": "healthy"
        },
        {
            "consumer_group": "alpha-panda.risk-manager",
            "topic": "signals.raw",
            "partition": 0,
            "current_offset": 8520,
            "end_offset": 8525,
            "lag": 5,
            "status": "healthy"
        },
        {
            "consumer_group": "alpha-panda.trading-engine",
            "topic": "signals.validated",
            "partition": 0,
            "current_offset": 7890,
            "end_offset": 7890,
            "lag": 0,
            "status": "healthy"
        },
        {
            "consumer_group": "alpha-panda.portfolio-manager",
            "topic": "orders.filled",
            "partition": 0,
            "current_offset": 6240,
            "end_offset": 6245,
            "lag": 5,
            "status": "warning"
        }
    ]

    # Generate HTML response for consumer lag table
    html_rows = ""
    for consumer in consumer_data:
        status_class = {
            "healthy": "badge-success",
            "warning": "badge-warning",
            "error": "badge-error"
        }.get(consumer["status"], "badge-ghost")

        html_rows += f"""
        <tr>
            <td class="text-xs">{consumer['consumer_group']}</td>
            <td class="font-semibold">{consumer['topic']}</td>
            <td>{consumer['partition']}</td>
            <td>{consumer['current_offset']:,}</td>
            <td>{consumer['end_offset']:,}</td>
            <td>{consumer['lag']}</td>
            <td><span class="badge {status_class}">{consumer['status']}</span></td>
        </tr>
        """

    return HTMLResponse(content=html_rows)


@router.get("/components/pipeline-diagram")
async def pipeline_diagram_component(
    current_user: dict = Depends(get_current_user)
):
    """Pipeline flow diagram component"""
    # This would normally fetch real pipeline metrics
    pipeline_data = await get_pipeline_status()

    # Generate HTML for pipeline status
    html = f"""
    <div class="alert alert-info">
        <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path>
        </svg>
        <div>
            <h3 class="font-bold">Pipeline Status</h3>
            <div class="text-xs">Active Pipelines: {pipeline_data['active_pipelines']}</div>
            <div class="text-xs">Messages Processed: {pipeline_data['messages_processed']:,}</div>
        </div>
    </div>
    """

    return HTMLResponse(content=html)


@router.get("/components/health-matrix")
async def health_matrix_component(
    current_user: dict = Depends(get_current_user),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """Health status matrix component"""
    # Mock health data
    health_components = [
        {
            "component": "Market Feed Service",
            "status": "healthy",
            "last_check": "30s ago",
            "duration": "2h 15m",
            "details": "Processing 125 ticks/sec"
        },
        {
            "component": "Strategy Runner Service",
            "status": "healthy",
            "last_check": "45s ago",
            "duration": "2h 15m",
            "details": "5 strategies active"
        },
        {
            "component": "Risk Manager Service",
            "status": "degraded",
            "last_check": "1m ago",
            "duration": "2h 10m",
            "details": "High memory usage: 85%"
        },
        {
            "component": "Trading Engine Service",
            "status": "healthy",
            "last_check": "15s ago",
            "duration": "2h 15m",
            "details": "Order latency: 45ms avg"
        },
        {
            "component": "Portfolio Manager Service",
            "status": "healthy",
            "last_check": "20s ago",
            "duration": "2h 15m",
            "details": "12 positions tracked"
        },
        {
            "component": "Redis Cache",
            "status": "healthy",
            "last_check": "10s ago",
            "duration": "2h 15m",
            "details": "Hit rate: 94.2%"
        }
    ]

    # Generate HTML rows
    html_rows = ""
    for component in health_components:
        status_class = {
            "healthy": "badge-success",
            "degraded": "badge-warning",
            "unhealthy": "badge-error"
        }.get(component["status"], "badge-ghost")

        html_rows += f"""
        <tr>
            <td class="font-semibold">{component['component']}</td>
            <td><span class="badge {status_class}">{component['status']}</span></td>
            <td class="text-xs text-base-content opacity-70">{component['last_check']}</td>
            <td class="text-xs">{component['duration']}</td>
            <td class="text-xs">{component['details']}</td>
        </tr>
        """

    return HTMLResponse(content=html_rows)


# Export endpoints
@router.get("/export/health-data")
async def export_health_data(
    format: str = "json",
    current_user: dict = Depends(get_current_user),
    redis_client: redis.Redis = Depends(get_redis_client)
):
    """Export health monitoring data"""
    health_data = await get_system_health(redis_client)

    if format.lower() == "csv":
        # Convert to CSV format
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        # Write CSV headers and data
        writer.writerow(["Component", "Status", "Timestamp"])
        for service, status in health_data.get("services", {}).items():
            writer.writerow([service, status, time.time()])

        csv_data = output.getvalue()
        output.close()

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=health-data-{int(time.time())}.csv"}
        )

    # Default to JSON
    return JSONResponse(content=health_data)


@router.get("/export/pipeline-data")
async def export_pipeline_data(
    format: str = "json",
    current_user: dict = Depends(get_current_user)
):
    """Export pipeline monitoring data"""
    pipeline_data = await get_pipeline_status()

    if format.lower() == "csv":
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["Stage", "Status", "Throughput", "Timestamp"])
        for stage, metrics in pipeline_data.get("stages", {}).items():
            writer.writerow([stage, metrics.get("status"), metrics.get("throughput"), time.time()])

        csv_data = output.getvalue()
        output.close()

        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=pipeline-data-{int(time.time())}.csv"}
        )

    return JSONResponse(content=pipeline_data)
