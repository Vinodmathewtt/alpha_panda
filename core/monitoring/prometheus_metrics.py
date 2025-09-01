"""
Prometheus metrics integration for production monitoring
Industry-standard metrics collection and exposure
"""

from prometheus_client import Counter, Gauge, Histogram, Summary, CollectorRegistry
from typing import Dict, Any, Optional
import time
from datetime import datetime


class PrometheusMetricsCollector:
    """Production-ready metrics for Prometheus"""
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        
        # Throughput metrics
        self.events_processed = Counter(
            'trading_events_processed_total',
            'Total trading events processed',
            ['service', 'broker', 'event_type'],
            registry=self.registry
        )
        
        # Latency metrics
        self.processing_latency = Histogram(
            'trading_processing_latency_seconds',
            'Event processing latency',
            ['service', 'event_type'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=self.registry
        )
        
        # Business metrics
        self.signals_generated = Counter(
            'trading_signals_generated_total',
            'Total trading signals generated',
            ['strategy_id', 'broker', 'signal_type'],
            registry=self.registry
        )
        
        self.orders_executed = Counter(
            'trading_orders_executed_total', 
            'Total orders executed',
            ['broker', 'order_type', 'status'],
            registry=self.registry
        )
        
        # System health metrics
        self.pipeline_stage_health = Gauge(
            'trading_pipeline_stage_healthy',
            'Pipeline stage health status (1=healthy, 0=unhealthy)',
            ['stage', 'broker'],
            registry=self.registry
        )
        
        # Market data metrics
        self.market_ticks_received = Counter(
            'market_ticks_received_total',
            'Total market ticks received',
            ['source'],
            registry=self.registry
        )
        
        # Strategy performance metrics
        self.strategy_pnl = Gauge(
            'strategy_pnl_current',
            'Current P&L by strategy',
            ['strategy_id', 'broker'],
            registry=self.registry
        )
        
        # Error metrics
        self.errors_total = Counter(
            'trading_errors_total',
            'Total errors by component',
            ['component', 'error_type', 'broker'],
            registry=self.registry
        )
        
        # Connection health
        self.connection_status = Gauge(
            'trading_connection_status',
            'Connection status (1=connected, 0=disconnected)',
            ['connection_type', 'broker'],
            registry=self.registry
        )

        # DLQ metrics
        self.dlq_messages = Counter(
            'trading_dlq_messages_total',
            'Total messages sent to Dead Letter Queues',
            ['service', 'broker'],
            registry=self.registry
        )

        # Activity timestamps (unix seconds) for inactivity alerts/panels
        self.last_activity_timestamp = Gauge(
            'trading_last_activity_timestamp_unix',
            'Last activity timestamp (unix seconds) by service/stage/broker',
            ['service', 'stage', 'broker'],
            registry=self.registry
        )
        
        # Cache metrics
        self.cache_hits = Counter(
            'cache_hits_total',
            'Total cache hits',
            ['cache_type'],
            registry=self.registry
        )
        
        self.cache_misses = Counter(
            'cache_misses_total',
            'Total cache misses',
            ['cache_type'],
            registry=self.registry
        )
    
    def record_event_processed(self, service: str, broker: str, event_type: str):
        """Record event processing"""
        self.events_processed.labels(service=service, broker=broker, event_type=event_type).inc()
    
    def record_processing_time(self, service: str, event_type: str, duration_seconds: float):
        """Record processing latency"""  
        self.processing_latency.labels(service=service, event_type=event_type).observe(duration_seconds)
    
    def record_signal_generated(self, strategy_id: str, broker: str, signal_type: str):
        """Record signal generation"""
        self.signals_generated.labels(strategy_id=strategy_id, broker=broker, signal_type=signal_type).inc()
    
    def record_order_executed(self, broker: str, order_type: str, status: str):
        """Record order execution"""
        self.orders_executed.labels(broker=broker, order_type=order_type, status=status).inc()
    
    def set_pipeline_health(self, stage: str, broker: str, healthy: bool):
        """Set pipeline stage health status"""
        self.pipeline_stage_health.labels(stage=stage, broker=broker).set(1 if healthy else 0)
    
    def record_market_tick(self, source: str = "zerodha"):
        """Record market tick received"""
        self.market_ticks_received.labels(source=source).inc()
    
    def set_strategy_pnl(self, strategy_id: str, broker: str, pnl: float):
        """Set current strategy P&L"""
        self.strategy_pnl.labels(strategy_id=strategy_id, broker=broker).set(pnl)
    
    def record_error(self, component: str, error_type: str, broker: str):
        """Record error by component"""
        self.errors_total.labels(component=component, error_type=error_type, broker=broker).inc()
    
    def set_connection_status(self, connection_type: str, broker: str, connected: bool):
        """Set connection status"""
        self.connection_status.labels(connection_type=connection_type, broker=broker).set(1 if connected else 0)
    
    def record_cache_hit(self, cache_type: str):
        """Record cache hit"""
        self.cache_hits.labels(cache_type=cache_type).inc()
    
    def record_cache_miss(self, cache_type: str):
        """Record cache miss"""
        self.cache_misses.labels(cache_type=cache_type).inc()

    def record_dlq_message(self, service: str, broker: str):
        """Record a message sent to DLQ for a service/broker."""
        self.dlq_messages.labels(service=service, broker=broker).inc()

    def set_last_activity(self, service: str, stage: str, broker: str):
        """Set last activity timestamp for a service/stage/broker to now (unix seconds)."""
        try:
            self.last_activity_timestamp.labels(service=service, stage=stage, broker=broker).set(time.time())
        except Exception:
            pass


class MetricsContextManager:
    """Context manager for timing operations"""
    
    def __init__(self, metrics_collector: PrometheusMetricsCollector, 
                 service: str, event_type: str):
        self.metrics_collector = metrics_collector
        self.service = service
        self.event_type = event_type
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.perf_counter() - self.start_time
            self.metrics_collector.record_processing_time(
                self.service, self.event_type, duration
            )


def create_metrics_collector() -> PrometheusMetricsCollector:
    """Factory function to create metrics collector"""
    return PrometheusMetricsCollector()


def get_metrics_for_testing() -> PrometheusMetricsCollector:
    """Get metrics collector with custom registry for testing"""
    test_registry = CollectorRegistry()
    return PrometheusMetricsCollector(registry=test_registry)
