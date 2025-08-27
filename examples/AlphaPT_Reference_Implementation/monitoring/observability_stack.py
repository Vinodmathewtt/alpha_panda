"""
Comprehensive Observability Stack for AlphaPT
Provides distributed tracing, advanced metrics, and structured logging.
"""

import asyncio
import json
import logging
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps
from typing import Any, AsyncGenerator, Dict, List, Optional

import aiohttp
from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest

from core.config.settings import get_settings
from core.logging.logger import get_logger


@dataclass
class TraceContext:
    """Distributed tracing context"""

    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    operation_name: str = ""
    start_time: float = field(default_factory=time.time)
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: List[Dict[str, Any]] = field(default_factory=list)
    finished: bool = False

    def log(self, message: str, level: str = "info", **kwargs):
        """Add log entry to span"""
        log_entry = {"timestamp": time.time(), "level": level, "message": message, **kwargs}
        self.logs.append(log_entry)

    def set_tag(self, key: str, value: Any):
        """Set tag on span"""
        self.tags[key] = value

    def finish(self):
        """Finish the span"""
        if not self.finished:
            self.finished = True
            self.tags["duration_seconds"] = time.time() - self.start_time


class DistributedTracer:
    """Distributed tracing system"""

    def __init__(self):
        self.logger = get_logger(__name__)
        self.active_spans: Dict[str, TraceContext] = {}
        self.jaeger_endpoint: Optional[str] = None

        # Metrics for tracing
        self.trace_counter = Counter("alphapt_traces_total", "Total number of traces", ["operation", "status"])

        self.span_duration = Histogram(
            "alphapt_span_duration_seconds",
            "Span duration in seconds",
            ["operation"],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0],
        )

    def start_span(self, operation_name: str, parent_context: Optional[TraceContext] = None) -> TraceContext:
        """Start a new span"""
        trace_id = parent_context.trace_id if parent_context else str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        parent_span_id = parent_context.span_id if parent_context else None

        span = TraceContext(
            trace_id=trace_id, span_id=span_id, parent_span_id=parent_span_id, operation_name=operation_name
        )

        self.active_spans[span_id] = span
        return span

    def finish_span(self, span: TraceContext):
        """Finish a span and report metrics"""
        span.finish()

        # Record metrics
        self.span_duration.labels(operation=span.operation_name).observe(span.tags.get("duration_seconds", 0))

        status = "success" if not span.tags.get("error") else "error"
        self.trace_counter.labels(operation=span.operation_name, status=status).inc()

        # Send to Jaeger if configured
        if self.jaeger_endpoint:
            asyncio.create_task(self._send_to_jaeger(span))

        # Remove from active spans
        if span.span_id in self.active_spans:
            del self.active_spans[span.span_id]

    async def _send_to_jaeger(self, span: TraceContext):
        """Send span to Jaeger tracing system"""
        try:
            jaeger_span = {
                "traceID": span.trace_id,
                "spanID": span.span_id,
                "parentSpanID": span.parent_span_id,
                "operationName": span.operation_name,
                "startTime": int(span.start_time * 1000000),  # microseconds
                "duration": int(span.tags.get("duration_seconds", 0) * 1000000),
                "tags": [{"key": k, "value": str(v)} for k, v in span.tags.items()],
                "logs": span.logs,
                "process": {
                    "serviceName": "alphapt",
                    "tags": [{"key": "version", "value": "1.0.0"}, {"key": "environment", "value": "production"}],
                },
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.jaeger_endpoint}/api/traces", json={"data": [jaeger_span]}) as response:
                    if response.status != 200:
                        self.logger.warning(f"Failed to send trace to Jaeger: {response.status}")

        except Exception as e:
            self.logger.error(f"Error sending trace to Jaeger: {e}")

    @asynccontextmanager
    async def trace(
        self, operation_name: str, parent_context: Optional[TraceContext] = None
    ) -> AsyncGenerator[TraceContext, None]:
        """Context manager for tracing operations"""
        span = self.start_span(operation_name, parent_context)
        try:
            yield span
        except Exception as e:
            span.set_tag("error", True)
            span.set_tag("error.message", str(e))
            span.log(f"Exception: {str(e)}", level="error")
            raise
        finally:
            self.finish_span(span)


