Of course. While the existing event system has a solid foundation with NATS JetStream and includes many advanced features, a different architectural approach could have enhanced its robustness, maintainability, and developer experience from the outset.

Here’s a blueprint for an idealized event system designed for a high-performance trading environment.

---

### 🏛️ Core Design Principles

A production-grade event system for algorithmic trading should be built on the following principles:

1.  **Separation of Concerns**: Each component should do one thing well. The event bus should manage connections, publishers should handle publishing logic, and subscribers should focus on consuming events.
2.  **Explicit Contracts (Schema-Driven)**: Events are the lifeblood of the system. Their structure should be rigorously defined, versioned, and validated, making the interactions between components predictable.
3.  **Declarative Usage**: Developers should declare their intent (e.g., "this function handles this event") rather than writing boilerplate code for subscribing and handling messages.
4.  **Decoupled Components**: The event bus should be a transport layer, not a monolith. Publishers and subscribers should not need to know the intricate details of its internal workings.
5.  **Transparent Observability**: Metrics, logs, and traces should be built-in, not bolted on. It should be effortless to understand the health and performance of the event flow.

---

### 🏗️ An Alternative Architectural Blueprint

Based on these principles, here is a more robust and maintainable architecture.

This design introduces a clearer separation of responsibilities:

#### 1\. The "Thin" `EventBus` Core

The `EventBus` class would be dramatically simplified. Its **only job** is to manage the connection to NATS JetStream.

- **Responsibilities**:
  - Connect and disconnect from the NATS server.
  - Handle reconnection logic and connection-related callbacks (`_error_callback`, `_reconnected_callback`, etc.).
  - Expose the raw `nats.js` context for other components to use.
- **What it _doesn't_ do**:
  - It does **not** have `publish` or `subscribe` methods.
  - It does **not** manage streams, consumers, or metrics.

This makes the `EventBus` a simple, stable, and highly reusable component.

#### 2\. A Centralized `SchemaRegistry` and Smart `EventFactory`

This component addresses the critical deserialization flaw head-on.

- **`SchemaRegistry`**:
  - A simple registry that maps an `event_type` string (e.g., `"MARKET_TICK"`) to its corresponding Python class (e.g., `MarketDataEvent`).
  - It can be extended to handle event versioning (e.g., `"MARKET_TICK_V2"`).
- **`EventFactory`**:
  - A class with a `deserialize` method that takes raw message data.
  - It inspects the `event_type` field in the JSON payload, looks up the correct class in the `SchemaRegistry`, and instantiates the correct event object.
  - It also handles decompression based on message headers.

<!-- end list -->

```python
# Conceptual Example
class EventFactory:
    def __init__(self, registry: SchemaRegistry):
        self.registry = registry

    def deserialize(self, msg: nats.aio.msg.Msg) -> BaseEvent:
        data = self._decompress_if_needed(msg.data, msg.headers)
        event_dict = json.loads(data)
        event_type = event_dict.get("event_type")

        event_class = self.registry.get_class_for(event_type)
        if not event_class:
            raise EventParsingError(f"Unknown event type: {event_type}")

        return event_class.from_dict(event_dict)
```

#### 3\. An Intentional `EventPublisher` Service

This service would be the single, authoritative way to publish events. It provides different publishing strategies based on reliability and performance needs.

- **Responsibilities**:
  - Takes an `EventBus` and `EventFactory` as dependencies.
  - Provides methods like `publish(event, subject)` and `publish_batch(events)`.
  - Internally, it handles serialization, compression, and setting the correct headers.
  - Implements retry logic and circuit-breaking for publish operations.
- **High-Performance Mode**: For extreme throughput scenarios (like market data), it could use a background task for batching and sending, similar to the existing `HighPerformancePublisher`.

#### 4\. A Declarative `EventSubscriber` Model (Using Decorators)

This is a significant departure from the current design and dramatically improves the developer experience. Instead of manually creating subscribers and passing callbacks, developers would use decorators.

- **How it works**:
  1.  A developer decorates a function with `@subscriber.on_event("subject.pattern.*")`.
  2.  During application startup, a central `SubscriberManager` discovers all decorated functions.
  3.  The `SubscriberManager` uses the `EventBus` to create the necessary NATS subscriptions and binds them to the decorated functions.
  4.  The manager also handles creating durable consumers, message acknowledgment, and routing messages to the correct handler.

<!-- end list -->

```python
# Conceptual Example of what a developer would write
from .event_system import subscriber

@subscriber.on_event(
    "market.tick.NSE.*",
    durable_name="strategy_alpha_ticks",
    ack_policy=AckPolicy.EXPLICIT
)
async def handle_market_tick(event: MarketDataEvent):
    """This function automatically receives deserialized MarketDataEvent objects."""
    print(f"Received tick for {event.instrument_token}: {event.last_price}")
    # The framework handles acknowledging the message after this function completes.
```

This approach is:

- **Cleaner**: Business logic is not cluttered with subscription boilerplate.
- **Safer**: It eliminates common errors like forgetting to `await` a callback or incorrect subscription tracking.
- **More Maintainable**: It's easy to see which functions are triggered by which events.

