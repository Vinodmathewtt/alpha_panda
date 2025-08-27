# Alpha Panda Monitoring and Observability Implementation Guide

This document provides a comprehensive guide for implementing the remaining monitoring and observability features in Alpha Panda. The enhanced logging system and health checks have been implemented, but several critical monitoring features still need to be completed.

## Current Implementation Status ✅

### Completed Features:
1. **Enhanced Logging Configuration** - Configurable JSON/plain text logging formats
2. **Multi-Channel Logging** - Dedicated log files for different components (trading, market_data, api, etc.)
3. **Centralized Logs Directory** - Organized log storage in `/logs` directory with rotation
4. **Health Check System** - Comprehensive health checking for all services
5. **Basic Service Logging Enhancement** - Market Feed and Strategy Runner services updated

### Enhanced Logging Features Implemented:
- **Configurable Formats**: JSON for files, plain text for console
- **Multi-Channel Logging**: Separate log files per component type
- **Log Rotation**: Configurable file sizes and backup counts
- **Channel-Specific Levels**: Different log levels per component
- **Backward Compatibility**: Legacy logging functions still work

### Files Created/Updated:
- `core/config/settings.py` - Added LoggingSettings and MonitoringSettings
- `core/logging/channels.py` - Logging channel definitions and configuration
- `core/logging/enhanced_logging.py` - Enhanced logging manager implementation
- `core/logging/__init__.py` - Updated with backward-compatible enhanced logging
- `core/health/health_checker.py` - Comprehensive health checking system
- `core/health/__init__.py` - Updated health module exports

## Remaining Implementation Tasks 🚧

### 1. Complete Service Logging Enhancement
**Priority: HIGH** | **Effort: Medium**

#### Services Still Need Updates:
```bash
services/risk_manager/service.py
services/trading_engine/service.py
services/portfolio_manager/service.py
```

#### Implementation Pattern:
```python
# Replace imports
from core.logging import get_trading_logger_safe, get_performance_logger_safe, get_error_logger_safe

# Replace logger initialization
self.logger = get_trading_logger_safe("service_name")
self.perf_logger = get_performance_logger_safe("service_name_performance") 
self.error_logger = get_error_logger_safe("service_name_errors")

# Add pipeline monitoring metrics
self.processed_count = 0
self.last_processed_time = None
self.error_count = 0
```

#### Add Structured Logging Throughout Services:
```python
# Information logging
self.logger.info("Processing signal", 
                signal_id=signal.id,
                strategy_id=signal.strategy_id,
                symbol=signal.symbol,
                broker=self.settings.broker_namespace)

# Performance logging  
self.perf_logger.info("Signal processing completed",
                     processing_time_ms=duration_ms,
                     signals_processed=self.processed_count,
                     throughput_per_sec=throughput)

# Error logging
self.error_logger.error("Signal processing failed",
                       signal_id=signal.id,
                       error=str(e),
                       stacktrace=traceback.format_exc())
```

### 2. Pipeline Flow Monitoring and Metrics
**Priority: HIGH** | **Effort: High**

