# Event System Refactor Migration Guide

## Overview

The AlphaPT event system has been completely refactored to address several critical issues and improve maintainability. This guide helps you migrate from the old system to the new one.

## What Changed

### 🗂️ File Structure
- **Old files moved to** `core/events/archive/`
- **New components** implemented with clear separation of concerns
- **Backward compatibility** maintained where possible

### 🏗️ Architecture Changes

#### Before (Old System)
```python
# Monolithic EventBus handling everything
from core.events import EventBus, EventPublisher, EventSubscriber

event_bus = EventBus(settings)
await event_bus.connect()
await event_bus.publish("subject", event_dict)  # Published raw dicts
await event_bus.subscribe("pattern", callback)
```

#### After (New System)  
```python
# Clean separation of concerns
from core.events import (
    get_event_bus_core, get_event_publisher, 
    subscriber, create_subscriber_manager
)

# Connection management only
event_bus = get_event_bus_core()
await event_bus.connect()

# Dedicated publishing service
publisher = get_event_publisher()
await publisher.publish("subject", event_object)  # Publishes typed events

# Declarative subscription with decorators
@subscriber.on_event("pattern.*")
async def handle_event(event: EventType):
    # Automatically gets typed, deserialized event
    pass
```

## Migration Steps

### Step 1: Update Imports

**Replace Old Imports:**
```python
from core.events import EventBus, EventPublisher, EventSubscriber
```

**With New Imports:**
```python
from core.events import (
    EventBusCore, get_event_bus_core,
    EventPublisherService, get_event_publisher,
    subscriber, create_subscriber_manager
)
```

### Step 2: Connection Management

**Old Way:**
```python
event_bus = EventBus(settings)
await event_bus.connect()
```

**New Way:**
```python
event_bus = get_event_bus_core(settings)  # Singleton
await event_bus.connect()
```

### Step 3: Publishing Events

**Old Way:**
```python
# Published raw dictionaries (problematic!)
await event_bus.publish("market.tick", {
    "instrument_token": 123456,
    "last_price": 100.50
})
```

**New Way:**
```python
# Publish typed event objects (robust!)
publisher = get_event_publisher()

event = MarketDataEvent(
    event_id=str(uuid.uuid4()),
    event_type=EventType.MARKET_TICK,
    timestamp=datetime.now(timezone.utc),
    source="market_feed",
    instrument_token=123456,
    last_price=100.50
)

await publisher.publish("market.tick.NSE.123456", event)
```

### Step 4: Event Subscription

**Old Way (Manual Subscription):**
```python
async def my_handler(msg):
    # Manual deserialization required
    try:
        data = json.loads(msg.data)
        # Process raw data...
        await msg.ack()
    except Exception as e:
        # Manual error handling...
        pass

await event_bus.subscribe("market.tick.*", my_handler)
```

**New Way (Declarative with Decorators):**
```python
@subscriber.on_event("market.tick.*", durable_name="my-consumer")
async def my_handler(event: MarketDataEvent):
    # Automatic deserialization, error handling, and ack!
    print(f"Price: {event.last_price}")
    # Framework handles ack/nack automatically
```

### Step 5: Application Lifecycle

**Old Way:**
```python
# Complex manual management
event_bus = EventBus(settings)
await event_bus.connect()
# Manual subscription management...
```

**New Way:**
```python
# Clean startup
event_bus = get_event_bus_core(settings)
await event_bus.connect()

subscriber_manager = create_subscriber_manager()
await subscriber_manager.start()  # Discovers and subscribes ALL @subscriber decorated functions

# Clean shutdown
await subscriber_manager.stop()
await event_bus.disconnect()
```

## Key Benefits of New System

### ✅ Solved Issues
- **No more deserialization bugs**: Schema registry ensures proper event parsing
- **No more manual subscription tracking**: SubscriberManager handles it all
- **No more raw dictionary publishing**: Type-safe event objects only
- **No more complex error handling**: Built into wrapper functions
- **No more race conditions**: Proper async patterns throughout

### 🏗️ Architectural Improvements
- **Single Responsibility**: Each component does one thing well
- **Declarative Handlers**: Business logic is clean, infrastructure is hidden
- **Schema-Driven**: Event structure is enforced and validated
- **Retry Logic**: Built-in resilience for publishing failures
- **Compression Support**: Automatic payload optimization

### 🧹 Developer Experience
- **Less Boilerplate**: Decorators eliminate subscription management code
- **Type Safety**: Full IDE support with typed event objects
- **Easier Testing**: Components are decoupled and mockable
- **Clear Errors**: Specific exceptions with helpful error messages

## Common Migration Patterns

### Pattern 1: Strategy Manager Event Handling
**Before:**
```python
class StrategyManager:
    async def _setup_subscriptions(self):
        await self.event_bus.subscribe("trading.signals.*", self._handle_signal)
    
    async def _handle_signal(self, msg):
        try:
            data = json.loads(msg.data)
            # Manual parsing and processing...
            await msg.ack()
        except Exception as e:
            # Manual error handling...
            await msg.nak()
```

**After:**
```python
@subscriber.on_event("trading.signals.*", durable_name="strategy-manager-signals")
async def handle_trading_signal(event: TradingEvent):
    # Automatic deserialization and error handling
    strategy_name = event.strategy_name
    # Process signal...
    # Automatic ack/nack based on success/failure
```

### Pattern 2: Market Data Processing
**Before:**
```python
async def market_data_callback(msg):
    try:
        tick_data = json.loads(msg.data)
        # Process raw dictionary...
        await msg.ack()
    except Exception:
        await msg.nak()
```

**After:**
```python
@subscriber.on_event("market.tick.NSE.*", queue_group="tick-processors")
async def handle_nse_tick(event: MarketDataEvent):
    # Typed event object with full IDE support
    if event.last_price > threshold:
        await generate_signal(event.instrument_token, event.last_price)
```

## Backward Compatibility

### Legacy Support
The old components are still available in the archive for temporary compatibility:

```python
# Still works (but deprecated)
try:
    from core.events.archive.event_bus import EventBus  # Legacy
    print("Using legacy EventBus")
except ImportError:
    from core.events import get_event_bus_core  # New
    print("Using new EventBusCore")
```

### Gradual Migration Strategy
1. **Phase 1**: Install new system alongside old system
2. **Phase 2**: Migrate publishing to new `EventPublisherService`  
3. **Phase 3**: Convert subscriptions to `@subscriber.on_event` decorators
4. **Phase 4**: Remove legacy imports and clean up old code
5. **Phase 5**: Delete archive folder when migration complete

## Testing the New System

```python
# Run the demo
python examples/refactored_event_system_demo.py

# Run unit tests
pytest tests/unit/test_refactored_event_system.py -v
```

## Troubleshooting

### Common Issues

1. **Import Error**: `Cannot import EventPublishError`
   - **Solution**: Make sure you're importing from the new modules, not archived ones

2. **Decorator Not Working**: Handler not receiving events
   - **Solution**: Ensure `SubscriberManager.start()` is called during app startup

3. **Event Deserialization Fails**: Wrong event type received
   - **Solution**: Check that event type strings match EventType enum values

### Getting Help
- Check `examples/refactored_event_system_demo.py` for usage patterns
- Review tests in `tests/unit/test_refactored_event_system.py`
- Examine the refactor plan: `docs/2_EVENT_SYSTEM_REFACTOR_AND_REBUILD_PLAN.md`

---

**The refactored event system delivers on the promise: cleaner, lighter, and less problematic! 🎉**