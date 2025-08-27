import asyncio
from typing import Optional, Set
import redis.asyncio as redis

class DeduplicationManager:
    """Manages event deduplication using Redis."""
    
    def __init__(self, redis_client: redis.Redis, 
                 service_name: str, ttl_seconds: int = 3600):
        self.redis_client = redis_client
        self.service_name = service_name
        self.ttl_seconds = ttl_seconds
        self._key_prefix = f"dedup:{service_name}"
        
        # In-memory cache for frequently checked events
        self._local_cache: Set[str] = set()
        self._cache_max_size = 1000
    
    async def is_duplicate(self, event_id: str, broker_context: str = None) -> bool:
        """Check if event has already been processed with optional broker context."""
        cache_key = f"{event_id}"
        if broker_context:
            cache_key = f"{broker_context}:{event_id}"
        
        # Check local cache first
        if cache_key in self._local_cache:
            return True
        
        # Check Redis
        redis_key = f"{self._key_prefix}:{cache_key}"
        exists = await self.redis_client.exists(redis_key)
        
        if exists:
            # Add to local cache
            self._add_to_local_cache(cache_key)
            return True
        
        return False
    
    async def mark_processed(self, event_id: str, broker_context: str = None) -> None:
        """Mark event as processed with optional broker context."""
        cache_key = f"{event_id}"
        if broker_context:
            cache_key = f"{broker_context}:{event_id}"
        
        redis_key = f"{self._key_prefix}:{cache_key}"
        await self.redis_client.setex(redis_key, self.ttl_seconds, "1")
        
        # Add to local cache
        self._add_to_local_cache(cache_key)
    
    def _add_to_local_cache(self, cache_key: str) -> None:
        """Add event to local cache with size management."""
        if len(self._local_cache) >= self._cache_max_size:
            # Remove oldest entries (simple FIFO)
            for _ in range(self._cache_max_size // 4):
                try:
                    self._local_cache.pop()
                except KeyError:
                    break
        
        self._local_cache.add(cache_key)