#### Create Pipeline Metrics Collector:
```python
# File: core/monitoring/pipeline_metrics.py
class PipelineMetricsCollector:
    """Collects and tracks pipeline flow metrics across all services."""
    
    def __init__(self, redis_client, settings):
        self.redis = redis_client
        self.settings = settings
        
    async def record_market_tick(self, tick_data):
        """Record market tick received"""
        await self.redis.setex(
            f"pipeline:market_ticks:{self.settings.broker_namespace}:last",
            300,  # 5 min TTL
            json.dumps({
                "timestamp": datetime.utcnow().isoformat(),
                "symbol": tick_data.symbol,
                "tick_count": await self.redis.incr(f"pipeline:market_ticks:{self.settings.broker_namespace}:count")
            })
        )
        
    async def record_signal_generated(self, signal):
        """Record trading signal generated"""
        await self.redis.setex(
            f"pipeline:signals:{self.settings.broker_namespace}:last",
            300,
            json.dumps({
                "timestamp": datetime.utcnow().isoformat(),
                "signal_id": signal.id,
                "strategy_id": signal.strategy_id,
                "signal_count": await self.redis.incr(f"pipeline:signals:{self.settings.broker_namespace}:count")
            })
        )
    
    async def record_order_processed(self, order):
        """Record order processed by trading engine"""
        await self.redis.setex(
            f"pipeline:orders:{self.settings.broker_namespace}:last",
            300,
            json.dumps({
                "timestamp": datetime.utcnow().isoformat(),
                "order_id": order.id,
                "status": order.status,
                "order_count": await self.redis.incr(f"pipeline:orders:{self.settings.broker_namespace}:count")
            })
        )
    
    async def get_pipeline_health(self):
        """Get overall pipeline health status"""
        now = datetime.utcnow()
        health = {}
        
        # Check each stage for recent activity
        for stage in ["market_ticks", "signals", "orders"]:
            key = f"pipeline:{stage}:{self.settings.broker_namespace}:last"
            data = await self.redis.get(key)
            
            if data:
                last_activity = json.loads(data)
                last_time = datetime.fromisoformat(last_activity["timestamp"])
                age_seconds = (now - last_time).total_seconds()
                
                health[stage] = {
                    "last_activity": last_activity,
                    "age_seconds": age_seconds,
                    "healthy": age_seconds < 60,  # Consider healthy if activity within 1 minute
                }
            else:
                health[stage] = {
                    "last_activity": None,
                    "age_seconds": float('inf'),
                    "healthy": False,
                }
        
        return health
```

#### Integrate Metrics in Services:
```python
# In each service __init__
from core.monitoring.pipeline_metrics import PipelineMetricsCollector
self.metrics_collector = PipelineMetricsCollector(redis_client, settings)

# In processing methods
await self.metrics_collector.record_market_tick(tick_data)  # Market Feed
await self.metrics_collector.record_signal_generated(signal)  # Strategy Runner
await self.metrics_collector.record_order_processed(order)  # Trading Engine
```

### 3. Enhance Streaming Path Observability with Correlation IDs
**Priority: HIGH** | **Effort: Medium**

#### Update Event Schemas:
```python
# File: core/schemas/events.py - Enhance EventEnvelope
@dataclass
class EventEnvelope:
    # ... existing fields ...
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_trace_id: Optional[str] = None
    
    def create_child_event(self, event_type: str, data: Any) -> 'EventEnvelope':
        """Create child event with trace inheritance"""
        return EventEnvelope(
            id=str(uuid7()),
            event_type=event_type,
            timestamp=datetime.utcnow(),
            source=self.source,
            broker=self.broker,
            data=data,
            correlation_id=self.correlation_id,
            causation_id=self.id,
            trace_id=self.trace_id,  # Inherit trace
            parent_trace_id=self.id  # Link parent
        )
```

#### Add Trace Logging:
```python
# In StreamProcessor base class
def log_with_trace(self, message: str, level: str = "info", **kwargs):
    """Log with trace context"""
    trace_context = {
        "trace_id": getattr(self, 'current_trace_id', None),
        "correlation_id": getattr(self, 'current_correlation_id', None),
        "service": self.name,
        "broker": self.settings.broker_namespace,
    }
    
    log_data = {**trace_context, **kwargs}
    getattr(self.logger, level)(message, **log_data)

# In event processing
async def process_message(self, message):
    envelope = EventEnvelope.from_message(message)
    self.current_trace_id = envelope.trace_id
    self.current_correlation_id = envelope.correlation_id
    
    self.log_with_trace("Processing event",
                       event_type=envelope.event_type,
                       event_id=envelope.id)
```

### 4. End-to-End Pipeline Validation Monitoring
**Priority: MEDIUM** | **Effort: High**

