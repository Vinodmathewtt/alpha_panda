import asyncio
import pytest
from types import SimpleNamespace
from core.monitoring.pipeline_validator import PipelineValidator
from core.monitoring.metrics_registry import MetricsRegistry


class FakeRedis:
    def __init__(self, data=None, ping_ok=True):
        self._data = data or {}
        self._ping_ok = ping_ok

    async def get(self, key: str):
        val = self._data.get(key)
        if isinstance(val, bytes) or val is None:
            return val
        # encode simple strings automatically for realism
        if isinstance(val, str):
            return val.encode()
        return val

    async def setex(self, key: str, ttl: int, value: str):
        self._data[key] = value
        return True

    async def ping(self):
        if not self._ping_ok:
            raise RuntimeError("redis down")
        return True


class DummyMarketHours:
    def __init__(self, open_state: bool):
        self._open = open_state

    def is_market_open(self) -> bool:
        return self._open


def _settings(active_brokers=("paper",)):
    # Minimal settings stub used by validator
    monitoring = SimpleNamespace(market_data_latency_threshold=1.0, startup_grace_period_seconds=0.0)
    return SimpleNamespace(monitoring=monitoring, active_brokers=list(active_brokers))


@pytest.mark.asyncio
async def test_validator_idle_when_market_closed_and_skip_stages():
    settings = _settings()
    redis = FakeRedis()
    validator = PipelineValidator(settings, redis, market_hours_checker=DummyMarketHours(open_state=False), broker="paper")
    # Force trading disabled for broker via monkeypatch to simplify
    validator._trading_enabled = False
    res = await validator.validate_end_to_end_flow()
    assert res["overall_health"] == "idle"
    assert res["stages"]["order_execution"]["skipped"] is True
    assert res["stages"]["portfolio_updates"]["skipped"] is True


@pytest.mark.asyncio
async def test_validator_no_signal_suppressed_when_no_strategies():
    broker = "paper"
    # No last signal, and strategies count is 0
    strat_key = MetricsRegistry.strategies_count(broker)
    redis = FakeRedis(data={strat_key: "0"})
    settings = _settings(active_brokers=(broker,))
    validator = PipelineValidator(settings, redis, market_hours_checker=DummyMarketHours(open_state=True), broker=broker)
    validator._trading_enabled = True
    # Directly validate signal generation stage
    stage = await validator._validate_signal_generation()
    assert stage["healthy"] is True


@pytest.mark.asyncio
async def test_validator_redis_connectivity_error_reported():
    settings = _settings()
    redis = FakeRedis(ping_ok=False)
    validator = PipelineValidator(settings, redis, market_hours_checker=DummyMarketHours(open_state=True), broker="paper")
    res = await validator.validate_end_to_end_flow()
    assert res["overall_health"] == "error"
    assert any(b.get("issue") == "redis_unavailable" for b in res.get("bottlenecks", []))
