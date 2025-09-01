# Zerodha Trading Service

## Overview
- Broker-scoped trading service for live Zerodha execution (zerodha broker).
- Consumes `zerodha.signals.validated` and emits `zerodha.orders.submitted` and `zerodha.pnl.snapshots`.

## Topics
- Input: `zerodha.signals.validated`
- Output:
  - `zerodha.orders.submitted` (EventType.ORDER_PLACED, status=PLACED)
  - `zerodha.pnl.snapshots` (EventType.PNL_SNAPSHOT)

## Consumer Group
- `alpha-panda.zerodha-trading.signals` (via container’s group-id prefix)

## DI Provider
- `zerodha_trading_service` (see `app/containers.py`)

## Metrics and Observability
- Prometheus counters: `trading_events_processed_total{service="zerodha_trading",broker="zerodha",event_type=...}`
- Last-activity gauge: `trading_last_activity_timestamp_unix{service="zerodha_trading",stage=...,broker="zerodha"}`
- Panels and alerts: see Grafana JSON in `docs/observability/grafana/` and Prometheus rules in `docs/observability/prometheus/`.

## Notes
- Emits order placement events; integration with the live Zerodha client can be added in `components/` to place/track real orders and fills.
- Ensure Zerodha credentials are configured when `zerodha` is active in `ACTIVE_BROKERS`.

## SDK Integration (Kite Connect / pykiteconnect)

- This service must integrate tightly with Zerodha’s official Python SDK (Kite Connect / pykiteconnect) for real trading.
- A reference copy of the SDK is available for review under:
  - `examples/pykiteconnect-zerodha-python-sdk-for-reference`
- Recommended adapter layout (under `components/`):
  - `auth_adapter.py`: Login/session management, token refresh, safe storage
  - `order_executor.py`: place/modify/cancel with idempotence, retries, and error mapping
  - `portfolio_adapter.py`: positions/holdings fetch for reconciliation
  - `stream_adapter.py` (optional): order/position updates via websockets, if supported
- Key concerns:
  - Rate limiting and backoff, clear error taxonomy
  - Order id mapping; ensure partition keys use `strategy_id:instrument:timestamp`
  - Emit `ORDER_PLACED` (and later `ORDER_FILLED` on confirmations) with proper envelopes
  - Robust retries to DLQ on persistent errors, alerts on auth failures

## Parameter Mapping (Zerodha → Adapter)

Sketch of how Kite Connect order parameters will map into the adapter (ZerodhaOrderParams) and where we source values.

| Zerodha API Param  | Description                       | Adapter Field            | Source                                | Notes |
|--------------------|-----------------------------------|--------------------------|----------------------------------------|-------|
| exchange           | Exchange code (e.g., NSE/BSE)     | (derive via metadata)    | Instrument registry / symbol metadata  | Map from instrument_token → instrument info |
| tradingsymbol      | Symbol with series (e.g., RELIANCE)| (derive via metadata)   | Instrument registry / signal metadata  | Prefer canonical mapping from token |
| transaction_type   | BUY/SELL                           | side                     | `signal.signal_type`                   | Enum conversion required |
| quantity           | Order quantity                     | quantity                 | `validated.validated_quantity`         | Int |
| price              | Limit price (if applicable)        | price                    | `validated.validated_price` or signal  | None for MARKET |
| product            | CNC/MIS/NRML, etc.                 | product                  | Strategy/broker config                  | Default from config |
| order_type         | LIMIT/MARKET/SL/SL-M               | order_type               | Strategy/broker config or signal meta   | Default MARKET/LIMIT as needed |
| validity           | DAY/IOC                            | validity                 | Config                                 | |
| variety            | REGULAR/AMO/CO/BO                  | variety                  | Config                                 | Start with REGULAR |
| tag                | Optional idempotency tag           | tag                      | Generated (strategy_id + ts)           | Useful for de-dup |

Notes
- `instrument_token` → (`exchange`, `tradingsymbol`) mapping is resolved via the instrument registry; fallback to `signal.metadata.symbol` if provided.
- For MARKET orders, omit `price` in SDK call. For LIMIT/SL variants, ensure `price` (and `trigger_price` if needed in future) is set.
- Product, order_type, validity, variety should be configurable per strategy/broker and validated before the SDK call.
- Consider adding a Redis-based idempotency check keyed by (`strategy_id`, `instrument_token`, `timestamp`) to prevent duplicate placements.


## Quick Start (Code)

```python
import asyncio
from app.containers import AppContainer

async def main():
    container = AppContainer()
    service = container.zerodha_trading_service()
    try:
        await service.start()
        # Service now consumes zerodha.signals.validated and emits orders/pnl
        await asyncio.Event().wait()  # keep running
    finally:
        await service.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Sample Events

Input: Validated signal envelope (from risk_manager) on `zerodha.signals.validated`

```json
{
  "id": "evt-...",
  "correlation_id": "corr-...",
  "trace_id": "trace-...",
  "broker": "zerodha",
  "type": "validated_signal",
  "ts": "2025-08-31T12:34:56Z",
  "key": "strategyA:12345",
  "source": "risk_manager",
  "version": 1,
  "data": {
    "original_signal": {
      "strategy_id": "strategyA",
      "instrument_token": 12345,
      "signal_type": "BUY",
      "quantity": 10,
      "price": 100.5,
      "timestamp": "2025-08-31T12:34:00Z"
    },
    "validated_quantity": 10,
    "validated_price": 100.5,
    "risk_checks": {"limit": true},
    "timestamp": "2025-08-31T12:34:56Z"
  }
}
```

Output: Order placed envelope on `zerodha.orders.submitted`

```json
{
  "id": "evt-...",
  "correlation_id": "corr-...",
  "trace_id": "trace-...",
  "broker": "zerodha",
  "type": "order_placed",
  "ts": "2025-08-31T12:34:56Z",
  "key": "strategyA:12345:2025-08-31T12:34:56Z",
  "source": "zerodha_trading",
  "version": 1,
  "data": {
    "order_id": "ord-...",
    "instrument_token": 12345,
    "signal_type": "BUY",
    "quantity": 10,
    "price": 100.5,
    "timestamp": "2025-08-31T12:34:56Z",
    "broker": "zerodha",
    "status": "PLACED",
    "strategy_id": "strategyA",
    "execution_mode": "zerodha"
  }
}
```

Output: PnL snapshot envelope on `zerodha.pnl.snapshots`

```json
{
  "id": "evt-...",
  "correlation_id": "corr-...",
  "trace_id": "trace-...",
  "broker": "zerodha",
  "type": "pnl_snapshot",
  "ts": "2025-08-31T12:34:56Z",
  "key": "portfolio_snapshot_zerodha:strategyA",
  "source": "zerodha_trading",
  "version": 1,
  "data": {
    "broker": "zerodha",
    "instrument_token": 12345,
    "realized_pnl": 0.0,
    "unrealized_pnl": 0.0,
    "total_pnl": 0.0,
    "timestamp": "2025-08-31T12:34:56Z"
  }
}
```
