# Core Health Module

## Overview

The `core/health/` module provides comprehensive health checking and monitoring capabilities for Alpha Panda services. It implements health checks for all system components including databases, message brokers, external APIs, and service-level health validation.

## Components

### `health_checker.py`
Main health checking framework with comprehensive monitoring:

- **HealthChecker**: Main health checking orchestrator
- **ComponentHealthCheck**: Individual component health validation
- **SystemHealthAggregator**: System-wide health status aggregation
- **AlertingIntegration**: Integration with monitoring and alerting systems
- **HealthStatus Enum**: Standardized health status levels (healthy, degraded, unhealthy, unknown)

### `multi_broker_health_checks.py`
Multi-broker specific health checks:

- **BrokerHealthChecker**: Health checks for trading broker connections
- **MultiBrokerHealthAggregator**: Aggregated health across all active brokers
- **AuthenticationHealthCheck**: Broker authentication validation
- **MarketDataHealthCheck**: Market data feed health validation

### `__init__.py`
Health module exports and utilities for easy import across the application.

## Key Features

- **Comprehensive Monitoring**: Database, Redis, Kafka, API, and service health checks
- **Multi-Broker Support**: Health validation across paper and Zerodha brokers
- **Alerting Integration**: Integration with monitoring and alert management systems
- **Performance Metrics**: Health check execution time and reliability tracking
- **Configurable Thresholds**: Customizable health check parameters and thresholds
- **Async Support**: Non-blocking health check execution
- **Health Aggregation**: System-wide health status rollup

## Usage

### Basic Health Checking
```python
from core.health.health_checker import HealthChecker
from core.config.settings import get_settings

# Initialize health checker
settings = get_settings()
health_checker = HealthChecker(settings)

# Perform system health check
health_status = await health_checker.check_system_health()
print(f"System health: {health_status.overall_status}")

# Check individual components
db_health = await health_checker.check_database_health()
redis_health = await health_checker.check_redis_health()
kafka_health = await health_checker.check_kafka_health()
```

### Multi-Broker Health Monitoring
```python
from core.health.multi_broker_health_checks import MultiBrokerHealthChecker

# Initialize multi-broker health checker
multi_broker_checker = MultiBrokerHealthChecker(settings)

# Check all broker health
broker_health = await multi_broker_checker.check_all_brokers_health()

# Check specific broker
zerodha_health = await multi_broker_checker.check_broker_health("zerodha")
paper_health = await multi_broker_checker.check_broker_health("paper")
```

### Service Integration
```python
from core.health import HealthChecker

class MyService:
    def __init__(self, settings):
        self.health_checker = HealthChecker(settings)
    
    async def health_check(self):
        """Service-specific health check endpoint"""
        return await self.health_checker.check_service_health()
    
    async def ready_check(self):
        """Readiness probe for Kubernetes"""
        return await self.health_checker.check_readiness()
```

## Health Check Types

### System Health Checks
- **Database Connectivity**: PostgreSQL connection and query validation
- **Redis Cache**: Redis connection and basic operations
- **Message Broker**: Kafka/Redpanda connectivity and topic access
- **External APIs**: Zerodha API and other external service health

### Service Health Checks  
- **Process Health**: Memory usage, CPU utilization, and resource monitoring
- **Service Dependencies**: Dependent service availability
- **Configuration Validation**: Settings and configuration consistency
- **Performance Metrics**: Response times and throughput validation

### Broker-Specific Health Checks
- **Authentication Status**: Broker login and session validation
- **Market Data Feed**: Real-time data feed connectivity
- **Order Management**: Order placement and management capabilities
- **Position Tracking**: Portfolio and position data accuracy

## Health Status Levels

### Status Definitions
- **HEALTHY**: All systems operating normally
- **DEGRADED**: Some non-critical issues detected, but system functional
- **UNHEALTHY**: Critical issues detected, system may not function properly
- **UNKNOWN**: Unable to determine health status

### Status Aggregation Rules
- **System Status**: Worst status among all critical components
- **Component Status**: Based on individual health check results
- **Broker Status**: Aggregated across all active brokers
- **Service Status**: Based on service-specific health criteria

## Configuration

Health check configuration through settings:

```python
# Health settings in core/config/settings.py
class HealthSettings(BaseModel):
    check_interval_seconds: int = 30
    timeout_seconds: int = 5
    retry_attempts: int = 3
    alert_thresholds: Dict[str, float] = {
        "database_response_time": 0.5,
        "redis_response_time": 0.1,
        "kafka_response_time": 1.0
    }
```

## Monitoring Integration

### Alerting Integration
```python
# Automatic alert generation for health issues
from core.health.health_checker import HealthChecker
from core.monitoring.alerting import AlertManager

health_checker = HealthChecker(settings)
health_status = await health_checker.check_system_health()

# Alerts are automatically sent for unhealthy components
if health_status.overall_status == HealthStatus.UNHEALTHY:
    # Critical alerts sent automatically
    pass
```

### Metrics Collection
```python
# Health check metrics for monitoring
health_metrics = await health_checker.get_health_metrics()
print(f"Database response time: {health_metrics['database_response_time']}ms")
print(f"Last successful health check: {health_metrics['last_success']}")
```

## Architecture Patterns

- **Observer Pattern**: Health status change notifications
- **Circuit Breaker**: Failing health checks trigger service degradation
- **Aggregation Pattern**: System health rolled up from component health
- **Async Execution**: Non-blocking health check execution
- **Timeout Handling**: Health checks with configurable timeouts
- **Retry Logic**: Configurable retry attempts for transient failures

## Best Practices

1. **Regular Monitoring**: Implement continuous health monitoring
2. **Appropriate Timeouts**: Set reasonable timeouts for health checks
3. **Graceful Degradation**: Handle health check failures gracefully
4. **Alert Fatigue Prevention**: Use appropriate alert thresholds
5. **Resource Monitoring**: Monitor system resources (CPU, memory, disk)
6. **Dependency Validation**: Check all external dependencies

## Dependencies

- **psutil**: System resource monitoring
- **asyncio**: Async health check execution
- **core.monitoring**: Integration with monitoring and alerting
- **core.config**: Health check configuration management