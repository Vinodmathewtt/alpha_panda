# Streaming Patterns

Service composition patterns for building robust streaming services with fluent APIs and reliability features.

## StreamServiceBuilder

The primary pattern for creating streaming services with composition-based architecture and automatic reliability features.

### Purpose

Provides a fluent API for building streaming services that:
- Compose multiple streaming components (producers, consumers, reliability layers)
- Integrate with the orchestration system
- Apply cross-cutting concerns (metrics, error handling, deduplication)
- Support the multi-broker architecture

### Key Features

- **Fluent Builder Pattern**: Chain method calls for readable service configuration
- **Automatic Reliability**: Built-in deduplication, error handling, and metrics
- **Topic-Aware Handlers**: Consumer handlers receive both message and topic parameters
- **Multi-Broker Support**: Handles broker-prefixed topics and context extraction
- **DLQ Integration**: Automatic Dead Letter Queue setup for failed messages
- **Composition Over Inheritance**: Uses composition to build service capabilities

### Basic Usage

```python
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder

# Build a complete streaming service
orchestrator = (StreamServiceBuilder("strategy-runner", config, settings)
    .with_redis(redis_client)           # Enable deduplication and metrics
    .with_error_handling()              # Add DLQ and retry logic
    .with_metrics()                     # Enable performance monitoring
    .add_producer()                     # Add message producer
    .add_consumer_handler(              # Add topic-aware consumer
        topics=["market.ticks"],
        group_id="alpha-panda.strategy-runner.ticks",
        handler_func=self._handle_market_tick
    )
    .build()
)

# Start the service
await orchestrator.start()
```

### Multi-Broker Example

```python
# Service handling multiple broker-specific topics
orchestrator = (StreamServiceBuilder("trading-engine", config, settings)
    .with_redis(redis_client)
    .with_error_handling()
    .add_producer()
    .add_consumer_handler(
        topics=["paper.signals.validated", "zerodha.signals.validated"],
        group_id="alpha-panda.trading-engine.signals",
        handler_func=self._handle_validated_signal  # Topic-aware handler
    )
    .build()
)

# Handler receives topic for broker context extraction
async def _handle_validated_signal(self, message: Dict[str, Any], topic: str):
    broker = topic.split('.')[0]  # Extract broker: "paper" or "zerodha"
    trader = self.trader_factory.get_trader(broker)
    await trader.execute_order(message['data'])
```

### Builder Methods

#### `.with_redis(redis_client)`
Enables Redis-based features:
- Event deduplication using event IDs
- Metrics collection and storage
- Cache-based state management

#### `.with_error_handling(error_handler=None)`
Adds error handling and DLQ:
- Automatic retry logic with exponential backoff
- Dead Letter Queue for failed messages
- Error classification and routing

#### `.with_metrics(metrics_collector=None)`
Enables performance monitoring:
- Message processing metrics
- Service health indicators
- Pipeline throughput tracking

#### `.add_producer()`
Adds a MessageProducer with:
- Automatic EventEnvelope wrapping
- Idempotent publishing
- Graceful shutdown with flushing

#### `.add_consumer_handler(topics, group_id, handler_func)`
Adds a topic-aware consumer:
- **topics**: List of topic patterns to consume
- **group_id**: Unique consumer group ID
- **handler_func**: `async def handler(message: Dict, topic: str)`

### Integration with Service Architecture

All Alpha Panda services use this pattern:

- **Strategy Runner**: Consumes market ticks, produces trading signals
- **Risk Manager**: Consumes raw signals, produces validated/rejected signals  
- **Trading Engine**: Consumes validated signals, produces order events
- **Portfolio Manager**: Consumes order fills, maintains portfolio state

### Reliability Features

- **Idempotent Producers**: Prevent duplicate message publishing
- **Consumer Deduplication**: Skip already-processed events using Redis
- **Manual Offset Commits**: Commit only after successful processing
- **DLQ Pattern**: Route failed messages to Dead Letter Queues
- **Graceful Shutdown**: Proper resource cleanup and message flushing

### Topic-Aware Architecture

Handlers receive both message and topic parameters to support:

- **Broker Context Extraction**: Determine broker from topic name
- **Dynamic Routing**: Route messages based on topic patterns
- **Multi-Tenant Processing**: Handle multiple brokers in single service
- **Debugging**: Log topic information for message tracing

This pattern is central to Alpha Panda's multi-broker architecture and service composition strategy.