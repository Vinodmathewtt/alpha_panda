"""
Centralized SchemaRegistry and EventFactory for robust event deserialization.

This module provides a single source of truth for event schemas and intelligent
deserialization of incoming messages.
"""

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

    def get_all_registered(self) -> Dict[EventType, Type[BaseEvent]]:
        """Returns a copy of all registered event types and their classes."""
        return self._registry.copy()


# --- Pre-populated default registry ---
# In a real application, this could be populated dynamically during startup
# by discovering event classes throughout the codebase.
default_schema_registry = SchemaRegistry()

# Register all event types with their corresponding classes
event_mappings = [
    (EventType.MARKET_TICK, MarketDataEvent),
    (EventType.MARKET_DEPTH, MarketDataEvent),
    (EventType.TRADING_SIGNAL, TradingEvent),
    (EventType.ORDER_PLACED, TradingEvent),
    (EventType.ORDER_FILLED, TradingEvent),
    (EventType.ORDER_CANCELLED, TradingEvent),
    (EventType.ORDER_REJECTED, TradingEvent),
    (EventType.ORDER_MODIFIED, TradingEvent),
    (EventType.POSITION_UPDATED, TradingEvent),
    (EventType.SYSTEM_ERROR, SystemEvent),
    (EventType.SYSTEM_STARTED, SystemEvent),
    (EventType.SYSTEM_STOPPED, SystemEvent),
    (EventType.STRATEGY_STARTED, SystemEvent),
    (EventType.STRATEGY_STOPPED, SystemEvent),
    (EventType.HEALTH_CHECK, SystemEvent),
    (EventType.RISK_ALERT, RiskEvent),
    (EventType.RISK_VIOLATION, RiskEvent),
    (EventType.POSITION_LIMIT_BREACHED, RiskEvent),
    (EventType.LOSS_LIMIT_BREACHED, RiskEvent),
]

for event_type, event_class in event_mappings:
    try:
        default_schema_registry.register_event(event_type, event_class)
    except EventRegistrationError:
        # In case of duplicate registrations during module reloads
        pass


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