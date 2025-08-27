"""Performance monitoring and optimization for AlphaPT."""

import asyncio
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import psutil

from core.utils.exceptions import AlphaPTException


@dataclass
class PerformanceMetric:
    """Performance metric data structure."""

    name: str
    value: float
    timestamp: datetime
    component: str
    unit: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class ComponentStats:
    """Component performance statistics."""

    component_name: str
    avg_latency_ms: float
    max_latency_ms: float
    min_latency_ms: float
    throughput_per_sec: float
    error_rate: float
    uptime_seconds: float
    memory_usage_mb: float
    cpu_usage_percent: float


class PerformanceMonitor:
    """Monitors and tracks system performance metrics."""

    def __init__(self, buffer_size: int = 1000):
        self.logger = logging.getLogger(__name__)
        self.buffer_size = buffer_size
        self.metrics_buffer: deque = deque(maxlen=buffer_size)
        self.component_metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=buffer_size))
        self.latency_trackers: Dict[str, Dict[str, float]] = {}
        self.throughput_counters: Dict[str, int] = defaultdict(int)
        self.error_counters: Dict[str, int] = defaultdict(int)
        self.component_start_times: Dict[str, datetime] = {}
        self.monitoring_active = False

    async def initialize(self) -> bool:
        """Initialize the performance monitor."""
        try:
            self.logger.info("📊 Initializing Performance Monitor")
            self.monitoring_active = True

            # Start background monitoring task
            asyncio.create_task(self._background_monitoring())

            self.logger.info("✅ Performance Monitor initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Performance Monitor: {e}")
            return False

    async def _background_monitoring(self):
        """Background task for continuous monitoring."""
        while self.monitoring_active:
            try:
                await self._collect_system_metrics()
                await asyncio.sleep(10)  # Collect system metrics every 10 seconds
            except Exception as e:
                self.logger.error(f"Error in background monitoring: {e}")
                await asyncio.sleep(5)

    async def _collect_system_metrics(self):
        """Collect system-level performance metrics."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.record_metric("system_cpu_usage", cpu_percent, "system", unit="%")

            # Memory usage
            memory = psutil.virtual_memory()
            self.record_metric("system_memory_usage", memory.percent, "system", unit="%")
            self.record_metric("system_memory_available", memory.available / (1024**3), "system", unit="GB")

            # Disk usage
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100
            self.record_metric("system_disk_usage", disk_percent, "system", unit="%")

            # Network I/O
            net_io = psutil.net_io_counters()
            self.record_metric("network_bytes_sent", net_io.bytes_sent, "system", unit="bytes")
            self.record_metric("network_bytes_recv", net_io.bytes_recv, "system", unit="bytes")

            # Process-specific metrics
            process = psutil.Process()
            process_memory = process.memory_info().rss / (1024**2)  # MB
            process_cpu = process.cpu_percent()

            self.record_metric("process_memory_usage", process_memory, "alphaPT", unit="MB")
            self.record_metric("process_cpu_usage", process_cpu, "alphaPT", unit="%")

        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")

    def record_metric(self, name: str, value: float, component: str, unit: str = "", tags: Dict[str, str] = None):
        """Record a performance metric."""
        metric = PerformanceMetric(
            name=name, value=value, timestamp=datetime.utcnow(), component=component, unit=unit, tags=tags or {}
        )

        self.metrics_buffer.append(metric)
        self.component_metrics[component].append(metric)

    def start_latency_tracking(self, operation: str, component: str) -> str:
        """Start tracking latency for an operation."""
        tracking_id = f"{component}_{operation}_{int(time.time() * 1000000)}"

        if component not in self.latency_trackers:
            self.latency_trackers[component] = {}

        self.latency_trackers[component][tracking_id] = time.time()
        return tracking_id

    def end_latency_tracking(self, tracking_id: str, component: str, operation: str):
        """End latency tracking and record the metric."""
        if component in self.latency_trackers and tracking_id in self.latency_trackers[component]:
            start_time = self.latency_trackers[component][tracking_id]
            latency_ms = (time.time() - start_time) * 1000

            self.record_metric(f"{operation}_latency", latency_ms, component, unit="ms", tags={"operation": operation})

            del self.latency_trackers[component][tracking_id]
            return latency_ms
        return None

    def record_throughput(self, component: str, count: int = 1):
        """Record throughput for a component."""
        self.throughput_counters[component] += count

    def record_error(self, component: str, error_type: str = "general"):
        """Record an error for a component."""
        self.error_counters[f"{component}_{error_type}"] += 1

    def mark_component_start(self, component: str):
        """Mark the start time of a component."""
        self.component_start_times[component] = datetime.utcnow()

    def get_component_stats(self, component: str, minutes: int = 30) -> Optional[ComponentStats]:
        """Get performance statistics for a component."""
        if component not in self.component_metrics:
            return None

        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        recent_metrics = [metric for metric in self.component_metrics[component] if metric.timestamp >= cutoff_time]

        if not recent_metrics:
            return None

        # Calculate latency statistics
        latency_metrics = [m for m in recent_metrics if "latency" in m.name]
        latencies = [m.value for m in latency_metrics] if latency_metrics else [0]

        avg_latency = statistics.mean(latencies) if latencies else 0
        max_latency = max(latencies) if latencies else 0
        min_latency = min(latencies) if latencies else 0

        # Calculate throughput (operations per second)
        throughput = self.throughput_counters.get(component, 0) / (minutes * 60)

        # Calculate error rate
        total_operations = self.throughput_counters.get(component, 1)
        total_errors = sum(count for key, count in self.error_counters.items() if key.startswith(component))
        error_rate = (total_errors / total_operations) * 100 if total_operations > 0 else 0

        # Calculate uptime
        start_time = self.component_start_times.get(component, datetime.utcnow())
        uptime_seconds = (datetime.utcnow() - start_time).total_seconds()

        # Get latest memory and CPU usage
        memory_metrics = [m for m in recent_metrics if "memory" in m.name]
        cpu_metrics = [m for m in recent_metrics if "cpu" in m.name]

        memory_usage = memory_metrics[-1].value if memory_metrics else 0
        cpu_usage = cpu_metrics[-1].value if cpu_metrics else 0

        return ComponentStats(
            component_name=component,
            avg_latency_ms=avg_latency,
            max_latency_ms=max_latency,
            min_latency_ms=min_latency,
            throughput_per_sec=throughput,
            error_rate=error_rate,
            uptime_seconds=uptime_seconds,
            memory_usage_mb=memory_usage,
            cpu_usage_percent=cpu_usage,
        )

    def get_system_overview(self) -> Dict[str, Any]:
        """Get overall system performance overview."""
        recent_metrics = [
            metric for metric in self.metrics_buffer if metric.timestamp >= datetime.utcnow() - timedelta(minutes=5)
        ]

        if not recent_metrics:
            return {}

        # Group metrics by name
        metric_groups = defaultdict(list)
        for metric in recent_metrics:
            metric_groups[metric.name].append(metric.value)

        overview = {}
        for metric_name, values in metric_groups.items():
            overview[metric_name] = {
                "current": values[-1] if values else 0,
                "average": statistics.mean(values) if values else 0,
                "max": max(values) if values else 0,
                "min": min(values) if values else 0,
            }

        return overview

    def get_performance_alerts(self) -> List[str]:
        """Get performance-related alerts."""
        alerts = []

        # Check for high CPU usage
        system_overview = self.get_system_overview()
        cpu_usage = system_overview.get("system_cpu_usage", {}).get("current", 0)
        if cpu_usage > 85:
            alerts.append(f"High CPU usage: {cpu_usage:.1f}%")

        # Check for high memory usage
        memory_usage = system_overview.get("system_memory_usage", {}).get("current", 0)
        if memory_usage > 90:
            alerts.append(f"High memory usage: {memory_usage:.1f}%")

        # Check for high disk usage
        disk_usage = system_overview.get("system_disk_usage", {}).get("current", 0)
        if disk_usage > 95:
            alerts.append(f"High disk usage: {disk_usage:.1f}%")

        return alerts

    def optimize_performance(self) -> Dict[str, str]:
        """Provide performance optimization recommendations."""
        recommendations = {}
        system_overview = self.get_system_overview()

        # CPU optimization recommendations
        cpu_usage = system_overview.get("system_cpu_usage", {}).get("current", 0)
        if cpu_usage > 80:
            recommendations["cpu"] = "Consider reducing concurrent operations or scaling to more CPU cores"

        # Memory optimization recommendations
        memory_usage = system_overview.get("system_memory_usage", {}).get("current", 0)
        if memory_usage > 85:
            recommendations["memory"] = "Consider increasing available memory or optimizing data structures"

        # Latency optimization recommendations
        avg_latencies = []
        for component_name in self.component_metrics.keys():
            stats = self.get_component_stats(component_name, minutes=10)
            if stats and stats.avg_latency_ms > 0:
                avg_latencies.append(stats.avg_latency_ms)

        if avg_latencies and statistics.mean(avg_latencies) > 500:
            recommendations["latency"] = (
                "High average latency detected. Consider optimizing database queries and async operations"
            )

        return recommendations

    def export_metrics(self, component: str = None, minutes: int = 60) -> List[Dict[str, Any]]:
        """Export metrics for external analysis."""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)

        if component:
            metrics = [
                metric for metric in self.component_metrics.get(component, []) if metric.timestamp >= cutoff_time
            ]
        else:
            metrics = [metric for metric in self.metrics_buffer if metric.timestamp >= cutoff_time]

        return [
            {
                "name": metric.name,
                "value": metric.value,
                "timestamp": metric.timestamp.isoformat(),
                "component": metric.component,
                "unit": metric.unit,
                "tags": metric.tags,
            }
            for metric in metrics
        ]

    async def cleanup_old_metrics(self):
        """Clean up old metrics from memory."""
        # The deque automatically handles size limits, but we can do additional cleanup here
        cutoff_time = datetime.utcnow() - timedelta(hours=24)

        # Clean up latency trackers that might be stuck
        for component in list(self.latency_trackers.keys()):
            for tracking_id in list(self.latency_trackers[component].keys()):
                # Remove trackers older than 1 hour (likely stuck)
                if time.time() - self.latency_trackers[component][tracking_id] > 3600:
                    del self.latency_trackers[component][tracking_id]

        self.logger.info("🧹 Cleaned up old performance metrics")

    async def shutdown(self):
        """Shutdown the performance monitor."""
        self.logger.info("🔄 Shutting down Performance Monitor")
        self.monitoring_active = False
        await self.cleanup_old_metrics()
        self.logger.info("✅ Performance Monitor shutdown complete")
