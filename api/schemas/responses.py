from pydantic import BaseModel, Field
from typing import Generic, TypeVar, List, Optional, Any, Dict
from datetime import datetime
from enum import Enum

T = TypeVar('T')

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

class ServiceStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    STARTING = "starting"
    STOPPING = "stopping"

class StandardResponse(BaseModel, Generic[T]):
    """Standard API response wrapper"""
    status: str = Field(description="Response status")
    message: Optional[str] = Field(None, description="Response message")
    data: Optional[T] = Field(None, description="Response data")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    broker: Optional[str] = Field(None, description="Broker namespace")

class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper"""
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Health Check Responses
class ComponentHealth(BaseModel):
    name: str
    component: str
    status: HealthStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime
    duration_ms: Optional[float] = None
    error: Optional[str] = None

class SystemHealthResponse(BaseModel):
    status: HealthStatus
    timestamp: datetime
    broker_namespace: str
    checks: Dict[str, ComponentHealth]
    summary: Dict[str, int]

# Service Management Responses
class ServiceInfo(BaseModel):
    name: str
    status: ServiceStatus
    started_at: Optional[datetime] = None
    uptime_seconds: Optional[float] = None
    version: Optional[str] = None
    health: HealthStatus
    metrics: Optional[Dict[str, Any]] = None

class ServiceListResponse(BaseModel):
    services: List[ServiceInfo]
    summary: Dict[str, int]

# Pipeline Monitoring Responses
class PipelineStageStatus(BaseModel):
    stage_name: str
    status: HealthStatus
    last_activity: Optional[Dict[str, Any]] = None
    age_seconds: float
    total_count: int
    healthy: bool
    threshold_seconds: float
    message: Optional[str] = None

class PipelineStatusResponse(BaseModel):
    broker: str
    timestamp: datetime
    overall_healthy: bool
    stages: Dict[str, PipelineStageStatus]
    health_check_interval: float

# Log Management Responses
class LogEntry(BaseModel):
    timestamp: datetime
    level: str
    service: str
    message: str
    details: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None

class LogStatistics(BaseModel):
    total_entries: int
    by_level: Dict[str, int]
    by_service: Dict[str, int]
    recent_errors: int
    time_range: Dict[str, datetime]

# Alert Responses
class Alert(BaseModel):
    id: str
    title: str
    message: str
    severity: str
    category: str
    component: str
    status: str
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    details: Optional[Dict[str, Any]] = None

class AlertSummary(BaseModel):
    active_alerts: int
    critical_alerts: int
    acknowledged_alerts: int
    alerts_24h: int
    top_categories: Dict[str, int]

# Dashboard Specific Responses
class DashboardSummary(BaseModel):
    system_health: Dict[str, Any]
    pipeline_status: Dict[str, Any]
    active_services: int
    total_services: int
    recent_activity: List[Dict[str, Any]]
    alert_summary: AlertSummary

class ActivityItem(BaseModel):
    id: str
    timestamp: datetime
    type: str
    service: str
    message: str
    severity: str
    details: Optional[Dict[str, Any]] = None