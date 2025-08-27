# AlphaPT Enhanced Multi-Channel Logging System

## Overview

The AlphaPT logging system provides sophisticated multi-channel logging with dedicated log files for different functional areas, comprehensive business event logging, and operational management tools. This implementation replaces the single log file approach with a production-ready logging infrastructure.

## Implementation Summary

### ✅ **Completed Features**

1. **Multi-Channel Logging Infrastructure** (`core/logging/log_channels.py`)
   - 9 dedicated log channels with specific configurations
   - Component-based routing logic
   - Configurable retention policies per channel

2. **Channel-Based Logger Routing** (`core/logging/multi_channel_logger.py`)
   - Automatic component-to-channel mapping
   - Cached logger instances for performance
   - Backward compatibility with existing logging

3. **Specialized Business Loggers** (`core/logging/business_loggers.py`)
   - `TradingAuditLogger` - Order lifecycle, position changes, risk events
   - `SystemPerformanceLogger` - Execution metrics, throughput, latency
   - `MarketDataQualityLogger` - Data quality monitoring, feed connectivity
   - `SystemErrorLogger` - Enhanced error tracking with context

4. **Enhanced Configuration** (`core/config/monitoring_config.py`)
   - Multi-channel settings with retention policies
   - Channel-specific log levels
   - Automatic cleanup and compression options

5. **Performance Decorators** (`core/logging/decorators.py`)
   - `@log_trading_performance` - Trading operation metrics
   - `@log_order_lifecycle` - Automatic order event logging
   - `@log_system_performance` - System performance tracking
   - `@log_database_operation` - Database operation monitoring

6. **Log Management Tools** (`core/logging/log_management.py`)
   - Log rotation and cleanup utilities
   - Log analysis and health monitoring
   - Export functionality (JSON/CSV)

7. **Operational Tools** (`scripts/log_management.py`)
   - Command-line log management utility
   - Status, analysis, cleanup, compression commands
   - Health monitoring and export capabilities

8. **API Integration** (`api/routers/logs.py`)
   - REST API endpoints for log management
   - Real-time log tailing and search
   - Export and analysis endpoints

## Quick Start

### Basic Usage

```python
from core.logging import get_trading_logger, get_api_logger, get_database_logger

# Get channel-specific loggers
trading_logger = get_trading_logger("order_manager")
api_logger = get_api_logger("auth_router")
database_logger = get_database_logger("clickhouse_manager")

# Log messages to specific channels
trading_logger.info("Order placed", order_id="12345", symbol="RELIANCE")
api_logger.info("User authenticated", user_id="user123", method="oauth")
database_logger.warning("Slow query detected", duration_ms=1500, table="ticks")
```

### Business Event Logging

```python
from core.logging.business_loggers import trading_audit_logger, system_performance_logger

# Audit logging for compliance
trading_audit_logger.order_lifecycle_event(
    event_type="placed",
    order_id="ORD001",
    strategy_name="momentum_v1", 
    instrument_token=738561,
    tradingsymbol="RELIANCE",
    transaction_type="BUY",
    quantity=100,
    price=2500.50
)

# Performance metrics
system_performance_logger.execution_metrics(
    operation="order_processing",
    component="trading_engine", 
    execution_time_ms=45.2,
    success=True
)
```

### Performance Decorators

```python
from core.logging.decorators import log_trading_performance, log_order_lifecycle

@log_trading_performance("order_placement", include_args=True)
async def place_order(order_data):
    # Your order placement logic
    return order_result

@log_order_lifecycle("filled")
def process_order_fill(order):
    # Your order fill processing
    return updated_order
```

## Architecture

### Log Channels

| Channel | File | Components | Retention | Purpose |
|---------|------|------------|-----------|---------|
| **APPLICATION** | `application.log` | app, main, startup, shutdown | 14 days | Application lifecycle |
| **TRADING** | `trading.log` | strategies, orders, positions, risk | 60 days | Trading operations |
| **MARKET_DATA** | `market_data.log` | feeds, storage, data quality | 7 days | Market data pipeline |
| **DATABASE** | `database.log` | clickhouse, postgres, redis | 7 days | Database operations |
| **AUDIT** | `audit.log` | audit, compliance, risk breaches | 365 days | Regulatory compliance |
| **PERFORMANCE** | `performance.log` | metrics, profiling, latency | 30 days | Performance monitoring |
| **ERRORS** | `errors.log` | exceptions, failures | 90 days | Error tracking |
| **MONITORING** | `monitoring.log` | health checks, alerts | 30 days | System monitoring |
| **API** | `api.log` | server, middleware, routers | 30 days | API operations |

