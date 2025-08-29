# Core Streaming Architecture

The Alpha Panda streaming system provides a dual-tier architecture for different streaming needs, built on top of aiokafka and Redpanda.

## Architecture Overview

**Two Complementary Systems (Both Valid and Active):**

### 1. Direct Streaming Clients (`clients.py`)
**Purpose**: Simple, lightweight streaming for basic producer/consumer needs

**Components**:
- `RedpandaProducer` - Direct aiokafka wrapper with idempotency
- `RedpandaConsumer` - Direct aiokafka wrapper with manual commits

**Usage**:
- DI container (`app/containers.py`) for simple producer needs
- Basic streaming operations without additional layers
- Direct control over Kafka operations

**When to Use**:
- Simple message publishing
- Direct Kafka operations
- Minimal overhead requirements
- Basic producer/consumer patterns

### 2. Enhanced Infrastructure (`infrastructure/`)
**Purpose**: Feature-rich streaming with automatic EventEnvelope wrapping and reliability

**Components**:
- `MessageProducer` - Enhanced producer with automatic envelope wrapping
- `MessageConsumer` - Enhanced consumer with reliability features

**Usage**:
- `StreamServiceBuilder` pattern for service architecture
- Full-featured services with reliability layers
- Automatic EventEnvelope compliance

**When to Use**:
- Service-oriented architecture
- Need automatic EventEnvelope wrapping
- Reliability and error handling requirements
- Integration with orchestration patterns

## Key Directories

### `/infrastructure/`
Enhanced message producers and consumers with automatic EventEnvelope wrapping and reliability features.

### `/patterns/`
Service composition patterns, primarily `StreamServiceBuilder` for fluent service creation.

### `/orchestration/`
Service orchestration components for managing multiple streaming components.

### `/reliability/`
Cross-cutting reliability concerns including deduplication, error handling, and metrics collection.

## Usage Patterns

### Simple Direct Usage
```python
# For basic streaming needs
from core.streaming.clients import RedpandaProducer

producer = RedpandaProducer(config)
await producer.send(topic="my.topic", key="partition-key", value=data)
```

### Service Architecture Pattern
```python
# For full-featured services
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder

orchestrator = (StreamServiceBuilder("my-service", config, settings)
    .with_redis(redis_client)
    .with_error_handling()
    .with_metrics()
    .add_producer()
    .add_consumer_handler(topics=["my.topic"], group_id="my.group", handler_func=handler)
    .build()
)
```

## Important Notes

**NOT Legacy Components**: Both systems are actively maintained and serve different architectural purposes. There are no deprecated or legacy components in this streaming stack.

**EventEnvelope Compliance**: 
- Direct clients require manual EventEnvelope creation
- Infrastructure components provide automatic EventEnvelope wrapping
- All services must use EventEnvelope standard for observability

**Multi-Broker Architecture**: All streaming components support the multi-broker architecture with topic-aware handlers and broker context extraction.

## Dependencies

- **aiokafka**: Async Kafka client
- **Redpanda**: Event streaming platform
- **Redis**: For deduplication and metrics (when using enhanced features)
- **Pydantic**: For EventEnvelope schema validation