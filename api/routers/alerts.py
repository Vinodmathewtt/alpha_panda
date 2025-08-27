from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import uuid

from api.dependencies import get_current_user, get_pagination_params
from api.schemas.responses import StandardResponse, PaginatedResponse, Alert, AlertSummary

router = APIRouter(prefix="/alerts", tags=["Alerts"])

# Simulated alert manager (in production this would be injected)
class MockAlertManager:
    def __init__(self):
        self.alerts = self._generate_mock_alerts()
    
    def _generate_mock_alerts(self) -> List[Dict[str, Any]]:
        """Generate mock alerts for demonstration"""
        return [
            {
                "id": str(uuid.uuid4()),
                "title": "High Memory Usage",
                "message": "Trading Engine Service memory usage above 90%",
                "severity": "warning",
                "category": "performance",
                "component": "trading_engine_service",
                "status": "active",
                "created_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                "acknowledged_at": None,
                "resolved_at": None,
                "details": {"memory_usage": "92%", "threshold": "90%"}
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Connection Timeout",
                "message": "Market data feed connection timeout",
                "severity": "critical",
                "category": "connectivity", 
                "component": "market_feed_service",
                "status": "acknowledged",
                "created_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
                "acknowledged_at": (datetime.utcnow() - timedelta(minutes=30)).isoformat(),
                "resolved_at": None,
                "details": {"timeout_duration": "30s", "retry_count": 3}
            },
            {
                "id": str(uuid.uuid4()),
                "title": "Pipeline Delay",
                "message": "Order processing pipeline experiencing delays",
                "severity": "warning",
                "category": "trading",
                "component": "order_processing_pipeline",
                "status": "resolved",
                "created_at": (datetime.utcnow() - timedelta(hours=4)).isoformat(),
                "acknowledged_at": (datetime.utcnow() - timedelta(hours=3, minutes=45)).isoformat(),
                "resolved_at": (datetime.utcnow() - timedelta(hours=3)).isoformat(),
                "details": {"avg_delay": "15s", "expected": "2s"}
            }
        ]
    
    async def get_alerts(self, status=None, severity=None, category=None, offset=0, limit=50):
        """Get filtered alerts"""
        filtered_alerts = []
        
        for alert in self.alerts:
            if status and alert["status"] != status:
                continue
            if severity and alert["severity"] != severity:
                continue
            if category and alert["category"] != category:
                continue
            filtered_alerts.append(Alert(**alert))
        
        return filtered_alerts[offset:offset + limit]
    
    async def count_alerts(self, status=None, severity=None, category=None):
        """Count filtered alerts"""
        count = 0
        for alert in self.alerts:
            if status and alert["status"] != status:
                continue
            if severity and alert["severity"] != severity:
                continue
            if category and alert["category"] != category:
                continue
            count += 1
        return count
    
    async def get_alert_summary(self):
        """Get alert summary statistics"""
        active_alerts = sum(1 for a in self.alerts if a["status"] == "active")
        critical_alerts = sum(1 for a in self.alerts if a["severity"] == "critical")
        acknowledged_alerts = sum(1 for a in self.alerts if a["status"] == "acknowledged")
        alerts_24h = len(self.alerts)  # All mock alerts are within 24h
        
        top_categories = {}
        for alert in self.alerts:
            category = alert["category"]
            top_categories[category] = top_categories.get(category, 0) + 1
        
        return AlertSummary(
            active_alerts=active_alerts,
            critical_alerts=critical_alerts,
            acknowledged_alerts=acknowledged_alerts,
            alerts_24h=alerts_24h,
            top_categories=top_categories
        )
    
    async def get_alert(self, alert_id: str):
        """Get specific alert"""
        for alert in self.alerts:
            if alert["id"] == alert_id:
                return Alert(**alert)
        return None
    
    async def acknowledge_alert(self, alert_id: str, user_id: str):
        """Acknowledge an alert"""
        for alert in self.alerts:
            if alert["id"] == alert_id:
                alert["status"] = "acknowledged"
                alert["acknowledged_at"] = datetime.utcnow().isoformat()
                return True
        return False
    
    async def resolve_alert(self, alert_id: str, user_id: str):
        """Resolve an alert"""
        for alert in self.alerts:
            if alert["id"] == alert_id:
                alert["status"] = "resolved" 
                alert["resolved_at"] = datetime.utcnow().isoformat()
                return True
        return False

