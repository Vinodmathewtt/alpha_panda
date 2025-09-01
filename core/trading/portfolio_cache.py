from __future__ import annotations

import json
from typing import Optional


class PortfolioCache:
    """
    Redis-backed cache for portfolio data, broker-agnostic.
    Moved from services/portfolio_manager/cache.py during Phase 6 cleanup.
    """

    def __init__(self, settings, redis_client=None):
        self.settings = settings
        self.redis_client = redis_client
        self.namespace: str | None = None

    async def initialize(self, namespace: str | None = None):
        import redis.asyncio as redis
        self.namespace = namespace
        if not self.redis_client:
            self.redis_client = redis.from_url(self.settings.redis.url)

    def _get_key(self, portfolio_id: str) -> str:
        if self.namespace:
            return f"{self.namespace}:portfolio:{portfolio_id}"
        return f"portfolio:{portfolio_id}"

    async def get_portfolio(self, portfolio_id: str):
        """Return Portfolio model from cache or None."""
        from core.trading.portfolio_models import Portfolio
        if not self.redis_client:
            await self.initialize()
        key = self._get_key(portfolio_id)
        data = await self.redis_client.get(key)
        if data:
            return Portfolio(**json.loads(data))
        return None

    async def save_portfolio(self, portfolio):
        """Persist Portfolio model to cache."""
        if not self.redis_client:
            await self.initialize()
        key = self._get_key(portfolio.portfolio_id)
        await self.redis_client.set(key, portfolio.model_dump_json())

    async def close(self):
        if self.redis_client:
            await self.redis_client.aclose()