---

### 📈 Benefits of This Design

- **Robustness**: By separating concerns and using explicit schemas, the system becomes far more predictable and less prone to runtime errors.
- **Maintainability**: Each component is smaller, simpler, and has a clear purpose, making it easier to modify and test.
- **Developer Experience**: The declarative subscriber model is intuitive and reduces the cognitive load on developers, allowing them to focus on writing trading logic.
- **Scalability**: With a clear separation between the "thin" event bus and the publisher/subscriber logic, it's easier to scale different parts of the system independently. For example, you could run multiple instances of a high-throughput publisher service.

"Thin" `EventBus`
Here is the complete code for the refactored "Thin" `EventBus` Core, followed by a detailed explanation of its design.

This version is significantly simplified, focusing only on the essential responsibility of managing the NATS connection.

### ⚙️ Full Code for the "Thin" `EventBus`

```python
# Location: core/events/event_bus_core.py

import asyncio
import logging
from typing import Any, Dict, Optional

import nats
from nats.js import JetStreamContext

from core.config.settings import Settings
from core.utils.exceptions import ConnectionError

logger = logging.getLogger(__name__)


class EventBusCore:
    """
    A simplified, core event bus responsible only for managing the NATS connection lifecycle.

    This class acts as a connection manager and provides access to the underlying NATS
    and JetStream contexts. It does not handle publishing, subscribing, or stream management.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[JetStreamContext] = None
        self._is_connected = False
        self._connection_lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Returns the current connection status."""
        return self._is_connected

    async def connect(self) -> None:
        """
        Connects to the NATS server and establishes a JetStream context.

        This method is idempotent and thread-safe, ensuring that only one
        connection attempt occurs at a time.
        """
        async with self._connection_lock:
            if self.is_connected:
                logger.debug("Already connected to NATS.")
                return

            try:
                options = {
                    "servers": [self.settings.nats_url],
                    "max_reconnect_attempts": self.settings.nats_max_reconnect_attempts,
                    "reconnect_time_wait": self.settings.nats_reconnect_time_wait,
                    "error_cb": self._on_error,
                    "disconnected_cb": self._on_disconnect,
                    "reconnected_cb": self._on_reconnect,
                    "name": "AlphasPT-CoreConnection"
                }

                if self.settings.nats_user:
                    options["user"] = self.settings.nats_user
                    options["password"] = self.settings.nats_password

                self.nc = await nats.connect(**options)
                self.js = self.nc.jetstream()
                self._is_connected = True
                logger.info("EventBusCore successfully connected to NATS JetStream.")

            except Exception as e:
                logger.critical(f"Failed to connect to NATS: {e}", exc_info=True)
                # Clean up any partial connections on failure
                if self.nc and not self.nc.is_closed:
                    await self.nc.close()
                self.nc = None
                self.js = None
                self._is_connected = False
                raise ConnectionError(f"NATS connection failed: {e}") from e

    async def disconnect(self) -> None:
        """
        Gracefully disconnects from the NATS server.

        Drains the connection to ensure all buffered messages are sent before closing.
        """
        async with self._connection_lock:
            if not self.is_connected or not self.nc:
                logger.debug("Already disconnected from NATS.")
                return

            try:
                if not self.nc.is_closed:
                    await self.nc.drain()
                    await self.nc.close()
                logger.info("EventBusCore disconnected from NATS.")
            except Exception as e:
                logger.error(f"Error during NATS disconnection: {e}", exc_info=True)
            finally:
                self.nc = None
                self.js = None
                self._is_connected = False

    async def _on_error(self, e: Exception) -> None:
        """Callback for handling connection errors."""
        logger.error(f"NATS connection error: {e}")

    async def _on_disconnect(self) -> None:
        """Callback for handling disconnections."""
        if self.is_connected: # Only log if it was an unexpected disconnect
            logger.warning("NATS connection lost. Attempting to reconnect...")
        self._is_connected = False

    async def _on_reconnect(self) -> None:
        """Callback for handling successful reconnections."""
        self._is_connected = True
        logger.info("NATS connection successfully restored.")


# --- Singleton Pattern for Global Access ---
_event_bus_core_instance: Optional[EventBusCore] = None

def get_event_bus_core(settings: Optional[Settings] = None) -> EventBusCore:
    """
    Gets the global singleton instance of the EventBusCore.

    This ensures that the entire application shares a single NATS connection manager.
    """
    global _event_bus_core_instance
    if _event_bus_core_instance is None:
        if settings is None:
            from core.config.settings import settings as default_settings
            settings = default_settings
        _event_bus_core_instance = EventBusCore(settings)
    return _event_bus_core_instance
```

---

### 🏛️ Design Explanation

This refactored `EventBusCore` embodies the **"Separation of Concerns"** principle. Its sole purpose is to be an expert at managing the NATS connection lifecycle.

#### 1\. **Single, Clear Responsibility**

The class is now a **Connection Manager**, not a monolithic event system. Its public API is minimal and focused:

- `connect()`: Establishes the connection.
- `disconnect()`: Tears down the connection.
- `is_connected`: A property to check the status.

This clarity makes the component much easier to understand, test, and maintain.

---

#### 2\. **What Was Removed and Why**

The most important changes are what the class _no longer does_. All of the following responsibilities have been stripped out to be handled by other, more specialized components:

- **No `publish()` method**: Publishing logic, including serialization and error handling, belongs in a dedicated `EventPublisher` service. This allows you to have different publishing strategies (e.g., batching vs. immediate) without cluttering the core connection logic.
- **No `subscribe()` method**: Subscription management, including creating consumers and routing messages to callbacks, is complex. This should be handled by a dedicated `SubscriberManager`, ideally using a declarative pattern like decorators.
- **No Stream or Consumer Management (`_create_streams`)**: Defining and managing JetStream streams and consumers is an administrative task. This logic belongs in a `StreamManager`, which can be run as a startup task or a separate operational script. Decoupling this prevents connection logic from being tied to a specific application's stream topology.
- **No Metrics or Monitoring**: Performance monitoring (`performance_monitor`), circuit breaking, and health checks are observability concerns. They should be implemented in a separate observability layer that can monitor the entire system, not just the event bus. The connection callbacks (`_on_error`, etc.) provide the necessary hooks for this layer to monitor connection health.

---

#### 3\. **Concurrency and Safety**

An `asyncio.Lock` (`_connection_lock`) is used to wrap the `connect` and `disconnect` logic. This is crucial in a complex asynchronous application where multiple components might try to initiate a connection or disconnection simultaneously, especially during startup or shutdown. The lock **prevents race conditions**, ensuring that these critical operations happen in an orderly, atomic fashion.

By adopting this "thin core" design, you create a stable and reliable foundation. Other components, like the `EventPublisher` and `SubscriberManager`, can then be built on top of this foundation, each focusing on its specific task without interfering with the others.

## A Centralized SchemaRegistry and Smart EventFactory

Of course. Here is the full code for a centralized `SchemaRegistry` and its companion `EventFactory`.

This design directly solves the critical deserialization bug in the original codebase and establishes a robust, maintainable pattern for handling different event types.

### ⚙️ Full Code for `SchemaRegistry` and `EventFactory`

```python
# Location: core/events/schema_registry.py

import json
import logging
from typing import Dict, Optional, Type

import nats

from .event_exceptions import EventParsingError, EventRegistrationError
from .event_types import (BaseEvent, EventType, MarketDataEvent,
                          SystemEvent, TradingEvent, RiskEvent)

logger = logging.getLogger(__name__)


class SchemaRegistry:
    """
    A centralized registry that maps event types to their corresponding data classes.

    This component provides a single source of truth for event schemas, ensuring
    that the system knows how to parse different types of incoming events.
    """

    def __init__(self):
        self._registry: Dict[EventType, Type[BaseEvent]] = {}

    def register_event(self, event_type: EventType, event_class: Type[BaseEvent]):
        """
        Registers an event type and its associated class.

        Args:
            event_type: The enum member for the event type (e.g., EventType.MARKET_TICK).
            event_class: The data class that represents the event (e.g., MarketDataEvent).

        Raises:
            EventRegistrationError: If the event type is already registered.
        """
        if event_type in self._registry:
            raise EventRegistrationError(f"Event type '{event_type.value}' is already registered.")

        logger.debug(f"Registering event type '{event_type.value}' with class {event_class.__name__}.")
        self._registry[event_type] = event_class

    def get_class_for(self, event_type: EventType) -> Optional[Type[BaseEvent]]:
        """
        Retrieves the class associated with a given event type.

        Returns:
            The event class if found, otherwise None.
        """
        return self._registry.get(event_type)

# --- Pre-populated default registry ---
# In a real application, this could be populated dynamically during startup
# by discovering event classes throughout the codebase.
default_schema_registry = SchemaRegistry()
default_schema_registry.register_event(EventType.MARKET_TICK, MarketDataEvent)
default_schema_registry.register_event(EventType.TRADING_SIGNAL, TradingEvent)
default_schema_registry.register_event(EventType.ORDER_PLACED, TradingEvent)
default_schema_registry.register_event(EventType.ORDER_FILLED, TradingEvent)
default_schema_registry.register_event(EventType.ORDER_CANCELLED, TradingEvent)
default_schema_registry.register_event(EventType.ORDER_REJECTED, TradingEvent)
default_schema_registry.register_event(EventType.SYSTEM_ERROR, SystemEvent)
default_schema_registry.register_event(EventType.SYSTEM_STARTED, SystemEvent)
# ... register all other event types here ...


class EventFactory:
    """
    Deserializes raw messages into strongly-typed event objects using a SchemaRegistry.

    This class is the gatekeeper for incoming data, ensuring that any message
    is correctly parsed into its specific event type before being processed by
    the application's business logic.
    """

    def __init__(self, registry: SchemaRegistry = default_schema_registry):
        self.registry = registry

    def deserialize(self, msg: nats.aio.msg.Msg) -> BaseEvent:
        """
        Parses a raw NATS message into a specific BaseEvent subclass.

        This method handles decompression and uses the schema registry to
        dispatch to the correct data class for parsing.

        Args:
            msg: The raw NATS message.

        Returns:
            A fully instantiated event object (e.g., MarketDataEvent, SystemEvent).

        Raises:
            EventParsingError: If the message payload is invalid, missing a type,
                               or the event type is not registered.
        """
        try:
            # 1. Handle potential compression
            payload = msg.data
            if msg.headers and msg.headers.get('compressed') == 'true':
                import gzip
                payload = gzip.decompress(payload)

            # 2. Decode and parse to a dictionary
            event_dict = json.loads(payload.decode("utf-8"))

            # 3. Extract the event type string
            event_type_str = event_dict.get("event_type")
            if not event_type_str:
                raise EventParsingError("Message payload is missing the 'event_type' field.")

            # 4. Convert string to EventType enum
            try:
                event_type = EventType(event_type_str)
            except ValueError:
                 raise EventParsingError(f"'{event_type_str}' is not a valid EventType.")

            # 5. Look up the corresponding class in the registry
            event_class = self.registry.get_class_for(event_type)
            if not event_class:
                raise EventParsingError(f"No schema registered for event type '{event_type.value}'.")

            # 6. Instantiate the specific event class from the dictionary
            return event_class.from_dict(event_dict)

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise EventParsingError(f"Failed to decode JSON payload: {e}") from e
        except Exception as e:
            # Re-raise known parsing errors, otherwise wrap unknown errors.
            if isinstance(e, EventParsingError):
                raise
            raise EventParsingError(f"An unexpected error occurred during deserialization: {e}") from e

```

