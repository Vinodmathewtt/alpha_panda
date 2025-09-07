import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.config.settings import RedpandaSettings, Settings
from core.schemas.events import TradingSignal, ValidatedSignal, EventType
from core.schemas.topics import TopicMap, PartitioningKeys
from core.streaming.infrastructure.message_producer import MessageProducer
from services.paper_trading.service import PaperTradingService


@pytest.mark.asyncio
async def test_paper_trading_emits_filled_event_integration():
    # Require docker-compose infra
    try:
        import redis.asyncio as aioredis
        redis = aioredis.from_url("redis://localhost:6379/0")
        await redis.ping()
    except Exception:
        pytest.skip("Redis not available on localhost:6379")

    # Kafka admin quick check (optional)
    try:
        from aiokafka.admin import AIOKafkaAdminClient
        admin = AIOKafkaAdminClient(bootstrap_servers="localhost:9092", client_id="alpha-panda-test-admin")
        await admin.start()
        await admin.describe_cluster()
        await admin.close()
    except Exception:
        pytest.skip("Redpanda not available on localhost:9092")

    settings = Settings()
    cfg = RedpandaSettings(bootstrap_servers="localhost:9092", client_id="alpha-panda-client")

    paper = PaperTradingService(config=cfg, settings=settings, redis_client=redis, prometheus_metrics=None)

    # Start paper service and give it a moment to subscribe
    await paper.start()
    await asyncio.sleep(0.5)

    # Prepare producer to emit a validated signal to paper.signals.validated
    producer = MessageProducer(cfg, service_name="integration-test")
    topic_in = TopicMap("paper").signals_validated()
    topic_out = TopicMap("paper").orders_filled()
    ts = datetime.now(timezone.utc)

    sig = TradingSignal(
        strategy_id="itest_strategy",
        instrument_token=256265,
        signal_type="BUY",
        quantity=3,
        price=Decimal("100.0"),
        timestamp=ts,
        confidence=0.9,
        metadata={"itest": True},
    )
    val = ValidatedSignal(
        original_signal=sig,
        validated_quantity=sig.quantity,
        validated_price=sig.price,
        risk_checks={"max_position": True},
        timestamp=ts,
    )
    key = PartitioningKeys.trading_signal_key(sig.strategy_id, sig.instrument_token)

    # Consume from paper.orders.filled with a temporary consumer (start before send)
    from aiokafka import AIOKafkaConsumer

    group_id = f"alpha-panda-itest-paper-orders"
    consumer = AIOKafkaConsumer(
        topic_out,
        bootstrap_servers="localhost:9092",
        group_id=group_id,
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
    )
    await consumer.start()
    received = None
    try:
        # Give consumer a moment to join group
        await asyncio.sleep(0.5)

        # Now emit the validated signal
        await producer.send(
            topic=topic_in,
            key=key,
            data=val.model_dump(mode="json"),
            event_type=EventType.VALIDATED_SIGNAL,
            broker="paper",
        )

        # Wait up to ~5 seconds to get the fill
        for _ in range(50):
            msgs = await consumer.getmany(timeout_ms=100)
            if not msgs:
                await asyncio.sleep(0.1)
                continue
            for tp, batch in msgs.items():
                for record in batch:
                    val = record.value
                    # Envelope is a dict with 'type' and 'data'
                    if isinstance(val, dict) and (val.get("type") in (EventType.ORDER_FILLED, EventType.ORDER_FILLED.value, "order_filled")):
                        received = val
                        break
                if received:
                    break
            if received:
                break
    finally:
        await consumer.stop()
        try:
            await producer.stop()
        except Exception:
            pass
        await paper.stop()

    assert received is not None, "Did not receive paper.orders.filled event"
    assert received.get("data", {}).get("broker") == "paper"
    assert received.get("data", {}).get("instrument_token") == 256265
