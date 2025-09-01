# Core Monitoring Framework

**Status**: ✅ **PRODUCTION-READY** | 📊 **Prometheus Integration** | 🔄 **Centralized Registry** | 🏥 **Health Monitoring**

## Advanced Monitoring Architecture

Alpha Panda implements a comprehensive monitoring system with:
- **Centralized Metrics Registry**: Prevents key drift between components
- **Prometheus Integration**: Industry-standard metrics collection and alerting
- **Pipeline Health Validation**: End-to-end flow monitoring with bottleneck detection
- **Multi-Broker Monitoring**: Separate metrics tracking for paper and live trading
- **Performance Metrics**: Real-time throughput, latency, and error tracking

## 📁 Core Monitoring Components

```
core/monitoring/
├── README.md                          # This documentation
├── __init__.py                        # Monitoring framework exports
├── alerting.py                        # Alert manager and notification system
├── health_checker.py                  # Comprehensive system health validation
├── metrics_registry.py                # ✅ NEW - Centralized key management
├── pipeline_validator.py              # End-to-end pipeline flow monitoring
└── prometheus_metrics.py              # ✅ NEW - Production metrics integration
```

## Centralized Metrics Registry

### Purpose
The `MetricsRegistry` class prevents monitoring key drift between metric writers and readers - a critical production issue that causes monitoring blindness.

### Key Management
```python
from core.monitoring.metrics_registry import MetricsRegistry

# Shared market data keys
market_ticks_key = MetricsRegistry.market_ticks_last()  
# Returns: "pipeline:market_ticks:market:last"

# Broker-specific signal keys  
signals_key = MetricsRegistry.signals_last("paper")
# Returns: "pipeline:signals:paper:last"

# Broker-specific order keys
orders_key = MetricsRegistry.orders_last("zerodha")
# Returns: "pipeline:orders:zerodha:last"

# Health check keys
health_key = MetricsRegistry.health_check_result("trading_engine", "kafka_producer")
# Returns: "health_check:result:trading_engine:kafka_producer"
```

### Consistency Validation
```python
# Validate all keys for active brokers
active_brokers = ["paper", "zerodha"]
validation_result = MetricsRegistry.validate_key_consistency(active_brokers)

print(f"Total metrics keys: {validation_result['total_keys']}")
print(f"All keys: {validation_result['keys']}")
```

## Prometheus Metrics Integration

Note: The API exposes a shared Prometheus registry at `/metrics`. Collectors should register against the DI‑provided registry to ensure one scrape source for the whole app.

### Production Metrics Collection
```python
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector

# Create metrics collector
metrics = PrometheusMetricsCollector()

# Record business events
metrics.record_signal_generated("momentum_strategy", "paper", "BUY")
metrics.record_order_executed("zerodha", "market", "filled")

# Track system performance
metrics.record_processing_time("strategy_runner", "market_tick", 0.005)

# Monitor system health
metrics.set_pipeline_health("signal_generation", "paper", True)
metrics.set_connection_status("zerodha_api", "zerodha", True)

# Track strategy performance
metrics.set_strategy_pnl("momentum_strategy", "paper", 1250.50)
```

### Automatic Timing Context Manager
```python
from core.monitoring.prometheus_metrics import MetricsContextManager

# Automatic timing for operations
with MetricsContextManager(metrics, "portfolio_manager", "position_update"):
    # Operation is automatically timed
    await portfolio_manager.update_position(order_fill)
```

### Available Metrics

#### Business Metrics
- **Signal Generation**: `trading_signals_generated_total{strategy_id, broker, signal_type}`
- **Order Execution**: `trading_orders_executed_total{broker, order_type, status}`  
- **Strategy Performance**: `strategy_pnl_current{strategy_id, broker}`
- **Market Data**: `market_ticks_received_total{source}`
- **DLQ Messages**: `trading_dlq_messages_total{service, broker}` (increments on DLQ publish)

#### System Performance Metrics
- **Processing Latency**: `trading_processing_latency_seconds{service, event_type}`
- **Event Throughput**: `trading_events_processed_total{service, broker, event_type}`
- **Pipeline Health**: `trading_pipeline_stage_healthy{stage, broker}`
- **Connection Status**: `trading_connection_status{connection_type, broker}`

#### Infrastructure Metrics
- **Cache Performance**: `cache_hits_total{cache_type}`, `cache_misses_total{cache_type}`
- **Error Tracking**: `trading_errors_total{component, error_type, broker}`

## Health Monitoring System

### ServiceHealthChecker
```python
from core.health.health_checker import ServiceHealthChecker
from core.config.settings import Settings

# Initialize with dependencies
settings = Settings()
health_checker = ServiceHealthChecker(
    settings=settings,
    redis_client=redis_client,
    kafka_producer=kafka_producer,
    kafka_consumer=kafka_consumer,
    auth_service=auth_service
)

# Start continuous health monitoring
await health_checker.start()

# Get current health status
health_status = await health_checker.get_overall_health()
print(f"System status: {health_status['status']}")
print(f"Active brokers: {health_status['active_brokers']}")
```

### Health Check Categories
- **🚨 Critical**: Authentication, database, streaming components
- **⚠️ Important**: Redis cache, system resources, network connectivity  
- **📊 Pipeline**: Market data flow, signal generation, order execution
- **💾 System**: Memory usage, disk space, CPU utilization

### Health Status Levels
- **✅ Healthy**: All systems operating normally
- **⚠️ Degraded**: Non-critical issues detected, reduced functionality
- **❌ Unhealthy**: Critical failures requiring immediate attention  
- **❓ Unknown**: Health status cannot be determined

## Pipeline Flow Validation

