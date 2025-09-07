# Paper Trading Improvements

This document outlines pragmatic, high‑value enhancements to the paper trading module to increase realism, utility, and observability without overengineering.

## Execution Realism
- Slippage model: configurable bps per instrument/liquidity profile; support fixed and volatility‑scaled slippage. Apply at fill time and expose slippage in metadata.
- Commission/fees: exchange/broker schedule; percent or per‑order/lot flat. Include in realized PnL.
- Latency simulation: add fixed and jitter components; optionally draw from a distribution; surface `paper_fill_latency_seconds` metric.
- Partial fills: split validated quantity into multiple fills based on simulated book depth; emit multiple `orders.filled` with cumulative quantity.
- Order types/TIF: support market, limit, stop, stop‑limit; IOC/FOK/GTD semantics; for limits, simulate queue priority by price distance.
- Bracket/OCO: simulate protective stop and take‑profit creation on primary fill; enforce OCO cancellation on opposing fill.

## Portfolio & Risk Accounting
- Position accounting: maintain average price; realized/unrealized and day PnL; enforce cash balance and margin/leverage rules.
- Corporate actions (optional): handle splits/dividends for extended runs; provide no‑op defaults unless enabled.
- Idempotence: deduplicate validated signals on `(strategy_id, instrument_token, timestamp)` to avoid double fills on retries.

## Determinism & Replays
- Deterministic seeds: configurable RNG for slippage/latency/partial‑fill draws to make results reproducible.
- Scenario/backtest replays: consume historical ticks from a topic or file, advance simulated clock, and run paper trading end‑to‑end.

## Observability
- Metrics: 
  - `paper_orders_total{status}` counts (placed/filled/rejected).
  - `paper_fill_latency_seconds` histogram (p95/p99 tracking).
  - `paper_slippage_bps` histogram and per‑strategy gauges.
  - `paper_trading_last_activity_timestamp_unix{stage}` gauges for liveness.
- DLQ hygiene: route malformed validated signals to per‑topic `.dlq` and tag `dlq=true`.
- Structured logs: annotate fills with `execution_mode=paper`, slippage_bps, fees, and decision rationale.

## Configuration & Safety
- Config surface (env): `PAPER__SLIPPAGE_BPS`, `PAPER__COMMISSION_BPS`, `PAPER__LATENCY_MS_{MEAN,STD}`, `PAPER__PARTIAL_FILL_PROB`, `PAPER__MAX_PARTIALS`.
- Guardrails: configurable min/max allowed quantity, price sanity checks, and instrument allowlists.

## Testing
- Unit tests: deterministic slippage/latency with seeded RNG; partial‑fill aggregation; limit/stop price crossing behavior.
- Integration tests: end‑to‑end from `paper.signals.validated` to `paper.orders.*` with timing assertions and metrics presence.

## Minimal Roadmap (Phased)
1) Add metrics + deterministic RNG hooks; basic slippage/commission; latency knob.
2) Partial fills + order types/TIF; idempotence.
3) Bracket/OCO; portfolio cash/margin; scenario replays.

