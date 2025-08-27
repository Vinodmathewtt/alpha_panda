"""
Refactored NATS JetStream-based event system for AlphaPT.

This module provides a clean, lightweight, and robust event system with:
- Simplified EventBusCore for connection management only
- Schema-driven deserialization with EventFactory
- Declarative event handlers using decorators
- Reliable publishing with retries and compression
"""

# Core components
from core.events.event_bus_core import EventBusCore, get_event_bus_core
from core.events.event_publisher_service import EventPublisherService, get_event_publisher
from core.events.subscriber_manager import (
    SubscriberManager,
    subscriber,
    create_subscriber_manager,
)
from core.events.schema_registry import SchemaRegistry, EventFactory, default_schema_registry
from core.events.stream_manager import StreamManager, create_stream_manager

# Event types and exceptions
from core.events.event_types import (
    BaseEvent,
    EventType,
    MarketDataEvent,
    SystemEvent,
    TradingEvent,
    RiskEvent,
)
from core.events.event_exceptions import (
    EventParsingError,
    EventPublishError,
    EventSubscriptionError,
    EventRegistrationError,
)



__all__ = [
    # Core components
    "EventBusCore",
    "get_event_bus_core",
    "EventPublisherService", 
    "get_event_publisher",
    "SubscriberManager",
    "subscriber",
    "create_subscriber_manager",
    "SchemaRegistry",
    "EventFactory",
    "default_schema_registry",
    "StreamManager",
    "create_stream_manager",
    
    # Event types
    "BaseEvent",
    "EventType",
    "MarketDataEvent",
    "TradingEvent",
    "SystemEvent",
    "RiskEvent",
    
    # Exceptions
    "EventParsingError",
    "EventPublishError", 
    "EventSubscriptionError",
    "EventRegistrationError",
]
