import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and tracks metrics for streaming service reliability."""
    
    def __init__(self, service_name: str, window_size: int = 100):
        self.service_name = service_name
        self.window_size = window_size
        
        # Counters
        self._success_count = 0
        self._failure_count = 0
        self._total_messages = 0
        
        # Timing metrics - keep recent durations for percentile calculations
        self._processing_durations = deque(maxlen=window_size)
        self._total_processing_time = 0.0
        
        # Error tracking
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._last_error_time: Optional[datetime] = None
        
        # Throughput tracking
        self._message_timestamps = deque(maxlen=window_size)
        
        # Service health
        self._health_status = "healthy"
        self._last_health_check = datetime.now(timezone.utc)
        
        # Session metrics
        self._session_start_time = datetime.now(timezone.utc)
    
    async def record_success(self, processing_duration: float, broker_context: str = None) -> None:
        """Record a successful message processing with optional broker context."""
        self._success_count += 1
        self._total_messages += 1
        self._total_processing_time += processing_duration
        self._processing_durations.append(processing_duration)
        self._message_timestamps.append(time.time())
        
        # Log broker-specific success if context available
        if broker_context:
            logger.debug(f"Success recorded for {broker_context}", 
                        duration_ms=processing_duration * 1000)
        
        # Update health status
        self._update_health_status()
    
    async def record_failure(self, error_type: str, broker_context: str = None) -> None:
        """Record a failed message processing with optional broker context."""
        self._failure_count += 1
        self._total_messages += 1
        error_key = f"{broker_context}:{error_type}" if broker_context else error_type
        self._error_counts[error_key] += 1
        self._last_error_time = datetime.now(timezone.utc)
        self._message_timestamps.append(time.time())
        
        # Log broker-specific failure if context available
        if broker_context:
            logger.warning(f"Failure recorded for {broker_context}: {error_type}")
        
        # Update health status
        self._update_health_status()
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary."""
        now = datetime.now(timezone.utc)
        uptime_seconds = (now - self._session_start_time).total_seconds()
        
        # Calculate percentiles for processing duration
        durations = list(self._processing_durations)
        duration_percentiles = self._calculate_percentiles(durations) if durations else {}
        
        # Calculate throughput (messages per second in last window)
        throughput = self._calculate_throughput()
        
        # Calculate success rate
        success_rate = (self._success_count / self._total_messages * 100) if self._total_messages > 0 else 0
        
        # Calculate average processing time
        avg_processing_time = (
            self._total_processing_time / self._success_count 
            if self._success_count > 0 else 0
        )
        
        return {
            "service_name": self.service_name,
            "timestamp": now.isoformat(),
            "uptime_seconds": uptime_seconds,
            "health_status": self._health_status,
            "counters": {
                "total_messages": self._total_messages,
                "successful_messages": self._success_count,
                "failed_messages": self._failure_count,
                "success_rate_percent": round(success_rate, 2)
            },
            "timing": {
                "average_processing_ms": round(avg_processing_time * 1000, 2),
                "percentiles_ms": {
                    k: round(v * 1000, 2) for k, v in duration_percentiles.items()
                }
            },
            "throughput": {
                "messages_per_second": round(throughput, 2),
                "window_size": len(self._message_timestamps)
            },
            "errors": dict(self._error_counts),
            "last_error": self._last_error_time.isoformat() if self._last_error_time else None
        }
    
    def get_health_status(self) -> str:
        """Get current health status."""
        self._update_health_status()
        return self._health_status
    
    def _calculate_percentiles(self, values: list) -> Dict[str, float]:
        """Calculate percentiles for a list of values."""
        if not values:
            return {}
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        
        def percentile(p: int) -> float:
            index = int((p / 100.0) * n)
            if index >= n:
                index = n - 1
            return sorted_values[index]
        
        return {
            "p50": percentile(50),
            "p90": percentile(90),
            "p95": percentile(95),
            "p99": percentile(99)
        }
    
    def _calculate_throughput(self) -> float:
        """Calculate messages per second in the current window."""
        if len(self._message_timestamps) < 2:
            return 0.0
        
        now = time.time()
        # Count messages in the last 60 seconds
        recent_timestamps = [ts for ts in self._message_timestamps if now - ts <= 60]
        
        if len(recent_timestamps) < 2:
            return 0.0
        
        time_span = recent_timestamps[-1] - recent_timestamps[0]
        return len(recent_timestamps) / time_span if time_span > 0 else 0.0
    
    def _update_health_status(self) -> None:
        """Update health status based on recent metrics."""
        if self._total_messages == 0:
            self._health_status = "starting"
            return
        
        # Calculate recent error rate (last 50 messages)
        recent_window = min(50, self._total_messages)
        recent_failures = min(self._failure_count, recent_window)
        recent_error_rate = recent_failures / recent_window
        
        # Health thresholds
        if recent_error_rate > 0.5:  # >50% error rate
            self._health_status = "critical"
        elif recent_error_rate > 0.1:  # >10% error rate
            self._health_status = "degraded" 
        elif recent_error_rate > 0.05:  # >5% error rate
            self._health_status = "warning"
        else:
            self._health_status = "healthy"
        
        self._last_health_check = datetime.now(timezone.utc)
    
    def reset_metrics(self) -> None:
        """Reset all metrics (useful for testing)."""
        self._success_count = 0
        self._failure_count = 0
        self._total_messages = 0
        self._processing_durations.clear()
        self._total_processing_time = 0.0
        self._error_counts.clear()
        self._last_error_time = None
        self._message_timestamps.clear()
        self._health_status = "healthy"
        self._session_start_time = datetime.now(timezone.utc)