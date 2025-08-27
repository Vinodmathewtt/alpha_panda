"""
Event Deduplication Strategy Example

Demonstrates how to implement event deduplication using Redis
to ensure exactly-once processing semantics.
"""

import redis.asyncio as redis
from typing import Set

class EventDeduplicator:
    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 3600):
        self.redis = redis_client
        self.ttl = ttl_seconds
        
    async def is_duplicate(self, event_id: str) -> bool:
        """Check if event was already processed"""
        key = f"processed_events:{event_id}"
        exists = await self.redis.exists(key)
        if not exists:
            await self.redis.setex(key, self.ttl, "1")
            return False
        return True

# Usage in consumer:
async def handle_event(self, event: dict):
    if await self.deduplicator.is_duplicate(event["id"]):
        self.logger.info("Skipping duplicate event", event_id=event["id"])
        return
        
    # Process event...
    await self.process_event(event)
    
    # Commit offset ONLY after successful processing
    await self.consumer.commit()