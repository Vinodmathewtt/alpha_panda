# Implementation Patterns

## Critical Architecture Patterns

**📁 Code Examples**: All implementation patterns are demonstrated with working code examples in the `examples/` directory. See `examples/README.md` for complete overview.

### Event Envelope Standard
ALL events MUST use `EventEnvelope` from `core/schemas/events.py`. See example format in `examples/trading/message_publishing.py`.

**Critical Fields**:
- `id`: Globally unique UUID v7 for event deduplication
- `correlation_id`: Links related events across services for tracing
- `causation_id`: Points to the event that caused this one
- `broker`: Audit field only - NEVER use for routing (use topic namespaces)

### Streaming Patterns
- **Producer Keys**: Every message MUST have partition key for ordering
- **Consumer Groups**: Each service has unique consumer group ID  
- **Topic Routing**: Route by topic namespace, NO wildcard subscriptions
- **Idempotent Producers**: acks='all', enable_idempotence=True
- **Manual Offset Commits**: Disable auto-commit, commit only after successful processing
- **Graceful Shutdown**: await consumer.stop() and await producer.stop() (includes flush)
- **Event Deduplication**: Consumer-side dedup using event_id in Redis with TTL
- **DLQ Pattern**: Bounded retries (3-5 attempts) → Dead Letter Queue → Replay tool

### Broker-Namespaced Topic Taxonomy
**CRITICAL**: Topics are namespaced by broker to ensure hard segregation:

#### Topic Naming Convention
**Format**: `{broker}.{domain}.{event_type}[.dlq]`

**Examples**: 
- market.ticks (shared)
- paper.signals.raw, zerodha.signals.validated
- paper.orders.filled, zerodha.orders.filled
- paper.orders.filled.dlq (Dead Letter Queue)

#### Complete Topic Map
See complete topic mapping in `examples/architecture/topic_configuration.py`:
- **Market Data (shared)**: market.ticks
- **Paper Trading**: paper.signals.raw, paper.signals.validated, paper.orders.submitted, paper.orders.ack, paper.orders.filled, paper.pnl.snapshots, paper.*.dlq
- **Zerodha Trading**: zerodha.signals.raw, zerodha.signals.validated, zerodha.orders.submitted, zerodha.orders.ack, zerodha.orders.filled, zerodha.pnl.snapshots, zerodha.*.dlq

#### Hard Isolation Guardrails
- **Topic Namespacing**: All topics prefixed by broker for hard segregation
- **Schema Registry**: Separate subjects: `paper.orders.filled-v2`, `zerodha.orders.filled-v2`
- **Message Routing**: Services extract broker context from topic names, never mix broker data
- **Redis Isolation**: Separate key prefixes: `paper:` vs `zerodha:`
- **Database Isolation**: Separate schemas or credential-level separation

### Delivery Semantics & Deduplication
**CRITICAL**: Producer idempotence alone does NOT guarantee exactly-once delivery:

#### Event Deduplication Strategy
See implementation example: `examples/streaming/event_deduplication.py`

#### Offset Commit Strategy
See implementation example: `examples/streaming/offset_commit_strategy.py`

### Enhanced Error Handling & DLQ Pattern
**CRITICAL**: Replace blanket "never raise" with structured retry + DLQ pattern:

#### Error Classification & Retry Strategy
See implementation example: `examples/patterns/error_handling.py`

#### Dead Letter Queue Implementation
See implementation example: `examples/patterns/error_handling.py`

#### DLQ Replay Tool
See implementation example: `examples/patterns/dlq_replay_tool.py`

### Partitioning Strategy & Hot Key Management
**CRITICAL**: Prevent hot partitions while maintaining ordering guarantees:

#### Partitioning Scheme
See implementation example: `examples/architecture/partitioning_strategy.py`

#### Hot Partition Monitoring
See implementation example: `examples/monitoring/partition_metrics.py`

### Operational Guardrails & Monitoring
**CRITICAL**: Production observability and reliability measures:

#### Health Checks & Readiness Probes
See implementation example: `examples/monitoring/health_checks.py`

#### SLO Monitoring & Alerting
See implementation example: `examples/monitoring/service_metrics.py`

#### Cache Management & TTL Strategy
See implementation example: `examples/patterns/cache_management.py`

#### Async Broker SDK Integration
See implementation example: `examples/patterns/async_broker_adapter.py`

## Implementation Patterns (From docs)

### Broker Authentication Pattern
See implementation example: `examples/trading/broker_authentication.py`

### Pure Strategy Pattern
See implementation example: `examples/trading/pure_strategy_pattern.py`

### Message Publishing Pattern
See implementation example: `examples/trading/message_publishing.py`

### Trading Engine Routing Pattern
See implementation example: `examples/trading/trading_engine_routing.py`

### Consumer Lifecycle & Commit Management
**CRITICAL**: Proper partition assignment/revocation handling for data safety:

#### Consumer Lifecycle Implementation
See implementation example: `examples/streaming/lifecycle_management.py`

#### Graceful Shutdown Implementation
See implementation example: `examples/streaming/lifecycle_management.py`

### Optimized Producer/Consumer Configuration
See optimized configuration examples: `examples/streaming/producer_consumer_config.py`

## Modern Service Architecture Patterns (2025 Update)

### StreamServiceBuilder Pattern
**CRITICAL**: All services now use composition-based StreamServiceBuilder for service orchestration:

```python
self.orchestrator = (StreamServiceBuilder("service_name", config, settings)
    .with_redis(redis_client)           # Optional Redis integration
    .with_error_handling()              # Automatic DLQ and retry logic  
    .with_metrics()                     # Performance monitoring
    .add_producer()                     # Kafka producer with idempotence
    .add_consumer_handler(              # Topic-aware consumer
        topics=topic_list,
        group_id="alpha-panda.service.group", 
        handler_func=self._handle_message
    )
    .build()
)
```

### Topic-Aware Handler Pattern  
**CRITICAL**: Message handlers accept `(message, topic)` parameters for broker context extraction:

```python
async def _handle_message(self, message: Dict[str, Any], topic: str) -> None:
    # Extract broker from topic name for routing decisions
    broker = topic.split('.')[0]  # "paper.signals.validated" -> "paper"
    
    # Route based on extracted broker context
    trader = self.trader_factory.get_trader(broker)
    await trader.execute_order(signal)
```

### Multi-Broker Service Architecture
**CRITICAL**: Services handle multiple brokers simultaneously with unified deployment:

- **Unified Consumer Groups**: Single consumer group per service processes all broker topics
- **Dynamic Topic Subscription**: Services subscribe to topics for all active brokers at startup
- **Cache Key Isolation**: Redis keys prefixed by broker (`paper:*` vs `zerodha:*`)
- **Configuration-Driven**: `ACTIVE_BROKERS=paper,zerodha` determines which brokers to handle

## Component Initialization Pattern

All services follow modern composition-based patterns:
- **StreamServiceBuilder Pattern**: Composition-based service orchestration
- **Protocol Contracts**: Use `typing.Protocol` for interfaces instead of inheritance
- **Topic-Aware Handlers**: Message handlers extract broker context from topic names
- **Async/await Pattern**: Full asyncio support throughout the codebase
- **Graceful Shutdown**: Proper producer.flush() and consumer.stop() handling
- **Structured Logging**: Correlation IDs with structlog for request tracing
- **Event-Driven Architecture**: All dynamic data flows through Redpanda streams

## Documentation References

### Comprehensive Module Documentation
All implementation patterns are now documented with complete README.md files:
- [Core Architecture Patterns](../../core/README.md) - StreamServiceBuilder and foundational patterns
- [Service Implementation Patterns](../../services/README.md) - Multi-broker service architecture  
- [Strategy Framework Patterns](../../strategies/README.md) - Composition vs inheritance approaches
- [Configuration Patterns](../../core/config/README.md) - Settings and environment management
