"""Structured logging implementation for AlphaPT."""

import logging
import logging.handlers
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from structlog import configure
from structlog import get_logger as structlog_get_logger
from structlog.stdlib import LoggerFactory

from core.config.settings import Settings
from core.logging.base_logger import (
    LogContext,
    TimestampProcessor,
    ComponentProcessor,
    JSONRenderer,
    ConsoleRenderer,
    StructuredLogger
)

# Multi-channel logging imports
try:
    from core.logging.multi_channel_logger import (
        initialize_multi_channel_logging,
        get_channel_logger,
        get_component_logger
    )
    MULTI_CHANNEL_AVAILABLE = True
except ImportError:
    MULTI_CHANNEL_AVAILABLE = False

# Context variables for request tracing
correlation_id_ctx: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
user_id_ctx: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
session_id_ctx: ContextVar[Optional[str]] = ContextVar("session_id", default=None)


# LogContext is now imported from base_logger


class CorrelationProcessor:
    """Processor to add correlation context to log records."""

    def __call__(self, logger, method_name, event_dict):
        # Add correlation context
        correlation_id = correlation_id_ctx.get()
        if correlation_id:
            event_dict["correlation_id"] = correlation_id

        user_id = user_id_ctx.get()
        if user_id:
            event_dict["user_id"] = user_id

        session_id = session_id_ctx.get()
        if session_id:
            event_dict["session_id"] = session_id

        return event_dict


# TimestampProcessor, ComponentProcessor, JSONRenderer, and ConsoleRenderer are now imported from base_logger


def configure_logging(settings: Settings, enable_multi_channel: bool = True) -> None:
    """Configure structured logging for the application."""

    # Create logs directory
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize multi-channel logging if available and enabled
    if enable_multi_channel and MULTI_CHANNEL_AVAILABLE:
        try:
            initialize_multi_channel_logging(settings)
            print(f"Multi-channel logging initialized with channels: application, trading, market_data, database, audit, performance, errors, monitoring, api")
        except Exception as e:
            print(f"Failed to initialize multi-channel logging, falling back to single file: {e}")
    else:
        print("Using single-file logging mode")

    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        TimestampProcessor(),
        CorrelationProcessor(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Add renderer based on effective JSON logs configuration
    if settings.get_effective_json_logs():
        processors.append(JSONRenderer())
    else:
        processors.append(ConsoleRenderer())

    configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.log_level.value))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    if settings.monitoring.log_console_enabled:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, settings.log_level.value))

        if settings.get_effective_json_logs():
            formatter = logging.Formatter("%(message)s")
        else:
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # File handler
    if settings.monitoring.log_file_enabled:
        file_handler = logging.handlers.RotatingFileHandler(
            filename=settings.logs_dir / settings.monitoring.log_file_path,
            maxBytes=_parse_size(settings.monitoring.log_file_max_size),
            backupCount=settings.monitoring.log_file_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(getattr(logging, settings.log_level.value))

        formatter = logging.Formatter("%(message)s")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Configure specific loggers
    # Reduce noise from external libraries and routine operations
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING) 
    logging.getLogger("nats").setLevel(logging.WARNING)
    
    # Set SQLAlchemy to DEBUG level to reduce verbosity (but keep warnings/errors)
    # Disable the verbose SQL query logging
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.orm").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    
    # Set routine monitoring operations level based on main log level
    # But ensure warnings and errors are always visible
    monitoring_level = max(logging.INFO, getattr(logging, settings.log_level.value))
    logging.getLogger("monitoring.health_checker").setLevel(monitoring_level)
    logging.getLogger("monitoring.metrics_collector").setLevel(monitoring_level)
    
    # Set event bus level to ensure warnings/errors are visible but routine operations are quiet
    event_bus_level = max(logging.INFO, getattr(logging, settings.log_level.value))
    logging.getLogger("core.events.event_bus").setLevel(event_bus_level)

    # AlphaPT loggers - ensure they respect the main log level
    logging.getLogger("alphaPT").setLevel(getattr(logging, settings.log_level.value))
    
    # Ensure all strategy and component loggers can show warnings/errors
    for component in ['strategy_manager', 'strategy_factory', 'storage_manager', 
                     'clickhouse_manager', 'redis_cache_manager', 'data_quality_monitor',
                     'zerodha_market_feed', 'paper_trade', 'risk_manager']:
        component_level = max(logging.INFO, getattr(logging, settings.log_level.value))
        logging.getLogger(component).setLevel(component_level)


