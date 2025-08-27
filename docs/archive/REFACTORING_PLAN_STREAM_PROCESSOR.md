# Stream Processor Refactoring Plan

## Overview

The current `StreamProcessor` base class is a "god class" that handles too many concerns: Kafka connections, message consumption, error handling, deduplication, metrics collection, and business logic coordination. This refactoring implements **Composition over Inheritance** to create a more flexible, testable architecture.

## Current Issues

1. **God Class Anti-Pattern**: Single class handles infrastructure, reliability, and business concerns
2. **Rigid Inheritance**: All services forced into same lifecycle and reliability patterns
3. **Tight Coupling**: Business logic tightly coupled to streaming infrastructure
4. **Hard to Test**: Complex base class makes unit testing business logic difficult
5. **Limited Flexibility**: Hard to customize reliability features per service

## Target Architecture

### New Components Structure
```
core/streaming/
├── __init__.py
├── clients.py                       # Refactored: Only low-level clients
├── infrastructure/
│   ├── __init__.py
│   ├── message_consumer.py          # New: Pure consumption logic
│   ├── message_producer.py          # Enhanced: Production with reliability
│   └── connection_manager.py        # New: Connection lifecycle
├── reliability/
│   ├── __init__.py
│   ├── reliability_layer.py         # New: Cross-cutting concerns
│   ├── deduplication_manager.py     # Enhanced: Deduplication logic
│   ├── error_handler.py             # Enhanced: Error handling
│   └── metrics_collector.py         # New: Metrics collection
├── orchestration/
│   ├── __init__.py
│   ├── service_orchestrator.py      # New: Service composition
│   └── lifecycle_coordinator.py     # New: Component lifecycle
└── patterns/
    ├── __init__.py
    └── stream_service_builder.py     # New: Builder pattern for services
```

## Phase 1: Infrastructure Components

### Step 1.1: Pure Message Consumer

**File**: `core/streaming/infrastructure/message_consumer.py`

```python
import asyncio
import logging
from typing import List, AsyncGenerator, Dict, Any, Optional
from aiokafka import AIOKafkaConsumer
from core.config.settings import RedpandaSettings

logger = logging.getLogger(__name__)

class MessageConsumer:
    """Pure message consumption without business logic concerns."""
    
    def __init__(self, config: RedpandaSettings, topics: List[str], group_id: str):
        self.config = config
        self.topics = topics
        self.group_id = group_id
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the Kafka consumer."""
        if self._running:
            return
        
        self._consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.config.bootstrap_servers,
            client_id=f"{self.config.client_id}-consumer",
            group_id=self.group_id,
            auto_offset_reset='earliest',
            enable_auto_commit=False,  # Manual commits only
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000,
            max_poll_records=50,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        await self._consumer.start()
        self._running = True
        logger.info(f"Message consumer started for topics: {self.topics}")
    
    async def stop(self) -> None:
        """Stop the Kafka consumer."""
        if not self._running or not self._consumer:
            return
        
        await self._consumer.stop()
        self._running = False
        logger.info("Message consumer stopped")
    
    async def consume(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Yield raw messages from Kafka."""
        if not self._running:
            await self.start()
        
        try:
            async for message in self._consumer:
                yield {
                    'topic': message.topic,
                    'key': message.key.decode('utf-8') if message.key else None,
                    'value': message.value,
                    'partition': message.partition,
                    'offset': message.offset,
                    'timestamp': message.timestamp,
                    '_raw_message': message  # For commit operations
                }
        except Exception as e:
            logger.error(f"Error in message consumption: {e}")
            raise
    
    async def commit(self, message: Optional[Dict[str, Any]] = None) -> None:
        """Commit message offset."""
        if not self._consumer:
            raise RuntimeError("Consumer not started")
        
        try:
            if message and '_raw_message' in message:
                # Commit specific message
                await self._consumer.commit({
                    message['_raw_message'].topic_partition: message['_raw_message'].offset + 1
                })
            else:
                # Commit current position
                await self._consumer.commit()
        except Exception as e:
            logger.error(f"Failed to commit offset: {e}")
            raise
```

### Step 1.2: Enhanced Message Producer

