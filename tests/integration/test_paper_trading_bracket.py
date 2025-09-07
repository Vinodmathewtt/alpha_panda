import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.config.settings import RedpandaSettings, Settings
from core.schemas.events import TradingSignal, ValidatedSignal, EventType, MarketTick
from core.schemas.topics import TopicMap, TopicNames, PartitioningKeys
from core.streaming.infrastructure.message_producer import MessageProducer
from services.paper_trading.service import PaperTradingService


@pytest.mark.asyncio
async def test_paper_trading_bracket_exit_on_market_tick():
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
    await paper.start()
    await asyncio.sleep(0.5)

    producer = MessageProducer(cfg, service_name="integration-test")

    # 1) Emit a validated BUY with bracket (tp=1%)
    topic_in = TopicMap("paper").signals_validated()
    ts = datetime.now(timezone.utc)
    entry_price = Decimal("100.0")
    sig = TradingSignal(
        strategy_id="itest_bracket",
        instrument_token=256265,
        signal_type="BUY",
        quantity=3,
        price=entry_price,
        timestamp=ts,
        confidence=0.9,
        metadata={"bracket": True, "take_profit_pct": 1.0},
    )
    val = ValidatedSignal(
        original_signal=sig,
        validated_quantity=sig.quantity,
        validated_price=sig.price,
        risk_checks={"max_position": True},
        timestamp=ts,
    )
    key = PartitioningKeys.trading_signal_key(sig.strategy_id, sig.instrument_token)
    await producer.send(
        topic=topic_in,
        key=key,
        data=val.model_dump(mode="json"),
        event_type=EventType.VALIDATED_SIGNAL,
        broker="paper",
    )

    # 2) Start consumer to capture SELL (bracket exit)
    from aiokafka import AIOKafkaConsumer
    topic_out = TopicMap("paper").orders_filled()
    consumer = AIOKafkaConsumer(
        topic_out,
        bootstrap_servers="localhost:9092",
        group_id="alpha-panda-itest-bracket",
        auto_offset_reset="latest",
        enable_auto_commit=False,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
    )
    await consumer.start()
    await asyncio.sleep(0.5)

    # 3) Send a market tick above take-profit (101.0)
    mkt = MarketTick(
        instrument_token=256265,
        last_price=Decimal("101.2"),
        timestamp=datetime.now(timezone.utc),
        symbol="NIFTY",
    )
    await producer.send(
        topic=TopicNames.MARKET_TICKS,
        key=str(mkt.instrument_token),
        data=mkt.model_dump(mode="json"),
        event_type=EventType.MARKET_TICK,
        broker="shared",
    )

    received_sell = False
    try:
        # Wait up to 5s for bracket exit SELL
        for _ in range(50):
            msgs = await consumer.getmany(timeout_ms=100)
            if not msgs:
                await asyncio.sleep(0.1)
                continue
            for tp, batch in msgs.items():
                for rec in batch:
                    env = rec.value
                    if env.get("type") in (EventType.ORDER_FILLED, EventType.ORDER_FILLED.value, "order_filled"):
                        data = env.get("data", {})
                        if data.get("strategy_id") == "itest_bracket" and data.get("side") in ("SELL", "sell"):
                            received_sell = True
                            break
                if received_sell:
                    break
            if received_sell:
                break
    finally:
        await consumer.stop()
        try:
            await producer.stop()
        except Exception:
            pass
        await paper.stop()

    assert received_sell, "Did not receive bracket exit SELL fill"