### PipelineValidator
```python
from core.monitoring.pipeline_validator import PipelineValidator

# Initialize for specific broker
validator = PipelineValidator(
    settings=settings,
    redis_client=redis_client,
    broker="paper"  # or "zerodha"
)

# Validate end-to-end pipeline flow
validation_result = await validator.validate_end_to_end_flow()

print(f"Overall health: {validation_result['overall_health']}")
print(f"Bottlenecks: {validation_result['bottlenecks']}")
print(f"Recommendations: {validation_result['recommendations']}")
```

### Pipeline Stages Monitored
1. **Market Data Flow**: Tick ingestion and distribution
2. **Signal Generation**: Strategy processing and signal creation
3. **Risk Validation**: Signal validation and filtering
4. **Order Execution**: Order placement and fill processing
5. **Portfolio Updates**: Position and P&L updates

### Bottleneck Detection
- **Latency Thresholds**: Configurable per-stage performance limits
- **Flow Rate Monitoring**: Events per minute tracking
- **Graceful Degradation**: Startup grace periods and market hours awareness
- **Root Cause Analysis**: Detailed recommendations for performance issues

## Usage Examples

### Basic Monitoring Setup
```python
from core.monitoring.prometheus_metrics import create_metrics_collector
from core.monitoring.metrics_registry import MetricsRegistry

# Initialize metrics
metrics = create_metrics_collector()

# Use centralized registry for consistent keys
market_key = MetricsRegistry.market_ticks_count()
broker_signals_key = MetricsRegistry.signals_last("paper")

# Record events with proper metrics
metrics.record_market_tick("zerodha")
metrics.record_signal_generated("momentum_strategy", "paper", "BUY")
```

### Health Monitoring Integration
```python
from core.health.health_checker import ServiceHealthChecker
from core.monitoring.pipeline_validator import PipelineValidator

# Setup health monitoring
health_checker = ServiceHealthChecker(settings, redis_client=redis)
pipeline_validator = PipelineValidator(settings, redis_client=redis, broker="paper")

# Start monitoring
await health_checker.start()

# Get comprehensive system status
health_status = await health_checker.get_overall_health()
pipeline_status = await pipeline_validator.validate_end_to_end_flow()

if health_status["status"] != "healthy":
    print(f"Health issues detected: {health_status['summary']}")

if pipeline_status["overall_health"] != "healthy":
    print(f"Pipeline bottlenecks: {pipeline_status['bottlenecks']}")
```

### Performance Monitoring
```python
from core.monitoring.prometheus_metrics import MetricsContextManager

# Monitor strategy processing performance
async def process_market_tick(tick, strategy_executor):
    with MetricsContextManager(metrics, "strategy_runner", "tick_processing"):
        signal = strategy_executor.process_tick(tick)
        if signal:
            metrics.record_signal_generated(
                strategy_executor.config.strategy_id,
                strategy_executor.context.broker,
                signal.signal_type
            )
        return signal
```

## Configuration

### Monitoring Settings
```python
# In core/config/settings.py
class MonitoringSettings(BaseSettings):
    health_check_enabled: bool = True
    health_check_interval: int = 30  # seconds
    pipeline_flow_monitoring_enabled: bool = True
    
    # Performance thresholds
    market_data_latency_threshold: float = 1.0  # seconds
    memory_alert_threshold: float = 0.85  # 85% usage
    disk_alert_threshold: float = 0.90   # 90% usage
    cpu_alert_threshold: float = 0.80    # 80% usage
    consumer_lag_threshold: int = 1000   # messages
```

### Alerting Configuration  
```python
# In core/monitoring/alerting.py
alert_manager = get_alert_manager(settings)

# Critical system alerts
await alert_manager.send_alert(
    title="Trading Engine Health Check Failed",
    message="Critical component failure detected",
    severity=AlertSeverity.CRITICAL,
    category=AlertCategory.SYSTEM,
    component="trading_engine",
    broker_namespace="zerodha"
)
```

## Recent Improvements (2025-08-29)

### Centralized Key Management
- **MetricsRegistry**: Single source of truth for all monitoring keys
- **Consistent Naming**: Standardized `pipeline:stage:broker:metric` pattern
- **Key Validation**: Automated consistency checking across components
- **Drift Prevention**: Eliminates mismatched keys between writers and readers

### Production Metrics Integration
- **Prometheus Integration**: Industry-standard metrics collection
- **Business Metrics**: Trading signals, orders, P&L, strategy performance
- **System Metrics**: Processing latency, throughput, error rates, connection health
- **Custom Registries**: Isolated test environments with separate metric collections

### Enhanced Health Monitoring
- **Multi-Broker Awareness**: Separate health tracking for paper and live trading
- **Pipeline Validation**: End-to-end flow monitoring with bottleneck detection
- **Graceful Degradation**: Startup grace periods and intelligent failure handling
- **Actionable Recommendations**: Specific guidance for performance optimization

## Testing

The monitoring framework is fully tested with the advanced testing architecture:

```bash
# Test monitoring components
python -m pytest tests/unit/monitoring/ -v

# Test metrics registry consistency
python -m pytest tests/unit/monitoring/test_metrics_registry.py -v

# Test Prometheus metrics integration
python -m pytest tests/unit/monitoring/test_prometheus_metrics.py -v

# Test metric key namespacing and topic routing (added)
python -m pytest tests/unit/test_metrics_registry_keys.py -v
python -m pytest tests/unit/test_topic_routing.py -v
```

The monitoring system supports the modern composition-based strategy framework while maintaining full compatibility with legacy inheritance-based strategies currently running in production.
> Compatibility note: historical use of a global `broker_namespace` label for metrics may still appear in some keys for backward compatibility. New code should always pass explicit `broker`/`broker_context`. Over time, migrate remaining metrics and dashboards away from `broker_namespace` to avoid ambiguity.