### Directory Structure

```
logs/
├── application.log       # Main app lifecycle
├── trading.log          # Orders, strategies, risk
├── market_data.log      # Feed data, storage
├── database.log         # SQL queries, migrations
├── audit.log           # Business audit trail
├── performance.log     # System metrics
├── errors.log          # All error conditions
├── monitoring.log      # Health checks, alerts
├── api.log            # API requests, responses
├── archive/           # Archived old logs
└── daily/            # Daily log organization
```

### Automatic Component Routing

Components are automatically routed to appropriate channels based on naming patterns:

```python
# Examples of automatic routing
"strategy_manager" → TRADING channel
"zerodha_trade_engine" → TRADING channel  
"clickhouse_manager" → DATABASE channel
"api_server" → API channel
"health_checker" → MONITORING channel
"unknown_component" → APPLICATION channel (fallback)
```

## Module Files

### Core Files

- **`logger.py`** - Main logging configuration and basic loggers
- **`log_channels.py`** - Channel definitions and routing configuration
- **`multi_channel_logger.py`** - Multi-channel logger implementation
- **`business_loggers.py`** - Specialized business event loggers
- **`decorators.py`** - Performance and audit logging decorators
- **`log_management.py`** - Log rotation, analysis, and export utilities

## Available Loggers

### 1. Channel-Specific Loggers

```python
from core.logging import (
    get_trading_logger,      # → trading.log
    get_market_data_logger,  # → market_data.log
    get_database_logger,     # → database.log
    get_audit_logger,        # → audit.log
    get_performance_logger,  # → performance.log
    get_api_logger,          # → api.log
    get_monitoring_logger,   # → monitoring.log
    get_error_logger         # → errors.log
)
```

### 2. Business Event Loggers

```python
from core.logging.business_loggers import (
    TradingAuditLogger,        # Order lifecycle, risk events
    SystemPerformanceLogger,   # Performance metrics
    MarketDataQualityLogger,   # Data quality monitoring  
    SystemErrorLogger          # Enhanced error tracking
)

# Global instances
from core.logging.business_loggers import (
    trading_audit_logger,
    system_performance_logger,
    market_data_quality_logger,
    system_error_logger
)
```

### 3. Convenience Functions

```python
from core.logging.business_loggers import (
    log_order_event,          # Quick order event logging
    log_performance_metric,   # Quick performance logging
    log_system_error,         # Quick system error logging
    log_trading_error         # Quick trading error logging
)

# Usage
log_order_event("filled", order_id="12345", symbol="RELIANCE")
log_performance_metric("db_query", "clickhouse", 150.5)
log_system_error(exception, "trading_engine")
```

### 4. Performance Decorators

```python
from core.logging.decorators import (
    log_trading_performance,   # Trading operation metrics
    log_order_lifecycle,       # Automatic order event logging
    log_system_performance,    # System performance tracking
    log_database_operation     # Database operation monitoring
)

# Examples
@log_trading_performance("signal_generation", include_args=True)
@log_system_performance("strategy_execution", measure_memory=True)
@log_database_operation("INSERT", "orders", slow_query_threshold_ms=500)
```

## Configuration

### Environment Variables

```env
# Multi-Channel Logging Settings
MONITORING__LOG_MULTI_CHANNEL_ENABLED=true    # Enable separate log files
MONITORING__LOG_AUDIT_RETENTION_DAYS=365      # Audit logs retention (compliance)
MONITORING__LOG_PERFORMANCE_RETENTION_DAYS=30 # Performance logs retention
MONITORING__LOG_DATABASE_LEVEL=WARNING        # Reduce SQL query noise
MONITORING__LOG_TRADING_LEVEL=INFO            # Trading operations detail level
MONITORING__LOG_API_LEVEL=INFO                # API operations detail level
MONITORING__LOG_AUTO_CLEANUP_ENABLED=true     # Automatic old log cleanup
MONITORING__LOG_COMPRESSION_ENABLED=true      # Compress old log files
MONITORING__LOG_COMPRESSION_AGE_DAYS=7        # Compress logs older than 7 days
```