---

### 🏛️ Design Explanation

This design introduces a clear, robust, and scalable pattern for handling event data.

#### 1\. **Single Source of Truth (`SchemaRegistry`)**

The `SchemaRegistry` acts as a central dictionary for your event system. Instead of having parsing logic scattered throughout the code, there is now **one place** that defines the relationship between an event's "type" and its data structure.

- **Why is this better?**
  - **Maintainability**: When you add a new event type (e.g., `ComplianceEvent`), you only need to register it in this one location. You don't have to modify complex `if/elif/else` chains in your message handling code.
  - **Clarity**: It provides a clear and immediate overview of all event types the system knows how to handle.
  - **Decoupling**: The registry decouples the message-receiving code from the specific event class implementations. The code that receives a message doesn't need to know about `MarketDataEvent`; it only needs to ask the `EventFactory` to handle it.

#### 2\. **Intelligent Deserialization (`EventFactory`)**

The `EventFactory` is the "smart" component that uses the `SchemaRegistry` to perform its work. It encapsulates the entire process of turning a raw byte payload from NATS into a fully-validated, type-hinted Python object.

Its step-by-step process is crucial for robustness:

1.  **Handles Physical Layer**: It first deals with transport-level concerns like decompression.
2.  **Validates Payload Structure**: It ensures the message is valid JSON and contains the essential `event_type` field.
3.  **Looks up the Schema**: It consults the `SchemaRegistry` to find the "blueprint" (the Python class) for the event.
4.  **Instantiates the Correct Type**: It uses the specific class's logic (e.g., `MarketDataEvent.from_dict`) to create the object. This is what correctly preserves all fields like `last_price`, `instrument_token`, etc.

#### 3\. **Custom Exceptions for Clear Errors**

Using custom exceptions like `EventParsingError` and `EventRegistrationError` is a significant improvement. When a message fails to parse, you get a precise error that tells you _why_ it failed (e.g., "missing event_type field," "unknown event type"). This is invaluable for debugging and for routing unparseable messages to a dead-letter queue.

By implementing this pattern, you eliminate the original deserialization bug and create a system that is easier to reason about, safer to modify, and more resilient to data errors.

## Intentional EventPublisher Service

Of course. Here is the complete code for the refactored `EventPublisherService`, designed to be the single, intentional, and reliable way to send events in your system.

This service encapsulates all the logic related to serialization, compression, and resilient publishing, providing a clean and robust API to the rest of your application.

### ⚙️ Full Code for the `EventPublisherService`

