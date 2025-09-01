"""
Simple DLQ replay tool.

Consumes messages from a DLQ topic and republishes the original payload
to the original topic recorded in the DLQ envelope. Supports dry-run mode.

Usage:
  python scripts/dlq_replay.py --bootstrap localhost:9092 --dlq paper.signals.raw.dlq --group replay-tool \
      [--limit 100] [--dry-run]
"""

import argparse
import asyncio
import json
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer


async def replay(args: argparse.Namespace) -> None:
    consumer = AIOKafkaConsumer(
        args.dlq,
        bootstrap_servers=args.bootstrap,
        group_id=args.group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=args.bootstrap,
        acks="all",
        enable_idempotence=True,
        value_serializer=lambda x: json.dumps(x).encode("utf-8"),
    )

    await consumer.start()
    await producer.start()
    processed = 0
    try:
        async for msg in consumer:
            val = msg.value
            dlq_meta = (val or {}).get("dlq_metadata", {})
            original_topic = dlq_meta.get("original_topic")
            original_message = (val or {}).get("original_message", {})
            data = original_message.get("value")
            key = original_message.get("key", "")
            if not original_topic or data is None:
                # Skip malformed DLQ entries
                await consumer.commit()
                continue
            if args.dry_run:
                print(f"DRY-RUN would replay to {original_topic} with key={key}")
            else:
                await producer.send_and_wait(
                    topic=original_topic,
                    key=str(key).encode("utf-8"),
                    value=data,
                )
            processed += 1
            await consumer.commit()
            if args.limit and processed >= args.limit:
                break
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="DLQ replay tool")
    parser.add_argument("--bootstrap", required=True, help="Kafka/Redpanda bootstrap servers")
    parser.add_argument("--dlq", required=True, help="DLQ topic to consume from")
    parser.add_argument("--group", default="alpha-panda.dlq-replay", help="Consumer group id")
    parser.add_argument("--limit", type=int, default=0, help="Max messages to replay (0=no limit)")
    parser.add_argument("--dry-run", action="store_true", help="Do not publish, just log actions")
    args = parser.parse_args()
    asyncio.run(replay(args))


if __name__ == "__main__":
    main()

