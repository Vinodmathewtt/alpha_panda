# Core Module Documentation

## Overview

The `core/` module contains shared libraries and utilities used across all services and components of Alpha Panda. It provides the foundation for the unified log architecture with event streaming, multi-broker support, and composition-first design patterns.

## Module Structure

```
core/
├── config/            # Pydantic settings and configuration management
├── database/          # PostgreSQL models and async connection management  
├── health/            # Comprehensive health checking and monitoring
├── logging/           # Enhanced structured logging with correlation tracking
├── market_hours/      # Indian stock market hours validation and checking
├── monitoring/        # Metrics collection and performance monitoring
├── schemas/           # Event contracts, topic definitions, and data models
├── services/          # Base service classes and common service patterns
├── streaming/         # Stream processing patterns and utilities
└── utils/             # Common utilities, exceptions, and state management
```

## Key Components

### Configuration (`core/config/`)
- **Pydantic Settings**: Type-safe configuration with environment variable support
- **Environment Support**: `.env` file loading with validation
- **Broker Configuration**: Dual broker settings for paper and Zerodha trading

### Event System (`core/schemas/`)
- **EventEnvelope**: Standardized event wrapper with correlation tracking
- **Topic Definitions**: Centralized topic naming and configuration
- **Event Types**: Enumerated event types for type safety

### Streaming (`core/streaming/`)
- **Producer/Consumer Config**: Optimized aiokafka settings
- **Lifecycle Management**: Graceful startup and shutdown patterns
- **Event Deduplication**: Consumer-side deduplication using Redis
- **Error Handling**: Structured retry and DLQ patterns

### Database (`core/database/`)
- **Async Connection**: PostgreSQL with asyncio support
- **SQLAlchemy Models**: ORM models for configuration and metadata
- **Migration Support**: Alembic integration for schema changes

### Monitoring (`core/monitoring/`)
- **Metrics Collection**: Service-level metrics and KPIs
- **Health Checks**: Service readiness and liveness probes
- **Performance Monitoring**: Latency and throughput tracking
- **Pipeline Validation**: End-to-end flow monitoring

## Usage Patterns

### Event Publishing
```python
from core.schemas.events import EventEnvelope, EventType

envelope = EventEnvelope(
    event_type=EventType.TRADING_SIGNAL,
    data=signal_data,
    correlation_id=correlation_id
)
```

### Configuration Access
```python
from core.config.settings import get_settings

settings = get_settings()
database_url = settings.database.url
```

### Stream Processing (Modern Pattern)
```python
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder

# Modern StreamServiceBuilder pattern
self.orchestrator = (StreamServiceBuilder("service_name", config, settings)
    .with_redis(redis_client)
    .with_error_handling()
    .with_metrics()
    .add_producer()
    .add_consumer_handler(
        topics=topic_list,
        group_id="alpha-panda.service.group",
        handler_func=self._handle_message
    )
    .build()
)
```

### Topic-Aware Message Handling
```python
# Handlers accept (message, topic) for broker context extraction
async def _handle_message(self, message: Dict[str, Any], topic: str) -> None:
    broker = topic.split('.')[0]  # Extract broker from topic name
    # Route based on broker context
```

## Architecture Patterns

### Multi-Broker Architecture  
- **Unified Deployment**: Single service instance handles multiple brokers simultaneously
- **Topic-Level Isolation**: Hard segregation via broker-prefixed topics (paper.*, zerodha.*)
- **Shared Services**: Market data uses single feed model for consistency
- **Cache Segregation**: Redis keys prefixed by broker for state isolation

### Composition-First Design
- **Protocol Contracts**: Use `typing.Protocol` for interfaces instead of ABCs
- **Dependency Injection**: Constructor-based dependency injection with typed parameters
- **Factory Functions**: Module-level factories for object assembly
- **Service Builder**: StreamServiceBuilder pattern for service composition

### Event-Driven Architecture
- **EventEnvelope Standard**: All events use standardized envelope with correlation tracking
- **Topic Routing**: Route by topic name only, no wildcard subscriptions
- **Deduplication**: Consumer-side event deduplication using Redis with TTL
- **DLQ Pattern**: Structured retry with dead letter queue routing

## Critical Implementation Rules

- **Broker Segregation**: Maintain hard isolation between paper and Zerodha data
- **Fail-Fast Policy**: System must fail fast and fail hard - no silent failures
- **Event Deduplication**: All consumers must implement idempotent message processing
- **Correlation Tracking**: All events must include correlation IDs for tracing
- **Type Safety**: Full type hints required on all public APIs