#### Create Pipeline Validator:
```python
# File: core/monitoring/pipeline_validator.py
class PipelineValidator:
    """Validates end-to-end pipeline flow and detects bottlenecks"""
    
    def __init__(self, settings, redis_client):
        self.settings = settings
        self.redis = redis_client
        self.logger = get_monitoring_logger_safe("pipeline_validator")
        
    async def validate_end_to_end_flow(self) -> Dict[str, Any]:
        """Validate complete pipeline flow from market data to orders"""
        validation_id = str(uuid.uuid4())
        
        results = {
            "validation_id": validation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "broker": self.settings.broker_namespace,
            "stages": {},
            "overall_health": "unknown"
        }
        
        # Stage 1: Market Data Flow
        market_health = await self._validate_market_data_flow()
        results["stages"]["market_data"] = market_health
        
        # Stage 2: Strategy Processing
        strategy_health = await self._validate_strategy_processing()
        results["stages"]["strategy_processing"] = strategy_health
        
        # Stage 3: Risk Management
        risk_health = await self._validate_risk_management()
        results["stages"]["risk_management"] = risk_health
        
        # Stage 4: Trade Execution
        execution_health = await self._validate_trade_execution()
        results["stages"]["trade_execution"] = execution_health
        
        # Stage 5: Portfolio Updates
        portfolio_health = await self._validate_portfolio_updates()
        results["stages"]["portfolio_updates"] = portfolio_health
        
        # Calculate overall health
        all_healthy = all(
            stage.get("healthy", False) 
            for stage in results["stages"].values()
        )
        
        results["overall_health"] = "healthy" if all_healthy else "degraded"
        
        return results
    
    async def _validate_market_data_flow(self) -> Dict[str, Any]:
        """Validate market data is flowing correctly"""
        # Check for recent ticks in Redis
        ticks_key = f"pipeline:market_ticks:{self.settings.broker_namespace}:last"
        last_tick = await self.redis.get(ticks_key)
        
        if last_tick:
            tick_data = json.loads(last_tick)
            age = (datetime.utcnow() - datetime.fromisoformat(tick_data["timestamp"])).total_seconds()
            
            return {
                "healthy": age < self.settings.monitoring.market_data_latency_threshold,
                "last_tick_age_seconds": age,
                "message": f"Last tick {age:.1f}s ago"
            }
        else:
            return {
                "healthy": False,
                "message": "No recent market data found"
            }
    
    # Similar implementations for other validation methods...
```

#### Add Periodic Pipeline Validation:
```python
# File: core/monitoring/pipeline_monitor.py
class PipelineMonitor:
    """Continuous pipeline monitoring and alerting"""
    
    def __init__(self, settings):
        self.settings = settings
        self.validator = PipelineValidator(settings, redis_client)
        self.logger = get_monitoring_logger_safe("pipeline_monitor")
        self._running = False
        self._monitor_task = None
    
    async def start(self):
        """Start pipeline monitoring"""
        if self._running:
            return
            
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        self._running = True
        self.logger.info("Pipeline monitoring started")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                # Run end-to-end validation
                validation_results = await self.validator.validate_end_to_end_flow()
                
                # Log results
                if validation_results["overall_health"] == "healthy":
                    self.logger.info("Pipeline validation passed", **validation_results)
                else:
                    self.logger.warning("Pipeline validation failed", **validation_results)
                
                # Store results for API access
                await self.redis.setex(
                    f"pipeline:validation:{self.settings.broker_namespace}",
                    300,  # 5 min TTL
                    json.dumps(validation_results)
                )
                
                await asyncio.sleep(self.settings.monitoring.health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Pipeline monitoring error", error=str(e))
                await asyncio.sleep(30)  # Wait before retrying
```

### 5. Update Configuration Support
**Priority: LOW** | **Effort: Low**

#### Environment Variables to Add:
```bash
# .env additions
LOGGING__JSON_FORMAT=true
LOGGING__CONSOLE_JSON_FORMAT=false
LOGGING__MULTI_CHANNEL_ENABLED=true
LOGGING__FILE_ENABLED=true
LOGGING__LOGS_DIR=logs

MONITORING__HEALTH_CHECK_ENABLED=true
MONITORING__HEALTH_CHECK_INTERVAL=30.0
MONITORING__PIPELINE_FLOW_MONITORING_ENABLED=true
MONITORING__CONSUMER_LAG_THRESHOLD=1000
MONITORING__MARKET_DATA_LATENCY_THRESHOLD=1.0
```

