# Paper Trading Service

## Overview
- Broker-scoped trading service for simulated execution (paper broker).
- Consumes `paper.signals.validated` and emits `paper.orders.filled` and `paper.pnl.snapshots`.

## Topics
- Input: `paper.signals.validated`
- Output:
  - `paper.orders.filled` (EventType.ORDER_FILLED)
  - `paper.pnl.snapshots` (EventType.PNL_SNAPSHOT)

## Consumer Group
- `alpha-panda.paper-trading.signals` (via container’s group-id prefix)

## DI Provider
- `paper_trading_service` (see `app/containers.py`)

## Metrics and Observability
- Prometheus counters: `trading_events_processed_total{service="paper_trading",broker="paper",event_type=...}`
- Last-activity gauge: `trading_last_activity_timestamp_unix{service="paper_trading",stage=...,broker="paper"}`
- Panels and alerts: see Grafana JSON in `docs/observability/grafana/` and Prometheus rules in `docs/observability/prometheus/`.

## Notes
- Execution is simulated: validated signals are converted to fills.
- Extend components under `components/` to introduce adapters and richer portfolio logic if required.

## Execution Simulation (Phase 1 Improvements)
- Slippage: configurable via `Settings.paper_trading.slippage_percent` (percent of price). BUY pays up, SELL receives less.
- Commission: configurable via `Settings.paper_trading.commission_percent` (percent of notional). Included in `OrderFilled.fees`.
- Latency: optional latency simulation using Gaussian(ms) with `Settings.paper_trading.latency_ms_mean` and `latency_ms_std`.
- Determinism: RNG seed based on `(strategy_id, instrument_token, timestamp)` ensures reproducible outcomes.

## Execution Simulation (Phase 2 Improvements)
- Partial fills: controlled by `Settings.paper_trading.partial_fill_prob` and `max_partials`; emits multiple `order_filled` events with same `order_id`.
- Order types: `metadata.order_type = market|limit`; for limit, `metadata.limit_price` is honored (side-aware crossing).
- Time-in-force: `metadata.tif = IOC|FOK|DAY`.
  - IOC: may partially fill immediately, cancel remainder (simulated).
  - FOK: fills only if fully fillable; otherwise emits `order_failed`.
- Idempotence: per-signal idempotency to avoid duplicate fills on retries.

## Portfolio & Risk (Phase 3)
- Positions: per strategy+instrument quantity and average price maintained in memory.
- PnL: unrealized PnL computed from last price and average price; realized PnL updated on SELL fills.
- Cash: per strategy cash balance from `Settings.paper_trading.starting_cash`; BUY reduces cash, SELL increases cash (fees applied on both).
- Constraints: no shorting (SELL limited to held quantity); insufficient cash results in `order_failed` (FOK rejects; IOC may partially fill).

## Design Notes & Future Enhancements

- This service is strictly simulated/virtual trading. No calls to live broker APIs.
- Safe to enrich with utility features without risk:
  - Slippage and commission models (configurable)
  - Latency/queueing simulation; partial fills and cancellations
  - Advanced order types (bracket/OCO simulation) for strategies to consume
  - Scenario replays and determinism (seed-based)
  - Stress tests for downstream portfolio and monitoring flows
- Keep event contracts stable (`OrderFilled`, `PnlSnapshot`) while enriching internals.

## Quick Start (Code)

```python
import asyncio
from app.containers import AppContainer

async def main():
    container = AppContainer()
    service = container.paper_trading_service()
    try:
        await service.start()
        # Service now consumes paper.signals.validated and emits orders/pnl
        await asyncio.Event().wait()  # keep running
    finally:
        await service.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Sample Events

Input: Validated signal envelope (from risk_manager) on `paper.signals.validated`

```json
{
  "id": "evt-...",
  "correlation_id": "corr-...",
  "trace_id": "trace-...",
  "broker": "paper",
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

Output: Order filled envelope on `paper.orders.filled`

```json
{
  "id": "evt-...",
  "correlation_id": "corr-...",
  "trace_id": "trace-...",
  "broker": "paper",
  "type": "order_filled",
  "ts": "2025-08-31T12:34:56Z",
  "key": "strategyA:12345:2025-08-31T12:34:56Z",
  "source": "paper_trading",
  "version": 1,
  "data": {
    "order_id": "ord-...",
    "instrument_token": 12345,
    "quantity": 10,
    "fill_price": 100.55,
    "timestamp": "2025-08-31T12:34:56Z",
    "broker": "paper",
    "side": "BUY",
    "strategy_id": "strategyA",
    "signal_type": "BUY",
    "execution_mode": "paper",
    "fees": 0.1
  }
}
```

Output: PnL snapshot envelope on `paper.pnl.snapshots`

```json
{
  "id": "evt-...",
  "correlation_id": "corr-...",
  "trace_id": "trace-...",
  "broker": "paper",
  "type": "pnl_snapshot",
  "ts": "2025-08-31T12:34:56Z",
  "key": "portfolio_snapshot_paper:strategyA",
  "source": "paper_trading",
  "version": 1,
  "data": {
    "broker": "paper",
    "instrument_token": 12345,
    "realized_pnl": 0.0,
    "unrealized_pnl": 0.0,
    "total_pnl": 0.0,
    "timestamp": "2025-08-31T12:34:56Z"
  }
}
```
