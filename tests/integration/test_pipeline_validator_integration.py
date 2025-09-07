import asyncio
from datetime import datetime

import pytest
import redis.asyncio as aioredis

from core.monitoring.pipeline_validator import PipelineValidator
from core.monitoring.metrics_registry import MetricsRegistry


@pytest.mark.asyncio
async def test_pipeline_validator_with_real_redis():
    # Connect to Redis from docker-compose (localhost:6379)
    try:
        redis = aioredis.from_url("redis://localhost:6379/0")
        await redis.ping()
    except Exception:
        pytest.skip("Redis not available on localhost:6379")

    # Seed last market tick to be recent (healthy)
    now = datetime.utcnow()
    payload = {"timestamp": now.isoformat()}
    await redis.set(MetricsRegistry.market_ticks_last(), __import__("json").dumps(payload))

    class _Settings:
        active_brokers = ["paper"]

        class Monitoring:
            market_data_latency_threshold = 2.0

        monitoring = Monitoring()

        def is_paper_trading_enabled(self):
            return True

        def is_zerodha_trading_enabled(self):
            return False

    class AlwaysOpenMarket:
        def is_market_open(self):
            return True

    pv = PipelineValidator(_Settings(), redis, AlwaysOpenMarket(), broker="paper")
    res = await pv._validate_market_data_flow()
    assert res["healthy"] is True