```python
# Location: core/events/event_publisher_service.py

import asyncio
import gzip
import logging
from typing import Optional

from nats.errors import TimeoutError as NatsTimeoutError

from .event_bus_core import EventBusCore, get_event_bus_core
from .event_exceptions import EventPublishError
from .event_types import BaseEvent
from core.config.settings import Settings

logger = logging.getLogger(__name__)


class EventPublisherService:
    """
    A dedicated service for publishing events to the NATS JetStream.

    This service encapsulates all logic for event serialization, compression,
    and reliable delivery with retries. It depends on a connected EventBusCore
    instance to interact with NATS.
    """

    def __init__(self, event_bus: EventBusCore, settings: Settings):
        self.bus = event_bus
        self.settings = settings.event_system.publishing

    async def publish(self, subject: str, event: BaseEvent) -> None:
        """
        Serializes, compresses, and publishes an event with a retry mechanism.

        This is the standard method for reliable, single-event publishing.

        Args:
            subject: The NATS subject to publish the event to.
            event: The event object to be published.

        Raises:
            EventPublishError: If the event cannot be published after all retry attempts.
            ConnectionError: If the event bus is not connected.
        """
        if not self.bus.is_connected or not self.bus.js:
            raise EventPublishError("Event bus is not connected. Cannot publish event.")

        # 1. Serialize the event to its JSON representation.
        payload = event.to_json().encode("utf-8")

        # 2. Compress the payload if enabled.
        if self.settings.compression_enabled:
            payload = gzip.compress(payload)

        # 3. Construct message headers.
        headers = {
            "event-id": event.event_id,
            "event-type": event.event_type.value,
            "source": event.source,
            "timestamp": event.timestamp.isoformat(),
            "compressed": "true" if self.settings.compression_enabled else "false",
        }
        if event.correlation_id:
            headers["correlation-id"] = event.correlation_id

        # 4. Attempt to publish with a retry loop.
        last_exception = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                await self.bus.js.publish(
                    subject=subject,
                    payload=payload,
                    headers=headers,
                    timeout=self.settings.publish_timeout_seconds
                )
                logger.debug(f"Successfully published event {event.event_id} to {subject} on attempt {attempt + 1}.")
                return  # Success, exit the function.

            except NatsTimeoutError as e:
                last_exception = e
                logger.warning(
                    f"Publish attempt {attempt + 1}/{self.settings.max_retries + 1} timed out for event "
                    f"{event.event_id} to {subject}."
                )
            except Exception as e:
                last_exception = e
                logger.error(
                    f"An unexpected error occurred on publish attempt {attempt + 1} for event "
                    f"{event.event_id}: {e}", exc_info=True
                )

            # Wait before retrying, if this is not the last attempt.
            if attempt < self.settings.max_retries:
                delay = self.settings.retry_delay_seconds * (2 ** attempt)  # Exponential backoff
                await asyncio.sleep(delay)

        # If all retries fail, raise a specific error.
        raise EventPublishError(
            f"Failed to publish event {event.event_id} to {subject} after {self.settings.max_retries + 1} attempts."
        ) from last_exception


# --- Singleton Pattern for Global Access ---
_event_publisher_instance: Optional[EventPublisherService] = None

def get_event_publisher(settings: Optional[Settings] = None) -> EventPublisherService:
    """
    Gets the global singleton instance of the EventPublisherService.

    This ensures that all parts of the application use the same publisher
    service, configured with the same settings and sharing the same event bus connection.
    """
    global _event_publisher_instance
    if _event_publisher_instance is None:
        if settings is None:
            from core.config.settings import settings as default_settings
            settings = default_settings

        event_bus_core = get_event_bus_core(settings)
        _event_publisher_instance = EventPublisherService(event_bus_core, settings)

    return _event_publisher_instance

```

You would also need to add a configuration section to your settings file for the publisher.

```python
# Location: core/config/event_config.py

from pydantic import BaseModel, Field

class PublishingConfig(BaseModel):
    """Configuration for the event publishing service."""
    max_retries: int = Field(3, description="Maximum number of retries for a failed publish.")
    retry_delay_seconds: float = Field(0.5, description="Initial delay in seconds for retries.")
    publish_timeout_seconds: float = Field(5.0, description="Timeout for each individual publish attempt.")
    compression_enabled: bool = Field(True, description="Enable gzip compression for event payloads.")

class EventSystemConfig(BaseModel):
    # ... other configs
    publishing: PublishingConfig = PublishingConfig()
```

---

### 🏛️ Design Explanation

This `EventPublisherService` is designed to be the **authoritative** component for sending events. It provides a simple, reliable interface while hiding the underlying complexity.

#### 1\. **Encapsulation of Complexity**

A developer using this service only needs to know two things: the `subject` and the `event` object.

```python
publisher = get_event_publisher()
await publisher.publish("trading.signal.my_strategy", my_signal_event)
```

All the messy but critical details are handled internally:

- **Serialization**: The event object is correctly converted to a JSON string and encoded to bytes.
- **Compression**: The payload is automatically compressed with `gzip` to save network bandwidth and storage, a crucial optimization for high-frequency data.
- **Header Creation**: Standardized headers are consistently applied to every message, which is essential for downstream consumers (like the `EventFactory`) and for observability.
- **Connection Management**: It doesn't manage the connection itself; it correctly uses the shared `EventBusCore` instance, ensuring it doesn't try to publish on a disconnected bus.

#### 2\. **Reliability Through Retries with Exponential Backoff**

In a distributed system, transient network failures are inevitable. A publish operation might fail not because the event is bad, but because of a momentary network hiccup.

This publisher is resilient to such failures:

