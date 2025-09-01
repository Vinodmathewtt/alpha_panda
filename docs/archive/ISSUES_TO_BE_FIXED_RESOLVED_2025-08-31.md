# Alpha Panda — Consolidated Issues and Recommended Fixes

This document lists all current issues and inconsistencies identified during the end‑to‑end review, grouped by severity, along with concrete recommendations. It also proposes a focused overhaul of the test suite per the latest direction.

Last reviewed: 2025‑08‑31

## Summary

- Two production bugs were fixed immediately:
  - DI provider order bug in `app/containers.py` (Prometheus providers referenced before defined).
  - Schema inconsistency in `core/schemas/events.py` (`OrderFailed` missing `timestamp` and `broker`).
- Remaining issues are primarily enum/string mismatches in handlers, test/schema drift, minor metrics/monitoring consistency, and small correctness/maintainability gaps.

## Critical Issues (Status)

1) Enum/string mismatches in service handlers (breaks message processing) — DONE

- Problem: Consumers compare `message.get('type')` (string) to `EventType` enum objects, which never match.
- Impact: Handlers early‑return or take wrong branches; pipeline appears idle even when messages flow.
- Files/lines (indicative):
  - `services/risk_manager/service.py`: comparisons to `EventType.TRADING_SIGNAL`, `EventType.MARKET_TICK` via `message.get('type') == ...` and `!= ...`.
  - `services/trading_engine/service.py`: `if message.get('type') != EventType.VALIDATED_SIGNAL:`
  - `services/strategy_runner/service.py`: `if message.get('type') != EventType.MARKET_TICK:`
- Fix: Always compare to `.value` or coerce input to Enum.
  - Example: `if message.get('type') == EventType.TRADING_SIGNAL.value:`
  - Or: `if EventType(message['type']) == EventType.TRADING_SIGNAL:` (with try/except for safety).

2) Tests vs schema/enum mismatches (false failures, drift) — DONE (overhauled)

- Problems:
  - `MarketTick(volume=...)` used instead of `volume_traded`.
  - `OrderFilled(ts=...)` used instead of `timestamp`.
  - Assertions compare strings to Enums (e.g., `status == 'PLACED'`, `signal_type == 'BUY'`).
- Impact: Tests fail spuriously and encourage string‑literal usage.
- Fix: Update tests to use correct field names and compare Enums (or `.value` when asserting serialized output).
- Directional note: Given the request to replace most tests, see the “Test Overhaul” section.

3) Settings misuse in script (deprecated pattern) — DONE

- Problem: `scripts/test_monitoring.py` references `settings.broker_namespace`, which does not exist in Settings v2.
- Fix: Use `settings.active_brokers` (list) and pick a context (e.g., first broker or `'shared'` for market data), and align log messages accordingly.

## High Priority (Status)

4) Metrics registry parity for “signals_rejected” — DONE

- Problem: `PipelineMetricsCollector.record_signal_validated(..., passed=False)` increments a raw key `pipeline:signals_rejected:{ns}:count` that is not represented in `MetricsRegistry`.
- Fix: Add `signals_rejected_count(namespace)` and optionally `signals_rejected_last(namespace)` to `core/monitoring/metrics_registry.py`; switch the collector to use them.

5) Monitoring router DI consistency — DONE

- Problem: `api/routers/monitoring.py` instantiates `ServiceHealthChecker` directly instead of using the DI dependency (`get_health_checker`).
- Fix: Use the dependency to ensure consistent wiring (settings/redis/auth) and make it more testable.

6) Event type defaulting in `MessageProducer` — DONE

- Problem: If `event_type` is not provided and data is missing a clear `type`, producer defaults to `EventType.MARKET_TICK` and logs a warning.
- Resolution: For non‑market topics, the producer now raises if `event_type` is absent. It only defaults to `MARKET_TICK` for market tick topics.

## Medium Priority (Status)

7) Market feed processing rate computation — DONE

- Problem: `_calculate_processing_rate()` references `_start_time` which is not set; rate always returns 0.0.
- Fix: Set `self._start_time = datetime.now(timezone.utc)` in `start()` and compute elapsed using it.

8) Enum clarity in order events — DONE
  - Using `OrderStatus.PLACED` in Zerodha trader: DONE
  - Introduced type safety for `OrderFilled.side` by reusing `SignalType` (enum) instead of a free string.

- Observations:
  - `ZerodhaTrader` passes `status="PLACED"` where schema expects `OrderStatus` — Pydantic coerces but explicit `OrderStatus.PLACED` improves clarity.
  - `OrderFilled.side` is plain string; consider a `Side` enum or reuse `SignalType` to prevent typos.
- Fix: Prefer Enums in code and tests; optionally add `Side` enum for type safety.

