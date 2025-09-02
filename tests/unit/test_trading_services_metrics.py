import sys
import types
import pytest
from types import SimpleNamespace
from datetime import datetime, timezone

# Provide fake aiokafka modules before importing services to avoid hard dependency
_fake_aiokafka = types.ModuleType("aiokafka")
setattr(_fake_aiokafka, "AIOKafkaProducer", object)
setattr(_fake_aiokafka, "AIOKafkaConsumer", object)
_fake_admin = types.ModuleType("aiokafka.admin")
setattr(_fake_admin, "AIOKafkaAdminClient", object)
sys.modules.setdefault("aiokafka", _fake_aiokafka)
sys.modules.setdefault("aiokafka.admin", _fake_admin)
_fake_errors = types.ModuleType("aiokafka.errors")
setattr(_fake_errors, "KafkaError", type("KafkaError", (), {}) )
setattr(_fake_errors, "KafkaConnectionError", type("KafkaConnectionError", (), {}) )
sys.modules.setdefault("aiokafka.errors", _fake_errors)
_fake_structs = types.ModuleType("aiokafka.structs")
setattr(_fake_structs, "TopicPartition", type("TopicPartition", (), {"__init__": lambda self, topic, partition: None}))
sys.modules.setdefault("aiokafka.structs", _fake_structs)

from services.paper_trading.service import PaperTradingService
from services.zerodha_trading.service import ZerodhaTradingService
from core.config.settings import Settings, RedpandaSettings
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector
from core.schemas.events import ValidatedSignal, TradingSignal, SignalType


class FakeProducer:
    def __init__(self):
        self.sent = []

    async def send(self, topic, key, data, event_type, broker, correlation_id=None):
        self.sent.append({
            "topic": topic,
            "key": key,
            "data": data,
            "event_type": getattr(event_type, "value", str(event_type)),
            "broker": broker,
        })


class FakeMetrics:
    def __init__(self):
        self.calls = []

    async def record_order_processed(self, order, broker_context=None):
        self.calls.append(("orders", broker_context, order))

    async def record_portfolio_update(self, portfolio_id, update_data, broker_context=None):
        self.calls.append(("portfolio", broker_context, update_data))


def _settings():
    s = Settings()
    return s


def _validated_signal(strategy_id="s1", instrument_token=1, price=100.0, qty=1):
    ts = TradingSignal(
        strategy_id=strategy_id,
        instrument_token=instrument_token,
        signal_type=SignalType.BUY,
        quantity=qty,
        price=price,
        timestamp=datetime.now(timezone.utc),
    )
    vs = ValidatedSignal(
        original_signal=ts,
        validated_quantity=qty,
        validated_price=price,
        risk_checks={},
        timestamp=datetime.now(timezone.utc),
    )
    return vs


@pytest.mark.asyncio
async def test_paper_trading_records_pipeline_metrics(monkeypatch):
    cfg = RedpandaSettings(bootstrap_servers="localhost:9092")
    settings = _settings()
    service = PaperTradingService(cfg, settings, redis_client=None, prometheus_metrics=PrometheusMetricsCollector())
    # Inject fake producer
    service.orchestrator.producers = [FakeProducer()]
    # Inject fake metrics collector
    service.metrics_collector = FakeMetrics()

    msg = {"type": "validated_signal", "data": _validated_signal().model_dump(mode="json")}
    await service._handle_validated_signal(msg, topic="paper.signals.validated")

    # Expect metrics to include broker_context="paper"
    kinds = [(k, b) for (k, b, _d) in service.metrics_collector.calls]
    assert ("orders", "paper") in kinds
    assert ("portfolio", "paper") in kinds
    # Ensure fake producer sent two events
    assert len(service.orchestrator.producers[0].sent) >= 2


@pytest.mark.asyncio
async def test_zerodha_trading_records_pipeline_metrics(monkeypatch):
    cfg = RedpandaSettings(bootstrap_servers="localhost:9092")
    settings = _settings()
    service = ZerodhaTradingService(cfg, settings, redis_client=None, prometheus_metrics=PrometheusMetricsCollector())
    service.orchestrator.producers = [FakeProducer()]
    service.metrics_collector = FakeMetrics()

    msg = {"type": "validated_signal", "data": _validated_signal().model_dump(mode="json")}
    await service._handle_validated_signal(msg, topic="zerodha.signals.validated")

    kinds = [(k, b) for (k, b, _d) in service.metrics_collector.calls]
    assert ("orders", "zerodha") in kinds
    assert ("portfolio", "zerodha") in kinds
    assert len(service.orchestrator.producers[0].sent) >= 2
