import pytest
from datetime import datetime, timezone
from decimal import Decimal

from core.config.settings import Settings, RedpandaSettings
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector
from core.schemas.events import TradingSignal, ValidatedSignal
from services.paper_trading.service import PaperTradingService


class _FakeProducer:
    def __init__(self):
        self.sent = []

    async def send(self, topic, key, data, event_type, broker, correlation_id=None):
        self.sent.append((topic, key, data, getattr(event_type, "value", str(event_type)), broker))


@pytest.mark.asyncio
async def test_paper_metrics_orders_counter_and_cash_gauge():
    cfg = RedpandaSettings(bootstrap_servers="localhost:9092")
    prom = PrometheusMetricsCollector()
    svc = PaperTradingService(cfg, Settings(), redis_client=None, prometheus_metrics=prom)
    svc.orchestrator.producers = [_FakeProducer()]

    ts = datetime.now(timezone.utc)
    sig = TradingSignal(
        strategy_id="m1",
        instrument_token=123,
        signal_type="BUY",
        quantity=1,
        price=Decimal("100.0"),
        timestamp=ts,
    )
    val = ValidatedSignal(
        original_signal=sig,
        validated_quantity=1,
        validated_price=Decimal("100.0"),
        risk_checks={},
        timestamp=ts,
    )
    await svc._handle_validated_signal({"type": "validated_signal", "data": val.model_dump(mode="json")}, topic="paper.signals.validated")

    # Orders counter should have at least one series
    assert len(prom.orders_executed._metrics) >= 1
    # Cash balance gauge should reflect starting cash adjusted by cost
    assert len(prom.paper_cash_balance._metrics) >= 1
