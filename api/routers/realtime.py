from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from sse_starlette.sse import EventSourceResponse
from typing import List, Optional
import asyncio
import json
from datetime import datetime

from api.dependencies import get_dashboard_service, get_current_user_optional
from api.services.dashboard_service import DashboardService
from api.services.realtime_service import RealtimeService, ConnectionManager

router = APIRouter(prefix="/realtime", tags=["Real-time"])

# Connection manager for WebSocket connections
connection_manager = ConnectionManager()
realtime_service = RealtimeService()

@router.get("/events/health")
async def health_stream(
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user_optional)
):
    """Server-Sent Events stream for health monitoring updates"""
    async def event_generator():
        while True:
            try:
                health_data = await dashboard_service.get_health_summary()
                yield {
                    "event": "health_update",
                    "data": json.dumps({
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": health_data,
                        "user": current_user.user_id if current_user else None
                    })
                }
                await asyncio.sleep(10)  # Update every 10 seconds
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
                await asyncio.sleep(10)
    
    return EventSourceResponse(event_generator())

@router.get("/events/pipeline")
async def pipeline_stream(
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user_optional)
):
    """Server-Sent Events stream for pipeline monitoring updates"""
    async def event_generator():
        while True:
            try:
                pipeline_data = await dashboard_service.get_pipeline_summary()
                yield {
                    "event": "pipeline_update",
                    "data": json.dumps({
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": pipeline_data,
                        "user": current_user.user_id if current_user else None
                    })
                }
                await asyncio.sleep(5)  # Update every 5 seconds
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
                await asyncio.sleep(5)
    
    return EventSourceResponse(event_generator())

@router.get("/events/logs")
async def log_stream(
    level: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user_optional)
):
    """Server-Sent Events stream for log entries"""
    async def event_generator():
        async for log_entry in dashboard_service.stream_logs(level=level, service=service):
            try:
                yield {
                    "event": "log_entry",
                    "data": json.dumps({
                        "timestamp": log_entry.get("timestamp"),
                        "level": log_entry.get("level"),
                        "service": log_entry.get("service"),
                        "message": log_entry.get("message"),
                        "details": log_entry.get("details"),
                        "user": current_user.user_id if current_user else None
                    })
                }
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
    
    return EventSourceResponse(event_generator())

@router.get("/events/activity")
async def activity_stream(
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user_optional)
):
    """Server-Sent Events stream for system activity feed"""
    async def event_generator():
        async for activity in dashboard_service.stream_activity():
            try:
                yield {
                    "event": "activity_item",
                    "data": json.dumps({
                        "timestamp": activity.get("timestamp"),
                        "type": activity.get("type"),
                        "service": activity.get("service"),
                        "message": activity.get("message"),
                        "severity": activity.get("severity", "info"),
                        "user": current_user.user_id if current_user else None
                    })
                }
            except Exception as e:
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    })
                }
    
    return EventSourceResponse(event_generator())

@router.websocket("/ws/monitoring")
async def monitoring_websocket(
    websocket: WebSocket,
    dashboard_service: DashboardService = Depends(get_dashboard_service)
):
    """WebSocket endpoint for real-time monitoring (fallback for SSE)"""
    await connection_manager.connect(websocket)
    
    try:
        while True:
            # Send periodic updates
            health_data = await dashboard_service.get_health_summary()
            pipeline_data = await dashboard_service.get_pipeline_summary()
            
            await connection_manager.send_json({
                "type": "monitoring_update",
                "timestamp": datetime.utcnow().isoformat(),
                "health": health_data,
                "pipeline": pipeline_data
            }, websocket)
            
            await asyncio.sleep(10)
            
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as e:
        await connection_manager.send_json({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)
        connection_manager.disconnect(websocket)

@router.websocket("/ws/logs")
async def logs_websocket(
    websocket: WebSocket,
    dashboard_service: DashboardService = Depends(get_dashboard_service)
):
    """WebSocket endpoint for real-time log streaming"""
    await connection_manager.connect(websocket)
    
    try:
        async for log_entry in dashboard_service.stream_logs():
            await connection_manager.send_json({
                "type": "log_entry",
                "timestamp": log_entry.get("timestamp"),
                "data": log_entry
            }, websocket)
            
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as e:
        await connection_manager.send_json({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }, websocket)
        connection_manager.disconnect(websocket)

@router.get("/status")
async def get_realtime_status():
    """Get real-time streaming status"""
    return {
        "status": "success",
        "data": {
            "sse_enabled": True,
            "websocket_enabled": True,
            "active_connections": len(connection_manager.active_connections),
            "supported_streams": [
                "health",
                "pipeline", 
                "logs",
                "activity"
            ]
        },
        "message": "Real-time streaming is active"
    }