**File**: `core/streaming/infrastructure/message_producer.py`

```python
import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer
from core.config.settings import RedpandaSettings
from core.schemas.events import EventEnvelope, generate_uuid7

class MessageProducer:
    """Enhanced message producer with reliability features."""
    
    def __init__(self, config: RedpandaSettings, service_name: str):
        self.config = config
        self.service_name = service_name
        self._producer: Optional[AIOKafkaProducer] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the producer."""
        if self._running:
            return
        
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.config.bootstrap_servers,
            client_id=f"{self.config.client_id}-producer-{self.service_name}",
            enable_idempotence=True,
            acks='all',
            request_timeout_ms=30000,
            linger_ms=5,
            compression_type='gzip',
            retry_backoff_ms=100,
            value_serializer=lambda x: json.dumps(x, default=self._json_serializer).encode('utf-8')
        )
        
        await self._producer.start()
        self._running = True
    
    async def stop(self) -> None:
        """Stop the producer with flush."""
        if not self._running or not self._producer:
            return
        
        await self._producer.flush()
        await self._producer.stop()
        self._running = False
    
    async def send(self, topic: str, key: str, data: Dict[str, Any], 
                   event_type: Optional[str] = None,
                   correlation_id: Optional[str] = None) -> str:
        """Send message with automatic envelope wrapping."""
        if not self._running:
            await self.start()
        
        # Create event envelope if not already wrapped
        if not isinstance(data, dict) or 'id' not in data:
            event_id = generate_uuid7()
            envelope = EventEnvelope(
                id=event_id,
                type=event_type or data.get('type', 'unknown'),
                timestamp=datetime.now(timezone.utc),
                source=self.service_name,
                correlation_id=correlation_id,
                data=data
            ).model_dump(mode='json')
        else:
            envelope = data
            event_id = data.get('id')
        
        await self._producer.send_and_wait(
            topic=topic,
            key=key.encode('utf-8'),
            value=envelope
        )
        
        return event_id
    
    @staticmethod
    def _json_serializer(obj):
        """Custom JSON serializer."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')
```

## Phase 2: Reliability Layer

### Step 2.1: Reliability Layer Implementation

**File**: `core/streaming/reliability/reliability_layer.py`

```python
import logging
from typing import Callable, Awaitable, Dict, Any, Optional
from datetime import datetime, timezone

from .deduplication_manager import DeduplicationManager
from .error_handler import ErrorHandler  
from .metrics_collector import MetricsCollector
from ..correlation import CorrelationContext, CorrelationLogger

logger = logging.getLogger(__name__)

class ReliabilityLayer:
    """Wraps business logic with cross-cutting reliability concerns."""
    
    def __init__(
        self,
        service_name: str,
        handler_func: Callable[[Dict[str, Any]], Awaitable[None]],
        consumer,  # MessageConsumer instance
        deduplicator: Optional[DeduplicationManager] = None,
        error_handler: Optional[ErrorHandler] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        self.service_name = service_name
        self.handler_func = handler_func
        self.consumer = consumer
        self.deduplicator = deduplicator
        self.error_handler = error_handler
        self.metrics_collector = metrics_collector
        self.correlation_logger = CorrelationLogger(service_name)
    
    async def process_message(self, raw_message: Dict[str, Any]) -> None:
        """Process a message with all reliability features."""
        message_value = raw_message['value']
        event_id = message_value.get('id')
        correlation_id = message_value.get('correlation_id')
        
        # 1. Set up correlation context
        if correlation_id:
            CorrelationContext.continue_trace(
                correlation_id, event_id, self.service_name, 
                f"process_{raw_message['topic']}"
            )
        else:
            correlation_id = CorrelationContext.start_new_trace(
                self.service_name, f"process_{raw_message['topic']}"
            )
        
        # 2. Check for duplicates
        if (self.deduplicator and event_id and 
            await self.deduplicator.is_duplicate(event_id)):
            self.correlation_logger.debug("Skipping duplicate event", event_id=event_id)
            await self.consumer.commit(raw_message)
            return
        
        # 3. Process with error handling and metrics
        start_time = datetime.now(timezone.utc)
        try:
            # Execute business logic
            await self.handler_func(message_value)
            
            # Commit and mark as processed
            await self.consumer.commit(raw_message)
            if self.deduplicator and event_id:
                await self.deduplicator.mark_processed(event_id)
            
            # Record success metrics
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.correlation_logger.debug("Message processed successfully", 
                                        duration_ms=duration * 1000)
            
            if self.metrics_collector:
                await self.metrics_collector.record_success(duration)
        
        except Exception as e:
            self.correlation_logger.error("Failed to process message", error=str(e))
            
            if self.error_handler:
                # Error handler manages retries, DLQ, and commits
                await self.error_handler.handle_processing_error(
                    raw_message, e, 
                    processing_func=lambda: self.handler_func(message_value),
                    commit_func=lambda: self.consumer.commit(raw_message)
                )
            else:
                # Simple error handling - log and commit to avoid reprocessing
                logger.error(f"Unhandled processing error: {e}")
                await self.consumer.commit(raw_message)
            
            if self.metrics_collector:
                await self.metrics_collector.record_failure(str(e))
```

