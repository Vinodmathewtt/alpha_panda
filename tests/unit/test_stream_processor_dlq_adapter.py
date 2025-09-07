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
    # Fake aiokafka module hierarchy to satisfy imports
    ak = types.ModuleType("aiokafka")
    ak.AIOKafkaProducer = object
    ak.AIOKafkaConsumer = object
    sys.modules.setdefault("aiokafka", ak)

    ak_admin = types.ModuleType("aiokafka.admin")
    ak_admin.AIOKafkaAdminClient = object
    sys.modules.setdefault("aiokafka.admin", ak_admin)

    # Fake aiokafka.errors
    ak_errors = types.ModuleType("aiokafka.errors")
    class _KafkaError(Exception):
        pass
    class _KafkaConnectionError(_KafkaError):
        pass
    ak_errors.KafkaError = _KafkaError
    ak_errors.KafkaConnectionError = _KafkaConnectionError
    sys.modules.setdefault("aiokafka.errors", ak_errors)

    # Fake aiokafka.structs
    ak_structs = types.ModuleType("aiokafka.structs")
    class _TopicPartition:
        def __init__(self, topic, partition):
            self.topic = topic
            self.partition = partition
    ak_structs.TopicPartition = _TopicPartition
    sys.modules.setdefault("aiokafka.structs", ak_structs)

    # Fake redis.asyncio to satisfy import
    redis_asyncio = types.ModuleType("redis.asyncio")
    class _Redis:
        pass
    redis_asyncio.Redis = _Redis
    sys.modules.setdefault("redis.asyncio", redis_asyncio)


async def _run():
    _install_fakes()

    # Dynamically load the clients module (contains the adapter)
    clients_path = Path(__file__).resolve().parents[2] / "core/streaming/clients.py"
    spec = importlib.util.spec_from_file_location("clients_mod", clients_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    from core.streaming.error_handling import DLQPublisher
    from core.schemas.events import EventType

    class FakeRedpandaProducer:
        def __init__(self):
            self.sent = []

        async def start(self):
            return

        async def stop(self):
            return

        async def send(self, topic: str, key: str, value):
            # Capture the envelope dict being sent
            self.sent.append({"topic": topic, "key": key, "value": value})

    # Create adapter and DLQ publisher
    rp = FakeRedpandaProducer()
    adapter = mod._MessageProducerAdapter(rp, service_name="unit_test_service")
    dlq = DLQPublisher(adapter, service_name="unit_test_service")

    # Invoke DLQ publish with a fake message
    msg = _FakeMessage()
    ok = await dlq.send_to_dlq(msg, RuntimeError("boom"), failure_reason="test", retry_count=1, error_type=None)

    assert ok is True
    assert len(rp.sent) == 1
    out = rp.sent[0]
    assert out["topic"].endswith(".dlq")
    env = out["value"]
    assert isinstance(env, dict)
    # Envelope broker should be 'system' per DLQPublisher call
    assert env.get("broker") == "system"
    # Type should be system_error (enum or value)
    et = env.get("type")
    assert et in (EventType.SYSTEM_ERROR, EventType.SYSTEM_ERROR.value, "system_error")


def test_stream_processor_dlq_adapter_sends_enveloped_event():
    asyncio.run(_run())
