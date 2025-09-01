"""
Validate local Avro schemas against Redpanda Schema Registry for compatibility.

Environment:
- SCHEMA_REGISTRY_URL: default http://localhost:8082
- COMPATIBILITY_LEVEL: BACKWARD|FORWARD|FULL (optional)
"""

import asyncio
import json
import os
from pathlib import Path
import httpx


SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8082")
COMPATIBILITY_LEVEL = os.getenv("COMPATIBILITY_LEVEL", "BACKWARD")


def _load_schema(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def _subject(topic: str) -> str:
    return f"{topic}-value"


async def check_compatibility(subject: str, schema_str: str) -> bool:
    url = f"{SCHEMA_REGISTRY_URL}/compatibility/subjects/{subject}/versions/latest"
    payload = {
        "schemaType": "AVRO",
        "schema": schema_str,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, json=payload)
        if r.status_code == 404:
            # No prior schema -> treat as compatible for initial registration
            return True
        if r.status_code != 200:
            raise RuntimeError(f"Compatibility check failed for {subject}: {r.status_code} {r.text}")
        data = r.json()
        return bool(data.get("is_compatible", False))


async def set_global_compatibility(level: str) -> None:
    url = f"{SCHEMA_REGISTRY_URL}/config"
    payload = {"compatibility": level}
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.put(url, json=payload)


async def main():
    base = Path(__file__).resolve().parents[1] / "schemas" / "avro"
    if not base.exists():
        raise SystemExit(f"Schemas folder not found: {base}")

    # Optionally set global compatibility
    try:
        await set_global_compatibility(COMPATIBILITY_LEVEL)
        print(f"Global compatibility set to {COMPATIBILITY_LEVEL}")
    except Exception as e:
        print(f"Warning: failed to set global compatibility: {e}")

    schemas = {
        "market.ticks": _load_schema(base / "market_tick.avsc"),
        "paper.signals.raw": _load_schema(base / "trading_signal.avsc"),
        "zerodha.signals.raw": _load_schema(base / "trading_signal.avsc"),
        "paper.signals.validated": _load_schema(base / "validated_signal.avsc"),
        "zerodha.signals.validated": _load_schema(base / "validated_signal.avsc"),
        "paper.signals.rejected": _load_schema(base / "validated_signal.avsc"),
        "zerodha.signals.rejected": _load_schema(base / "validated_signal.avsc"),
        "paper.orders.filled": _load_schema(base / "order_filled.avsc"),
        "zerodha.orders.filled": _load_schema(base / "order_filled.avsc"),
        "paper.pnl.snapshots": _load_schema(base / "pnl_snapshot.avsc"),
        "zerodha.pnl.snapshots": _load_schema(base / "pnl_snapshot.avsc"),
    }

    incompatible = []
    for topic, schema in schemas.items():
        subject = _subject(topic)
        try:
            ok = await check_compatibility(subject, schema)
            print(f"{subject}: {'compatible' if ok else 'incompatible'}")
            if not ok:
                incompatible.append(subject)
        except Exception as e:
            print(f"{subject}: error: {e}")
            incompatible.append(subject)

    if incompatible:
        raise SystemExit(f"Incompatible schemas: {incompatible}")
    print("All schemas compatible with latest registered versions")


if __name__ == "__main__":
    asyncio.run(main())