### Step 2.2: Enhanced Deduplication Manager

**File**: `core/streaming/reliability/deduplication_manager.py`

```python
import asyncio
from typing import Optional, Set
import redis.asyncio as redis

class DeduplicationManager:
    """Manages event deduplication using Redis."""
    
    def __init__(self, redis_client: redis.Redis, 
                 service_name: str, ttl_seconds: int = 3600):
        self.redis_client = redis_client
        self.service_name = service_name
        self.ttl_seconds = ttl_seconds
        self._key_prefix = f"dedup:{service_name}"
        
        # In-memory cache for frequently checked events
        self._local_cache: Set[str] = set()
        self._cache_max_size = 1000
    
    async def is_duplicate(self, event_id: str) -> bool:
        """Check if event has already been processed."""
        # Check local cache first
        if event_id in self._local_cache:
            return True
        
        # Check Redis
        key = f"{self._key_prefix}:{event_id}"
        exists = await self.redis_client.exists(key)
        
        if exists:
            # Add to local cache
            self._add_to_local_cache(event_id)
            return True
        
        return False
    
    async def mark_processed(self, event_id: str) -> None:
        """Mark event as processed."""
        key = f"{self._key_prefix}:{event_id}"
        await self.redis_client.setex(key, self.ttl_seconds, "1")
        
        # Add to local cache
        self._add_to_local_cache(event_id)
    
    def _add_to_local_cache(self, event_id: str) -> None:
        """Add event to local cache with size management."""
        if len(self._local_cache) >= self._cache_max_size:
            # Remove oldest entries (simple FIFO)
            for _ in range(self._cache_max_size // 4):
                try:
                    self._local_cache.pop()
                except KeyError:
                    break
        
        self._local_cache.add(event_id)
```

## Phase 3: Service Orchestration

### Step 3.1: Service Orchestrator

**File**: `core/streaming/orchestration/service_orchestrator.py`

