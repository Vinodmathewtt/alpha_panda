# Core Module Documentation

## Overview

The `core/` module contains shared libraries and utilities used across all services and components of Alpha Panda.

## Module Structure

```
core/
├── config/            # Pydantic settings and configuration
├── database/          # PostgreSQL models and connection management
├── health/           # Health checking utilities
├── logging/          # Enhanced logging with channels
├── market_hours/     # Market hours validation
├── monitoring/       # Metrics and monitoring
├── schemas/          # Event contracts and topic definitions
└── streaming/        # aiokafka client utilities and patterns
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

### Stream Processing
```python
from core.streaming.lifecycle_manager import StreamProcessor

class MyService(StreamProcessor):
    async def process_message(self, message):
        # Process message with automatic deduplication
        pass
```

## Critical Patterns

- **EventEnvelope Standard**: All events must use the standardized envelope
- **Broker Segregation**: All components respect broker namespace isolation
- **Async Patterns**: Full asyncio support throughout
- **Type Safety**: Pydantic models for all data structures
- **Correlation Tracking**: Event correlation for debugging and monitoring