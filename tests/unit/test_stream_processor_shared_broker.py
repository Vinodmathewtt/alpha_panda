import asyncio
import types
import sys
import importlib.util
from pathlib import Path


def _install_fakes():
    # Fake aiokafka module hierarchy
    ak = types.ModuleType("aiokafka")
    ak.AIOKafkaProducer = object
    ak.AIOKafkaConsumer = object
    sys.modules.setdefault("aiokafka", ak)

    ak_admin = types.ModuleType("aiokafka.admin")
    ak_admin.AIOKafkaAdminClient = object
    sys.modules.setdefault("aiokafka.admin", ak_admin)

    # Fake redis.asyncio to satisfy import
    redis_asyncio = types.ModuleType("redis.asyncio")
    sys.modules.setdefault("redis.asyncio", redis_asyncio)


async def _run():
    _install_fakes()

    # Dynamically load the clients module
    clients_path = Path(__file__).resolve().parents[2] / "core/streaming/clients.py"
    spec = importlib.util.spec_from_file_location("clients_mod", clients_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    from core.config.settings import RedpandaSettings
    from core.schemas.events import EventType
    from core.schemas.topics import TopicNames

    class FakeProducer:
        def __init__(self):
            self.sent = []

        async def start(self):
            return

        async def stop(self):
            return

        async def send(self, topic: str, key: str, value):
            self.sent.append({"topic": topic, "key": key, "value": value})

    # Initialize a StreamProcessor with a fake producer and no consumer topics
    sp = mod.StreamProcessor(
        name="test_sp",
        config=RedpandaSettings(bootstrap_servers="localhost:9092"),
        consume_topics=[],
        group_id="g",
    )
    sp.producer = FakeProducer()

    # Emit to shared market.ticks and assert broker label is 'shared'
    await sp._emit_event(
        topic=TopicNames.MARKET_TICKS,
        event_type=EventType.MARKET_TICK,
        key="k",
        data={"ok": True},
    )

    assert len(sp.producer.sent) == 1
    env = sp.producer.sent[0]["value"]
    # Envelope is serialized via model_dump() in _emit_event
    assert isinstance(env, dict)
    assert env.get("broker") == "shared"
    assert env.get("type") in (EventType.MARKET_TICK, EventType.MARKET_TICK.value, "market_tick")


def test_stream_processor_uses_shared_broker_for_market_ticks():
    asyncio.run(_run())