- **Retry Loop**: It will automatically retry a failed publish operation up to a configured number of times (`max_retries`).
- **Exponential Backoff**: It doesn't hammer the server on failure. The delay between retries increases exponentially (`0.5s`, `1s`, `2s`, `4s`...). This is a standard best practice that gives the network or server time to recover.
- **Specific Errors**: If all retries ultimately fail, it raises a single, specific `EventPublishError`. This allows calling code to handle persistent publishing failures cleanly without needing to implement its own retry logic.

#### 3\. **Clear Separation of Concerns**

This service adheres strictly to its responsibility of _publishing_.

- It is completely decoupled from subscribers and event handlers.
- It has no knowledge of how NATS streams are configured.
- It relies on the `EventBusCore` for the raw connection, reinforcing the architectural separation.

#### 4\. **Configuration-Driven Behavior**

Key operational parameters like retry counts, timeouts, and compression are not hard-coded. They are managed in the central `Settings` object, allowing you to tune the publisher's behavior for different environments (e.g., more aggressive retries in production, no compression in local testing) without changing a single line of code.

By using this intentional service, you make your application code cleaner, more declarative, and far more resilient to the common failures of distributed messaging systems.

## A Declarative EventSubscriber Model (Using Decorators)

Of course. This is the final and most impactful piece of the redesigned architecture. The Declarative Subscriber Model completely changes how developers interact with the event system, making it safer, cleaner, and more intuitive.

Here is the full code for the `SubscriberManager` and the decorator-based system, followed by a detailed explanation and a usage example.

### ⚙️ Full Code for the Declarative Subscriber Model

This system is composed of two main parts: the `SubscriberManager` which does the work, and the `subscriber` object which provides the decorator.

```python
# Location: core/events/subscriber_manager.py

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict, List, Optional

import nats
from nats.js.api import AckPolicy, ConsumerConfig

from .event_bus_core import EventBusCore, get_event_bus_core
from .event_exceptions import EventSubscriptionError
from .event_factory import EventFactory
from .event_types import BaseEvent
from core.config.settings import Settings

logger = logging.getLogger(__name__)

# Type alias for an event handler function
EventHandler = Callable[[BaseEvent], Coroutine[Any, Any, None]]

@dataclass(frozen=True)
class HandlerConfig:
    """Configuration for a discovered event handler."""
    subject_pattern: str
    handler_func: EventHandler
    durable_name: Optional[str] = None
    queue_group: Optional[str] = None
    ack_policy: AckPolicy = AckPolicy.EXPLICIT
    max_deliver: int = 3
    ack_wait_seconds: int = 30


class SubscriberDecorator:
    """
    Provides the @subscriber.on_event() decorator for registering event handlers.

    This class doesn't perform any logic itself. It simply acts as a container
    to store the configuration of all decorated functions across the application,
    which will later be collected by the SubscriberManager.
    """
    def __init__(self):
        self.handlers: List[HandlerConfig] = []

    def on_event(
        self,
        subject_pattern: str,
        *,
        durable_name: Optional[str] = None,
        queue_group: Optional[str] = None,
        ack_policy: AckPolicy = AckPolicy.EXPLICIT,
    ) -> Callable[[EventHandler], EventHandler]:
        """
        Decorator to register an async function as a handler for a NATS subject.
        """
        def decorator(func: EventHandler) -> EventHandler:
            if not asyncio.iscoroutinefunction(func):
                raise TypeError(f"Event handler <{func.__name__}> must be an async function.")

            config = HandlerConfig(
                subject_pattern=subject_pattern,
                handler_func=func,
                durable_name=durable_name,
                queue_group=queue_group,
                ack_policy=ack_policy,
            )
            self.handlers.append(config)
            logger.debug(f"Discovered and registered event handler: {func.__name__} for subject '{subject_pattern}'.")
            return func
        return decorator

# Global instance of the decorator to be imported by other modules.
subscriber = SubscriberDecorator()


class SubscriberManager:
    """

    Discovers, registers, and manages all event subscriptions for the application.

    During application startup, this manager iterates through all handlers registered
    with the global `subscriber` decorator, creates the necessary NATS JetStream
    subscriptions, and wraps the handlers with logic for deserialization, error
    handling, and message acknowledgment.
    """

    def __init__(
        self,
        bus: EventBusCore,
        event_factory: EventFactory,
        handler_source: SubscriberDecorator = subscriber,
    ):
        self.bus = bus
        self.factory = event_factory
        self.handler_source = handler_source
        self._active_subscriptions: List[nats.aio.subscription.Subscription] = []
        self._is_running = False

    async def start(self):
        """
        Starts the manager by subscribing all discovered handlers to NATS.
        """
        if self._is_running:
            logger.warning("SubscriberManager is already running.")
            return

        if not self.bus.is_connected or not self.bus.js:
            raise EventSubscriptionError("Cannot start SubscriberManager: EventBusCore is not connected.")

        logger.info(f"Starting SubscriberManager. Found {len(self.handler_source.handlers)} event handlers to subscribe.")

        for config in self.handler_source.handlers:
            await self._subscribe_handler(config)

        self._is_running = True
        logger.info("SubscriberManager started successfully and all handlers are subscribed.")

    async def stop(self):
        """
        Gracefully unsubscribes all active event handlers.
        """
        if not self._is_running:
            return

        logger.info(f"Stopping SubscriberManager. Unsubscribing {len(self._active_subscriptions)} active handlers.")

        # Unsubscribe all active subscriptions concurrently
        unsubscribe_tasks = [sub.unsubscribe() for sub in self._active_subscriptions]
        await asyncio.gather(*unsubscribe_tasks, return_exceptions=True)

        self._active_subscriptions.clear()
        self._is_running = False
        logger.info("SubscriberManager stopped.")

    async def _subscribe_handler(self, config: HandlerConfig):
        """
        Creates a NATS subscription for a single handler configuration.
        """
        try:
            # Create a wrapper function that includes deserialization and error handling.
            wrapped_handler = self._create_handler_wrapper(config.handler_func)

            # Let the nats-py library handle the consumer creation implicitly.
            subscription = await self.bus.js.subscribe(
                subject=config.subject_pattern,
                queue=config.queue_group,
                durable=config.durable_name,
                cb=wrapped_handler,
                manual_ack=True,
                config=ConsumerConfig(
                    ack_policy=config.ack_policy,
                    max_deliver=config.max_deliver,
                    ack_wait=config.ack_wait_seconds,
                ),
            )
            self._active_subscriptions.append(subscription)
            logger.info(f"Successfully subscribed handler '{config.handler_func.__name__}' to '{config.subject_pattern}'.")

        except Exception as e:
            logger.error(f"Failed to subscribe handler '{config.handler_func.__name__}': {e}", exc_info=True)
            # Depending on desired behavior, you might want to re-raise to halt startup
            # raise EventSubscriptionError(f"Subscription failed for {config.handler_func.__name__}") from e

    def _create_handler_wrapper(self, original_handler: EventHandler) -> Callable[[nats.aio.msg.Msg], Coroutine[Any, Any, None]]:
        """
        Creates an async function that wraps the original handler.

        This wrapper is the actual callback given to NATS. It is responsible for:
        1. Deserializing the raw message using the EventFactory.
        2. Calling the original, user-written handler with the typed event object.
        3. Acknowledging the message with NATS based on the handler's outcome.
        4. Handling all exceptions gracefully to prevent the subscriber from crashing.
        """
        async def handler_wrapper(msg: nats.aio.msg.Msg):
            try:
                # 1. Deserialize
                event = self.factory.deserialize(msg)

                # 2. Call original handler
                await original_handler(event)

                # 3. Acknowledge on success
                await msg.ack()

            except Exception as e:
                logger.error(
                    f"Error processing event in handler '{original_handler.__name__}'. "
                    f"Subject: {msg.subject}, Event ID: {getattr(event, 'event_id', 'N/A')}. Error: {e}",
                    exc_info=True
                )
                # Decide what to do with the message on failure.
                # .nak() tells NATS to redeliver it later.
                # .term() tells NATS to not redeliver (and it will go to the DLQ if configured).
                await msg.term()

        return handler_wrapper
```

