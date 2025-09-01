# Core Logging Module

## Overview

The `core/logging/` module provides enhanced logging capabilities for Alpha Panda with structured logging, correlation tracking, and multi-channel log routing. It uses structlog for structured logging with support for different log channels and correlation IDs for request tracing.

## Components

### `enhanced_logging.py`
Main enhanced logging framework with structured logging support:

- **Enhanced Logger Factory**: Creates specialized loggers for different components
- **Structured Logging**: JSON-formatted logs with consistent structure
- **Performance Logging**: Specialized logging for performance metrics
- **Error Logging**: Enhanced error logging with stack traces and context
- **Correlation Support**: Integration with correlation ID tracking

### `correlation.py`
Correlation ID management for request/event tracing:

- **CorrelationManager**: Manages correlation IDs across service boundaries
- **Context Variables**: Thread-safe correlation ID storage
- **Request Tracing**: End-to-end request tracking across services
- **Event Correlation**: Links related events across the system

### `service_logger.py`
Service-specific logging utilities:

- **ServiceLogger**: Service-aware logging with service identification
- **Component Logging**: Per-component log formatting and routing
- **Service Context**: Automatic service context injection in logs
- **Lifecycle Logging**: Service startup/shutdown logging

### `channels.py`
Multi-channel log routing system:

- **Channel Definitions**: Predefined log channels for different purposes
- **Channel Routing**: Route logs to appropriate channels based on content
- **Channel Configuration**: Configure log levels and outputs per channel
- **Channel Filtering**: Filter logs by channel for specific analysis

### `__init__.py`
Logging module exports and convenience functions for easy import across the application.

## Key Features

- **Structured Logging**: JSON-formatted logs with consistent schema
- **Correlation Tracking**: End-to-end request/event tracing with correlation IDs
- **Multi-Channel Routing**: Route logs to different channels (trading, market data, errors, etc.)
- **Performance Monitoring**: Specialized performance logging and metrics
- **Context Injection**: Automatic injection of service and correlation context
- **Error Enhancement**: Enhanced error logging with stack traces and debugging info
- **Thread Safety**: Safe logging across asyncio tasks and threads
 - **ProcessorFormatter**: Pretty console output and JSON file output via structlog ProcessorFormatter
 - **Async Queue Logging**: Non-blocking logging using QueueHandler/QueueListener with Prometheus metrics
 - **Redaction**: Sensitive keys (authorization, tokens, api_key, secret, etc.) are redacted
 - **Access Log Enrichment**: Uvicorn access logs parsed into structured fields (method, path, status, latency_ms)
 - **Channel Filters**: Per-channel file handlers with filters to avoid duplication

## Usage

### Basic Enhanced Logging
```python
from core.logging.enhanced_logging import (
    get_trading_logger_safe,
    get_performance_logger_safe,
    get_error_logger_safe
)

# Get specialized loggers
trading_logger = get_trading_logger_safe("trading_engine")
perf_logger = get_performance_logger_safe("trading_engine")
error_logger = get_error_logger_safe("trading_engine")

# Structured logging
trading_logger.info(
    "Order executed",
    order_id="ORD-123",
    symbol="RELIANCE",
    quantity=100,
    price=2500.0
)

# Performance logging
with perf_logger.timer("order_processing"):
    # Process order
    pass

# Error logging
try:
    # Some operation
    pass
except Exception as e:
    error_logger.error("Order processing failed", exc_info=True, order_id="ORD-123")
```

### Correlation ID Management
```python
from core.logging.correlation import CorrelationManager
from core.logging.enhanced_logging import get_trading_logger_safe

# Initialize correlation manager
correlation_manager = CorrelationManager()

# Start new correlation
correlation_id = correlation_manager.start_correlation()
logger = get_trading_logger_safe("service")

# All logs will include correlation ID
logger.info("Processing started", symbol="RELIANCE")

# In another service/function
current_correlation = correlation_manager.get_current_correlation()
logger.info("Processing continued", correlation_id=current_correlation)
```

### Service-Specific Logging
```python
from core.logging.service_logger import ServiceLogger

class TradingEngineService:
    def __init__(self):
        self.logger = ServiceLogger("trading_engine", "TradingEngine")
    
    async def process_signal(self, signal):
        self.logger.info("Signal received", signal_id=signal.id)
        
        try:
            # Process signal
            result = await self._execute_signal(signal)
            self.logger.info("Signal executed successfully", 
                           signal_id=signal.id, result=result)
        except Exception as e:
            self.logger.error("Signal execution failed", 
                            signal_id=signal.id, error=str(e), exc_info=True)
```

### Channel-Based Logging
```python
from core.logging.channels import LogChannels, get_channel_logger

# Get channel-specific loggers
trading_logger = get_channel_logger(LogChannels.TRADING)
market_logger = get_channel_logger(LogChannels.MARKET_DATA)
error_logger = get_channel_logger(LogChannels.ERRORS)

# Channel-specific logging
trading_logger.info("Order placed", order_id="ORD-123")
market_logger.info("Tick received", symbol="RELIANCE", price=2500.0)
error_logger.error("System error detected", component="risk_manager")
```

## Log Channels

