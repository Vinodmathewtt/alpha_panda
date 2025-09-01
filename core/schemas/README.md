# Core Schemas Module

## Overview

The `core/schemas/` module defines the standardized event schemas, topic naming conventions, and data models used throughout Alpha Panda. It enforces consistent data structures and messaging patterns across all services using Pydantic models.

## Components

### `events.py`
Standardized event envelope and data models:

- **EventEnvelope**: Mandatory wrapper for ALL events with correlation tracking
- **Event Types**: Enumerated event types for type safety (market_tick, trading_signal, order_filled, etc.)
- **Data Models**: Pydantic models for market data, trading signals, orders, and PnL
- **ID Generation**: Centralized `generate_event_id()` in `core/utils/ids.py` (prefers UUID v7/ULID fallbacks) for envelope IDs and trace IDs
- **JSON Encoding**: Proper serialization of Decimal and datetime objects

### `topics.py`  
Centralized topic naming and routing definitions:

- **TopicNames**: Centralized topic name constants with broker segregation
- **Broker-Specific Topics**: Paper vs Zerodha topic segregation (paper.*, zerodha.*)
- **Market Data Topics**: Shared market data topics with asset class routing
- **DLQ Support**: Dead Letter Queue topic definitions
- **Topic Helpers**: Utility methods for dynamic topic name generation

### `topic_validator.py`
Topic name validation and compliance checking:

- **Topic Validation**: Ensures topic names follow naming conventions
- **Broker Segregation**: Validates proper broker namespace usage
- **Pattern Matching**: Regex-based topic name validation
- **Compliance Checking**: Enforces architectural topic patterns

## Key Features

- **Event Envelope Standard**: Mandatory EventEnvelope for all inter-service communication
- **Correlation Tracking**: Built-in correlation and causation ID tracking
- **Type Safety**: Full Pydantic validation for all event data
- **Broker Segregation**: Hard topic-level isolation between paper and Zerodha
- **Deduplication Support**: UUID v7 based event deduplication
- **JSON Serialization**: Proper handling of Decimal and datetime serialization
- **Topic Validation**: Compile-time and runtime topic name validation

## Usage

### Event Envelope Usage
```python
from core.schemas.events import EventEnvelope, EventType, TradingSignal
from datetime import datetime
from decimal import Decimal

# Create standardized event envelope
signal_data = TradingSignal(
    strategy_id="momentum_v1",
    instrument_token=256265,
    signal_type="buy",
    quantity=100,
    price=Decimal("2500.50"),
    timestamp=datetime.now(),
    broker="zerodha"
)

envelope = EventEnvelope(
    event_type=EventType.TRADING_SIGNAL,
    data=signal_data,
    correlation_id="corr-123-abc",
    causation_id="market-tick-456"
)

# All events must use this envelope format
```

### Topic Name Usage
```python
from core.schemas.topics import TopicNames

# Use centralized topic definitions
market_topic = TopicNames.MARKET_TICKS
paper_signals = TopicNames.get_signals_topic("paper") 
zerodha_orders = TopicNames.get_orders_topic("zerodha")

# Broker-specific topic generation
def get_order_topic(broker: str) -> str:
    return TopicNames.get_orders_topic(broker)

# Send to appropriate broker topic
await producer.send(get_order_topic("paper"), order_data)
```

### Data Model Validation
```python
from core.schemas.events import MarketTick, OrderFilled
from decimal import Decimal

# Market data with full validation
tick = MarketTick(
    instrument_token=256265,
    last_price=Decimal("2500.75"),
    volume=1000,
    timestamp=datetime.now()
)

# Order execution data
order_fill = OrderFilled(
    broker="zerodha",
    order_id="ORD-123",
    instrument_token=256265,
    quantity=100,
    fill_price=Decimal("2500.50"),
    timestamp=datetime.now()
)
```

## Event Types

