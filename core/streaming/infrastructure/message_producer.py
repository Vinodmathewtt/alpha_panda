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
        
        await self._producer.flush()
        await self._producer.stop()
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
            elif 'type' in data and isinstance(data['type'], EventType):
                envelope_type = data['type']
            else:
                envelope_type = EventType.MARKET_TICK  # Safe default
            
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
        
        await self._producer.send_and_wait(
            topic=topic,
            key=key.encode('utf-8'),
            value=envelope
        )
        
        return event_id
    
    @staticmethod
    def _json_serializer(obj):
        """Custom JSON serializer."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')