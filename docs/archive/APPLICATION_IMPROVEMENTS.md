# Application Improvements Plan

This document summarizes confirmed post‑refactor status and a focused set of actionable improvements, based on analysis of the logs in `logs/debug/` and the current codebase.

## Refactor Confirmation (Strategy Runner & Strategies)

- Composition‑only architecture is in place (`services/strategy_runner`, `strategies/*`). No legacy BaseStrategy paths are used.
- Strategy discovery and execution use `StrategyExecutor` + processor/validator composition. Instrument→strategy routing is O(1) via reverse index.
- Envelope/producer usage follows rules: only `market.ticks` defaults `event_type`; other topics pass explicit `event_type`.
- Risk Manager subscribes to broker‑scoped raw signals and emits per‑broker validated/rejected topics; Paper/Zerodha trading services subscribe only to their own `{broker}.signals.validated`.
- Logs that showed frequent ML feature‑shape errors were produced before the refactor. Mean‑reversion and momentum processors now return 4–5 features consistently; however, `ml_breakout` still emits 4 features. Some issues in the logs are therefore already resolved by the refactor; remaining work is captured below.

## Priority Improvements

### 1) ML Inference Robustness
- Feature shape validation: before `model.predict(...)`, compare feature length to `getattr(model, 'n_features_in_', None)` when available. If mismatch:
  - Option A: pad/truncate deterministically (documented),
  - Option B: skip signal with explicit error log + Prom counter (preferred for safety in prod).
- Align training vs inference features per strategy; document expected feature count in each strategy config.
- Remove duplicate model loading: currently `create_ml_*_processor` and `services/strategy_runner/factory.py` both call `load_model()`. Choose one (factory) and drop the other.

### 2) Observability for ML Strategies
- Prometheus error counters: when the strategy runner classifies ML errors (`ML_INFERENCE`, `ML_FEATURE_EXTRACTION`, `ML_GENERAL`), record via `PrometheusMetricsCollector.record_error(component='strategy_runner', error_type=..., broker=...)`.
- ML model metadata: extend `ModelLoader` to optionally expose model metadata (e.g., feature count, model version) and log on load success to aid troubleshooting.

### 3) Validator Alignment (Pipeline Monitor)
- Update the end‑to‑end validator to the composition architecture so ML inference/feature issues are not mis‑labeled as `risk_validation`/`order_execution`/`portfolio_updates` failures.
- Incorporate “startup grace window” and “no strategies for broker” rules to avoid false criticals (paper vs zerodha enablement, market‑closed idle).

### 4) Partitioning & Ordering Hygiene
- Use `PartitioningKeys` helpers for all emitted signals/orders everywhere (Risk Manager currently builds some keys manually).
- Re‑affirm per‑service consumer group names and keys are stable strings for consistent ordering.

### 5) Market Feed Throughput Tuning (Docs + Config)
- Document suggested producer tuning for `market_feed` under realistic loads; code already supports `settings.producer_tuning`:
  - Example defaults: `linger_ms=2–5`, `compression_type='zstd'`, optional `batch_size` sizing.
- Capture recommended `MARKET_FEED` queue size and optional `enqueue_block_timeout_ms` trade‑offs for dev vs perf profiles.

### 6) Preflight Enhancements (Non‑blocking in Dev)
- Optional ML readiness check: if `model.n_features_in_` is available, warn (dev) or block (prod) when the configured processor’s `extract_features` canonical length does not match.
- Emit a one‑page `preflight_summary.json` section for ML feature compatibility findings for quick triage.

### 7) DLQ Path Validation
- Add a lightweight integration test or script that intentionally routes a poison message to a `.dlq` topic to verify:
  - DLQ event format (contains `dlq_metadata`, `failure_info`, `original_message`),
  - Prom counter `trading_dlq_messages_total{service,broker}` increments,
  - Optional: examples/pattern replay tool can consume and replay.

### 8) Logging Volume Controls (Dev)
- For large `alpha_panda.log` in development, document use of `LOGGING__INFO_SAMPLING_RATIO` or set a lower console/file level for chatty modules. Keep JSON file logs for analysis; sample INFO where acceptable.

## Secondary Improvements

- Strategy confidence semantics: processors may return HOLD when confidence < threshold to reduce downstream work; strategy runner already normalizes confidence to 0.0–1.0.
- Per‑broker metrics namespace: continue passing explicit `broker_context` to `PipelineMetricsCollector` and `broker` label to Prometheus counters/gauges.
- Add service metrics endpoints consistency notes (API already exposes shared registry at `/metrics`).

## Documentation & Tests

- Document expected feature vectors for each ML strategy in `strategies/configs/*.yaml` and strategy READMEs.
- Unit tests: per‑strategy feature shape and invariants on synthetic histories; producer send error on missing `event_type` for non‑market topics; validator mapping to new stages.
- Integration tests: paper trading e2e (signal → validate → filled → pnl), and DLQ smoke as above.

## Non‑Goals (Out of Scope for Now)

- Changing runtime serialization from JSON to Avro (runtime remains JSON; schema registry is used for contract validation in CI).
- Removing `ACTIVE_BROKERS` entirely (planned once all fan‑out/subscription logic is fully localized).

## Quick Status

- Many log‑observed issues were produced before the refactor. Current code already addresses most architecture concerns (composition‑only runner, broker‑scoped services, envelope rules, metrics wiring). The primary remaining functional gap is ML feature‑shape guarding and de‑dup model load; both are straightforward, low‑risk improvements.