### 6. API Health and Monitoring Endpoints
**Priority: MEDIUM** | **Effort: Low**

#### Add Health Endpoints:
```python
# File: api/routers/monitoring.py
from fastapi import APIRouter, Depends
from core.health import ServiceHealthChecker

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

@router.get("/health")
async def health_check():
    """Get overall system health"""
    health_checker = get_health_checker()  # From DI
    return await health_checker.get_overall_health()

@router.get("/pipeline")  
async def pipeline_status():
    """Get pipeline flow status"""
    # Return pipeline metrics from Redis
    pass

@router.get("/logs/statistics")
async def log_statistics():
    """Get logging system statistics"""
    from core.logging import get_statistics
    return get_statistics()
```

## Testing the Enhanced Monitoring 🧪

### Create Test Script:
```bash
# File: scripts/test_monitoring.py
import asyncio
from core.config.settings import Settings
from core.logging import configure_logging, get_trading_logger_safe
from core.health import ServiceHealthChecker

async def test_enhanced_monitoring():
    settings = Settings()
    
    # Test logging configuration
    configure_logging(settings)
    
    # Test loggers
    trading_logger = get_trading_logger_safe("test_trading")
    trading_logger.info("Test trading log", test_data="example")
    
    # Test health checker
    health_checker = ServiceHealthChecker(settings)
    await health_checker.start()
    
    health_status = await health_checker.get_overall_health()
    print(f"System health: {health_status['status']}")
    
    await health_checker.stop()

if __name__ == "__main__":
    asyncio.run(test_enhanced_monitoring())
```

### Verification Steps:
1. **Check Log Files**: Verify logs are created in `logs/` directory with proper rotation
2. **Test Health Endpoints**: Ensure health check API returns proper status
3. **Monitor Pipeline Flow**: Verify pipeline metrics are recorded and accessible
4. **Trace Correlation**: Confirm trace IDs flow through the entire pipeline

## Integration with Existing Services 🔧

### Update Service Initialization:
```python
# In app/main.py or service startup
async def startup():
    # Configure enhanced logging
    configure_logging(settings)
    
    # Initialize health checker
    health_checker = ServiceHealthChecker(
        settings=settings,
        db_manager=db_manager,
        redis_client=redis_client,
        kafka_producer=producer,
        kafka_consumer=consumer
    )
    await health_checker.start()
    
    # Initialize pipeline monitor
    pipeline_monitor = PipelineMonitor(settings)
    await pipeline_monitor.start()
```

### Update CLI Commands:
```python
# In cli.py
@app.command("monitor")
def monitor():
    """Show monitoring status"""
    # Display health status, logs statistics, pipeline metrics
    pass

@app.command("logs")  
def logs_command():
    """Manage logging configuration"""
    # Show/configure logging options
    pass
```

## Critical Implementation Notes ⚠️

1. **Performance Impact**: Monitor the performance impact of enhanced logging, especially in high-throughput scenarios
2. **Log Volume**: Market data logging can generate large volumes - monitor disk usage
3. **Redis Memory**: Pipeline metrics stored in Redis - implement proper TTLs and cleanup
4. **Correlation ID Propagation**: Ensure correlation IDs flow through all async boundaries
5. **Error Handling**: All monitoring should be non-blocking and handle failures gracefully

## Success Metrics 📊

After implementation, you should achieve:
- ✅ Complete observability of the trading pipeline (Market Feed → Strategy Runner → Risk Manager → Trading Engine → Portfolio Manager)
- ✅ Real-time health monitoring of all services
- ✅ Structured logging with proper correlation IDs across all events
- ✅ Pipeline flow validation and bottleneck detection
- ✅ Configurable logging formats (JSON/plain text) for different environments
- ✅ Automated log rotation and cleanup
- ✅ API endpoints for monitoring and health status

This enhanced monitoring system will provide the observability needed to ensure the Alpha Panda trading pipeline operates reliably in production environments.