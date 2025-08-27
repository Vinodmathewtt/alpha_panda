"""
Cache Management & TTL Strategy Example

Demonstrates Redis cache management with TTL policies and
stale-while-revalidate pattern for high availability.
"""

import json
import asyncio
from typing import Any, Callable, Optional

class CacheManager:
    def __init__(self, redis_client):
        self.redis = redis_client
        
    async def set_with_ttl(self, key: str, value: Any, ttl_seconds: int = 300):
        """Set cache value with TTL"""
        await self.redis.setex(key, ttl_seconds, json.dumps(value))
        
    async def get_with_stale_while_revalidate(self, key: str, refresh_func: Callable, 
                                            ttl: int = 300, stale_ttl: int = 600):
        """Serve stale data while refreshing in background"""
        cached = await self.redis.get(key)
        if cached:
            # Check if needs refresh (but still serve cached)
            cache_age = await self.redis.ttl(key)
            if cache_age < ttl * 0.2:  # Refresh when 20% of TTL remaining
                asyncio.create_task(self._background_refresh(key, refresh_func, ttl))
            return json.loads(cached)
            
        # Cache miss - fetch immediately
        fresh_data = await refresh_func()
        await self.set_with_ttl(key, fresh_data, ttl)
        return fresh_data
        
    async def portfolio_state_rebuild(self, account_id: str, from_offset: Optional[int] = None):
        """Rebuild portfolio state from order fills"""
        portfolio_key = f"portfolio:{account_id}"
        
        # Clear existing state
        await self.redis.delete(portfolio_key)
        
        # Replay fills from offset
        consumer = await self.create_replay_consumer(f"{self.broker}.orders.filled", from_offset)
        
        async for message in consumer:
            fill_event = message.value
            if fill_event["data"]["account_id"] == account_id:
                await self.apply_fill_to_portfolio(portfolio_key, fill_event)
                
        await consumer.stop()