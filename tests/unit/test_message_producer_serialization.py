from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import json
import importlib.util

from core.config.settings import RedpandaSettings


def _load_message_producer_module():
    path = Path(__file__).resolve().parents[2] / "core/streaming/infrastructure/message_producer.py"
    spec = importlib.util.spec_from_file_location("mp_mod_serialize", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_message_producer_json_serialization_handles_datetime_and_decimal():
    mp_mod = _load_message_producer_module()
    cfg = RedpandaSettings(bootstrap_servers="localhost:9092")
    producer = mp_mod.MessageProducer(cfg, service_name="serialize-test")

    payload = {
        "ts": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "price": Decimal("123.45"),
    }

    b = producer._serialize_value(payload)
    s = b.decode("utf-8")
    data = json.loads(s)
    assert data["ts"].startswith("2024-01-01T00:00:00")
    assert data["price"] == 123.45

