"""
StreamManager for NATS JetStream stream lifecycle management.

This component handles the creation, configuration, and management of NATS JetStream
streams as specified in the refactor plan. It operates independently of the EventBusCore.
"""

import asyncio
import logging
from typing import Dict, List, Optional

from nats.js.api import StreamConfig, DiscardPolicy, RetentionPolicy, StorageType

from .event_bus_core import EventBusCore
from .event_exceptions import EventSubscriptionError
from core.config.settings import Settings

logger = logging.getLogger(__name__)


class StreamManager:
    """
    Manages NATS JetStream stream creation and lifecycle.
    
    This component is responsible for:
    - Creating and configuring JetStream streams
    - Managing stream retention policies
    - Handling Dead Letter Queue (DLQ) streams
    - Stream health monitoring and cleanup
    """

    def __init__(self, settings: Settings, event_bus: EventBusCore):
        self.settings = settings
        self.event_bus = event_bus
        self._streams_created = False

    async def ensure_streams(self) -> bool:
        """
        Ensures all required streams exist with proper configuration.
        
        Returns:
            True if all streams were created/verified successfully
        """
        if not self.event_bus.is_connected or not self.event_bus.js:
            raise EventSubscriptionError("Cannot create streams: EventBusCore is not connected")

        try:
            await self._create_core_streams()
            await self._create_dlq_stream()
            self._streams_created = True
            logger.info("All required streams created successfully")

            # NEW: Signal to the event bus that streams are ready for publishing
            self.event_bus.signal_streams_ready()

            return True
            
        except Exception as e:
            logger.error(f"Failed to create streams: {e}")
            return False

    async def _create_core_streams(self):
        """Create the core application streams as defined in the plan."""
        
        # Stream configurations based on the plan document
        stream_configs = [
            {
                "name": "MARKET_DATA",
                "subjects": ["market.tick.*", "market.depth.*", "market.instrument.*"], # MODIFIED: Added market.instrument.*
                "retention": RetentionPolicy.LIMITS,
                "max_msgs": 5_000_000,
                "max_bytes": 4 * 1024 * 1024 * 1024,  # 4GB
                "max_age": self.settings.event_system.stream_management.market_data_retention_hours * 3600,
            },
            {
                "name": "TRADING", 
                "subjects": ["trading.signal.*", "trading.order.*", "trading.position.*"],
                "retention": RetentionPolicy.LIMITS,
                "max_msgs": 1_000_000,
                "max_bytes": 1024 * 1024 * 1024,  # 1GB
                "max_age": self.settings.event_system.stream_management.trading_retention_hours * 3600,
            },
            {
                "name": "SYSTEM",
                "subjects": ["system.*", "health.*", "risk.*", "strategy.*"], # MODIFIED: Added strategy.*
                "retention": RetentionPolicy.LIMITS,
                "max_msgs": 100_000,
                "max_bytes": 100 * 1024 * 1024,  # 100MB
                "max_age": self.settings.event_system.stream_management.system_retention_hours * 3600,
            }
        ]

        for config in stream_configs:
            await self._create_or_update_stream(config)

    async def _create_dlq_stream(self):
        """Create Dead Letter Queue stream if enabled."""
        if not self.settings.event_system.dead_letter_queue.enabled:
            logger.info("DLQ stream creation skipped (disabled in config)")
            return

        dlq_config = {
            "name": "DLQ",
            "subjects": ["dlq.*"],
            "retention": RetentionPolicy.LIMITS,
            "max_msgs": 50_000,
            "max_bytes": 50 * 1024 * 1024,  # 50MB
            "max_age": self.settings.event_system.dead_letter_queue.dlq_retention_hours * 3600,
        }

        await self._create_or_update_stream(dlq_config)

    async def _create_or_update_stream(self, config: Dict):
        """Create or update a single stream with the given configuration."""
        stream_name = config["name"]
        
        try:
            # Check if stream already exists
            try:
                stream_info = await self.event_bus.js.stream_info(stream_name)
                logger.debug(f"Stream {stream_name} already exists with {stream_info.state.messages} messages")
                return
            except Exception:
                # Stream doesn't exist, create it
                pass

            # Create new stream
            stream_config = StreamConfig(
                name=stream_name,
                subjects=config["subjects"],
                retention=config["retention"],
                max_msgs=config["max_msgs"],
                max_bytes=config["max_bytes"],
                max_age=config["max_age"],
                storage=StorageType.FILE,
                discard=DiscardPolicy.OLD,
            )

            await self.event_bus.js.add_stream(stream_config)
            logger.info(f"Created stream: {stream_name} with subjects {config['subjects']}")

        except Exception as e:
            logger.error(f"Failed to create/update stream {stream_name}: {e}")
            raise

    async def get_stream_health(self) -> Dict:
        """Get health information for all streams."""
        if not self.event_bus.is_connected or not self.event_bus.js:
            return {"status": "disconnected", "streams": {}}

        health_info = {"status": "healthy", "streams": {}}
        
        try:
            # Get info for all known streams
            stream_names = ["MARKET_DATA", "TRADING", "SYSTEM"]
            if self.settings.event_system.dead_letter_queue.enabled:
                stream_names.append("DLQ")

            for stream_name in stream_names:
                try:
                    info = await self.event_bus.js.stream_info(stream_name)
                    health_info["streams"][stream_name] = {
                        "messages": info.state.messages,
                        "bytes": info.state.bytes,
                        "consumers": info.state.consumer_count,
                        "first_seq": info.state.first_seq,
                        "last_seq": info.state.last_seq,
                    }
                except Exception as e:
                    health_info["streams"][stream_name] = {"error": str(e)}
                    health_info["status"] = "degraded"

        except Exception as e:
            health_info["status"] = "error"
            health_info["error"] = str(e)

        return health_info

    @property
    def streams_ready(self) -> bool:
        """Returns whether streams have been successfully created."""
        return self._streams_created


# Factory function for easy creation
def create_stream_manager(settings: Settings, event_bus: EventBusCore) -> StreamManager:
    """
    Factory function to create a StreamManager instance.
    
    Args:
        settings: Application settings
        event_bus: Connected EventBusCore instance
        
    Returns:
        Configured StreamManager instance
    """
    return StreamManager(settings, event_bus)