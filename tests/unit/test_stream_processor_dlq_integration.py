import asyncio
import types
import sys
import importlib.util
from pathlib import Path


class _FakeMessage:
    def __init__(self):
        self.topic = "paper.signals.raw"
        self.key = b"k1"
        self.value = {"id": "evt1", "type": "TRADING_SIGNAL", "correlation_id": "corr1", "data": {}}
        self.partition = 0
        self.offset = 123
        self.timestamp = 0
        self.headers = [("h1", b"v1")]


def _install_fakes():
    # Fake aiokafka
    ak = types.ModuleType("aiokafka")
    ak.AIOKafkaProducer = object
    ak.AIOKafkaConsumer = object
    sys.modules.setdefault("aiokafka", ak)

    ak_admin = types.ModuleType("aiokafka.admin")
    ak_admin.AIOKafkaAdminClient = object
    sys.modules.setdefault("aiokafka.admin", ak_admin)

    ak_errors = types.ModuleType("aiokafka.errors")
    class _KafkaError(Exception):
        pass
    class _KafkaConnectionError(_KafkaError):
        pass
    ak_errors.KafkaError = _KafkaError
    ak_errors.KafkaConnectionError = _KafkaConnectionError
    sys.modules.setdefault("aiokafka.errors", ak_errors)

    ak_structs = types.ModuleType("aiokafka.structs")
    class _TopicPartition:
        def __init__(self, topic, partition):
            self.topic = topic
            self.partition = partition
    ak_structs.TopicPartition = _TopicPartition
    sys.modules.setdefault("aiokafka.structs", ak_structs)

    # Fake redis.asyncio
    redis_asyncio = types.ModuleType("redis.asyncio")
    class _Redis:
        pass
    redis_asyncio.Redis = _Redis
    sys.modules.setdefault("redis.asyncio", redis_asyncio)


async def _run():
    _install_fakes()

    # Load StreamProcessor
    clients_path = Path(__file__).resolve().parents[2] / "core/streaming/clients.py"
    spec = importlib.util.spec_from_file_location("clients_mod", clients_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    from core.config.settings import RedpandaSettings

    class FakeRedpandaProducer:
        def __init__(self):
            self.sent = []
        async def start(self):
            return
        async def stop(self):
            return
        async def send(self, topic: str, key: str, value):
            self.sent.append({"topic": topic, "key": key, "value": value})

    # Initialize StreamProcessor with no consume topics
    sp = mod.StreamProcessor(
        name="test_sp",
        config=RedpandaSettings(bootstrap_servers="localhost:9092"),
        consume_topics=[],
        group_id="g",
    )

    # Replace DLQ publisher's producer with adapter wrapping fake producer
    fake_prod = FakeRedpandaProducer()
    sp.dlq_publisher.producer = mod._MessageProducerAdapter(fake_prod, service_name="test_sp")

    # Simulate a poison error to trigger DLQ immediately
    msg = _FakeMessage()
    async def _noop():
        return None

    handled = await sp.error_handler.handle_processing_error(
        msg,
        ValueError("poison"),
        processing_func=_noop,
        commit_func=_noop,
    )

    assert handled is True
    assert len(fake_prod.sent) == 1
    env = fake_prod.sent[0]["value"]
    assert isinstance(env, dict)
    assert env.get("broker") == "system"
    t = env.get("type")
    assert str(t).endswith("system_error") or t == "system_error"


def test_stream_processor_dlq_integration_sends_to_adapter():
    asyncio.run(_run())
