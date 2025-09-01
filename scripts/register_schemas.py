"""
Register Avro schemas with Redpanda Schema Registry (Confluent-compatible).

Environment:
- SCHEMA_REGISTRY_URL: default http://localhost:8082

This script registers value schemas for core topics. It does not switch
runtime serialization yet; it provides scaffolding for compatibility checks.
"""

import asyncio
import json
import os
from pathlib import Path
import httpx


SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8082")


def _load_schema(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def _subject(topic: str) -> str:
    return f"{topic}-value"


async def register(subject: str, schema_str: str) -> None:
    url = f"{SCHEMA_REGISTRY_URL}/subjects/{subject}/versions"
    payload = {
        "schemaType": "AVRO",
        "schema": schema_str,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, json=payload)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Failed to register {subject}: {r.status_code} {r.text}")


async def main():
    base = Path(__file__).resolve().parents[1] / "schemas" / "avro"
    if not base.exists():
        raise SystemExit(f"Schemas folder not found: {base}")

    # Load core schemas
    envelope = _load_schema(base / "event_envelope.avsc")
    market_tick = _load_schema(base / "market_tick.avsc")
    trading_signal = _load_schema(base / "trading_signal.avsc")
    validated_signal = _load_schema(base / "validated_signal.avsc")
    order_filled = _load_schema(base / "order_filled.avsc")
    pnl_snapshot = _load_schema(base / "pnl_snapshot.avsc")

    # Map subjects (topics) to schemas
    topics = {
        # Shared market data
        "market.ticks": market_tick,

        # Signals (broker-specific)
        "paper.signals.raw": trading_signal,
        "zerodha.signals.raw": trading_signal,
        "paper.signals.validated": validated_signal,
        "zerodha.signals.validated": validated_signal,
        "paper.signals.rejected": validated_signal,
        "zerodha.signals.rejected": validated_signal,

        # Orders
        "paper.orders.filled": order_filled,
        "zerodha.orders.filled": order_filled,

        # PnL
        "paper.pnl.snapshots": pnl_snapshot,
        "zerodha.pnl.snapshots": pnl_snapshot,
    }

    # Register all subjects
    for topic, schema in topics.items():
        subject = _subject(topic)
        print(f"Registering schema for {subject} ...")
        await register(subject, schema)
        print(f"✓ Registered {subject}")


if __name__ == "__main__":
    asyncio.run(main())

