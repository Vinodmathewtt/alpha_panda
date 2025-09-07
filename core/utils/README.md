# Core Utils Module

## Overview

The `core/utils/` module provides common utilities, exception handling, and supporting infrastructure used throughout Alpha Panda. It includes structured exception hierarchies, circuit breaker patterns, and state management utilities.

## Components

### `exceptions.py`
Structured exception hierarchy for comprehensive error handling:

- **AlphaPandaException**: Base exception class with correlation tracking
- **TransientError**: Retryable errors with exponential backoff support
- **PermanentError**: Non-retryable errors for immediate DLQ routing
- **Domain-Specific Exceptions**: Trading, authentication, validation, and infrastructure errors
- **Error Context**: Rich error context with correlation IDs and metadata

### `circuit_breaker.py`
Circuit breaker pattern implementation for service protection:

- **CircuitBreaker**: Main circuit breaker implementation
- **Failure Detection**: Automatic failure threshold detection
- **State Management**: Open, closed, half-open state management
- **Recovery Logic**: Automatic recovery attempt coordination
- **Metrics Integration**: Circuit breaker metrics and monitoring

### `state_manager.py`
Application state management and persistence utilities:

- **StateManager**: Central state management coordinator
- **State Persistence**: Redis-backed state persistence
- **State Recovery**: Automatic state recovery on service restart
- **State Validation**: State consistency and validation
- **Multi-Broker State**: Broker-isolated state management

### `__init__.py`
Module exports and convenience functions for common utilities.

## Key Features

- **Structured Error Handling**: Comprehensive exception hierarchy with rich context
- **Circuit Breaker Protection**: Service protection from cascading failures
- **State Management**: Centralized application state with persistence
- **Correlation Tracking**: Error correlation across service boundaries
- **Retry Logic**: Built-in retry mechanisms with exponential backoff
- **Multi-Broker Support**: Broker-isolated utility functions
- **Monitoring Integration**: Rich metrics and monitoring support

## Usage

### Exception Handling
```python
from core.utils.exceptions import (
    TradingError,
    AuthenticationError,
    ValidationError,
    TransientError,
    PermanentError
)

try:
    # Trading operation
    result = await trading_operation()
    
except AuthenticationError as e:
    # Transient error - retry with backoff
    logger.warning(f"Auth failed, will retry: {e.message}")
    if e.retryable:
        await asyncio.sleep(2 ** e.retry_count)
        # Retry logic
        
except ValidationError as e:
    # Permanent error - send to DLQ
    logger.error(f"Validation failed: {e.message}")
    await send_to_dlq(message, str(e))
    
except TradingError as e:
    # Trading-specific error handling
    logger.error(f"Trading error: {e.message}", extra={
        "order_id": e.details.get("order_id"),
        "broker": e.details.get("broker"),
        "correlation_id": e.correlation_id
    })
```

### Circuit Breaker Usage
```python
from core.utils.circuit_breaker import CircuitBreaker

# Initialize circuit breaker
circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    timeout=30,  # seconds
    expected_exception=AuthenticationError
)

# Use circuit breaker to protect operations
@circuit_breaker
async def protected_api_call():
    # External API call that might fail
    return await external_api.call()

# Manual circuit breaker usage
async def manual_protection():
    try:
        async with circuit_breaker:
            result = await risky_operation()
            return result
    except CircuitBreakerOpenException:
        # Circuit is open, fallback behavior
        return await fallback_operation()
```

### State Management
```python
from core.utils.state_manager import StateManager

# Initialize state manager
state_manager = StateManager(redis_client, namespace="trading_engine")

# Store state
await state_manager.set_state("portfolio", {
    "cash": 100000.0,
    "positions": {"RELIANCE": 100}
})

# Retrieve state
portfolio = await state_manager.get_state("portfolio")

# Multi-broker state isolation
await state_manager.set_broker_state("zerodha", "orders", order_data)
zerodha_orders = await state_manager.get_broker_state("zerodha", "orders")
```

## Exception Hierarchy

### Base Exceptions
- **AlphaPandaException**: Root exception with correlation tracking
- **TransientError**: Retryable errors with backoff support
- **PermanentError**: Non-retryable errors for DLQ routing

