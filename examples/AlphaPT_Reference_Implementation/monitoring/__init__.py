"""Observability and monitoring for AlphaPT."""

from monitoring.alert_manager import AlertManager
from monitoring.health_checker import HealthChecker
from monitoring.metrics_collector import MetricsCollector
from monitoring.performance_monitor import PerformanceMonitor

# Global instances for API access
# These will be initialized by the application
health_checker: HealthChecker = None
metrics_collector: MetricsCollector = None

__all__ = [
    "MetricsCollector",
    "HealthChecker",
    "AlertManager",
    "PerformanceMonitor",
    "health_checker",
    "metrics_collector",
]