```python
import asyncio
from typing import Dict, Any, List, Optional
from ..infrastructure.message_consumer import MessageConsumer
from ..infrastructure.message_producer import MessageProducer
from ..reliability.reliability_layer import ReliabilityLayer

class ServiceOrchestrator:
    """Orchestrates the composition of streaming service components."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.consumers: List[MessageConsumer] = []
        self.producers: List[MessageProducer] = []
        self.reliability_layers: List[ReliabilityLayer] = []
        self._running = False
    
    def add_consumer_flow(
        self, 
        consumer: MessageConsumer,
        reliability_layer: ReliabilityLayer
    ) -> None:
        """Add a consumer flow with reliability layer."""
        self.consumers.append(consumer)
        self.reliability_layers.append(reliability_layer)
    
    def add_producer(self, producer: MessageProducer) -> None:
        """Add a producer."""
        self.producers.append(producer)
    
    async def start(self) -> None:
        """Start all components."""
        if self._running:
            return
        
        # Start producers
        for producer in self.producers:
            await producer.start()
        
        # Start consumers
        for consumer in self.consumers:
            await consumer.start()
        
        # Start consumption loops
        self._consumption_tasks = []
        for consumer, reliability_layer in zip(self.consumers, self.reliability_layers):
            task = asyncio.create_task(
                self._consumption_loop(consumer, reliability_layer)
            )
            self._consumption_tasks.append(task)
        
        self._running = True
    
    async def stop(self) -> None:
        """Stop all components gracefully."""
        if not self._running:
            return
        
        # Cancel consumption tasks
        for task in self._consumption_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self._consumption_tasks, return_exceptions=True)
        
        # Stop consumers
        for consumer in self.consumers:
            await consumer.stop()
        
        # Stop producers
        for producer in self.producers:
            await producer.stop()
        
        self._running = False
    
    async def _consumption_loop(
        self, 
        consumer: MessageConsumer, 
        reliability_layer: ReliabilityLayer
    ) -> None:
        """Run the consumption loop for a consumer."""
        try:
            async for message in consumer.consume():
                await reliability_layer.process_message(message)
        except asyncio.CancelledError:
            # Graceful shutdown
            pass
        except Exception as e:
            logger.error(f"Fatal error in consumption loop: {e}")
            # In production, you might want to restart the loop
            raise
```

### Step 3.2: Stream Service Builder

**File**: `core/streaming/patterns/stream_service_builder.py`

```python
from typing import Dict, Any, Callable, Awaitable, Optional, List
from core.config.settings import RedpandaSettings, Settings
from ..infrastructure.message_consumer import MessageConsumer
from ..infrastructure.message_producer import MessageProducer
from ..reliability.reliability_layer import ReliabilityLayer
from ..reliability.deduplication_manager import DeduplicationManager
from ..reliability.error_handler import ErrorHandler
from ..orchestration.service_orchestrator import ServiceOrchestrator

class StreamServiceBuilder:
    """Builder pattern for creating streaming services with composition."""
    
    def __init__(self, service_name: str, config: RedpandaSettings, settings: Settings):
        self.service_name = service_name
        self.config = config
        self.settings = settings
        self.orchestrator = ServiceOrchestrator(service_name)
        
        # Default reliability components
        self._redis_client = None
        self._deduplicator = None
        self._error_handler = None
        self._metrics_collector = None
    
    def with_redis(self, redis_client) -> 'StreamServiceBuilder':
        """Configure Redis for deduplication and metrics."""
        self._redis_client = redis_client
        self._deduplicator = DeduplicationManager(redis_client, self.service_name)
        return self
    
    def with_error_handling(self, error_handler: ErrorHandler) -> 'StreamServiceBuilder':
        """Configure custom error handling."""
        self._error_handler = error_handler
        return self
    
    def with_metrics(self, metrics_collector) -> 'StreamServiceBuilder':
        """Configure metrics collection."""
        self._metrics_collector = metrics_collector
        return self
    
    def add_consumer_handler(
        self,
        topics: List[str],
        group_id: str,
        handler_func: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> 'StreamServiceBuilder':
        """Add a consumer with handler function."""
        
        # Create consumer
        consumer = MessageConsumer(self.config, topics, group_id)
        
        # Create reliability layer
        reliability_layer = ReliabilityLayer(
            service_name=self.service_name,
            handler_func=handler_func,
            consumer=consumer,
            deduplicator=self._deduplicator,
            error_handler=self._error_handler,
            metrics_collector=self._metrics_collector
        )
        
        # Add to orchestrator
        self.orchestrator.add_consumer_flow(consumer, reliability_layer)
        return self
    
    def add_producer(self) -> 'StreamServiceBuilder':
        """Add a producer."""
        producer = MessageProducer(self.config, self.service_name)
        self.orchestrator.add_producer(producer)
        return self
    
    def build(self) -> ServiceOrchestrator:
        """Build the final service orchestrator."""
        return self.orchestrator
```

## Phase 4: Refactored Service Examples

### Step 4.1: New Trading Engine Service

**File**: `services/trading_engine/service.py`

