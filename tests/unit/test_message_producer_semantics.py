import asyncio
import pytest
from types import SimpleNamespace, ModuleType
import sys

# Provide a fake aiokafka module to satisfy imports without installing dependency
fake_aiokafka = ModuleType("aiokafka")
setattr(fake_aiokafka, "AIOKafkaProducer", object)
setattr(fake_aiokafka, "AIOKafkaConsumer", object)
sys.modules.setdefault("aiokafka", fake_aiokafka)

from core.config.settings import RedpandaSettings
from core.schemas.topics import TopicNames
from pathlib import Path
import importlib.util

# Dynamically load the message_producer module to avoid importing core.streaming.clients
_mp_path = Path(__file__).resolve().parents[2] / "core/streaming/infrastructure/message_producer.py"
_mp_spec = importlib.util.spec_from_file_location("mp_mod", _mp_path)
mp_mod = importlib.util.module_from_spec(_mp_spec)
assert _mp_spec and _mp_spec.loader
_mp_spec.loader.exec_module(mp_mod)
MessageProducer = mp_mod.MessageProducer


class FakeAIOKafkaProducer:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.sent = []

    async def start(self):
        self.started = True

    async def stop(self):
        self.started = False

    async def flush(self):
        return

    async def send_and_wait(self, topic, key, value, headers=None):
        # Record without serialization; value is expected to be a dict envelope
        self.sent.append({
            "topic": topic,
            "key": key,
            "value": value,
            "headers": headers or [],
        })
        return SimpleNamespace(topic=topic, key=key)


@pytest.mark.asyncio
async def test_producer_requires_event_type_for_non_market_topics(monkeypatch):
    # Patch the AIOKafkaProducer used by MessageProducer
    # Patch the AIOKafkaProducer symbol inside the dynamically loaded module
    monkeypatch.setattr(mp_mod, "AIOKafkaProducer", FakeAIOKafkaProducer, raising=True)

    cfg = RedpandaSettings(bootstrap_servers="localhost:9092")
    producer = MessageProducer(cfg, service_name="test-service")

    # Missing event_type and no type in data should fail for non-market topics
    with pytest.raises(ValueError):
        await producer.send(
            topic="paper.signals.raw",
            key="k1",
            data={"foo": "bar"},
            event_type=None,
            broker="paper",
        )


@pytest.mark.asyncio
async def test_producer_defaults_to_market_tick_for_market_topic(monkeypatch):
    monkeypatch.setattr(mp_mod, "AIOKafkaProducer", FakeAIOKafkaProducer, raising=True)

    cfg = RedpandaSettings(bootstrap_servers="localhost:9092")
    producer = MessageProducer(cfg, service_name="market-feed")

    event_id = await producer.send(
        topic=TopicNames.MARKET_TICKS,
        key="123",
        data={"instrument_token": 1, "last_price": 100},
        event_type=None,
        broker="shared",
    )
    # Ensure envelope was created and captured by fake producer
    fp: FakeAIOKafkaProducer = producer._producer  # type: ignore[attr-defined]
    assert fp.started is True
    assert len(fp.sent) == 1
    env = fp.sent[0]["value"]
    assert env["type"] == "market_tick" or env["type"].value == "market_tick"
    assert env["broker"] == "shared"
    assert env["key"] == "123"
    assert env["id"] == event_id
