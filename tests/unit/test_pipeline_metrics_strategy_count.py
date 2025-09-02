import pytest
from core.monitoring.pipeline_metrics import PipelineMetricsCollector
from core.monitoring.metrics_registry import MetricsRegistry


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def setex(self, key: str, ttl: int, value: str):
        self.store[key] = value
        return True

    async def get(self, key: str):
        v = self.store.get(key)
        if v is None:
            return None
        return v if isinstance(v, (bytes, bytearray)) else str(v).encode()


class _S:
    # minimal settings stub
    def __init__(self):
        self.monitoring = type("m", (), {"health_check_interval": 30.0})()


@pytest.mark.asyncio
async def test_set_strategy_count_records_value():
    r = FakeRedis()
    metrics = PipelineMetricsCollector(r, _S())
    await metrics.set_strategy_count("paper", 3)
    key = MetricsRegistry.strategies_count("paper")
    got = await r.get(key)
    assert got.decode() == "3"

