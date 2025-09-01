# Core Streaming Reliability

## Overview

The streaming reliability module provides robust reliability patterns and error handling mechanisms for Alpha Panda's event streaming infrastructure. It ensures reliable message processing, handles failures gracefully, and maintains system resilience under various failure scenarios.

## Components

### `reliability_layer.py`
Main reliability layer coordination:

- **Reliability Patterns**: Implements circuit breaker, retry, and timeout patterns
- **Failure Detection**: Detects and categorizes different types of failures
- **Recovery Coordination**: Coordinates recovery across reliability components
- **Resilience Monitoring**: Monitors system resilience and reliability metrics

### `deduplication_manager.py`
Event deduplication management:

- **Deduplication Logic**: Ensures exactly-once message processing semantics
- **Redis Integration**: Uses Redis for distributed deduplication state
- **TTL Management**: Manages time-to-live for deduplication records
- **Performance Optimization**: Optimized deduplication for high-throughput scenarios

### `error_handler.py`
Comprehensive error handling and recovery:

- **Error Classification**: Classifies errors as transient or permanent
- **Retry Logic**: Implements exponential backoff retry mechanisms
- **Dead Letter Queue**: Routes failed messages to DLQ for manual intervention
- **Error Reporting**: Reports errors with full context and correlation

### `metrics_collector.py`
Reliability metrics collection and monitoring:

- **Reliability Metrics**: Collects metrics on message processing reliability
- **Failure Tracking**: Tracks failure rates and patterns
- **Performance Metrics**: Monitors processing latency and throughput
- **Alert Integration**: Integrates with alerting systems for reliability issues

## Architecture Patterns

### Reliability Layer
```python
class ReliabilityLayer:
    """Main reliability coordination layer"""
    
    def __init__(self, redis_client, settings):
        self.deduplication_manager = DeduplicationManager(redis_client)
        self.error_handler = ErrorHandler(settings)
        self.metrics_collector = MetricsCollector(redis_client)
        self.circuit_breaker = CircuitBreaker(settings)
    
    async def process_message_reliably(self, message: dict, processor_func):
        """Process message with full reliability patterns"""
        message_id = message.get('id')
        
        # Check for duplicate
        if await self.deduplication_manager.is_duplicate(message_id):
            self.metrics_collector.increment('messages_deduplicated')
            return
        
        try:
            # Process with circuit breaker protection
            async with self.circuit_breaker:
                result = await processor_func(message)
                
            # Mark as processed
            await self.deduplication_manager.mark_processed(message_id)
            self.metrics_collector.increment('messages_processed_successfully')
            return result
            
        except Exception as e:
            await self.error_handler.handle_error(message, e)
            self.metrics_collector.increment('messages_failed')
            raise
```

### Deduplication Manager
```python
class DeduplicationManager:
    """Manages event deduplication using Redis"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.ttl = 3600  # 1 hour TTL for dedup records
    
    async def is_duplicate(self, message_id: str) -> bool:
        """Check if message has already been processed"""
        key = f"dedup:{message_id}"
        return await self.redis_client.exists(key)
    
    async def mark_processed(self, message_id: str):
        """Mark message as processed with TTL"""
        key = f"dedup:{message_id}"
        await self.redis_client.setex(key, self.ttl, "processed")
```

### Error Handler
```python
class ErrorHandler:
    """Handles errors with classification and retry logic"""
    
    def __init__(self, settings):
        self.settings = settings
        self.max_retries = settings.max_retries
        self.backoff_factor = settings.backoff_factor
    
    async def handle_error(self, message: dict, error: Exception):
        """Handle error with appropriate strategy"""
        error_classification = self.classify_error(error)
        
        if error_classification == "transient":
            await self.handle_transient_error(message, error)
        elif error_classification == "permanent":
            await self.handle_permanent_error(message, error)
        else:
            await self.handle_unknown_error(message, error)
    
    def classify_error(self, error: Exception) -> str:
        """Classify error as transient, permanent, or unknown"""
        if isinstance(error, (ConnectionError, TimeoutError)):
            return "transient"
        elif isinstance(error, (ValidationError, ValueError)):
            return "permanent"
        else:
            return "unknown"
```

### Metrics Collector
```python
class MetricsCollector:
    """Collects reliability metrics"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
    
    async def increment(self, metric_name: str, value: int = 1):
        """Increment reliability metric"""
        key = f"reliability:metrics:{metric_name}"
        await self.redis_client.incrby(key, value)
    
    async def get_reliability_metrics(self) -> dict:
        """Get comprehensive reliability metrics"""
        keys = await self.redis_client.keys("reliability:metrics:*")
        metrics = {}
        
        for key in keys:
            metric_name = key.decode().split(":")[-1]
            value = await self.redis_client.get(key)
            metrics[metric_name] = int(value) if value else 0
        
        return metrics
```

## Usage

### Reliable Message Processing
```python
from core.streaming.reliability import ReliabilityLayer

# Initialize reliability layer
reliability_layer = ReliabilityLayer(redis_client, settings)

# Process message with full reliability
async def process_trading_signal(message):
    signal_data = message['data']
    # Process signal logic here
    return {"status": "processed"}

# Use reliability layer
result = await reliability_layer.process_message_reliably(
    message=signal_message,
    processor_func=process_trading_signal
)
```

### Error Handling Integration
```python
try:
    await process_message(message)
except Exception as e:
    await error_handler.handle_error(message, e)
```

### Metrics Monitoring
```python
# Get reliability metrics
metrics = await metrics_collector.get_reliability_metrics()
print(f"Success rate: {metrics['messages_processed_successfully']} / {metrics['total_messages']}")
```

## Reliability Patterns

### Circuit Breaker Pattern
- **Failure Detection**: Automatically detects service failures
- **Fast Fail**: Fails fast when service is unavailable
- **Automatic Recovery**: Automatically attempts recovery after timeout
- **State Management**: Manages circuit state (closed, open, half-open)

### Retry Pattern
- **Exponential Backoff**: Implements exponential backoff for retries
- **Jitter**: Adds jitter to prevent thundering herd
- **Max Retries**: Limits maximum retry attempts
- **Retry Classification**: Only retries transient errors

### Dead Letter Queue
- **Failed Message Storage**: Stores messages that can't be processed
- **Manual Recovery**: Allows manual inspection and recovery
- **Poison Message Detection**: Detects and isolates poison messages
- **Replay Capability**: Supports replaying messages from DLQ

## Configuration

Reliability configuration:

```python
class ReliabilitySettings(BaseModel):
    max_retries: int = 3
    backoff_factor: float = 2.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 30
    deduplication_ttl: int = 3600
    dlq_enabled: bool = True
```

## Monitoring

### Reliability Metrics
- **Message Success Rate**: Percentage of successfully processed messages
- **Deduplication Rate**: Rate of duplicate message detection
- **Error Rate**: Rate of message processing errors
- **Circuit Breaker State**: Current state of circuit breakers
- **Retry Statistics**: Retry attempt statistics and success rates

### Alerts
- **High Error Rate**: Alert when error rate exceeds threshold
- **Circuit Breaker Open**: Alert when circuit breakers open
- **DLQ Accumulation**: Alert when DLQ messages accumulate
- **Deduplication Issues**: Alert on deduplication failures

## Dependencies

- **Redis**: Distributed state for deduplication and metrics
- **core.utils.exceptions**: Structured exception handling
- **core.monitoring**: Metrics integration and alerting
- **asyncio**: Async reliability pattern implementation