### Core Event Types
- **MARKET_TICK**: Real-time market data updates
- **TRADING_SIGNAL**: Strategy-generated trading signals  
- **VALIDATED_SIGNAL**: Risk-approved trading signals
- **REJECTED_SIGNAL**: Risk-rejected trading signals
- **ORDER_PLACED**: Order submission confirmations
- **ORDER_FILLED**: Order execution confirmations
- **ORDER_FAILED**: Order execution failures
- **PNL_SNAPSHOT**: Portfolio profit/loss snapshots
- **SYSTEM_ERROR**: System-level error events

### Event Data Models

#### MarketTick
- **instrument_token**: Unique instrument identifier
- **last_price**: Current market price (Decimal)
- **timestamp**: Tick timestamp
- **symbol**: Optional symbol (when available from source)
- **volume_traded / depth / ohlc / oi**: Optional market structure fields

#### TradingSignal  
- **strategy_id**: Originating strategy identifier
- **instrument_token**: Target instrument
- **signal_type**: "buy" or "sell"
- **quantity**: Number of shares/units
- **price**: Target price (Decimal)
- **broker**: Target broker for execution

#### OrderFilled
- **broker**: Executing broker
- **order_id**: Unique order identifier
- **instrument_token**: Executed instrument
- **quantity**: Executed quantity
- **fill_price**: Execution price (Decimal)
- **timestamp**: Fill timestamp

## Topic Naming Convention

### Broker-Segregated Topics
**Format**: `{broker}.{domain}.{event_type}[.dlq]`

**Examples**:
- Paper Trading: `paper.signals.raw`, `paper.orders.filled`, `paper.pnl.snapshots`
- Zerodha Trading: `zerodha.signals.validated`, `zerodha.orders.placed`, `zerodha.orders.filled`
- Dead Letter Queue: `paper.orders.filled.dlq`, `zerodha.signals.raw.dlq`

### Shared Topics
- **Market Data**: `market.ticks` (single source for all brokers)
- **System Events**: `system.errors`, `system.health`

### Topic Categories
- **Market Data**: `market.*` - Market data feeds
- **Signals**: `{broker}.signals.*` - Trading signal pipeline
- **Orders**: `{broker}.orders.*` - Order lifecycle events  
- **Portfolio**: `{broker}.pnl.*` - Portfolio and PnL updates
- **System**: `system.*` - System-level events

## Architecture Patterns

- **Event Envelope Pattern**: Standardized message wrapper with metadata
- **Event Sourcing**: Time-ordered events with correlation tracking
- **Broker Segregation**: Hard isolation via topic namespaces
- **Type Safety**: Pydantic validation for all data structures
- **Deduplication**: Event ID based deduplication support
- **Schema Evolution**: Versioned schemas for backward compatibility

## Validation Rules

### Event Envelope Requirements
- **Mandatory Fields**: id, correlation_id, event_type, timestamp, data
- **Optional Fields**: causation_id, trace_id, parent_trace_id
- **Data Validation**: All event data must use defined Pydantic models

### Topic Naming Rules
- **Broker Prefixes**: All broker-specific topics must be prefixed (paper.*, zerodha.*)
- **Domain Separation**: Topics grouped by domain (signals, orders, pnl, market)
- **No Wildcards**: Services must subscribe to specific topics, no wildcard patterns
- **DLQ Suffix**: Dead letter topics use .dlq suffix

### Data Type Rules
- **Decimal Precision**: All monetary values must use Decimal type
- **Timezone Awareness**: All timestamps must be timezone-aware
- **Required Fields**: All data models must specify required vs optional fields
- **Type Hints**: Full type annotations required for all model fields

## Best Practices

1. **Use Event Envelopes**: All inter-service messages must use EventEnvelope
2. **Include Correlation IDs**: Enable tracing across service boundaries
3. **Validate Early**: Use Pydantic validation at service boundaries
4. **Type Safety**: Always use defined event types and data models
5. **Broker Segregation**: Respect topic namespace isolation
6. **Schema Versioning**: Plan for schema evolution and backward compatibility

## Dependencies

- **pydantic**: Data validation and settings management
- **decimal**: High-precision decimal arithmetic for financial data
- **datetime**: Timezone-aware timestamp handling
- **uuid**: Event ID generation for deduplication
- **enum**: Type-safe enumeration for event types