### Programmatic Configuration

```python
from core.config.settings import Settings

settings = Settings()
# Multi-channel logging automatically enabled if available
# Configuration automatically loaded from environment variables
```

## Log Management

### Command-Line Tools

```bash
# Show status of all log channels
python scripts/log_management.py status

# Analyze specific channel logs
python scripts/log_management.py analyze trading --lines 1000

# Get log health summary  
python scripts/log_management.py health

# Clean up old logs
python scripts/log_management.py cleanup --days 30

# Compress old logs
python scripts/log_management.py compress --days 7

# Export logs for analysis
python scripts/log_management.py export trading --format json --output trading_export.json
```

### Programmatic Management

```python
from core.logging.log_management import (
    LogRotationManager,
    LogAnalyzer,
    LogExporter
)

# Log rotation and cleanup
rotation_manager = LogRotationManager(settings)
status = rotation_manager.get_all_log_status()
cleanup_stats = rotation_manager.cleanup_old_logs(30)

# Log analysis
analyzer = LogAnalyzer(settings)
analysis = analyzer.analyze_channel_logs(LogChannel.TRADING, 1000)
health_summary = analyzer.get_log_health_summary()

# Log export
exporter = LogExporter(settings)
json_file = await exporter.export_channel_logs(LogChannel.AUDIT, "json")
```

## API Integration

### REST Endpoints

The logging system provides REST API endpoints for external monitoring tools:

```http
GET /api/v1/logs/status           # Channel status and file sizes
GET /api/v1/logs/health           # Log health summary
GET /api/v1/logs/analyze/{channel}  # Analyze specific channel
GET /api/v1/logs/tail/{channel}   # Get last N lines from channel
GET /api/v1/logs/search/{channel} # Search logs for patterns
POST /api/v1/logs/export/{channel} # Export logs in JSON/CSV
POST /api/v1/logs/cleanup         # Clean up old log files  
POST /api/v1/logs/compress        # Compress old log files
```

### API Usage Examples

```python
import requests

# Get log status
response = requests.get("http://localhost:8000/api/v1/logs/status")
status = response.json()

# Analyze trading logs
response = requests.get("http://localhost:8000/api/v1/logs/analyze/trading?lines=500")
analysis = response.json()

# Search for errors
response = requests.get("http://localhost:8000/api/v1/logs/search/errors?query=RuntimeError")
search_results = response.json()
```

## Advanced Features

### Structured Logging

All logs use structured JSON format with consistent fields:

```json
{
  "timestamp": "2025-08-20T10:30:00.123Z",
  "level": "INFO",
  "component": "strategy_manager", 
  "channel": "trading",
  "correlation_id": "abc123def",
  "message": "Strategy signal generated",
  "business_context": {
    "strategy_name": "momentum_v1",
    "instrument": "RELIANCE",
    "signal_type": "BUY",
    "confidence": 0.85
  }
}
```

### Performance Monitoring

Built-in performance tracking with metrics:

```python
# Automatic performance logging
@log_system_performance("data_processing", critical_threshold_ms=1000)
async def process_market_data(data):
    # Processing logic
    return processed_data

# Manual performance logging  
system_performance_logger.latency_metrics(
    operation="api_request",
    component="auth_router",
    latency_ms=25.3,
    target_latency_ms=50.0
)
```

### Business Metrics

Specialized logging for business events:

```python
# Order lifecycle tracking
trading_audit_logger.order_lifecycle_event("placed", ...)
trading_audit_logger.order_lifecycle_event("filled", ...)
trading_audit_logger.order_lifecycle_event("cancelled", ...)

# Risk management events
trading_audit_logger.risk_event(
    event_type="breach",
    strategy_name="momentum_v1", 
    risk_type="position_limit",
    current_value=95000,
    limit_value=100000,
    breach_level="warning"
)

# Performance metrics
system_performance_logger.throughput_metrics(
    operation="tick_processing",
    component="storage_manager",
    count=10000,
    time_window_seconds=60.0
)
```

