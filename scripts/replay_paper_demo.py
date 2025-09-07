#!/usr/bin/env python3
"""
Replay helper for paper trading demos.

Two modes:
- bracket_demo: emits a validated BUY with bracket, then emits a market tick to trigger exit.
- jsonl: replays JSONL lines with fields: topic, key, data, event_type, broker.
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.config.settings import RedpandaSettings
from core.schemas.events import EventType, TradingSignal, ValidatedSignal, MarketTick
from core.schemas.topics import TopicMap, TopicNames, PartitioningKeys
from core.streaming.infrastructure.message_producer import MessageProducer


async def send(producer: MessageProducer, topic: str, key: str, data: dict, event_type: EventType | None, broker: str) -> None:
    await producer.send(topic=topic, key=key, data=data, event_type=event_type, broker=broker)


async def bracket_demo(args):
    cfg = RedpandaSettings(bootstrap_servers=args.bootstrap, client_id="alpha-panda-replay")
    producer = MessageProducer(cfg, service_name="replay")
    try:
        # 1) validated BUY with bracket
        ts = datetime.now(timezone.utc)
        entry_price = Decimal(str(args.entry_price))
        sig = TradingSignal(
            strategy_id=args.strategy_id,
            instrument_token=args.instrument,
            signal_type="BUY",
            quantity=args.quantity,
            price=entry_price,
            timestamp=ts,
            confidence=0.9,
            metadata={
                "bracket": True,
                "take_profit_pct": args.take_profit_pct,
                "stop_loss_pct": args.stop_loss_pct,
            },
        )
        val = ValidatedSignal(
            original_signal=sig,
            validated_quantity=sig.quantity,
            validated_price=sig.price,
            risk_checks={"max_position": True},
            timestamp=ts,
        )
        topic_in = TopicMap("paper").signals_validated()
        key = PartitioningKeys.trading_signal_key(sig.strategy_id, sig.instrument_token)
        await send(producer, topic_in, key, val.model_dump(mode="json"), EventType.VALIDATED_SIGNAL, "paper")

        # 2) trigger tick
        await asyncio.sleep(args.delay)
        tick_price = Decimal(str(args.exit_price))
        mkt = MarketTick(
            instrument_token=args.instrument,
            last_price=tick_price,
            timestamp=datetime.now(timezone.utc),
            symbol="REPLAY",
        )
        await send(producer, TopicNames.MARKET_TICKS, str(args.instrument), mkt.model_dump(mode="json"), EventType.MARKET_TICK, "shared")
        print("Bracket demo emitted.")
    finally:
        try:
            await producer.stop()
        except Exception:
            pass


async def jsonl_replay(args):
    cfg = RedpandaSettings(bootstrap_servers=args.bootstrap, client_id="alpha-panda-replay")
    producer = MessageProducer(cfg, service_name="replay")
    try:
        with open(args.file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                msg = json.loads(line)
                topic = msg["topic"]
                key = str(msg.get("key", ""))
                data = msg.get("data", {})
                et = msg.get("event_type")
                broker = msg.get("broker", "paper")
                et_enum = None
                if et:
                    try:
                        et_enum = EventType(et)
                    except Exception:
                        et_enum = None
                await send(producer, topic, key, data, et_enum, broker)
        print("JSONL replay completed.")
    finally:
        try:
            await producer.stop()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser(description="Paper trading replay tool")
    ap.add_argument("mode", choices=["bracket_demo", "jsonl"])
    ap.add_argument("--bootstrap", default="localhost:9092")

    # bracket demo params
    ap.add_argument("--strategy-id", default="replay_demo")
    ap.add_argument("--instrument", type=int, default=256265)
    ap.add_argument("--quantity", type=int, default=3)
    ap.add_argument("--entry-price", type=float, default=100.0)
    ap.add_argument("--exit-price", type=float, default=101.2)
    ap.add_argument("--take-profit-pct", type=float, default=1.0)
    ap.add_argument("--stop-loss-pct", type=float, default=0.0)
    ap.add_argument("--delay", type=float, default=0.5)

    # jsonl params
    ap.add_argument("--file")
    args = ap.parse_args()

    if args.mode == "bracket_demo":
        asyncio.run(bracket_demo(args))
    else:
        if not args.file:
            raise SystemExit("--file required for jsonl mode")
        asyncio.run(jsonl_replay(args))


if __name__ == "__main__":
    main()

