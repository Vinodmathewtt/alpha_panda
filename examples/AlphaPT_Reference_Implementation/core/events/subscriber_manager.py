"""
Declarative SubscriberManager with decorator-based event handling.

This module provides a clean, declarative way to handle events using decorators
and centralized subscription management.
"""

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Dict, List, Optional

import nats
from nats.js.api import AckPolicy, ConsumerConfig

from .event_bus_core import EventBusCore, get_event_bus_core
from .event_exceptions import EventSubscriptionError
from .schema_registry import EventFactory, default_schema_registry
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
        
        Args:
            subject_pattern: NATS subject pattern to subscribe to (e.g., "market.tick.NSE.*")
            durable_name: Optional durable consumer name for persistence
            queue_group: Optional queue group for load balancing
            ack_policy: Message acknowledgment policy
            
        Returns:
            The decorated function (unchanged)
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

    def clear_handlers(self):
        """Clear all registered handlers. Useful for testing."""
        self.handlers.clear()


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
        event_factory: Optional[EventFactory] = None,
        handler_source: Optional[SubscriberDecorator] = None,
        settings: Optional[Settings] = None,
    ):
        self.bus = bus
        self.factory = event_factory or EventFactory(default_schema_registry)
        self.handler_source = handler_source or subscriber
        self.settings = settings or Settings()
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

            # Create consumer configuration
            consumer_config = ConsumerConfig(
                ack_policy=config.ack_policy,
                max_deliver=config.max_deliver,
                ack_wait=config.ack_wait_seconds,
            )

            # Let the nats-py library handle the consumer creation implicitly.
            subscription = await self.bus.js.subscribe(
                subject=config.subject_pattern,
                queue=config.queue_group,
                durable=config.durable_name,
                cb=wrapped_handler,
                manual_ack=True,
                config=consumer_config,
            )
            self._active_subscriptions.append(subscription)
            logger.info(f"Successfully subscribed handler '{config.handler_func.__name__}' to '{config.subject_pattern}'.")

        except Exception as e:
            logger.error(f"Failed to subscribe handler '{config.handler_func.__name__}': {e}", exc_info=True)
            # Depending on desired behavior, you might want to re-raise to halt startup
            raise EventSubscriptionError(f"Subscription failed for {config.handler_func.__name__}") from e

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
            event = None
            try:
                # 1. Deserialize
                event = self.factory.deserialize(msg)

                # 2. Call original handler
                await original_handler(event)

                # 3. Acknowledge on success
                await msg.ack()
                logger.debug(f"Successfully processed event {event.event_id} in handler '{original_handler.__name__}'.")

            except Exception as e:
                event_id = getattr(event, 'event_id', 'N/A') if event else 'N/A'
                logger.error(
                    f"Error processing event in handler '{original_handler.__name__}'. "
                    f"Subject: {msg.subject}, Event ID: {event_id}. Error: {e}",
                    exc_info=True
                )
                # Decide what to do with the message on failure.
                # .nak() tells NATS to redeliver it later.
                # .term() tells NATS to not redeliver (and it will go to the DLQ if configured).
                try:
                    await msg.term()  # Terminate message to prevent redelivery
                except Exception as ack_error:
                    logger.error(f"Failed to terminate message: {ack_error}")

        return handler_wrapper

    @property
    def is_running(self) -> bool:
        """Returns whether the subscriber manager is currently running."""
        return self._is_running

    @property
    def active_subscription_count(self) -> int:
        """Returns the number of active subscriptions."""
        return len(self._active_subscriptions)


# --- Factory function for creating SubscriberManager instances ---
def create_subscriber_manager(
    settings: Optional[Settings] = None,
    event_bus: Optional[EventBusCore] = None,
    event_factory: Optional[EventFactory] = None,
) -> SubscriberManager:
    """
    Factory function to create a SubscriberManager with appropriate dependencies.
    
    Args:
        settings: Application settings (will create default if not provided)
        event_bus: EventBusCore instance (will get singleton if not provided)  
        event_factory: EventFactory instance (will create default if not provided)
        
    Returns:
        Configured SubscriberManager instance
    """
    if settings is None:
        settings = Settings()
    
    if event_bus is None:
        event_bus = get_event_bus_core(settings)
        
    if event_factory is None:
        event_factory = EventFactory(default_schema_registry)
        
    return SubscriberManager(
        bus=event_bus,
        event_factory=event_factory,
        handler_source=subscriber,
        settings=settings
    )