"""Performance profiling and monitoring module."""

import asyncio
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import psutil

from core.config.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Performance metric data structure."""

    name: str
    value: float
    timestamp: datetime
    category: str
    unit: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


class PerformanceProfiler:
    """Performance profiler for monitoring system performance."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._counters: Dict[str, int] = defaultdict(int)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()

        # Performance thresholds
        self.thresholds = {
            "cpu_usage": 80.0,  # %
            "memory_usage": 85.0,  # %
            "market_data_latency": 50.0,  # ms
            "order_latency": 100.0,  # ms
            "event_queue_size": 10000,  # messages
            "database_connections": 80,  # % of pool
        }

    async def start(self) -> None:
        """Start performance monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Performance profiler started")

    async def stop(self) -> None:
        """Stop performance monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Performance profiler stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._collect_system_metrics()
                await asyncio.sleep(5)  # Collect metrics every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in performance monitor loop: {e}")
                await asyncio.sleep(1)

    async def _collect_system_metrics(self) -> None:
        """Collect system performance metrics."""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=None)
            self.record_metric("cpu_usage", cpu_percent, "system", "percent")

            # Memory metrics
            memory = psutil.virtual_memory()
            self.record_metric("memory_usage", memory.percent, "system", "percent")
            self.record_metric("memory_available", memory.available / (1024**3), "system", "GB")

            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if disk_io:
                self.record_metric("disk_read_bytes", disk_io.read_bytes, "system", "bytes")
                self.record_metric("disk_write_bytes", disk_io.write_bytes, "system", "bytes")

            # Network I/O
            net_io = psutil.net_io_counters()
            if net_io:
                self.record_metric("network_bytes_sent", net_io.bytes_sent, "system", "bytes")
                self.record_metric("network_bytes_recv", net_io.bytes_recv, "system", "bytes")

            # Process-specific metrics
            process = psutil.Process()
            self.record_metric("process_cpu", process.cpu_percent(), "process", "percent")
            self.record_metric("process_memory", process.memory_info().rss / (1024**2), "process", "MB")
            self.record_metric("process_threads", process.num_threads(), "process", "count")

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")

    def record_metric(
        self, name: str, value: float, category: str, unit: str = "", tags: Optional[Dict[str, str]] = None
    ) -> None:
        """Record a performance metric."""
        with self._lock:
            metric = PerformanceMetric(
                name=name, value=value, timestamp=datetime.now(), category=category, unit=unit, tags=tags or {}
            )
            self._metrics[name].append(metric)

            # Check thresholds
            if name in self.thresholds and value > self.thresholds[name]:
                logger.warning(f"Performance threshold exceeded: {name}={value}{unit} > {self.thresholds[name]}{unit}")

    def increment_counter(self, name: str, value: int = 1) -> None:
        """Increment a counter metric."""
        with self._lock:
            self._counters[name] += value

    def record_timing(self, name: str, duration: float) -> None:
        """Record a timing metric."""
        with self._lock:
            self._timers[name].append(duration)
            # Keep only last 1000 timings
            if len(self._timers[name]) > 1000:
                self._timers[name] = self._timers[name][-1000:]

    def get_metric_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a metric."""
        with self._lock:
            if name not in self._metrics or not self._metrics[name]:
                return None

            values = [m.value for m in self._metrics[name]]
            return {
                "current": values[-1] if values else None,
                "average": sum(values) / len(values) if values else 0,
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
                "count": len(values),
                "last_updated": self._metrics[name][-1].timestamp if self._metrics[name] else None,
            }

    def get_timing_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """Get timing statistics."""
        with self._lock:
            if name not in self._timers or not self._timers[name]:
                return None

            timings = self._timers[name]
            timings.sort()
            count = len(timings)

            return {
                "count": count,
                "average": sum(timings) / count,
                "min": timings[0],
                "max": timings[-1],
                "p50": timings[count // 2],
                "p95": timings[int(count * 0.95)],
                "p99": timings[int(count * 0.99)],
            }

    def get_counter_value(self, name: str) -> int:
        """Get counter value."""
        with self._lock:
            return self._counters.get(name, 0)

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get overall performance summary."""
        with self._lock:
            summary = {
                "timestamp": datetime.now(),
                "system": {},
                "counters": dict(self._counters),
                "timings": {},
                "alerts": [],
            }

            # System metrics
            for metric_name in ["cpu_usage", "memory_usage", "process_cpu", "process_memory"]:
                stats = self.get_metric_stats(metric_name)
                if stats:
                    summary["system"][metric_name] = stats

            # Timing metrics
            for timer_name in self._timers:
                stats = self.get_timing_stats(timer_name)
                if stats:
                    summary["timings"][timer_name] = stats

            # Performance alerts
            for metric_name, threshold in self.thresholds.items():
                stats = self.get_metric_stats(metric_name)
                if stats and stats["current"] and stats["current"] > threshold:
                    summary["alerts"].append(
                        {
                            "metric": metric_name,
                            "current": stats["current"],
                            "threshold": threshold,
                            "severity": "warning" if stats["current"] < threshold * 1.2 else "critical",
                        }
                    )

            return summary

    def reset_metrics(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._timers.clear()
        logger.info("Performance metrics reset")


# Context manager for timing operations
class TimingContext:
    """Context manager for timing operations."""

    def __init__(self, profiler: PerformanceProfiler, operation_name: str):
        self.profiler = profiler
        self.operation_name = operation_name
        self.start_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = (time.perf_counter() - self.start_time) * 1000  # Convert to milliseconds
            self.profiler.record_timing(self.operation_name, duration)


# Global profiler instance
_profiler: Optional[PerformanceProfiler] = None


def get_performance_profiler(settings: Optional[Settings] = None) -> PerformanceProfiler:
    """Get the global performance profiler instance."""
    global _profiler
    if _profiler is None:
        if settings is None:
            from core.config.settings import settings as default_settings

            settings = default_settings
        _profiler = PerformanceProfiler(settings)
    return _profiler


async def initialize_performance_profiler(settings: Optional[Settings] = None) -> PerformanceProfiler:
    """Initialize the performance profiler."""
    profiler = get_performance_profiler(settings)
    await profiler.start()
    return profiler


async def close_performance_profiler() -> None:
    """Close the performance profiler."""
    global _profiler
    if _profiler:
        await _profiler.stop()
        _profiler = None


# Decorator for timing functions
def profile_performance(operation_name: str):
    """Decorator to profile function performance."""

    def decorator(func):
        if asyncio.iscoroutinefunction(func):

            async def async_wrapper(*args, **kwargs):
                profiler = get_performance_profiler()
                with TimingContext(profiler, operation_name):
                    return await func(*args, **kwargs)

            return async_wrapper
        else:

            def sync_wrapper(*args, **kwargs):
                profiler = get_performance_profiler()
                with TimingContext(profiler, operation_name):
                    return func(*args, **kwargs)

            return sync_wrapper

    return decorator
