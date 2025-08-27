"""
Simplified EventBusCore focused only on NATS connection management.

This module provides a "thin" event bus that handles only the essential responsibility
of managing the NATS connection lifecycle. It does not handle publishing, subscribing,
or stream management - these are delegated to specialized components.
"""

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
        self._streams_ready_event = asyncio.Event()  # NEW: Event to signal stream readiness

    @property
    def is_connected(self) -> bool:
        """Returns the current NATS connection status."""
        return self._is_connected

    @property
    def is_fully_ready(self) -> bool:  # NEW: Property to check connection and stream readiness
        """Returns True only if connected to NATS and streams are confirmed to be ready."""
        return self._is_connected and self._streams_ready_event.is_set()

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
                    "max_reconnect_attempts": getattr(self.settings, 'nats_max_reconnect_attempts', 5),
                    "reconnect_time_wait": getattr(self.settings, 'nats_reconnect_time_wait', 2.0),
                    "error_cb": self._on_error,
                    "disconnected_cb": self._on_disconnect,
                    "reconnected_cb": self._on_reconnect,
                    "name": "AlphaPT-CoreConnection"
                }

                # Add authentication if configured
                nats_user = getattr(self.settings, 'nats_user', None)
                nats_password = getattr(self.settings, 'nats_password', None)
                if nats_user:
                    options["user"] = nats_user
                    options["password"] = nats_password

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
                self._streams_ready_event.clear() # NEW: Reset readiness on disconnect

    def signal_streams_ready(self) -> None:  # NEW: Method for StreamManager to call
        """Signals that NATS JetStream streams have been successfully created/verified."""
        if not self._streams_ready_event.is_set():
            logger.info("Signaling that NATS JetStream streams are ready.")
            self._streams_ready_event.set()

    async def wait_for_ready(self, timeout: float = 30.0) -> None: # NEW: Method for services to wait on
        """
        Waits until the event bus is fully connected and streams are ready.

        Args:
            timeout: The maximum time in seconds to wait.

        Raises:
            asyncio.TimeoutError: If the bus is not ready within the timeout period.
        """
        logger.debug("Waiting for EventBusCore to be fully ready (connected and streams verified)...")
        await asyncio.wait_for(self._streams_ready_event.wait(), timeout=timeout)
        logger.debug("EventBusCore is fully ready.")

    async def _on_error(self, e: Exception) -> None:
        """Callback for handling connection errors."""
        logger.error(f"NATS connection error: {e}")

    async def _on_disconnect(self) -> None:
        """Callback for handling disconnections."""
        if self.is_connected:  # Only log if it was an unexpected disconnect
            logger.warning("NATS connection lost. Attempting to reconnect...")
        self._is_connected = False
        self._streams_ready_event.clear() # NEW: Reset readiness on disconnect

    async def _on_reconnect(self) -> None:
        """Callback for handling successful reconnections."""
        self._is_connected = True
        logger.info("NATS connection successfully restored. Stream verification may be needed.")
        # Note: Streams are durable, so we don't need to re-signal here unless we implement
        # a process to re-verify them upon reconnection. For now, this is sufficient.


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
            # MODIFIED: Import moved inside to avoid circular dependency issues
            from core.config.settings import Settings
            settings = Settings()
        _event_bus_core_instance = EventBusCore(settings)
    return _event_bus_core_instance