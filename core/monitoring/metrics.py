"""
Comprehensive service metrics collection and monitoring system.

This module provides metrics collection for service health monitoring,
performance tracking, and operational observability.
"""

from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
import asyncio
import json
import time
import statistics
from dataclasses import dataclass, field
from enum import Enum
import redis.asyncio as redis
from core.logging import get_monitoring_logger_safe

logger = get_monitoring_logger_safe("monitoring.metrics")


class MetricType(Enum):
    """Types of metrics that can be collected"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class MetricValue:
    """Individual metric value with metadata"""
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags
        }


class MetricsCollector:
    """Collect and manage metrics for a service"""
    
    def __init__(self, service_name: str, redis_client: Optional[redis.Redis] = None):
        self.service_name = service_name
        self.redis_client = redis_client
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, MetricValue] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._timers: Dict[str, List[float]] = {}
        self._start_time = datetime.utcnow()
        self._last_reset = datetime.utcnow()
        
        # Performance tracking
        self._performance_metrics = {
            "messages_processed": 0,
            "messages_per_second": 0.0,
            "average_processing_time_ms": 0.0,
            "error_rate": 0.0,
            "last_message_timestamp": None
        }
    
    def increment_counter(self, metric_name: str, value: float = 1.0, tags: Dict[str, str] = None) -> None:
        """Increment a counter metric"""
        key = self._make_metric_key(metric_name, tags)
        self._counters[key] = self._counters.get(key, 0.0) + value
        
        # Persist to Redis if available
        if self.redis_client:
            asyncio.create_task(self._persist_counter(key, self._counters[key]))
        
        logger.debug(f"Incremented counter {key}: {self._counters[key]}")
    
    def set_gauge(self, metric_name: str, value: float, tags: Dict[str, str] = None) -> None:
        """Set a gauge metric value"""
        key = self._make_metric_key(metric_name, tags)
        self._gauges[key] = MetricValue(
            value=value,
            timestamp=datetime.utcnow(),
            tags=tags or {}
        )
        
        # Persist to Redis if available
        if self.redis_client:
            asyncio.create_task(self._persist_gauge(key, self._gauges[key]))
        
        logger.debug(f"Set gauge {key}: {value}")
    
    def record_histogram(self, metric_name: str, value: float, tags: Dict[str, str] = None) -> None:
        """Record a value in a histogram"""
        key = self._make_metric_key(metric_name, tags)
        if key not in self._histograms:
            self._histograms[key] = []
        
        self._histograms[key].append(value)
        
        # Keep only last 1000 values to prevent memory issues
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]
        
        logger.debug(f"Recorded histogram {key}: {value}")
    
    def record_timer(self, metric_name: str, duration_ms: float, tags: Dict[str, str] = None) -> None:
        """Record a timing measurement"""
        key = self._make_metric_key(metric_name, tags)
        if key not in self._timers:
            self._timers[key] = []
        
        self._timers[key].append(duration_ms)
        
        # Keep only last 1000 measurements
        if len(self._timers[key]) > 1000:
            self._timers[key] = self._timers[key][-1000:]
        
        # Update performance metrics
        self._update_performance_metrics(duration_ms)
        
        logger.debug(f"Recorded timer {key}: {duration_ms}ms")
    
    def time_operation(self, metric_name: str, tags: Dict[str, str] = None):
        """Context manager for timing operations"""
        return TimerContext(self, metric_name, tags)
    
    def _make_metric_key(self, metric_name: str, tags: Dict[str, str] = None) -> str:
        """Create unique metric key with tags"""
        if not tags:
            return metric_name
        
        tag_string = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{metric_name}[{tag_string}]"
    
    def _update_performance_metrics(self, processing_time_ms: float) -> None:
        """Update overall performance metrics"""
        self._performance_metrics["messages_processed"] += 1
        self._performance_metrics["last_message_timestamp"] = datetime.utcnow()
        
        # Calculate messages per second
        elapsed_seconds = (datetime.utcnow() - self._start_time).total_seconds()
        if elapsed_seconds > 0:
            self._performance_metrics["messages_per_second"] = (
                self._performance_metrics["messages_processed"] / elapsed_seconds
            )
        
        # Update average processing time
        current_avg = self._performance_metrics["average_processing_time_ms"]
        message_count = self._performance_metrics["messages_processed"]
        self._performance_metrics["average_processing_time_ms"] = (
            (current_avg * (message_count - 1) + processing_time_ms) / message_count
        )
    
    async def _persist_counter(self, key: str, value: float) -> None:
        """Persist counter to Redis"""
        try:
            redis_key = f"metrics:{self.service_name}:counter:{key}"
            await self.redis_client.set(redis_key, value)
        except Exception as e:
            logger.error(f"Failed to persist counter {key}: {e}")
    
    async def _persist_gauge(self, key: str, metric_value: MetricValue) -> None:
        """Persist gauge to Redis"""
        try:
            redis_key = f"metrics:{self.service_name}:gauge:{key}"
            await self.redis_client.set(redis_key, json.dumps(metric_value.to_dict()))
        except Exception as e:
            logger.error(f"Failed to persist gauge {key}: {e}")
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        now = datetime.utcnow()
        uptime_seconds = (now - self._start_time).total_seconds()
        
        # Calculate histogram statistics
        histogram_stats = {}
        for key, values in self._histograms.items():
            if values:
                histogram_stats[key] = {
                    "count": len(values),
                    "min": min(values),
                    "max": max(values),
                    "mean": statistics.mean(values),
                    "median": statistics.median(values),
                    "p95": self._percentile(values, 95),
                    "p99": self._percentile(values, 99)
                }
        
        # Calculate timer statistics
        timer_stats = {}
        for key, values in self._timers.items():
            if values:
                timer_stats[key] = {
                    "count": len(values),
                    "min_ms": min(values),
                    "max_ms": max(values),
                    "mean_ms": statistics.mean(values),
                    "median_ms": statistics.median(values),
                    "p95_ms": self._percentile(values, 95),
                    "p99_ms": self._percentile(values, 99)
                }
        
        return {
            "service": self.service_name,
            "timestamp": now.isoformat(),
            "uptime_seconds": uptime_seconds,
            "performance": self._performance_metrics.copy(),
            "counters": self._counters.copy(),
            "gauges": {k: v.to_dict() for k, v in self._gauges.items()},
            "histograms": histogram_stats,
            "timers": timer_stats,
            "metadata": {
                "start_time": self._start_time.isoformat(),
                "last_reset": self._last_reset.isoformat()
            }
        }
    
    def _percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile of values"""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        index = int((percentile / 100.0) * len(sorted_values))
        if index >= len(sorted_values):
            index = len(sorted_values) - 1
        return sorted_values[index]
    
    def reset_metrics(self) -> None:
        """Reset all metrics"""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._timers.clear()
        self._last_reset = datetime.utcnow()
        
        # Reset performance metrics but keep start time
        self._performance_metrics = {
            "messages_processed": 0,
            "messages_per_second": 0.0,
            "average_processing_time_ms": 0.0,
            "error_rate": 0.0,
            "last_message_timestamp": None
        }
        
        logger.info(f"Reset metrics for {self.service_name}")