def _parse_size(size_str: str) -> int:
    """Parse size string (e.g., '100MB') to bytes."""
    size_str = size_str.upper()

    if size_str.endswith("B"):
        size_str = size_str[:-1]

    multipliers = {
        "K": 1024,
        "M": 1024 * 1024,
        "G": 1024 * 1024 * 1024,
    }

    for suffix, multiplier in multipliers.items():
        if size_str.endswith(suffix):
            return int(float(size_str[:-1]) * multiplier)

    return int(size_str)


def get_logger(name: str, component: Optional[str] = None) -> structlog.BoundLogger:
    """Get a structured logger instance with optional multi-channel routing."""
    
    # Try to use multi-channel logging if available
    if MULTI_CHANNEL_AVAILABLE:
        try:
            return get_channel_logger(name, component)
        except Exception:
            # Fall back to standard logging if multi-channel fails
            pass
    
    # Standard single-file logging
    logger = structlog_get_logger(name)
    if component:
        logger = logger.bind(component=component)
    return logger


def get_component_logger_safe(component_name: str) -> structlog.BoundLogger:
    """Safely get a component logger with fallback to standard logging."""
    if MULTI_CHANNEL_AVAILABLE:
        try:
            return get_component_logger(component_name)
        except Exception:
            pass
    
    # Fallback to standard logger
    return get_logger(component_name, component_name)


# StructuredLogger is now imported from base_logger


