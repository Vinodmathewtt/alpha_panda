"""
Enhanced metrics collection system for Alpha Panda.
Collects and aggregates metrics from all services for monitoring and alerting.
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from core.logging import get_monitoring_logger_safe
import json
from dataclasses import dataclass, field
from collections import defaultdict, deque

from .alerting import get_alert_manager, AlertSeverity, AlertCategory

logger = get_monitoring_logger_safe("metrics_collector")


@dataclass
class MetricThreshold:
    """Metric threshold configuration"""
    
    metric_name: str
    warning_threshold: float
    critical_threshold: float
    comparison: str = "greater"  # "greater", "less", "equal"
    window_minutes: int = 5
    min_samples: int = 3


@dataclass
class ServiceMetrics:
    """Metrics for a single service"""
    
    service_name: str
    broker_namespace: str
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Core metrics
    messages_processed: int = 0
    messages_published: int = 0
    error_count: int = 0
    uptime_seconds: float = 0
    
    # Performance metrics
    avg_processing_time_ms: float = 0
    min_processing_time_ms: float = 0
    max_processing_time_ms: float = 0
    messages_per_second: float = 0
    error_rate_percent: float = 0
    
    # Topic and partition metrics
    topic_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    partition_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Health status
    is_running: bool = True
    last_message_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "service_name": self.service_name,
            "broker_namespace": self.broker_namespace,
            "last_updated": self.last_updated.isoformat(),
            "messages_processed": self.messages_processed,
            "messages_published": self.messages_published,
            "error_count": self.error_count,
            "uptime_seconds": self.uptime_seconds,
            "avg_processing_time_ms": self.avg_processing_time_ms,
            "min_processing_time_ms": self.min_processing_time_ms,
            "max_processing_time_ms": self.max_processing_time_ms,
            "messages_per_second": self.messages_per_second,
            "error_rate_percent": self.error_rate_percent,
            "topic_stats": self.topic_stats,
            "partition_stats": self.partition_stats,
            "is_running": self.is_running,
            "last_message_time": self.last_message_time
        }


class MetricsCollector:
    """Collects and aggregates metrics from all services"""
    
    def __init__(self, redis_client=None, settings=None):
        self.redis_client = redis_client
        self.settings = settings
        self.services: Dict[str, ServiceMetrics] = {}
        self.thresholds: List[MetricThreshold] = []
        
        # Metrics history for trending
        self.metrics_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Alert manager integration
        self.alert_manager = get_alert_manager()
        
        # Collection statistics
        self._stats = {
            "collections": 0,
            "last_collection_time": None,
            "alerts_triggered": 0,
            "services_monitored": 0
        }
        
        # Setup default thresholds
        self._setup_default_thresholds()
        
        # Collection task
        self._collection_task: Optional[asyncio.Task] = None
        self._running = False
    
    def _setup_default_thresholds(self):
        """Setup default metric thresholds"""
        default_thresholds = [
            MetricThreshold(
                metric_name="error_rate_percent",
                warning_threshold=5.0,
                critical_threshold=15.0,
                comparison="greater"
            ),
            MetricThreshold(
                metric_name="avg_processing_time_ms",
                warning_threshold=100.0,
                critical_threshold=500.0,
                comparison="greater"
            ),
            MetricThreshold(
                metric_name="messages_per_second",
                warning_threshold=1.0,
                critical_threshold=0.1,
                comparison="less"
            ),
            MetricThreshold(
                metric_name="uptime_seconds",
                warning_threshold=300.0,  # Service should be running for at least 5 minutes
                critical_threshold=60.0,
                comparison="less"
            )
        ]
        
        self.thresholds.extend(default_thresholds)
        logger.info(f"Setup {len(default_thresholds)} default metric thresholds")
    
    def add_threshold(self, threshold: MetricThreshold):
        """Add custom metric threshold"""
        self.thresholds.append(threshold)
        logger.info(f"Added metric threshold: {threshold.metric_name}")
    
    async def start_collection(self, interval_seconds: int = 60):
        """Start periodic metrics collection"""
        if self._running:
            logger.warning("Metrics collection already running")
            return
        
        self._running = True
        self._collection_task = asyncio.create_task(
            self._collection_loop(interval_seconds)
        )
        logger.info(f"Started metrics collection with {interval_seconds}s interval")
    
    async def stop_collection(self):
        """Stop periodic metrics collection"""
        self._running = False
        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
            self._collection_task = None
        logger.info("Stopped metrics collection")
    
    async def _collection_loop(self, interval_seconds: int):
        """Main metrics collection loop"""
        while self._running:
            try:
                await self.collect_all_metrics()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in metrics collection loop: {e}")
                await asyncio.sleep(interval_seconds)
    
    async def collect_all_metrics(self):
        """Collect metrics from all registered services"""
        collection_start = time.time()
        
        # In a real implementation, this would:
        # 1. Query all StreamProcessor instances for their metrics
        # 2. Collect metrics from Redis
        # 3. Query health check endpoints
        # 4. Aggregate system-level metrics
        
        # For now, simulate collecting metrics from known services
        service_names = [
            "market_feed",
            "strategy_runner",
            "risk_manager",
            "paper_trading",
            "zerodha_trading",
        ]
        
        for service_name in service_names:
            try:
                await self._collect_service_metrics(service_name)
            except Exception as e:
                logger.error(f"Failed to collect metrics for {service_name}: {e}")
        
        # Check thresholds and trigger alerts
        await self._check_thresholds()
        
        # Update collection statistics
        self._stats["collections"] += 1
        self._stats["last_collection_time"] = datetime.now(timezone.utc).isoformat()
        self._stats["services_monitored"] = len(self.services)
        
        collection_time = time.time() - collection_start
        logger.debug(f"Metrics collection completed in {collection_time:.2f}s")
    
    async def _collect_service_metrics(self, service_name: str):
        """Collect metrics for a specific service"""
        # In real implementation, this would call service.get_processing_stats()
        # For now, simulate or read from Redis
        
        if self.redis_client:
            # Try to get metrics from Redis cache
            metrics_key = f"alpha_panda:service_metrics:{service_name}"
            try:
                cached_metrics = await self.redis_client.get(metrics_key)
                if cached_metrics:
                    metrics_data = json.loads(cached_metrics.decode('utf-8'))
                    self._update_service_metrics(service_name, metrics_data)
                    return
            except Exception as e:
                logger.debug(f"Could not get cached metrics for {service_name}: {e}")
        
        # Fallback to default/simulated metrics
        self._create_default_service_metrics(service_name)
    
    def _update_service_metrics(self, service_name: str, metrics_data: Dict[str, Any]):
        """Update service metrics from collected data"""
        # Modernize: accept explicit broker/context keys, fallback to legacy key
        broker_namespace = (
            metrics_data.get("broker")
            or metrics_data.get("broker_context")
            or metrics_data.get("namespace")
            or metrics_data.get("broker_namespace")
            or "unknown"
        )
        
        if service_name not in self.services:
            self.services[service_name] = ServiceMetrics(
                service_name=service_name,
                broker_namespace=broker_namespace
            )
        
        service = self.services[service_name]
        
        # Update metrics from data
        service.messages_processed = metrics_data.get("messages_processed", 0)
        service.messages_published = metrics_data.get("messages_published", 0)
        service.error_count = metrics_data.get("error_count", 0)
        service.uptime_seconds = metrics_data.get("uptime_seconds", 0)
        service.avg_processing_time_ms = metrics_data.get("average_processing_time_ms", 0)
        service.min_processing_time_ms = metrics_data.get("min_processing_time_ms", 0)
        service.max_processing_time_ms = metrics_data.get("max_processing_time_ms", 0)
        service.messages_per_second = metrics_data.get("messages_per_second", 0)
        service.error_rate_percent = metrics_data.get("error_rate_percent", 0)
        service.is_running = metrics_data.get("is_running", False)
        service.last_message_time = metrics_data.get("last_message_time")
        service.topic_stats = metrics_data.get("topic_stats", {})
        service.partition_stats = metrics_data.get("partition_stats", {})
        service.last_updated = datetime.now(timezone.utc)
        
        # Add to history for trending
        self.metrics_history[service_name].append({
            "timestamp": service.last_updated.timestamp(),
            "metrics": service.to_dict()
        })
    
    def _create_default_service_metrics(self, service_name: str):
        """Create default/placeholder metrics for a service"""
        if service_name not in self.services:
            # Prefer explicit, sensible defaults; avoid deprecated settings.broker_namespace
            default_broker = 'shared' if service_name == 'market_feed' else 'unknown'
            self.services[service_name] = ServiceMetrics(
                service_name=service_name,
                broker_namespace=default_broker
            )
        
        # Mark as potentially offline
        service = self.services[service_name]
        service.is_running = False
        service.last_updated = datetime.now(timezone.utc)
    
    async def _check_thresholds(self):
        """Check all metrics against configured thresholds"""
        alerts_triggered = 0
        
        for service_name, service in self.services.items():
            for threshold in self.thresholds:
                try:
                    if await self._check_service_threshold(service, threshold):
                        alerts_triggered += 1
                except Exception as e:
                    logger.error(f"Error checking threshold {threshold.metric_name} for {service_name}: {e}")
        
        if alerts_triggered > 0:
            self._stats["alerts_triggered"] += alerts_triggered
            logger.info(f"Triggered {alerts_triggered} alerts during threshold checks")
    
    async def _check_service_threshold(self, service: ServiceMetrics, threshold: MetricThreshold) -> bool:
        """Check a specific threshold against service metrics"""
        # Get metric value
        metric_value = getattr(service, threshold.metric_name, None)
        if metric_value is None:
            return False
        
        # Check threshold
        threshold_exceeded = False
        
        if threshold.comparison == "greater":
            if metric_value > threshold.critical_threshold:
                severity = AlertSeverity.CRITICAL
                threshold_exceeded = True
            elif metric_value > threshold.warning_threshold:
                severity = AlertSeverity.HIGH
                threshold_exceeded = True
        elif threshold.comparison == "less":
            if metric_value < threshold.critical_threshold:
                severity = AlertSeverity.CRITICAL
                threshold_exceeded = True
            elif metric_value < threshold.warning_threshold:
                severity = AlertSeverity.HIGH
                threshold_exceeded = True
        
        if threshold_exceeded:
            # Send alert
            await self.alert_manager.send_alert(
                title=f"Metric Threshold Exceeded: {threshold.metric_name}",
                message=f"{service.service_name}: {threshold.metric_name} is {metric_value:.2f} (threshold: {threshold.warning_threshold:.2f}/{threshold.critical_threshold:.2f})",
                severity=severity,
                category=AlertCategory.PERFORMANCE,
                component=service.service_name,
                broker_namespace=service.broker_namespace,
                details={
                    "metric_name": threshold.metric_name,
                    "current_value": metric_value,
                    "warning_threshold": threshold.warning_threshold,
                    "critical_threshold": threshold.critical_threshold,
                    "comparison": threshold.comparison
                },
                metrics=service.to_dict()
            )
            return True
        
        return False
    
    def get_service_metrics(self, service_name: str) -> Optional[ServiceMetrics]:
        """Get metrics for a specific service"""
        return self.services.get(service_name)
    
    def get_all_metrics(self) -> Dict[str, ServiceMetrics]:
        """Get metrics for all services"""
        return self.services.copy()
    
    def get_aggregated_metrics(self) -> Dict[str, Any]:
        """Get aggregated metrics across all services"""
        if not self.services:
            return {}
        
        total_messages_processed = sum(s.messages_processed for s in self.services.values())
        total_messages_published = sum(s.messages_published for s in self.services.values())
        total_errors = sum(s.error_count for s in self.services.values())
        
        running_services = sum(1 for s in self.services.values() if s.is_running)
        total_services = len(self.services)
        
        # Calculate average metrics
        avg_error_rate = sum(s.error_rate_percent for s in self.services.values()) / total_services
        avg_processing_time = sum(s.avg_processing_time_ms for s in self.services.values()) / total_services
        avg_throughput = sum(s.messages_per_second for s in self.services.values())
        
        return {
            "total_services": total_services,
            "running_services": running_services,
            "service_availability_percent": (running_services / total_services * 100) if total_services > 0 else 0,
            "total_messages_processed": total_messages_processed,
            "total_messages_published": total_messages_published,
            "total_errors": total_errors,
            "overall_error_rate_percent": (total_errors / total_messages_processed * 100) if total_messages_processed > 0 else 0,
            "average_error_rate_percent": avg_error_rate,
            "average_processing_time_ms": avg_processing_time,
            "total_throughput_mps": avg_throughput,
            "last_collection": self._stats["last_collection_time"],
            "collection_stats": self._stats
        }
    
    def get_trending_data(self, service_name: str, minutes: int = 60) -> List[Dict[str, Any]]:
        """Get trending data for a service over the last N minutes"""
        if service_name not in self.metrics_history:
            return []
        
        cutoff_time = time.time() - (minutes * 60)
        history = self.metrics_history[service_name]
        
        return [
            entry for entry in history 
            if entry["timestamp"] > cutoff_time
        ]
    
    async def cache_service_metrics(self, service_name: str, metrics: Dict[str, Any]):
        """Cache service metrics in Redis for collection"""
        if not self.redis_client:
            return
        
        try:
            metrics_key = f"alpha_panda:service_metrics:{service_name}"
            serialized_metrics = json.dumps(metrics, default=str)
            await self.redis_client.setex(metrics_key, 300, serialized_metrics)  # 5 minute cache
        except Exception as e:
            logger.error(f"Failed to cache metrics for {service_name}: {e}")


# Global metrics collector instance
_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector(redis_client=None, settings=None) -> MetricsCollector:
    """Get or create global metrics collector instance"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector(redis_client, settings)
    return _metrics_collector


async def start_metrics_collection(redis_client=None, settings=None, interval_seconds: int = 60):
    """Start global metrics collection"""
    collector = get_metrics_collector(redis_client, settings)
    await collector.start_collection(interval_seconds)
    return collector


async def stop_metrics_collection():
    """Stop global metrics collection"""
    global _metrics_collector
    if _metrics_collector:
        await _metrics_collector.stop_collection()