---

### 🏛️ Design Explanation and Usage

This declarative model revolutionizes how developers build components that react to events.

#### 1\. **The Developer Experience: Simple and Intentional (`@subscriber.on_event`)**

A developer wanting to process market data no longer needs to interact with the event bus, manage subscriptions, or handle message parsing. They simply write a clean, async function and decorate it.

**✅ How a developer would use the new system:**

```python
# Location: some_module/strategy/my_strategy.py
from core.events.subscriber_manager import subscriber
from core.events.event_types import MarketDataEvent, TradingEvent

@subscriber.on_event("market.tick.NSE.*", durable_name="alpha-strategy-tick-processor")
async def handle_market_data(event: MarketDataEvent):
    """
    This function is automatically called for every tick on the NSE exchange.
    The 'event' parameter is already a fully parsed and typed MarketDataEvent object.
    """
    if event.last_price > 200.0:
        print(f"Signal generated for {event.instrument_token} at price {event.last_price}")
        # ... logic to create and publish a TradingEvent

@subscriber.on_event("trading.order.filled", queue_group="order-auditors")
async def audit_filled_orders(event: TradingEvent):
    """
    This function logs all filled orders. The queue_group ensures only one
    instance of this service receives the event.
    """
    print(f"AUDIT: Order {event.order_id} was filled.")

```

Notice how the business logic is completely clean of any infrastructure code.

#### 2\. **Automatic Discovery (`SubscriberDecorator`)**

The global `subscriber` object acts as a simple, temporary list. When a module containing a decorated function is imported anywhere in the application, the decorator's code runs and adds the function and its configuration (`HandlerConfig`) to the global list `subscriber.handlers`. This happens automatically as Python loads your code.

#### 3\. **Centralized Management (`SubscriberManager`)**

The `SubscriberManager` is the "engine" that brings the system to life. During your application's startup sequence, you would create and start an instance of this manager.