### Available Channels
- **TRADING**: Trading-related logs (orders, executions, positions)
- **MARKET_DATA**: Market data feed logs (ticks, instruments, connectivity)
- **STRATEGY**: Strategy execution and signal generation logs
- **RISK**: Risk management and validation logs
- **PORTFOLIO**: Portfolio management and position tracking logs
- **AUTH**: Authentication and authorization logs
- **PERFORMANCE**: Performance metrics and timing logs
- **ERRORS**: Error and exception logs
- **MONITORING**: Health checks and monitoring logs
- **DATABASE**: Database operation logs

### Channel Configuration
```python
# Configure channel-specific settings
from core.logging.channels import configure_channel

configure_channel(
    channel=LogChannels.TRADING,
    level="INFO",
    format="detailed",
    output_file="/logs/trading.log"
)
```

## Structured Logging Schema

### Standard Log Fields
- **timestamp**: ISO 8601 timestamp with timezone
- **level**: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **service**: Service name generating the log
- **component**: Component within the service
- **correlation_id**: Request/event correlation identifier
- **message**: Human-readable log message
- **context**: Additional structured data

### Example Log Entry
```json
{
    "timestamp": "2024-08-30T12:00:00.000Z",
    "level": "INFO",
    "service": "trading_engine",
    "component": "order_executor",
    "correlation_id": "corr-123-abc",
    "message": "Order executed successfully",
    "context": {
        "order_id": "ORD-123",
        "symbol": "RELIANCE",
        "quantity": 100,
        "price": 2500.0,
        "broker": "zerodha"
    }
}
```

## Performance Monitoring

### Timing Utilities
```python
from core.logging.enhanced_logging import get_performance_logger_safe

perf_logger = get_performance_logger_safe("service")

# Method timing
@perf_logger.timed("order_processing")
async def process_order(order):
    # Process order
    pass

# Context manager timing
with perf_logger.timer("signal_generation"):
    signals = generate_signals(market_data)
```

### Performance Metrics
- **Execution Time**: Method and operation execution times
- **Throughput**: Messages/requests processed per second
- **Latency**: End-to-end latency measurements
- **Resource Usage**: Memory and CPU usage tracking

## Configuration

Logging configuration through settings:

```python
# Logging settings in core/config/settings.py
class LoggingSettings(BaseModel):
    # Core
    level: str = "INFO"
    structured: bool = True
    json_format: bool = True
    # Console
    console_enabled: bool = True
    console_json_format: bool = False
    # Files
    file_enabled: bool = True
    logs_dir: str = "logs"
    file_max_size: str = "100MB"
    file_backup_count: int = 5
    # Multi-channel
    multi_channel_enabled: bool = True
    # Async logging
    queue_enabled: bool = True
    queue_maxsize: int = 10000
    # Redaction
    redact_keys: list[str] = ["authorization", "access_token", "api_key", "secret", "password", "token"]
```

Other relevant settings:
```python
class Settings(BaseSettings):
    app_name: str = "Alpha Panda"
    version: str = "2.1.0"
```

## Architecture Patterns

- **Factory Pattern**: Logger factory for different logger types
- **Context Variables**: Thread-safe correlation ID management
- **Channel Routing**: Multi-channel log routing and filtering
- **Structured Data**: Consistent JSON-formatted log entries
- **Performance Monitoring**: Built-in performance timing and metrics
- **Error Context**: Enhanced error logging with full context

## Best Practices

1. **Use Structured Logging**: Always use structured log entries with context
2. **Include Correlation IDs**: Ensure all logs include correlation information
3. **Appropriate Log Levels**: Use correct log levels (DEBUG, INFO, WARNING, ERROR)
4. **Context Information**: Include relevant context in all log entries
5. **Prefer Channel-Aware Loggers**: Use get_api_logger_safe, get_trading_logger_safe, etc. for correct routing
6. **Avoid Noisy INFO**: Use DEBUG for high-frequency events (ticks); sample INFO logs as needed
7. **Respect Market Hours**: Avoid market-latency warnings when market is closed
8. **Monitor Queue Health**: Alert on logging queue drops and sustained backpressure

## Operational Endpoints and Metrics
- API logging stats: `/api/v1/logs/stats` (queue size/capacity/drops, channel handlers, config)
- Prometheus metrics:
  - `alpha_panda_logging_queue_size`
  - `alpha_panda_logging_queue_capacity`
  - `alpha_panda_logging_queue_dropped_total`
- Prometheus alert rules: `docs/observability/prometheus/logging_alerts.yml`

## Uvicorn/FastAPI Integration
- Uvicorn loggers (`uvicorn`, `uvicorn.error`, `uvicorn.access`, `fastapi`) are attached to the API channel.
- Access logs use a compact key=value format and are enriched into structured fields by `AccessLogEnricherFilter`.
- Propagation for these loggers is disabled to avoid duplicate writes.
5. **Performance Monitoring**: Use timing utilities for performance-critical operations
6. **Channel Usage**: Use appropriate channels for different log types

## Dependencies

- **structlog**: Structured logging framework
- **contextvars**: Context variable support for correlation IDs
- **asyncio**: Async-safe logging support
- **typing**: Type hints for logging functions