9) Pydantic v2 model config style — DONE
  - `AlphaPandaBaseModel` uses `model_config` (Pydantic v2)
  - Settings validators migrated to `@field_validator`

- Problem: `AlphaPandaBaseModel` uses v1‑style inner `Config` for JSON encoders.
- Fix: Consider switching to v2 `model_config` (via `ConfigDict`) for clarity and forward compatibility; serialization is already covered by custom producer serializer.

## Low Priority (Status)

10) Documentation cleanup for deprecated namespace — DONE (docs only)

- Problem: Some READMEs/examples mention `BROKER_NAMESPACE` (marked as legacy); runtime code has moved to `active_brokers` correctly.
- Fix: Verified repo-wide references and clarified deprecation everywhere it appears. README shows explicit migration to `ACTIVE_BROKERS`; app/README uses a legacy block explicitly stating removal; implementation guide reiterates the distinction. No active examples/docs encourage using `BROKER_NAMESPACE`.

11) Minor consistency/logging — DONE

- Changes:
  - Monitoring API now uses DI for `PipelineMetricsCollector` instead of ad‑hoc instantiation.
  - Market Feed metrics now distinguish `ticks_received` from `ticks_processed`.

## Already Fixed in This Pass

- DI provider order bug in `app/containers.py`: Prometheus providers are now defined before use by service providers.
- `OrderFailed` schema now includes `timestamp` and `broker` to match producers and logging/audit requirements.

## Proposed Fix Plan (Updated)

1) Service enum handling — DONE

2) Script settings correction — DONE

3) Metrics registry parity — DONE

4) Market feed processing rate — DONE

5) Enum clarity — PARTIAL (status updated above)

6) (Optional) Pydantic v2 config modernization — DONE
7) Docs cleanup for `BROKER_NAMESPACE` — DONE

## Test Overhaul Strategy (Replace Most Existing Tests) — DONE (Phase 1)

Per direction, favor a pragmatic, coverage‑effective rewrite over maintaining drifted tests.

Removed legacy tests that relied on outdated fields or string enums, and heavy infra coupling. Added focused unit tests:

- `tests/unit/test_event_schemas_v2.py` — event envelopes and order/signal schemas (enums and fields)
- `tests/unit/test_metrics_registry_v2.py` — validates new signals_rejected keys
- `tests/unit/test_market_tick_formatter.py` — validates MarketTick formatting

Next test additions (optional, Phase 2):
- Reliability/DLQ path unit test using fakes to validate DLQ event shape and Prometheus DLQ counter
- Topic validator edge cases

What to add (targeted and valuable):

1) Unit tests

- Schemas: Validate `EventEnvelope` required fields, enum serialization, and child event creation.
- Topic routing: `TopicMap` mapping and `get_broker_from_topic` with edge cases (shared topics, unknown prefixes).
- Utilities: `generate_event_id()` monotonicity and uniqueness across a short window (property‑based/quickcheck style if feasible).

2) Service unit/integration (with fakes)

- Reliability layer: Dedup, error classification, DLQ emission (ensure `data=dlq_event`, `.dlq` topics, and Prometheus DLQ counter updates via the callback).
- Stream builder: Ensure producer/consumer orchestration wires topic‑aware handlers, including broker extraction.

3) Integration tests (infra‑gated, behind `make test-setup`)

- Envelope round‑trip: Produce enveloped events with Decimals/timestamps and verify consumer side JSON decoding is faithful.
- Multi‑broker routing: Signals/validated/orders on `paper.*` and `zerodha.*` topics route to the correct handlers.
- Metrics: Pipeline Redis keys update as expected with explicit `broker_context`.

4) API tests

- `/metrics` exposes Prometheus registry; `/api/v1/monitoring/*` works with DI health checker; CORS policy enforced in production config.

5) Performance smoke (optional)

- Minimal load to verify no obvious regressions in producer/consumer send/receive with idempotent producers and manual commits.

Test authoring guidelines:

- Prefer asserting on Enums or on serialized `.value` explicitly.
- Prefer enveloped messages for service consumer tests.
- Keep infra‑gated tests optional and tagged; unit tests must not require external services.

## Validation Checklist After Fixes (Live)

- Handlers process messages when `type` is a string — OK
- New metrics keys exist in `MetricsRegistry` and are populated — OK
- Market feed reports a non‑zero processing rate after activity — OK
- No references to `broker_namespace` remain in runtime code/scripts — OK (scripts updated)
- API `/metrics` scrapes successfully and DLQ counters increment on DLQ publishes — TO VERIFY in integration

## Notes

- DLQ convention: Continue using per‑topic `.dlq` suffix; avoid `TopicNames.DEAD_LETTER_QUEUE` for new paths.
- Multi‑broker routing: Keep deriving broker from topic; never use wildcard grouping for functional logic.