class TimerContext:
    """Context manager for timing operations"""
    
    def __init__(self, collector: MetricsCollector, metric_name: str, tags: Dict[str, str] = None):
        self.collector = collector
        self.metric_name = metric_name
        self.tags = tags
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            self.collector.record_timer(self.metric_name, duration_ms, self.tags)


class ServiceHealthMonitor:
    """Monitor service health and generate alerts"""
    
    def __init__(self, service_name: str, metrics_collector: MetricsCollector):
        self.service_name = service_name
        self.metrics_collector = metrics_collector
        self._health_checks: List[Callable[[], bool]] = []
        self._alert_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        self._thresholds = {
            "max_error_rate": 0.05,  # 5%
            "max_processing_time_ms": 5000,  # 5 seconds
            "min_messages_per_second": 0.1,  # At least some activity
            "max_memory_usage_mb": 1000  # 1GB
        }
    
    def add_health_check(self, check_func: Callable[[], bool]) -> None:
        """Add custom health check function"""
        self._health_checks.append(check_func)
    
    def add_alert_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Add alert callback function"""
        self._alert_callbacks.append(callback)
    
    def set_threshold(self, metric_name: str, threshold_value: float) -> None:
        """Set alert threshold for metric"""
        self._thresholds[metric_name] = threshold_value
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        health_status = {
            "service": self.service_name,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "healthy",
            "checks": {},
            "alerts": []
        }
        
        # Get current metrics
        metrics = self.metrics_collector.get_metrics_summary()
        
        # Check error rate
        error_rate = metrics["performance"]["error_rate"]
        health_status["checks"]["error_rate"] = {
            "status": "ok" if error_rate <= self._thresholds["max_error_rate"] else "critical",
            "value": error_rate,
            "threshold": self._thresholds["max_error_rate"]
        }
        
        if error_rate > self._thresholds["max_error_rate"]:
            alert = {
                "type": "high_error_rate",
                "severity": "critical",
                "message": f"Error rate {error_rate:.2%} exceeds threshold {self._thresholds['max_error_rate']:.2%}"
            }
            health_status["alerts"].append(alert)
            await self._trigger_alert("high_error_rate", alert)
        
        # Check processing time
        avg_processing_time = metrics["performance"]["average_processing_time_ms"]
        health_status["checks"]["processing_time"] = {
            "status": "ok" if avg_processing_time <= self._thresholds["max_processing_time_ms"] else "warning",
            "value": avg_processing_time,
            "threshold": self._thresholds["max_processing_time_ms"]
        }
        
        if avg_processing_time > self._thresholds["max_processing_time_ms"]:
            alert = {
                "type": "slow_processing",
                "severity": "warning",
                "message": f"Average processing time {avg_processing_time:.1f}ms exceeds threshold {self._thresholds['max_processing_time_ms']}ms"
            }
            health_status["alerts"].append(alert)
            await self._trigger_alert("slow_processing", alert)
        
        # Check message throughput
        messages_per_second = metrics["performance"]["messages_per_second"]
        health_status["checks"]["throughput"] = {
            "status": "ok" if messages_per_second >= self._thresholds["min_messages_per_second"] else "warning",
            "value": messages_per_second,
            "threshold": self._thresholds["min_messages_per_second"]
        }
        
        # Run custom health checks
        for i, check_func in enumerate(self._health_checks):
            try:
                result = check_func()
                health_status["checks"][f"custom_check_{i}"] = {
                    "status": "ok" if result else "error",
                    "result": result
                }
            except Exception as e:
                health_status["checks"][f"custom_check_{i}"] = {
                    "status": "error",
                    "error": str(e)
                }
        
        # Determine overall status
        if any(alert["severity"] == "critical" for alert in health_status["alerts"]):
            health_status["status"] = "critical"
        elif any(alert["severity"] == "warning" for alert in health_status["alerts"]):
            health_status["status"] = "degraded"
        elif any(check["status"] == "error" for check in health_status["checks"].values()):
            health_status["status"] = "error"
        
        return health_status
    
    async def _trigger_alert(self, alert_type: str, alert_data: Dict[str, Any]) -> None:
        """Trigger alert callbacks"""
        for callback in self._alert_callbacks:
            try:
                callback(alert_type, alert_data)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")


class MetricsAggregator:
    """Aggregate metrics across multiple services"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self._service_collectors: Dict[str, MetricsCollector] = {}
    
    def register_service(self, service_name: str, collector: MetricsCollector) -> None:
        """Register service metrics collector"""
        self._service_collectors[service_name] = collector
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics across all services"""
        system_metrics = {
            "timestamp": datetime.utcnow().isoformat(),
            "services": {},
            "system_totals": {
                "total_messages_processed": 0,
                "total_errors": 0,
                "average_processing_time_ms": 0.0,
                "services_count": len(self._service_collectors)
            }
        }
        
        processing_times = []
        
        for service_name, collector in self._service_collectors.items():
            service_metrics = collector.get_metrics_summary()
            system_metrics["services"][service_name] = service_metrics
            
            # Aggregate totals
            perf = service_metrics["performance"]
            system_metrics["system_totals"]["total_messages_processed"] += perf["messages_processed"]
            
            if perf["average_processing_time_ms"] > 0:
                processing_times.append(perf["average_processing_time_ms"])
        
        # Calculate system averages
        if processing_times:
            system_metrics["system_totals"]["average_processing_time_ms"] = statistics.mean(processing_times)
        
        return system_metrics
    
    async def get_service_health_summary(self) -> Dict[str, Any]:
        """Get health summary for all services"""
        health_summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_status": "healthy",
            "services": {},
            "system_alerts": []
        }
        
        for service_name, collector in self._service_collectors.items():
            monitor = ServiceHealthMonitor(service_name, collector)
            service_health = await monitor.health_check()
            health_summary["services"][service_name] = service_health
            
            # Aggregate system-level alerts
            if service_health["status"] in ["critical", "error"]:
                health_summary["overall_status"] = "critical"
            elif service_health["status"] == "degraded" and health_summary["overall_status"] == "healthy":
                health_summary["overall_status"] = "degraded"
            
            # Add service alerts to system alerts
            for alert in service_health["alerts"]:
                alert["service"] = service_name
                health_summary["system_alerts"].append(alert)
        
        return health_summary"
