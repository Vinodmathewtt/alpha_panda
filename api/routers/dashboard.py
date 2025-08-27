from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any

from api.dependencies import get_dashboard_service, get_current_user_optional
from api.services.dashboard_service import DashboardService
from api.schemas.responses import StandardResponse, DashboardSummary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/summary", response_model=StandardResponse[Dict[str, Any]])
async def get_dashboard_summary(
    dashboard_service: DashboardService = Depends(get_dashboard_service),
    current_user = Depends(get_current_user_optional)
):
    """Get comprehensive dashboard summary"""
    try:
        # Get all dashboard data
        health_summary = await dashboard_service.get_health_summary()
        pipeline_summary = await dashboard_service.get_pipeline_summary()
        services_status = await dashboard_service.get_all_services_status()
        
        # Calculate service statistics
        active_services = sum(1 for s in services_status if s.status.value == "running")
        total_services = len(services_status)
        
        # Get recent activity (simplified)
        recent_activity = [
            {
                "id": "1",
                "timestamp": "2024-01-01T12:00:00Z",
                "type": "health_check",
                "service": "system",
                "message": "System health check completed",
                "severity": "info"
            }
        ]
        
        # Create alert summary (simplified)
        alert_summary = {
            "active_alerts": 2,
            "critical_alerts": 0,
            "acknowledged_alerts": 1,
            "alerts_24h": 5,
            "top_categories": {
                "performance": 2,
                "connectivity": 1,
                "trading": 2
            }
        }
        
        dashboard_data = {
            "system_health": health_summary,
            "pipeline_status": pipeline_summary,
            "active_services": active_services,
            "total_services": total_services,
            "recent_activity": recent_activity,
            "alert_summary": alert_summary,
            "user_context": {
                "user_id": current_user.user_id if current_user else None,
                "broker": dashboard_service.broker
            }
        }
        
        return StandardResponse(
            status="success",
            data=dashboard_data,
            message="Dashboard summary retrieved successfully",
            broker=dashboard_service.broker
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get dashboard summary: {str(e)}"
        )

@router.get("/health", response_model=StandardResponse[Dict[str, Any]])
async def get_health_overview(
    dashboard_service: DashboardService = Depends(get_dashboard_service)
):
    """Get detailed health overview for dashboard"""
    try:
        health_data = await dashboard_service.get_health_summary()
        
        return StandardResponse(
            status="success",
            data=health_data,
            message="Health overview retrieved successfully",
            broker=dashboard_service.broker
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get health overview: {str(e)}"
        )

@router.get("/pipeline", response_model=StandardResponse[Dict[str, Any]])
async def get_pipeline_overview(
    dashboard_service: DashboardService = Depends(get_dashboard_service)
):
    """Get detailed pipeline overview for dashboard"""
    try:
        pipeline_data = await dashboard_service.get_pipeline_summary()
        
        return StandardResponse(
            status="success", 
            data=pipeline_data,
            message="Pipeline overview retrieved successfully",
            broker=dashboard_service.broker
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get pipeline overview: {str(e)}"
        )

@router.get("/activity", response_model=StandardResponse[Dict[str, Any]])
async def get_recent_activity(
    limit: int = 20,
    dashboard_service: DashboardService = Depends(get_dashboard_service)
):
    """Get recent system activity for dashboard"""
    try:
        # Get activity from dashboard service
        activity_items = []
        count = 0
        
        async for activity in dashboard_service.stream_activity():
            activity_items.append(activity)
            count += 1
            if count >= limit:
                break
        
        return StandardResponse(
            status="success",
            data={
                "activities": activity_items,
                "total": len(activity_items),
                "limit": limit
            },
            message="Recent activity retrieved successfully",
            broker=dashboard_service.broker
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get recent activity: {str(e)}"
        )