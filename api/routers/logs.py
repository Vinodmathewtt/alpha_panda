from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import Optional, List
from datetime import datetime, timedelta
import asyncio

from api.dependencies import get_log_service, get_pagination_params, get_log_filter_params
from api.services.log_service import LogService
from api.schemas.responses import StandardResponse, PaginatedResponse, LogEntry, LogStatistics
from core.logging import get_statistics as get_logging_statistics

router = APIRouter(prefix="/logs", tags=["Logs"])

@router.get("/", response_model=PaginatedResponse[LogEntry])
async def get_logs(
    pagination: dict = Depends(get_pagination_params),
    filters: dict = Depends(get_log_filter_params),
    log_service: LogService = Depends(get_log_service)
):
    """Get paginated log entries with filtering"""
    try:
        logs = await log_service.get_logs(
            offset=pagination["offset"],
            limit=pagination["size"],
            filters=filters
        )
        
        total = await log_service.count_logs(filters)
        
        return PaginatedResponse(
            items=logs,
            total=total,
            page=pagination["page"],
            size=pagination["size"],
            pages=(total + pagination["size"] - 1) // pagination["size"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve logs: {str(e)}")

@router.get("/statistics", response_model=StandardResponse[LogStatistics])
async def get_log_statistics(
    hours: int = Query(24, ge=1, le=168, description="Hours to analyze"),
    log_service: LogService = Depends(get_log_service)
):
    """Get log statistics for the specified time period"""
    try:
        start_time = datetime.utcnow() - timedelta(hours=hours)
        stats = await log_service.get_statistics(start_time=start_time)
        
        return StandardResponse(
            status="success",
            data=stats,
            message=f"Log statistics for last {hours} hours"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get log statistics: {str(e)}")

@router.get("/services", response_model=StandardResponse[List[str]])
async def get_log_services(
    log_service: LogService = Depends(get_log_service)
):
    """Get list of available log services/sources"""
    try:
        services = await log_service.get_available_services()
        return StandardResponse(
            status="success",
            data=services,
            message="Available log services"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get log services: {str(e)}")

@router.get("/channels", response_model=StandardResponse[List[str]])
async def get_log_channels(
    log_service: LogService = Depends(get_log_service)
):
    """Get list of available log channels"""
    try:
        channels = await log_service.get_available_channels()
        return StandardResponse(
            status="success",
            data=channels,
            message="Available log channels"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get log channels: {str(e)}")

@router.post("/export")
async def export_logs(
    background_tasks: BackgroundTasks,
    format: str = Query("json", regex="^(json|csv|txt)$"),
    filters: dict = Depends(get_log_filter_params),
    log_service: LogService = Depends(get_log_service)
):
    """Export logs in specified format"""
    try:
        # Generate export file in background
        export_id = await log_service.create_export_task(
            format=format,
            filters=filters
        )
        
        background_tasks.add_task(
            log_service.process_export_task,
            export_id
        )
        
        return StandardResponse(
            status="success",
            data={"export_id": export_id, "format": format},
            message="Log export started. Check export status endpoint."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start log export: {str(e)}")

@router.get("/export/{export_id}/status")
async def get_export_status(
    export_id: str,
    log_service: LogService = Depends(get_log_service)
):
    """Get status of log export task"""
    try:
        status = await log_service.get_export_status(export_id)
        return StandardResponse(
            status="success",
            data=status,
            message="Export status retrieved"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get export status: {str(e)}")

@router.get("/search")
async def search_logs(
    query: str = Query(..., min_length=3, max_length=500),
    pagination: dict = Depends(get_pagination_params),
    log_service: LogService = Depends(get_log_service)
):
    """Full-text search in logs"""
    try:
        results = await log_service.search_logs(
            query=query,
            offset=pagination["offset"],
            limit=pagination["size"]
        )
        
        total = await log_service.count_search_results(query)
        
        return PaginatedResponse(
            items=results,
            total=total,
            page=pagination["page"],
            size=pagination["size"],
            pages=(total + pagination["size"] - 1) // pagination["size"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Log search failed: {str(e)}")

@router.get("/levels", response_model=StandardResponse[List[str]])
async def get_log_levels():
    """Get available log levels"""
    try:
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        return StandardResponse(
            status="success",
            data=levels,
            message="Available log levels"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get log levels: {str(e)}")


@router.get("/stats", response_model=StandardResponse[dict])
async def logging_stats():
    """Expose logging subsystem stats: queue, channels, and configuration."""
    try:
        stats = get_logging_statistics()
        return StandardResponse(status="success", data=stats, message="Logging statistics")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get logging stats: {str(e)}")

@router.get("/tail/{service_name}")
async def tail_service_logs(
    service_name: str,
    lines: int = Query(100, ge=1, le=1000),
    follow: bool = Query(False),
    log_service: LogService = Depends(get_log_service)
):
    """Tail logs for a specific service (like tail -f)"""
    try:
        # Get recent logs
        logs = await log_service.get_logs(
            offset=0,
            limit=lines,
            filters={"service": service_name}
        )
        
        result = {
            "service": service_name,
            "lines": lines,
            "following": follow,
            "logs": logs
        }
        
        if follow:
            result["message"] = f"Use /realtime/events/logs?service={service_name} for live streaming"
        
        return StandardResponse(
            status="success",
            data=result,
            message=f"Tail logs for service '{service_name}'"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to tail logs: {str(e)}")