# Mock alert manager instance
alert_manager = MockAlertManager()

@router.get("/", response_model=PaginatedResponse[Alert])
async def get_alerts(
    status: Optional[str] = Query(None, regex="^(active|acknowledged|resolved)$"),
    severity: Optional[str] = Query(None, regex="^(info|warning|error|critical)$"),
    category: Optional[str] = Query(None),
    pagination: dict = Depends(get_pagination_params),
    current_user = Depends(get_current_user)
):
    """Get paginated list of alerts with filtering"""
    try:
        alerts = await alert_manager.get_alerts(
            status=status,
            severity=severity,
            category=category,
            offset=pagination["offset"],
            limit=pagination["size"]
        )
        
        total = await alert_manager.count_alerts(
            status=status,
            severity=severity,
            category=category
        )
        
        return PaginatedResponse(
            items=alerts,
            total=total,
            page=pagination["page"],
            size=pagination["size"],
            pages=(total + pagination["size"] - 1) // pagination["size"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alerts: {str(e)}")

@router.get("/summary", response_model=StandardResponse[AlertSummary])
async def get_alert_summary(
    current_user = Depends(get_current_user)
):
    """Get alert summary statistics"""
    try:
        summary = await alert_manager.get_alert_summary()
        return StandardResponse(
            status="success",
            data=summary,
            message="Alert summary retrieved"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alert summary: {str(e)}")

@router.get("/{alert_id}", response_model=StandardResponse[Alert])
async def get_alert(
    alert_id: str,
    current_user = Depends(get_current_user)
):
    """Get specific alert details"""
    try:
        alert = await alert_manager.get_alert(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return StandardResponse(
            status="success",
            data=alert,
            message=f"Alert {alert_id} retrieved"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alert: {str(e)}")

@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    current_user = Depends(get_current_user)
):
    """Acknowledge an alert"""
    try:
        success = await alert_manager.acknowledge_alert(alert_id, current_user.user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return StandardResponse(
            status="success",
            data={"alert_id": alert_id, "acknowledged_by": current_user.user_id},
            message="Alert acknowledged successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to acknowledge alert: {str(e)}")

@router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    current_user = Depends(get_current_user)
):
    """Resolve an alert"""
    try:
        success = await alert_manager.resolve_alert(alert_id, current_user.user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return StandardResponse(
            status="success",
            data={"alert_id": alert_id, "resolved_by": current_user.user_id},
            message="Alert resolved successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resolve alert: {str(e)}")

@router.get("/categories/", response_model=StandardResponse[List[str]])
async def get_alert_categories():
    """Get available alert categories"""
    try:
        categories = ["performance", "connectivity", "trading", "system", "security"]
        return StandardResponse(
            status="success",
            data=categories,
            message="Alert categories retrieved"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alert categories: {str(e)}")

@router.get("/severities/", response_model=StandardResponse[List[str]])
async def get_alert_severities():
    """Get available alert severity levels"""
    try:
        severities = ["info", "warning", "error", "critical"]
        return StandardResponse(
            status="success",
            data=severities,
            message="Alert severities retrieved"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alert severities: {str(e)}")

@router.post("/test")
async def create_test_alert(
    current_user = Depends(get_current_user)
):
    """Create a test alert for development/testing"""
    try:
        test_alert = {
            "id": str(uuid.uuid4()),
            "title": "Test Alert",
            "message": f"Test alert created by {current_user.user_id}",
            "severity": "info",
            "category": "system",
            "component": "api_service",
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "acknowledged_at": None,
            "resolved_at": None,
            "details": {"test": True, "created_by": current_user.user_id}
        }
        
        alert_manager.alerts.insert(0, test_alert)
        
        return StandardResponse(
            status="success",
            data={"alert_id": test_alert["id"]},
            message="Test alert created successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create test alert: {str(e)}")