"""
Comprehensive service health monitoring.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthMetric:
    name: str
    value: Any
    status: HealthStatus
    timestamp: datetime
    message: Optional[str] = None
    threshold: Optional[float] = None


class ServiceHealthMonitor:
    """Enhanced health monitoring for services"""
    
    def __init__(self, service_name: str, redis_client=None):
        self.service_name = service_name
        self.redis_client = redis_client
        self.metrics_history: List[HealthMetric] = []
        self.max_history = 100
        
    async def record_metric(
        self, 
        name: str, 
        value: Any, 
        status: HealthStatus = HealthStatus.HEALTHY,
        message: str = None,
        threshold: float = None
    ):
        """Record a health metric"""
        metric = HealthMetric(
            name=name,
            value=value,
            status=status,
            timestamp=datetime.utcnow(),
            message=message,
            threshold=threshold
        )
        
        # Store in local history
        self.metrics_history.append(metric)
        if len(self.metrics_history) > self.max_history:
            self.metrics_history.pop(0)
        
        # Store in Redis for centralized monitoring
        if self.redis_client:
            await self._store_metric_in_redis(metric)
    
    async def _store_metric_in_redis(self, metric: HealthMetric):
        """Store metric in Redis for dashboard access"""
        try:
            redis_key = f"health:{self.service_name}:{metric.name}"
            metric_data = {
                "value": metric.value,
                "status": metric.status.value,
                "timestamp": metric.timestamp.isoformat(),
                "message": metric.message,
                "threshold": metric.threshold
            }
            
            # Store current value with TTL
            await self.redis_client.setex(
                redis_key,
                300,  # 5 minutes TTL
                json.dumps(metric_data)
            )
            
            # Store in history list
            history_key = f"health_history:{self.service_name}:{metric.name}"
            await self.redis_client.lpush(history_key, json.dumps(metric_data))
            await self.redis_client.ltrim(history_key, 0, 99)  # Keep last 100
            await self.redis_client.expire(history_key, 3600)  # 1 hour TTL
            
        except Exception as e:
            # Don't fail service operations due to monitoring issues
            pass
    
    async def get_current_health(self) -> Dict[str, Any]:
        """Get current health status"""
        if not self.metrics_history:
            return {
                "service": self.service_name,
                "status": HealthStatus.UNKNOWN.value,
                "last_check": None,
                "metrics": {}
            }
        
        # Get latest metrics by name
        latest_metrics = {}
        for metric in reversed(self.metrics_history):
            if metric.name not in latest_metrics:
                latest_metrics[metric.name] = metric
        
        # Determine overall health
        overall_status = HealthStatus.HEALTHY
        for metric in latest_metrics.values():
            if metric.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break
            elif metric.status == HealthStatus.DEGRADED:
                overall_status = HealthStatus.DEGRADED
        
        return {
            "service": self.service_name,
            "status": overall_status.value,
            "last_check": max(m.timestamp for m in latest_metrics.values()).isoformat(),
            "metrics": {
                name: {
                    "value": metric.value,
                    "status": metric.status.value,
                    "message": metric.message,
                    "timestamp": metric.timestamp.isoformat()
                }
                for name, metric in latest_metrics.items()
            }
        }