```python
from typing import Dict, Any
from core.config.settings import RedpandaSettings, Settings
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.schemas.topics import TopicMap, TopicNames
from core.schemas.events import EventType, TradingSignal

class TradingEngineService:
    """Refactored trading engine using composition."""
    
    def __init__(
        self, 
        config: RedpandaSettings, 
        settings: Settings, 
        redis_client,
        trader_factory,  # From previous refactoring
        execution_router,  # From previous refactoring
        market_hours_checker
    ):
        self.settings = settings
        self.trader_factory = trader_factory
        self.execution_router = execution_router
        self.market_hours_checker = market_hours_checker
        self.last_prices: Dict[int, float] = {}
        
        # Build service using composition
        topics = TopicMap(settings.broker_namespace)
        
        self.orchestrator = (StreamServiceBuilder("trading_engine", config, settings)
            .with_redis(redis_client)
            .add_producer()
            .add_consumer_handler(
                topics=[topics.signals_validated()],
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.signals",
                handler_func=self._handle_validated_signal
            )
            .add_consumer_handler(
                topics=[TopicNames.MARKET_TICKS],
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.ticks", 
                handler_func=self._handle_market_tick
            )
            .build()
        )
    
    async def start(self) -> None:
        """Start the service."""
        await self.trader_factory.initialize()
        await self.orchestrator.start()
    
    async def stop(self) -> None:
        """Stop the service."""
        await self.orchestrator.stop()
        await self.trader_factory.shutdown()
    
    async def _handle_validated_signal(self, message: Dict[str, Any]) -> None:
        """Handle validated signal - pure business logic."""
        if message.get('type') != EventType.VALIDATED_SIGNAL:
            return
        
        if not self.market_hours_checker.is_market_open():
            return
        
        data = message.get('data', {})
        original_signal = data.get('original_signal')
        if not original_signal:
            return
        
        signal = TradingSignal(**original_signal)
        target_namespaces = await self.execution_router.get_target_namespaces(signal.strategy_id)
        
        for namespace in target_namespaces:
            await self._execute_on_trader(signal, namespace)
    
    async def _handle_market_tick(self, message: Dict[str, Any]) -> None:
        """Handle market tick - pure business logic."""
        if message.get('type') != EventType.MARKET_TICK:
            return
        
        data = message.get('data', {})
        instrument_token = data.get('instrument_token')
        last_price = data.get('last_price')
        
        if instrument_token and last_price:
            self.last_prices[instrument_token] = last_price
    
    async def _execute_on_trader(self, signal: TradingSignal, namespace: str) -> None:
        """Execute signal on trader - same as before."""
        # Implementation from previous refactoring
        pass
```

## Migration Strategy

### Phase 1: Infrastructure Foundation (Week 1-2)
- Implement MessageConsumer and MessageProducer
- Create ReliabilityLayer with basic features
- Add comprehensive unit tests

### Phase 2: Service Builder Pattern (Week 3-4)
- Implement ServiceOrchestrator and StreamServiceBuilder
- Create example service using new pattern
- Integration testing with existing services

### Phase 3: Service Migration (Week 5-6)
- Migrate one service at a time using builder pattern
- Deploy with feature flags for gradual rollout
- Performance and reliability testing

### Phase 4: Legacy Cleanup (Week 7-8)
- Remove old StreamProcessor base class
- Update all services to use new pattern
- Documentation and training

## Benefits

### 1. Separation of Concerns
- **Infrastructure**: Pure message handling
- **Reliability**: Cross-cutting concerns
- **Business Logic**: Clean, testable handlers

### 2. Flexibility
- Mix and match reliability features per service
- Different error handling strategies
- Custom metrics and monitoring

### 3. Testability
- Unit test business logic without streaming infrastructure
- Mock individual components easily
- Integration test reliability features separately

### 4. Maintainability
- Single responsibility per component
- Clear dependency boundaries
- Easy to modify individual features

### 5. Performance
- Optimized consumption loops
- Configurable reliability features
- Better resource management

## Success Metrics

1. **Code Quality**: Reduced cyclomatic complexity, improved test coverage
2. **Developer Velocity**: Faster feature development and testing
3. **System Reliability**: Same or better error rates and recovery
4. **Performance**: No degradation in message throughput
5. **Flexibility**: Time to customize reliability features per service