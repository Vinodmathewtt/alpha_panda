"""
EventPublisherService - Intentional and reliable event publishing.

This module provides a dedicated service for publishing events to NATS JetStream
with comprehensive error handling, retries, and compression support.
"""

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

    async def publish(self, subject: str, event: BaseEvent, ignore_failures: bool = False) -> None:
        """
        Serializes, compresses, and publishes an event with a retry mechanism.

        This is the standard method for reliable, single-event publishing.

        Args:
            subject: The NATS subject to publish the event to.
            event: The event object to be published.
            ignore_failures: If True, logs errors but doesn't raise exceptions (useful for shutdown)

        Raises:
            EventPublishError: If the event cannot be published after all retry attempts (unless ignore_failures=True).
            ConnectionError: If the event bus is not connected (unless ignore_failures=True).
        """
        # MODIFIED: Check for full readiness (connection + streams)
        if not self.bus.is_fully_ready or not self.bus.js:
            error_msg = "Event bus is not fully ready. Cannot publish event."
            if ignore_failures:
                logger.warning(f"Ignoring publish failure for event {event.event_id}: {error_msg}")
                return
            raise EventPublishError(error_msg)

        # 1. Serialize the event to its JSON representation.
        try:
            payload = event.to_json().encode("utf-8")
        except Exception as e:
            error_msg = f"Failed to serialize event {event.event_id}: {e}"
            if ignore_failures:
                logger.warning(f"Ignoring serialization failure: {error_msg}")
                return
            raise EventPublishError(error_msg) from e

        # 2. Compress the payload if enabled.
        if self.settings.compression_enabled:
            try:
                payload = gzip.compress(payload)
            except Exception as e:
                logger.warning(f"Compression failed for event {event.event_id}, using uncompressed: {e}")

        # 3. Construct message headers.
        headers = {
            "event-id": event.event_id,
            "event-type": event.event_type.value,
            "source": event.source,
            "timestamp": event.timestamp.isoformat(),
            "compressed": "true" if self.settings.compression_enabled else "false",
        }
        if hasattr(event, 'correlation_id') and event.correlation_id:
            headers["correlation-id"] = event.correlation_id

        # 4. Attempt to publish with a retry loop with reduced retries for shutdown scenarios.
        max_attempts = 2 if ignore_failures else self.settings.max_retries + 1
        last_exception = None
        
        for attempt in range(max_attempts):
            try:
                # Use shorter timeout during shutdown
                timeout = 2.0 if ignore_failures else self.settings.publish_timeout_seconds
                await asyncio.wait_for(
                    self.bus.js.publish(
                        subject=subject,
                        payload=payload,
                        headers=headers,
                        timeout=timeout
                    ),
                    timeout=timeout + 1.0  # Add buffer to asyncio timeout
                )
                logger.debug(f"Successfully published event {event.event_id} to {subject} on attempt {attempt + 1}.")
                return  # Success, exit the function.

            except asyncio.TimeoutError as e:
                last_exception = e
                logger.warning(
                    f"Publish attempt {attempt + 1}/{max_attempts} timed out for event "
                    f"{event.event_id} to {subject} (asyncio timeout)."
                )
            except NatsTimeoutError as e:
                last_exception = e
                logger.warning(
                    f"Publish attempt {attempt + 1}/{max_attempts} timed out for event "
                    f"{event.event_id} to {subject} (NATS timeout)."
                )
            except Exception as e:
                last_exception = e
                logger.error(
                    f"An unexpected error occurred on publish attempt {attempt + 1} for event "
                    f"{event.event_id}: {e}"
                )

            # Wait before retrying, if this is not the last attempt.
            if attempt < max_attempts - 1:
                # Shorter delay during shutdown
                delay = 0.5 if ignore_failures else self.settings.retry_delay_seconds * (2 ** attempt)
                await asyncio.sleep(delay)

        # If all retries fail
        error_msg = f"Failed to publish event {event.event_id} to {subject} after {max_attempts} attempts."
        if ignore_failures:
            logger.warning(f"Ignoring publish failure: {error_msg}")
            return
        
        raise EventPublishError(error_msg) from last_exception

    async def publish_batch(self, events_and_subjects: list[tuple[str, BaseEvent]]) -> None:
        """
        Publishes multiple events concurrently.
        
        Args:
            events_and_subjects: List of (subject, event) tuples to publish.
            
        Raises:
            EventPublishError: If any events fail to publish.
        """
        if not events_and_subjects:
            return
            
        # Publish all events concurrently
        tasks = []
        for subject, event in events_and_subjects:
            task = asyncio.create_task(
                self.publish(subject, event),
                name=f"publish-{event.event_id}"
            )
            tasks.append(task)
        
        # Wait for all publications to complete
        try:
            await asyncio.gather(*tasks)
            logger.debug(f"Successfully published batch of {len(events_and_subjects)} events.")
        except Exception as e:
            logger.error(f"Batch publish failed: {e}")
            raise EventPublishError(f"Batch publish failed: {e}") from e


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
            from core.config.settings import Settings
            settings = Settings()

        event_bus_core = get_event_bus_core(settings)
        _event_publisher_instance = EventPublisherService(event_bus_core, settings)

    return _event_publisher_instance