class AdvancedMetricsCollector:
    """Advanced metrics collection with custom business metrics"""

    def __init__(self):
        self.logger = get_logger(__name__)

        # Business metrics
        self.portfolio_value = Gauge("alphapt_portfolio_value_total", "Total portfolio value", ["currency"])

        self.pnl_realized = Counter("alphapt_pnl_realized_total", "Realized P&L", ["strategy", "instrument"])

        self.pnl_unrealized = Gauge("alphapt_pnl_unrealized_total", "Unrealized P&L", ["strategy", "instrument"])

        self.trade_count = Counter(
            "alphapt_trades_total", "Total number of trades", ["strategy", "instrument", "side", "status"]
        )

        self.trade_volume = Counter("alphapt_trade_volume_total", "Total trade volume", ["strategy", "instrument"])

        self.trade_latency = Histogram(
            "alphapt_trade_latency_seconds",
            "Trade execution latency",
            ["strategy", "instrument"],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0],
        )

        # Strategy metrics
        self.strategy_signals = Counter(
            "alphapt_strategy_signals_total", "Strategy signals generated", ["strategy", "signal_type", "instrument"]
        )

        self.strategy_performance = Gauge(
            "alphapt_strategy_performance_ratio", "Strategy performance ratio", ["strategy", "period"]
        )

        self.strategy_drawdown = Gauge("alphapt_strategy_drawdown_ratio", "Strategy maximum drawdown", ["strategy"])

        # Risk metrics
        self.risk_exposure = Gauge("alphapt_risk_exposure_ratio", "Current risk exposure ratio", ["type"])

        self.var_estimate = Gauge(
            "alphapt_var_estimate", "Value at Risk estimate", ["confidence_level", "time_horizon"]
        )

        self.position_concentration = Gauge(
            "alphapt_position_concentration_ratio", "Position concentration ratio", ["instrument"]
        )

        # Market data metrics
        self.market_data_latency = Histogram(
            "alphapt_market_data_latency_seconds",
            "Market data latency",
            ["exchange", "instrument_type"],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
        )

        self.market_data_throughput = Gauge(
            "alphapt_market_data_ticks_per_second", "Market data ticks per second", ["exchange", "instrument_type"]
        )

        self.market_data_quality = Gauge(
            "alphapt_market_data_quality_score", "Market data quality score (0-1)", ["exchange", "quality_metric"]
        )

        # System metrics
        self.event_processing_latency = Histogram(
            "alphapt_event_processing_latency_seconds",
            "Event processing latency",
            ["event_type", "handler"],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
        )

        self.database_query_duration = Histogram(
            "alphapt_database_query_duration_seconds",
            "Database query duration",
            ["database", "operation"],
            buckets=[0.001, 0.01, 0.1, 0.5, 1.0, 5.0, 10.0],
        )

        self.cache_hit_ratio = Gauge("alphapt_cache_hit_ratio", "Cache hit ratio", ["cache_type"])

        # Custom application info
        self.app_info = Info("alphapt_application_info", "Application information")

        self._initialize_static_metrics()

    def _initialize_static_metrics(self):
        """Initialize static application metrics"""
        self.app_info.info(
            {
                "version": "1.0.0",
                "environment": "production",
                "build_date": datetime.utcnow().isoformat(),
                "python_version": "3.11",
                "component": "trading_engine",
            }
        )

    def record_trade(self, strategy: str, instrument: str, side: str, status: str, volume: float, latency: float):
        """Record trade metrics"""
        self.trade_count.labels(strategy=strategy, instrument=instrument, side=side, status=status).inc()

        self.trade_volume.labels(strategy=strategy, instrument=instrument).inc(volume)

        self.trade_latency.labels(strategy=strategy, instrument=instrument).observe(latency)

    def record_market_data(self, exchange: str, instrument_type: str, latency: float, tps: float):
        """Record market data metrics"""
        self.market_data_latency.labels(exchange=exchange, instrument_type=instrument_type).observe(latency)

        self.market_data_throughput.labels(exchange=exchange, instrument_type=instrument_type).set(tps)

    def record_strategy_signal(self, strategy: str, signal_type: str, instrument: str):
        """Record strategy signal"""
        self.strategy_signals.labels(strategy=strategy, signal_type=signal_type, instrument=instrument).inc()

    def update_portfolio_metrics(self, value: float, currency: str = "INR"):
        """Update portfolio value"""
        self.portfolio_value.labels(currency=currency).set(value)

    def update_risk_metrics(self, exposure_ratio: float, var_95_1d: float):
        """Update risk metrics"""
        self.risk_exposure.labels(type="total").set(exposure_ratio)
        self.var_estimate.labels(confidence_level="95", time_horizon="1d").set(var_95_1d)