## Migration Guide

### Backward Compatibility

Existing code continues to work without changes:

```python
# Existing code (still works)
from core.logging import get_logger
logger = get_logger("component_name")
logger.info("Message")  # Automatically routed to appropriate channel
```

### Enhanced Usage

For new code, use channel-specific loggers:

```python
# Enhanced approach
from core.logging import get_trading_logger
logger = get_trading_logger("component_name")  # Explicitly routes to trading.log
```

### Migration Steps

1. **Enable multi-channel logging** (automatic when available)
2. **Update key components** to use channel-specific loggers
3. **Add business event logging** with specialized loggers  
4. **Implement performance decorators** for critical operations
5. **Set up log management automation**

## Testing

### Unit Tests

```bash
# Run logging system tests
TESTING=true python -m pytest tests/test_multi_channel_logging.py -v

# Test specific functionality
TESTING=true python -m pytest tests/test_multi_channel_logging.py::TestBusinessLoggers -v
```

### Integration Testing

```python
from core.logging import initialize_multi_channel_logging, get_trading_logger

# Test integration
settings = Settings(secret_key="test_key")
manager = initialize_multi_channel_logging(settings)

trading_logger = get_trading_logger("test_component")
trading_logger.info("Test message", test_data="integration_test")

# Verify log files created
assert (settings.logs_dir / "trading.log").exists()
```

## Benefits Achieved

### Operational Improvements

1. **Faster Troubleshooting**
   - Component-specific log files reduce noise
   - Targeted analysis for specific issues
   - Clear separation of concerns

2. **Better Performance**
   - Reduced I/O contention from single file bottleneck
   - Database query noise isolated to separate file
   - Independent log rotation policies

3. **Enhanced Monitoring**
   - Business metrics separated from technical logs
   - Audit trail compliance with long retention
   - Performance monitoring with structured metrics

4. **Operational Excellence**
   - Automated log management and cleanup
   - API-driven log analysis and export
   - Command-line tools for operations

### Production Readiness

1. **Compliance Support**
   - Dedicated audit logs with 365-day retention
   - Structured business event logging
   - Regulatory-ready audit trails

2. **Scalability**
   - Independent file growth and rotation
   - Channel-specific retention policies
   - Automated compression and cleanup

3. **Monitoring Integration**
   - REST API for external monitoring tools
   - Health checks and status endpoints
   - Export capabilities for analysis tools

## Troubleshooting

### Common Issues

1. **Multi-channel not available**
   ```python
   from core.logging import MULTI_CHANNEL_AVAILABLE
   if not MULTI_CHANNEL_AVAILABLE:
       print("Falling back to single-file logging")
   ```

2. **Log files not created**
   ```python
   from core.logging.log_management import ensure_log_directory_structure
   ensure_log_directory_structure(settings.logs_dir)
   ```

3. **Performance issues**
   ```bash
   # Check log file sizes
   python scripts/log_management.py status
   
   # Clean up old logs
   python scripts/log_management.py cleanup --days 7
   ```

### Debug Mode

Enable debug logging for troubleshooting:

```env
LOG_LEVEL=DEBUG
MONITORING__LOG_JSON_FORMAT=false  # Human-readable format
```

## Performance Considerations

- **Channel-specific rotation**: Each channel has independent rotation policies
- **Automatic compression**: Old files are compressed to save space
- **Cached loggers**: Logger instances are cached for performance
- **Structured format**: JSON logging for efficient parsing
- **Asynchronous operations**: Non-blocking log operations

## Future Enhancements

### 🔄 **Planned: Console vs File Verbosity Control**

**Current Limitation**: Both terminal (console) and file logging currently use identical settings:
- Same log level (`settings.log_level` for both)
- Same format decision (`get_effective_json_logs()` for both)
- No separate verbosity control

**Enhancement Goal**: Enable clean terminal output while maintaining detailed file logs:

