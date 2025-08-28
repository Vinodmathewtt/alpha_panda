import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer
from core.config.settings import RedpandaSettings
from core.schemas.events import EventEnvelope, generate_uuid7, EventType

class MessageProducer:
    """Enhanced message producer with reliability features."""
    
    def __init__(self, config: RedpandaSettings, service_name: str):
        self.config = config
        self.service_name = service_name
        self._producer: Optional[AIOKafkaProducer] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the producer."""
        if self._running:
            return
        
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.config.bootstrap_servers,
            client_id=f"{self.config.client_id}-producer-{self.service_name}",
            enable_idempotence=True,
            acks='all',
            request_timeout_ms=30000,
            linger_ms=5,
            compression_type='gzip',
            retry_backoff_ms=100,
            value_serializer=lambda x: json.dumps(x, default=self._json_serializer).encode('utf-8')
        )
        
        await self._producer.start()
        self._running = True
    
    async def stop(self) -> None:
        """Stop the producer with flush."""
        if not self._running or not self._producer:
            return
        
        try:
            # Ensure all messages are sent before closing
            await self._producer.flush()
            await self._producer.stop()
        except Exception as e:
            # Log but don't raise to prevent shutdown issues
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error during producer shutdown: {e}")
        finally:
            self._producer = None
            self._running = False
    
    async def send(self, topic: str, key: str, data: Dict[str, Any], 
                   event_type: Optional[EventType] = None,
                   correlation_id: Optional[str] = None,
                   broker: str = "unknown") -> str:
        """Send message with automatic envelope wrapping."""
        if not self._running:
            await self.start()
        
        # Create event envelope if not already wrapped
        if not isinstance(data, dict) or 'id' not in data:
            event_id = generate_uuid7()
            
            # Use provided event_type or attempt to determine from data
            if event_type:
                envelope_type = event_type
            elif 'type' in data:
                envelope_type = data['type']
            else:
                # More explicit default with logging for debugging
                envelope_type = EventType.MARKET_TICK
                # Log when using default for debugging/monitoring
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Using default event type {envelope_type.value} for message without explicit type - "
                    f"service: {self.service_name}, topic: {topic}, key: {key}"
                )
            
            envelope = EventEnvelope(
                id=event_id,
                type=envelope_type,
                ts=datetime.now(timezone.utc),
                source=self.service_name,
                key=key,
                correlation_id=correlation_id or generate_uuid7(),
                broker=broker,
                data=data
            ).model_dump(mode='json')
        else:
            envelope = data
            event_id = data.get('id')
        
        # CRITICAL FIX: Ensure robust key and value handling
        try:
            # Ensure key is a string and can be encoded
            if not isinstance(key, str):
                key = str(key)
            
            # Safely encode key to bytes
            encoded_key = key.encode('utf-8')
            
            # Ensure envelope is JSON-serializable dict/object
            if not isinstance(envelope, (dict, list)):
                raise ValueError(f"Envelope must be dict or list, got {type(envelope)}")
            
            await self._producer.send_and_wait(
                topic=topic,
                key=encoded_key,
                value=envelope  # The value_serializer will handle JSON serialization
            )
            
        except Exception as send_error:
            # Add detailed error context for debugging
            error_context = {
                "topic": topic,
                "key": key,
                "key_type": type(key).__name__,
                "envelope_type": type(envelope).__name__,
                "service": self.service_name
            }
            
            # Re-raise with context
            raise RuntimeError(f"MessageProducer.send failed: {send_error}. Context: {error_context}") from send_error
        
        return event_id
    
    @staticmethod
    def _json_serializer(obj):
        """Custom JSON serializer."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        # Handle Decimal objects from price fields
        from decimal import Decimal
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')