class StructuredLogger:
    """Enhanced structured logging with correlation IDs"""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.correlation_id: Optional[str] = None

    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for all subsequent logs"""
        self.correlation_id = correlation_id

    def clear_correlation_id(self):
        """Clear correlation ID"""
        self.correlation_id = None

    def _log_with_context(self, level: str, message: str, **kwargs):
        """Log with additional context"""
        extra = {
            "timestamp": datetime.utcnow().isoformat(),
            "correlation_id": self.correlation_id,
            "component": "alphapt",
            **kwargs,
        }

        # Remove None values
        extra = {k: v for k, v in extra.items() if v is not None}

        getattr(self.logger, level)(message, extra=extra)

    def info(self, message: str, **kwargs):
        """Log info message"""
        self._log_with_context("info", message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self._log_with_context("warning", message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message"""
        self._log_with_context("error", message, **kwargs)

    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self._log_with_context("debug", message, **kwargs)


class ObservabilityStack:
    """Main observability stack coordinator"""

    def __init__(self):
        self.settings = get_settings()
        self.tracer = DistributedTracer()
        self.metrics = AdvancedMetricsCollector()
        self.logger = StructuredLogger(__name__)

        # Health check metrics
        self.health_status = Gauge(
            "alphapt_component_health_status", "Component health status (1=healthy, 0=unhealthy)", ["component"]
        )

        self.last_health_check = Gauge(
            "alphapt_last_health_check_timestamp", "Timestamp of last health check", ["component"]
        )

    async def initialize(self):
        """Initialize observability stack"""
        try:
            # Setup Jaeger endpoint if configured
            if hasattr(self.settings, "jaeger_endpoint"):
                self.tracer.jaeger_endpoint = self.settings.jaeger_endpoint

            self.logger.info("✅ Observability stack initialized")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize observability stack: {e}")
            raise

    def trace_operation(self, operation_name: str):
        """Decorator for tracing operations"""

        def decorator(func):
            if asyncio.iscoroutinefunction(func):

                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    async with self.tracer.trace(operation_name) as span:
                        span.set_tag("function", func.__name__)
                        span.set_tag("module", func.__module__)
                        try:
                            result = await func(*args, **kwargs)
                            span.set_tag("success", True)
                            return result
                        except Exception as e:
                            span.set_tag("error", True)
                            span.set_tag("error.type", type(e).__name__)
                            span.log(f"Exception in {func.__name__}: {str(e)}", level="error")
                            raise

                return async_wrapper
            else:

                @wraps(func)
                def sync_wrapper(*args, **kwargs):
                    # For sync functions, we'll create a basic span without async context
                    span = self.tracer.start_span(operation_name)
                    span.set_tag("function", func.__name__)
                    span.set_tag("module", func.__module__)
                    try:
                        result = func(*args, **kwargs)
                        span.set_tag("success", True)
                        return result
                    except Exception as e:
                        span.set_tag("error", True)
                        span.set_tag("error.type", type(e).__name__)
                        span.log(f"Exception in {func.__name__}: {str(e)}", level="error")
                        raise
                    finally:
                        self.tracer.finish_span(span)

                return sync_wrapper

        return decorator

    def update_health_status(self, component: str, healthy: bool):
        """Update component health status"""
        self.health_status.labels(component=component).set(1 if healthy else 0)
        self.last_health_check.labels(component=component).set(time.time())

    def get_metrics_endpoint(self) -> str:
        """Get Prometheus metrics in text format"""
        return generate_latest()

    async def export_metrics_to_prometheus(self, port: int = 9090):
        """Start Prometheus metrics server"""
        from prometheus_client import start_http_server

        try:
            start_http_server(port)
            self.logger.info(f"✅ Prometheus metrics server started on port {port}")
        except Exception as e:
            self.logger.error(f"❌ Failed to start Prometheus server: {e}")
            raise


# Global observability instance
observability = ObservabilityStack()