```python
# Proposed configuration additions in monitoring_config.py:
log_console_level: str = Field(default="WARNING")       # Higher threshold for terminal
log_console_json_format: bool = Field(default=False)    # Human-readable terminal format
log_file_level: str = Field(default="DEBUG")            # More verbose for files
log_file_json_format: bool = Field(default=True)        # Structured format for files
```

**Implementation Areas**:
1. **Settings Enhancement**: Add separate console/file configurations
2. **Logger Configuration**: Modify `core/logging/logger.py` to use different levels/formats
3. **Component Filtering**: Show only critical events in terminal, log everything to files
4. **Channel-Specific Terminal Control**: Configure which channels appear in console

**Benefits**:
- Clean, focused terminal output for development
- Comprehensive file logs for debugging and auditing
- Improved developer experience with reduced noise
- Maintained operational visibility in files

**Priority**: Medium - Enhances developer experience without affecting core functionality

**Expected Timeline**: 1-2 weeks implementation

### 🚀 **Future: Real-time Log Streaming**

**Enhancement Goal**: Enable real-time log monitoring and streaming capabilities for operational dashboards and monitoring tools.

**Proposed Features**:
- **WebSocket Endpoints**: Real-time log tailing through WebSocket connections
- **Event Subscriptions**: Subscribe to specific log channels or patterns
- **Dashboard Integration**: Live log feeds for monitoring dashboards
- **Filtering**: Real-time filtering by level, component, or custom patterns

**Implementation Areas**:
```python
# WebSocket endpoint examples:
GET /ws/logs/tail/{channel}           # Real-time log tailing
GET /ws/logs/subscribe/{pattern}      # Pattern-based subscriptions
GET /ws/logs/errors                   # Real-time error notifications
```

**Use Cases**:
- Operations dashboards with live log feeds
- Real-time error alerting and notifications
- Development debugging with live log streaming
- Performance monitoring with real-time metrics

**Priority**: Low - Advanced operational feature

**Expected Timeline**: 3-4 weeks implementation

### 🏗️ **Advanced: Log Aggregation and External Integration**

**Enhancement Goal**: Enable enterprise-scale log aggregation and integration with external monitoring systems.

**Proposed Integrations**:

1. **ELK Stack Integration**:
   - **Elasticsearch**: Log storage and indexing
   - **Logstash**: Log processing and transformation
   - **Kibana**: Advanced log visualization and analysis
   - **Beats**: Log shipping and forwarding

2. **Log Shipping**:
   - **Fluentd**: Unified logging layer
   - **Vector**: High-performance log router
   - **Custom Exporters**: Direct integration with external systems

3. **Cloud Logging Services**:
   - **AWS CloudWatch**: Amazon cloud logging
   - **Google Cloud Logging**: Google cloud integration
   - **Azure Monitor**: Microsoft cloud logging
   - **DataDog**: Application performance monitoring

**Implementation Strategy**:
```python
# Configuration example:
log_shipping_enabled: bool = Field(default=False)
log_shipping_destinations: List[str] = Field(default=[])
elasticsearch_url: Optional[str] = Field(default=None)
fluentd_endpoint: Optional[str] = Field(default=None)
```

**Benefits**:
- Centralized log management across multiple AlphaPT instances
- Advanced log analytics and correlation
- Long-term log retention and compliance
- Integration with existing enterprise monitoring infrastructure

**Priority**: Low - Enterprise feature for large-scale deployments

**Expected Timeline**: 4-6 weeks implementation

---

## Best Practices

1. **Use appropriate channels**: Route logs to the most relevant channel
2. **Include context**: Add relevant business context to log messages
3. **Monitor performance**: Use decorators for automatic performance tracking
4. **Set retention policies**: Configure appropriate retention for each channel
5. **Regular cleanup**: Enable automatic cleanup for operational efficiency
6. **Structured data**: Use structured logging for better analysis capabilities
7. **Terminal vs File Strategy**: Consider implementing separate verbosity controls for optimal UX

---

**Implementation Status**: ✅ Complete (Core System) | 🔄 Enhancement Planned (Console/File Separation)  
**Documentation Date**: August 2025  
**Version**: 1.0