class AuditLogger(StructuredLogger):
    """Audit logger for trading activities."""

    def __init__(self):
        super().__init__("alphaPT.audit", "audit")
        # Enhanced audit logging will be handled by business_loggers.py

    def order_placed(
        self,
        order_id: str,
        strategy_name: str,
        instrument_token: int,
        transaction_type: str,
        quantity: int,
        price: Optional[float] = None,
        user_id: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Log order placement."""
        self.info(
            "Order placed",
            order_id=order_id,
            strategy_name=strategy_name,
            instrument_token=instrument_token,
            transaction_type=transaction_type,
            quantity=quantity,
            price=price,
            user_id=user_id,
            **kwargs,
        )

    def order_filled(self, order_id: str, filled_quantity: int, average_price: float, **kwargs) -> None:
        """Log order fill."""
        self.info(
            "Order filled", order_id=order_id, filled_quantity=filled_quantity, average_price=average_price, **kwargs
        )

    def position_update(
        self,
        strategy_name: str,
        instrument_token: int,
        position_quantity: int,
        position_value: float,
        pnl: float,
        **kwargs,
    ) -> None:
        """Log position update."""
        self.info(
            "Position updated",
            strategy_name=strategy_name,
            instrument_token=instrument_token,
            position_quantity=position_quantity,
            position_value=position_value,
            pnl=pnl,
            **kwargs,
        )

    def risk_breach(
        self,
        strategy_name: str,
        risk_type: str,
        risk_metric: str,
        current_value: float,
        limit_value: float,
        breach_level: str,
        **kwargs,
    ) -> None:
        """Log risk breach."""
        self.warning(
            "Risk breach detected",
            strategy_name=strategy_name,
            risk_type=risk_type,
            risk_metric=risk_metric,
            current_value=current_value,
            limit_value=limit_value,
            breach_level=breach_level,
            **kwargs,
        )

    def strategy_action(self, strategy_name: str, action: str, user_id: Optional[str] = None, **kwargs) -> None:
        """Log strategy actions."""
        self.info("Strategy action", strategy_name=strategy_name, action=action, user_id=user_id, **kwargs)


class PerformanceLogger(StructuredLogger):
    """Performance logger for system metrics."""

    def __init__(self):
        super().__init__("alphaPT.performance", "performance")
        # Enhanced performance logging will be handled by business_loggers.py

    def execution_time(
        self, operation: str, execution_time_ms: float, component: Optional[str] = None, **kwargs
    ) -> None:
        """Log execution time."""
        self.info(
            "Performance metric",
            operation=operation,
            execution_time_ms=execution_time_ms,
            component=component,
            **kwargs,
        )

    def throughput(
        self, operation: str, count: int, time_window_sec: float, component: Optional[str] = None, **kwargs
    ) -> None:
        """Log throughput metrics."""
        rate = count / time_window_sec if time_window_sec > 0 else 0

        self.info(
            "Throughput metric",
            operation=operation,
            count=count,
            time_window_sec=time_window_sec,
            rate_per_sec=rate,
            component=component,
            **kwargs,
        )

    def resource_usage(self, cpu_percent: float, memory_mb: float, component: Optional[str] = None, **kwargs) -> None:
        """Log resource usage."""
        self.info("Resource usage", cpu_percent=cpu_percent, memory_mb=memory_mb, component=component, **kwargs)


class ErrorLogger(StructuredLogger):
    """Error logger with enhanced error tracking."""

    def __init__(self):
        super().__init__("alphaPT.errors", "error")
        # Enhanced error logging will be handled by business_loggers.py

    def system_error(
        self,
        error: Exception,
        component: str,
        operation: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        """Log system error."""
        error_data = {
            "component": component,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        }

        if operation:
            error_data["operation"] = operation

        if context:
            error_data["context"] = context

        error_data.update(kwargs)

        self.error("System error occurred", **error_data)

    def trading_error(
        self,
        error: Exception,
        strategy_name: Optional[str] = None,
        order_id: Optional[str] = None,
        instrument_token: Optional[int] = None,
        **kwargs,
    ) -> None:
        """Log trading-related error."""
        error_data = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        }

        if strategy_name:
            error_data["strategy_name"] = strategy_name
        if order_id:
            error_data["order_id"] = order_id
        if instrument_token:
            error_data["instrument_token"] = instrument_token

        error_data.update(kwargs)

        self.error("Trading error occurred", **error_data)

    def data_error(
        self,
        error: Exception,
        data_type: str,
        data_source: Optional[str] = None,
        record_count: Optional[int] = None,
        **kwargs,
    ) -> None:
        """Log data-related error."""
        error_data = {
            "data_type": data_type,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
        }

        if data_source:
            error_data["data_source"] = data_source
        if record_count:
            error_data["record_count"] = record_count

        error_data.update(kwargs)

        self.error("Data error occurred", **error_data)


# Context managers for setting correlation context
class LogContextManager:
    """Context manager for setting log context."""

    def __init__(
        self, correlation_id: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None
    ):
        self.correlation_id = correlation_id
        self.user_id = user_id
        self.session_id = session_id
        self._tokens = []

    def __enter__(self):
        if self.correlation_id:
            self._tokens.append(correlation_id_ctx.set(self.correlation_id))
        if self.user_id:
            self._tokens.append(user_id_ctx.set(self.user_id))
        if self.session_id:
            self._tokens.append(session_id_ctx.set(self.session_id))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for token in reversed(self._tokens):
            token.var.reset(token)
        self._tokens.clear()


# Performance measurement decorator
def log_performance(operation: str, component: Optional[str] = None):
    """Decorator to log performance metrics."""

    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start_time = datetime.now(timezone.utc)
            perf_logger = PerformanceLogger()

            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                end_time = datetime.now(timezone.utc)
                execution_time = (end_time - start_time).total_seconds() * 1000
                perf_logger.execution_time(operation=operation, execution_time_ms=execution_time, component=component)

        def sync_wrapper(*args, **kwargs):
            start_time = datetime.now(timezone.utc)
            perf_logger = PerformanceLogger()

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = datetime.now(timezone.utc)
                execution_time = (end_time - start_time).total_seconds() * 1000
                perf_logger.execution_time(operation=operation, execution_time_ms=execution_time, component=component)

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def setup_logging(settings: Optional[Settings] = None) -> None:
    """Setup logging configuration (alias for configure_logging)."""
    if settings is None:
        from core.config.settings import settings as default_settings

        settings = default_settings

    configure_logging(settings)