- **Discovery**: It takes the `subscriber.handlers` list, which now contains every decorated event handler in your entire application.
- **Subscription**: It iterates through the list and creates the actual NATS subscriptions, handling details like durable names and consumer configuration.
- **Wrapping Logic**: Crucially, it doesn't give your raw function to NATS. It gives NATS a **wrapper function** (`handler_wrapper`). This wrapper is where all the boilerplate lives:
  - It receives the raw `msg`.
  - It calls the `EventFactory` to deserialize the message into a typed object.
  - It `try...except` blocks to catch any errors from your handler.
  - It reliably calls `msg.ack()` on success or `msg.term()` on failure, ensuring no message is ever lost or unacknowledged.

This pattern elegantly separates the _what_ (the business logic in your handler) from the _how_ (the complex infrastructure logic of managing subscriptions), leading to a system that is vastly easier to build, test, and maintain.

## Additonal notes

Here are the additional notes on the refactoring, synthesizing the new components into a cohesive whole and providing a clear path for implementation.

### 🚀 Tying It All Together: The Application Lifecycle

The refactored components are designed to work together seamlessly. Here’s how they interact during the application's lifecycle:

**1. Application Startup ጅ**

This is the most critical phase where the system is wired together.

- **Initialization**: In your application's main entry point (e.g., `main.py` or `app/lifecycle.py`), you'll initialize the singleton instances in the correct order:

  1.  `get_event_bus_core()`: Creates the core connection manager.
  2.  `get_event_publisher()`: Creates the publisher, which depends on the event bus core.
  3.  Create instances of `EventFactory` and `SubscriberManager`.

- **Connection**: You call `await event_bus_core.connect()`. This is the first and only time you manually initiate the connection.

- **Subscriber Activation**: You then call `await subscriber_manager.start()`. This is a crucial step. The manager will now use the active connection from `event_bus_core` to discover and subscribe all the functions that were decorated with `@subscriber.on_event` across your entire codebase.

At this point, the system is fully operational. The publisher is ready to send events, and all subscribers are actively listening.

**2. Application Runtime 🏃**

During normal operation, the components work independently:

- **Publishing an Event**:

  - Any part of your application (e.g., a strategy manager, an API endpoint) gets the singleton publisher: `publisher = get_event_publisher()`.
  - It calls `await publisher.publish("some.subject", my_event)`.
  - The publisher service handles everything else: serialization, compression, retries, and sending the event via the `event_bus_core`.

- **Receiving an Event**:
  - The `event_bus_core` receives a raw message from NATS.
  - The message is automatically routed to the correct `handler_wrapper` created by the `SubscriberManager`.
  - The wrapper uses the `EventFactory` to deserialize the raw message into a specific, typed event object (e.g., `MarketDataEvent`).
  - The wrapper then calls your decorated business logic function (e.g., `handle_market_data(event: MarketDataEvent)`), passing the fully parsed object.
  - Finally, the wrapper acknowledges the message.

**3. Application Shutdown 🛑**

A graceful shutdown is essential to prevent data loss.

- **Stop Subscribers**: The first step is to call `await subscriber_manager.stop()`. This unsubscribes all handlers, ensuring no new messages are processed.
- **Disconnect the Bus**: Next, you call `await event_bus_core.disconnect()`. The `.drain()` method inside ensures that any outgoing messages buffered by the publisher are sent before the connection is closed.

This ordered shutdown guarantees that you stop accepting new work before you close the communication channel.

---

### 🗑️ Code Cleanup: What to Remove

With this new architecture, several of the original files in `core/events/` become redundant. You can safely **delete or replace** the following:

- `event_bus.py`: This monolithic class is completely replaced by the new, separated components.
- `event_publisher.py`: This is replaced by the more robust `event_publisher_service.py`.
- `event_subscriber.py`: This is replaced by the `subscriber_manager.py` and the declarative decorator model.
- `high_performance_publisher.py`: The functionality of this class (like batching) should be merged into the `EventPublisherService` as an optional, high-performance publishing strategy if needed. Keeping it separate creates confusion.

By removing these files, you finalize the transition to the new, cleaner architecture.

---

### 📊 Final Sanity Check: All Issues Resolved

This refactoring doesn't just improve the design; it directly resolves every critical issue identified in the original codebase:

- **Overlapping Subjects**: This is now a configuration issue handled by a dedicated `StreamManager`, completely separate from the event bus logic.
- **Wrong Deserialization**: **Solved** by the `SchemaRegistry` and `EventFactory`.
- **DLQ Stream Missing**: **Solved** by having a `StreamManager` define the DLQ stream.
- **Durable Consumer Not Used**: **Solved** by the `SubscriberManager`, which correctly configures durable subscriptions.
- **Fragile Subscription Tracking**: **Solved**. The manager tracks subscriptions internally, and developers don't need to manage subscription IDs at all.
- **Compression Incompatibility**: **Solved**. The `EventFactory` now correctly handles decompression based on message headers.
- **Race Conditions & Unhandled Errors**: **Solved** by adding locks and proper exception handling in the new, focused components.

This comprehensive refactoring moves your event system from a fragile, bug-prone implementation to a robust, production-grade architecture that is both powerful and a pleasure to work with.