### Domain-Specific Exceptions

#### Authentication & Authorization
- **AuthenticationError**: Login/token failures (transient)
- **AuthorizationError**: Permission denied (permanent)
- **TokenExpiredError**: Expired authentication tokens (transient)

#### Trading & Market Data
- **TradingError**: Generic trading operation failures
- **OrderExecutionError**: Order placement/execution failures
- **MarketDataError**: Market data feed issues (transient)
- **InstrumentError**: Invalid instrument data (permanent)

#### Validation & Configuration
- **ValidationError**: Data validation failures (permanent)
- **ConfigurationError**: Invalid configuration (permanent)
- **SchemaValidationError**: Event schema validation failures

#### Infrastructure
- **DatabaseError**: Database connection/query failures (transient)
- **CacheError**: Redis/cache operation failures (transient)
- **NetworkError**: Network connectivity issues (transient)
- **ServiceUnavailableError**: Dependent service unavailable (transient)

## Circuit Breaker States

### State Definitions
- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Circuit is open, requests fail immediately
- **HALF_OPEN**: Testing recovery, limited requests allowed

### Configuration Parameters
- **failure_threshold**: Number of failures before opening circuit
- **timeout**: Time to wait before attempting recovery
- **success_threshold**: Successes needed to close circuit in half-open state
- **expected_exception**: Exception types that trigger circuit breaker

### Example Configuration
```python
circuit_breaker = CircuitBreaker(
    failure_threshold=5,     # Open after 5 failures
    timeout=30,             # Wait 30 seconds before retry
    success_threshold=3,    # Need 3 successes to close
    expected_exception=(NetworkError, ServiceUnavailableError)
)
```

## State Management Features

### State Types
- **Service State**: Individual service configuration and runtime state
- **Portfolio State**: Trading portfolio positions and cash balances
- **Order State**: Active and historical order information
- **Market State**: Current market status and session information
- **System State**: System-wide configuration and health status

### Persistence Patterns
```python
# Atomic state updates
async with state_manager.transaction():
    await state_manager.update_state("portfolio", portfolio_update)
    await state_manager.update_state("orders", order_update)

# State versioning
await state_manager.set_versioned_state("config", config_data, version=2)
current_version = await state_manager.get_state_version("config")

# State expiration
await state_manager.set_state_with_ttl("session", session_data, ttl=3600)
```

## Error Recovery Patterns

### Retry with Exponential Backoff
```python
async def retry_with_backoff(operation, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await operation()
        except TransientError as e:
            if not e.retryable:
                raise
            wait_time = 2 ** attempt
            await asyncio.sleep(wait_time)
    raise PermanentError("Max retries exceeded")
```

### DLQ Routing (per-topic .dlq)
```python
async def handle_message_with_dlq(message, processor):
    try:
        await processor(message)
    except PermanentError as e:
        # Send to a per-topic DLQ (e.g., "paper.orders.filled.dlq")
        dlq_topic = f"{message.topic}.dlq"
        await dlq_producer.send(dlq_topic, {
            "original_message": message,
            "error": str(e),
            "error_details": e.details,
            "correlation_id": e.correlation_id,
            "timestamp": e.timestamp.isoformat()
        })
```

## Architecture Patterns

- **Exception Hierarchy**: Structured exception classification for proper handling
- **Circuit Breaker**: Protection against cascading failures
- **State Machine**: State management with transitions and validation
- **Repository Pattern**: State persistence abstraction
- **Decorator Pattern**: Circuit breaker and retry decorators
- **Context Manager**: Resource management and transaction support

## Best Practices

1. **Use Specific Exceptions**: Choose appropriate exception types for different errors
2. **Include Rich Context**: Provide correlation IDs and relevant details
3. **Distinguish Error Types**: Classify as transient or permanent appropriately
4. **Circuit Breaker Protection**: Protect external dependencies with circuit breakers
5. **State Isolation**: Maintain proper state isolation between brokers
6. **Monitoring Integration**: Ensure all errors and state changes are monitored

## Dependencies

- **redis**: State persistence and caching
- **asyncio**: Async utility operations
- **datetime**: Timestamp and time-based operations
- **typing**: Type hints for utility functions
- **core.logging**: Error logging and correlation tracking
