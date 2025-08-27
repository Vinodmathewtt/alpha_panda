import json
import redis.asyncio as redis
from typing import Optional

from .models import Portfolio
from core.config.settings import Settings


class PortfolioCache:
    """
    Manages the storage and retrieval of portfolio state in a Redis cache.
    """
    def __init__(self, settings: Settings, redis_client=None):
        self.settings = settings
        self.redis_client = redis_client
        self.namespace = None

    async def initialize(self, namespace: str = None):
        """Initialize Redis client connection with optional namespace"""
        if not self.redis_client:
            self.redis_client = redis.from_url(self.settings.redis.url, decode_responses=True)
        self.namespace = namespace

    def _get_key(self, portfolio_id: str) -> str:
        """Generates a standardized Redis key for a portfolio."""
        if self.namespace:
            return f"{self.namespace}:portfolio:{portfolio_id}"
        return f"portfolio:{portfolio_id}"

    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """
        Retrieves a portfolio from the cache.

        Returns:
            A Portfolio object if found, otherwise None.
        """
        if not self.redis_client:
            await self.initialize()
            
        key = self._get_key(portfolio_id)
        data = await self.redis_client.get(key)
        if data:
            return Portfolio(**json.loads(data))
        return None

    async def save_portfolio(self, portfolio: Portfolio):
        """
        Saves a portfolio's state to the cache.
        """
        if not self.redis_client:
            await self.initialize()
            
        key = self._get_key(portfolio.portfolio_id)
        # Convert the Pydantic model to a JSON string for storage
        await self.redis_client.set(key, portfolio.model_dump_json())

    async def close(self):
        """Closes the Redis connection."""
        if self.redis_client:
            # FIX: Use aclose() for consistent async Redis client closure (redis-py 5.x preferred method)
            await self.redis_client.aclose()