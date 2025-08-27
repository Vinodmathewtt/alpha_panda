from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Dict, Any

from api.dependencies import get_dashboard_service, get_current_user
from api.services.dashboard_service import DashboardService
from api.schemas.responses import StandardResponse, ServiceInfo, ServiceListResponse

router = APIRouter(prefix="/services", tags=["Services"])

@router.get("/", response_model=StandardResponse[ServiceListResponse])
async def get_all_services(
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get status of all Alpha Panda services"""
    try:
        services_info = await dashboard_service.get_all_services_status()
        
        summary = {
            "running": sum(1 for s in services_info if s.status == "running"),
            "stopped": sum(1 for s in services_info if s.status == "stopped"),
            "error": sum(1 for s in services_info if s.status == "error"),
            "total": len(services_info)
        }
        
        return StandardResponse(
            status="success",
            data=ServiceListResponse(services=services_info, summary=summary),
            message="Service status retrieved successfully",
            broker=dashboard_service.broker
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get services status: {str(e)}")

@router.get("/{service_name}", response_model=StandardResponse[ServiceInfo])
async def get_service_status(
    service_name: str,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get detailed status of a specific service"""
    try:
        service_info = await dashboard_service.get_service_status(service_name)
        
        if not service_info:
            raise HTTPException(status_code=404, detail=f"Service '{service_name}' not found")
        
        return StandardResponse(
            status="success",
            data=service_info,
            message=f"Status for service '{service_name}'",
            broker=dashboard_service.broker
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get service status: {str(e)}")

@router.get("/{service_name}/metrics", response_model=StandardResponse[Dict[str, Any]])
async def get_service_metrics(
    service_name: str,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get performance metrics for a specific service"""
    try:
        metrics = await dashboard_service.get_service_metrics(service_name)
        
        if not metrics:
            raise HTTPException(status_code=404, detail=f"Metrics for service '{service_name}' not found")
        
        return StandardResponse(
            status="success",
            data=metrics,
            message=f"Metrics for service '{service_name}'",
            broker=dashboard_service.broker
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get service metrics: {str(e)}")

@router.get("/{service_name}/health", response_model=StandardResponse[Dict[str, Any]])
async def get_service_health(
    service_name: str,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get health check details for a specific service"""
    try:
        health = await dashboard_service.get_service_health(service_name)
        
        if not health:
            raise HTTPException(status_code=404, detail=f"Health data for service '{service_name}' not found")
        
        return StandardResponse(
            status="success",
            data=health,
            message=f"Health check for service '{service_name}'",
            broker=dashboard_service.broker
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get service health: {str(e)}")

@router.post("/{service_name}/restart")
async def restart_service(
    service_name: str,
    background_tasks: BackgroundTasks,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Restart a specific service (admin only)"""
    try:
        # Add background task for service restart
        background_tasks.add_task(
            dashboard_service.restart_service,
            service_name,
            user_id=current_user.user_id
        )
        
        return StandardResponse(
            status="success",
            data={"service_name": service_name, "action": "restart_initiated"},
            message=f"Restart initiated for service '{service_name}'",
            broker=dashboard_service.broker
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart service: {str(e)}")

@router.get("/{service_name}/logs", response_model=StandardResponse[List[Dict[str, Any]]])
async def get_service_logs(
    service_name: str,
    lines: int = 100,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get recent logs for a specific service"""
    try:
        logs = await dashboard_service.get_service_logs(service_name, lines=lines)
        
        return StandardResponse(
            status="success",
            data=logs,
            message=f"Recent logs for service '{service_name}'",
            broker=dashboard_service.broker
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get service logs: {str(e)}")

@router.get("/{service_name}/status/history")
async def get_service_status_history(
    service_name: str,
    hours: int = 24,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user)
):
    """Get service status history"""
    try:
        # This would integrate with actual status history storage
        # For now, return simulated data
        history_data = {
            "service_name": service_name,
            "time_range_hours": hours,
            "status_changes": [
                {
                    "timestamp": "2024-01-01T10:00:00Z",
                    "from_status": "stopped",
                    "to_status": "running",
                    "reason": "Manual restart"
                },
                {
                    "timestamp": "2024-01-01T09:45:00Z", 
                    "from_status": "running",
                    "to_status": "stopped",
                    "reason": "Health check failure"
                }
            ],
            "uptime_percentage": 95.2,
            "total_downtimes": 2
        }
        
        return StandardResponse(
            status="success",
            data=history_data,
            message=f"Status history for service '{service_name}'",
            broker=dashboard_service.broker
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get service status history: {str(e)}")