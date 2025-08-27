"""Prometheus metrics collection for AlphaPT."""

import asyncio
import logging
import time
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    Summary,
    generate_latest,
    push_to_gateway,
    start_http_server,
)

from core.config.settings import Settings
from core.logging.logger import StructuredLogger

logger = StructuredLogger(__name__, "metrics")


class MetricsCollector:
    """Prometheus metrics collector for AlphaPT."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.registry = CollectorRegistry()
        self._metrics_server = None
        self._running = False
        self._lock = Lock()

        # Initialize metrics
        self._init_metrics()

    def _init_metrics(self) -> None:
        """Initialize Prometheus metrics."""

        # Market data metrics
        self.market_ticks_received = Counter(
            "alphapt_market_ticks_received_total",
            "Total number of market ticks received",
            ["exchange", "instrument_token"],
            registry=self.registry,
        )

        self.market_data_latency = Histogram(
            "alphapt_market_data_latency_seconds",
            "Market data processing latency",
            ["exchange", "data_type"],
            registry=self.registry,
        )

        self.market_feed_connection_status = Gauge(
            "alphapt_market_feed_connection_status",
            "Market feed connection status (1=connected, 0=disconnected)",
            ["provider"],
            registry=self.registry,
        )

        # Trading metrics
        self.orders_placed = Counter(
            "alphapt_orders_placed_total",
            "Total number of orders placed",
            ["strategy", "transaction_type", "order_type"],
            registry=self.registry,
        )

        self.order_fill_latency = Histogram(
            "alphapt_order_fill_latency_seconds",
            "Order fill latency",
            ["strategy", "order_type"],
            registry=self.registry,
        )

        self.positions_pnl = Gauge(
            "alphapt_positions_pnl_total", "Current PnL by strategy", ["strategy"], registry=self.registry
        )

        self.positions_count = Gauge(
            "alphapt_positions_count", "Number of open positions", ["strategy"], registry=self.registry
        )

        # Strategy metrics
        self.strategy_signals_generated = Counter(
            "alphapt_strategy_signals_generated_total",
            "Total number of signals generated",
            ["strategy", "signal_type"],
            registry=self.registry,
        )

        self.strategy_execution_time = Histogram(
            "alphapt_strategy_execution_time_seconds", "Strategy execution time", ["strategy"], registry=self.registry
        )

        self.strategy_health_status = Gauge(
            "alphapt_strategy_health_status",
            "Strategy health status (1=healthy, 0=unhealthy)",
            ["strategy"],
            registry=self.registry,
        )

        # System metrics
        self.event_queue_size = Gauge(
            "alphapt_event_queue_size", "Event queue size", ["stream_name"], registry=self.registry
        )

        self.database_connections = Gauge(
            "alphapt_database_connections", "Number of database connections", ["database_type"], registry=self.registry
        )

        self.memory_usage = Gauge(
            "alphapt_memory_usage_bytes", "Memory usage in bytes", ["process"], registry=self.registry
        )

        self.cpu_utilization = Gauge(
            "alphapt_cpu_utilization_percent", "CPU utilization percentage", ["process"], registry=self.registry
        )

        # Business metrics
        self.daily_pnl = Gauge("alphapt_daily_pnl", "Daily PnL", ["strategy"], registry=self.registry)

        self.total_trades = Counter(
            "alphapt_total_trades", "Total number of completed trades", ["strategy"], registry=self.registry
        )

        self.active_strategies = Gauge(
            "alphapt_active_strategies", "Number of active strategies", registry=self.registry
        )

        # Error metrics
        self.error_count = Counter(
            "alphapt_errors_total", "Total number of errors", ["component", "error_type"], registry=self.registry
        )

        # Application info
        self.app_info = Info("alphapt_app_info", "Application information", registry=self.registry)

        # Set application info
        self.app_info.info({"version": self.settings.app_version, "environment": self.settings.environment.value})

    async def start(self) -> None:
        """Start metrics collection."""
        if self._running:
            return

        if self.settings.monitoring.prometheus_enabled:
            # Start HTTP server for metrics endpoint
            try:
                self._metrics_server = start_http_server(
                    port=self.settings.monitoring.prometheus_port, registry=self.registry
                )
                logger.info(f"Metrics server started on port {self.settings.monitoring.prometheus_port}")
            except Exception as e:
                logger.error("Failed to start metrics server", error=e)

        self._running = True
        logger.info("Metrics collector started")

    async def stop(self) -> None:
        """Stop metrics collection."""
        if not self._running:
            return

        if self._metrics_server:
            self._metrics_server.shutdown()
            self._metrics_server = None

        self._running = False
        logger.info("Metrics collector stopped")

    # Market data metrics methods
    def record_market_tick(
        self, exchange: str, instrument_token: int, processing_latency: Optional[float] = None
    ) -> None:
        """Record market tick received."""
        with self._lock:
            self.market_ticks_received.labels(exchange=exchange, instrument_token=str(instrument_token)).inc()

            if processing_latency is not None:
                self.market_data_latency.labels(exchange=exchange, data_type="tick").observe(processing_latency)

    def set_market_feed_status(self, provider: str, connected: bool) -> None:
        """Set market feed connection status."""
        with self._lock:
            self.market_feed_connection_status.labels(provider=provider).set(1 if connected else 0)

    # Trading metrics methods
    def record_order_placed(self, strategy: str, transaction_type: str, order_type: str) -> None:
        """Record order placement."""
        with self._lock:
            self.orders_placed.labels(strategy=strategy, transaction_type=transaction_type, order_type=order_type).inc()

    def record_order_fill(self, strategy: str, order_type: str, fill_latency: float) -> None:
        """Record order fill."""
        with self._lock:
            self.order_fill_latency.labels(strategy=strategy, order_type=order_type).observe(fill_latency)

    def update_position_pnl(self, strategy: str, pnl: float) -> None:
        """Update position PnL."""
        with self._lock:
            self.positions_pnl.labels(strategy=strategy).set(pnl)

    def update_positions_count(self, strategy: str, count: int) -> None:
        """Update positions count."""
        with self._lock:
            self.positions_count.labels(strategy=strategy).set(count)

    # Strategy metrics methods
    def record_strategy_signal(self, strategy: str, signal_type: str) -> None:
        """Record strategy signal generation."""
        with self._lock:
            self.strategy_signals_generated.labels(strategy=strategy, signal_type=signal_type).inc()

    def record_strategy_execution_time(self, strategy: str, execution_time: float) -> None:
        """Record strategy execution time."""
        with self._lock:
            self.strategy_execution_time.labels(strategy=strategy).observe(execution_time)

    def set_strategy_health(self, strategy: str, healthy: bool) -> None:
        """Set strategy health status."""
        with self._lock:
            self.strategy_health_status.labels(strategy=strategy).set(1 if healthy else 0)

    def set_active_strategies_count(self, count: int) -> None:
        """Set active strategies count."""
        with self._lock:
            self.active_strategies.set(count)

    # System metrics methods
    def update_event_queue_size(self, stream_name: str, size: int) -> None:
        """Update event queue size."""
        with self._lock:
            self.event_queue_size.labels(stream_name=stream_name).set(size)

    def update_database_connections(self, database_type: str, count: int) -> None:
        """Update database connections count."""
        with self._lock:
            self.database_connections.labels(database_type=database_type).set(count)

    def update_system_resources(self, process: str, memory_bytes: float, cpu_percent: float) -> None:
        """Update system resource metrics."""
        with self._lock:
            self.memory_usage.labels(process=process).set(memory_bytes)
            self.cpu_utilization.labels(process=process).set(cpu_percent)

    # Business metrics methods
    def update_daily_pnl(self, strategy: str, pnl: float) -> None:
        """Update daily PnL."""
        with self._lock:
            self.daily_pnl.labels(strategy=strategy).set(pnl)

    def record_trade_completion(self, strategy: str) -> None:
        """Record completed trade."""
        with self._lock:
            self.total_trades.labels(strategy=strategy).inc()

    # Error metrics methods
    def record_error(self, component: str, error_type: str) -> None:
        """Record error occurrence."""
        with self._lock:
            self.error_count.labels(component=component, error_type=error_type).inc()

    # Utility methods
    def get_metrics_text(self) -> str:
        """Get metrics in Prometheus text format."""
        return generate_latest(self.registry).decode("utf-8")

    async def push_metrics(self, gateway_url: str, job_name: str) -> bool:
        """Push metrics to Prometheus pushgateway."""
        if not gateway_url:
            return False

        try:
            push_to_gateway(gateway_url, job=job_name, registry=self.registry)
            return True
        except Exception as e:
            logger.error("Failed to push metrics to gateway", error=e)
            return False

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current metrics as dictionary."""
        metrics = {}

        try:
            # This is a simplified version - in production you'd parse the
            # full metrics output or use metric family samples
            metrics_text = self.get_metrics_text()

            # Basic parsing for demonstration
            for line in metrics_text.split("\n"):
                if line.startswith("alphapt_") and not line.startswith("#"):
                    parts = line.split(" ")
                    if len(parts) >= 2:
                        metric_name = parts[0].split("{")[0]
                        try:
                            metric_value = float(parts[1])
                            metrics[metric_name] = metric_value
                        except ValueError:
                            continue

        except Exception as e:
            logger.error("Failed to get current metrics", error=e)

        return metrics

    def is_running(self) -> bool:
        """Check if metrics collector is running."""
        return self._running
