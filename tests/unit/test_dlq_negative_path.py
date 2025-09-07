import asyncio
import logging
from datetime import datetime

import pytest
from prometheus_client import CollectorRegistry

from core.streaming.error_handling import DLQPublisher
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector


class DummyProducer:
    def __init__(self):
        self.last_send = None

    async def send(self, topic: str, key: str, data: dict, event_type, broker: str):
        self.last_send = {
            "topic": topic,
            "key": key,
            "data": data,
            "event_type": event_type,
            "broker": broker,
        }


class DummyMessage:
    def __init__(self, topic: str):
        self.topic = topic
        self.partition = 0
        self.offset = 42
        self.timestamp = int(datetime.now().timestamp() * 1000)
        self.key = b"k"
        self.value = {"hello": "world"}
        self.headers = {"h": b"v"}


@pytest.mark.asyncio
async def test_dlq_publish_and_prometheus_counter_increment(caplog):
    caplog.set_level(logging.WARNING)

    prod = DummyProducer()
    service = "test_service"
    dlq = DLQPublisher(prod, service_name=service)

    # Prometheus collector with isolated registry
    reg = CollectorRegistry()
    prom = PrometheusMetricsCollector(registry=reg)

    # Attach a callback similar to StreamServiceBuilder wiring
    async def on_dlq(topic: str, event: dict):
        broker = topic.split(".")[0]
        prom.record_dlq_message(service, broker)

    dlq.set_on_dlq_callback(on_dlq)

    # Trigger DLQ
    msg = DummyMessage(topic="paper.signals.validated")
    err = ValueError("bad payload")
    ok = await dlq.send_to_dlq(msg, err, failure_reason="poison", retry_count=0)

    assert ok is True
    assert prod.last_send is not None
    assert prod.last_send["topic"].endswith(".dlq")
    assert prod.last_send["topic"].startswith("paper.")

    # Prom counter should be 1 for this service/broker
    val = reg.get_sample_value(
        "trading_dlq_messages_total",
        labels={"service": service, "broker": "paper"},
    )
    assert val == 1.0

    # Log record should carry dlq=True tag
    assert any(getattr(r, "dlq", False) for r in caplog.records), "expected dlq log tag"

