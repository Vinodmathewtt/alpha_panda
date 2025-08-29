# Streaming Infrastructure

Enhanced streaming components that provide automatic EventEnvelope wrapping, reliability features, and integration with the service orchestration patterns.

## Components

### MessageProducer
Enhanced producer with automatic EventEnvelope wrapping and reliability features.

**Key Features**:
- Automatic EventEnvelope wrapping for schema compliance
- Idempotent publishing with acks='all'
- Graceful shutdown with message flushing
- Service-specific client IDs for monitoring
- Built-in JSON serialization for datetime/Decimal types

**Usage**:
```python
from core.streaming.infrastructure.message_producer import MessageProducer

producer = MessageProducer(config, service_name="my-service")
await producer.start()

# Automatic EventEnvelope wrapping
event_id = await producer.send(
    topic="broker.signals.raw",
    key="strategy-123",
    data={"signal": "BUY", "quantity": 100},
    event_type=EventType.TRADING_SIGNAL,
    broker="paper"
)
```

### MessageConsumer
Enhanced consumer with reliability features and topic-aware handlers.

**Key Features**:
- Topic-aware message handling
- Manual offset commits for reliability
- Graceful shutdown with commit finalization
- Integration with reliability layers
- Consumer group isolation

**Usage**:
```python
from core.streaming.infrastructure.message_consumer import MessageConsumer

consumer = MessageConsumer(config, topics=["broker.signals.*"], group_id="my-service.signals")
await consumer.start()

async def message_handler(message: Dict[str, Any], topic: str):
    # Topic-aware processing
    broker = topic.split('.')[0]  # Extract broker from topic
    # Process message with broker context
    pass

# Used within StreamServiceBuilder pattern
```

## Integration with Service Architecture

These components are designed to work with the `StreamServiceBuilder` pattern:

```python
orchestrator = (StreamServiceBuilder("trading-engine", config, settings)
    .add_producer()  # Creates MessageProducer internally
    .add_consumer_handler(
        topics=["paper.signals.validated", "zerodha.signals.validated"],
        group_id="alpha-panda.trading-engine.signals",
        handler_func=self._handle_validated_signal  # Topic-aware handler
    )
    .build()
)
```

## EventEnvelope Integration

**Automatic Wrapping**: `MessageProducer.send()` automatically wraps data in EventEnvelope format if not already wrapped.

**Required Fields**:
- `id`: Generated UUID v7 for deduplication
- `correlation_id`: For tracing across services  
- `broker`: Audit field for message source identification
- `event_type`: Categorizes the event type
- `data`: The actual payload

**Manual EventEnvelope**: If you need custom envelope fields, create the EventEnvelope manually before sending.

## Reliability Features

- **Idempotent Producers**: `enable_idempotence=True`, `acks='all'`
- **Message Ordering**: Partition keys ensure ordering within partitions
- **Graceful Shutdown**: Proper flushing and commit handling
- **Error Handling**: Integration with reliability layer for DLQ and retries
- **Deduplication**: Consumer-side deduplication using event IDs

## Multi-Broker Support

Both components fully support the multi-broker architecture:

- **Topic Namespacing**: Handles broker-prefixed topics (`paper.*`, `zerodha.*`)
- **Context Extraction**: Handlers receive topic parameter for broker context
- **Isolation**: Separate consumer groups and producers per service
- **Cache Separation**: Redis keys can be broker-prefixed for data isolation

## Dependencies

- **aiokafka**: Core Kafka functionality
- **Pydantic**: EventEnvelope schema validation
- **Redis**: Optional, for enhanced reliability features
- **Core Schemas**: EventEnvelope, EventType enums