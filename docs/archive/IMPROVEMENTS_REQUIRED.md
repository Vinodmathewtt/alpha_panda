# Improvements Required (Archived)

This document captures a focused, end‑to‑end review of the application based on the current codebase and recent logs. It lists confirmed issues, gaps, and recommended actions to stabilize and improve the upgraded ML strategy module, multi‑broker operation, observability, and overall runtime correctness.

## Summary (High Priority Items)
- ML strategies are not registering because model artifacts are missing/misnamed; configs and runtime validation contradict “degraded mode” messages.
- Validator produces repeated Zerodha warnings despite no strategies targeting Zerodha; gating and Redis key usage need refinement.
- Trading service lifecycle logs are inconsistent; ensure startup gating and lifecycle visibility are aligned to effective flags.
- Multi‑channel logs mostly empty; verify channel routing, handlers, and queue logging wiring.
- Health checks claim “active strategies” based on DB rows, not the actually loaded/ready set.

- Kafka/runtime checks missing in health: add aiokafka/Python compat + bootstrap sanity and log consumer group/partition assignments.
- Market feed latency histograms: ensure enqueue/emit metrics are recorded and buckets are tuned via settings.

## 1) ML Strategy Module

Status: COMPLETED (Phase 1)

Changes implemented:
- Updated YAML configs to point to an existing sample artifact:
  - `strategies/configs/ml_momentum.yaml`: `model_path` -> `models/sample_momentum_v1.joblib`.
  - `strategies/configs/ml_mean_reversion.yaml`: `model_path` -> `models/sample_momentum_v1.joblib`.
  - `strategies/configs/ml_breakout.yaml`: `model_path` -> `models/sample_momentum_v1.joblib`.
- Rationale: Unblocks StrategyRunner registration in development without training new models.
- Follow-ups: Replace with real per-strategy models when available.
- Issue: Model artifacts missing or misnamed
  - Errors show attempts to load `strategies/models/momentum_v1.joblib`, `mean_reversion_v1.joblib`, and `breakout_v1.joblib` while only `sample_momentum_v1.joblib` exists.
  - Configs reference non‑existent filenames:
    - `strategies/configs/ml_momentum.yaml -> models/momentum_v1.joblib`
    - `strategies/configs/ml_mean_reversion.yaml -> models/mean_reversion_v1.joblib`
    - `strategies/configs/ml_breakout.yaml -> models/breakout_v1.joblib`

- Impact: StrategyRunner skips registration when model is not loaded; end‑to‑end pipeline has zero signal generation.

- Recommended actions:
  - Align artifacts and configs:
    - DONE (dev): Updated YAMLs to point to the existing sample model file to restore registration for smoke tests.
    - Pending (prod): Train and save per-strategy models with proper filenames; update YAMLs accordingly.
  - Clarify degraded mode semantics:
    - DECIDED: “Disabled” degraded mode. StrategyRunner skips registration when model is missing.
    - Implemented: Updated all ML strategy processors to log “strategy disabled (no registration)” rather than “degraded mode”.
  - Preflight validation:
    - DONE: Added `MLModelsPreflightCheck` that scans active strategies’ `model_path`s at startup.
      - Production: fails preflight on missing artifacts.
      - Development/Testing: warn-only pass with detailed missing list.
    - Added preflight summary JSON written to `logs/preflight_summary.json` with per-check status and policy.
  - Developer ergonomics:
    - Add a simple script `scripts/create_sample_ml_model.py` (already present) to generate tiny compatible models for smoke.
    - Add unit tests for `ModelLoader` path normalization (supports both `models/foo.joblib` and `strategies/models/foo.joblib`).

## 2) Strategy Runner (Composition + ML)
- Issue: Registration vs health mismatch
  - Health check reports “Found N active strategies” from DB, but StrategyRunner may skip all ML strategies due to model validation failures.
- Impact: Monitoring and operators believe the system is ready when it is not; validator later flags pipeline warnings.
- Recommended actions:
  - Post‑registration summary: after `_load_strategies()`, log a structured “Strategy Loading Summary” and emit a metric indicating the number of registered/ready strategies per broker. This is already partially implemented; ensure it always runs and is visible.
  - Record per‑broker counts in Redis via `PipelineMetricsCollector.set_strategy_count(broker, count)` (already present). Add verification logs on startup and when counts change.
  - Emit a clear, single WARN on skipped strategies with reasons (missing model, bad parameters, etc.).
  - DONE: Added Prometheus counters: `ml_model_load_success_total{strategy_id}`, `ml_model_load_failure_total{strategy_id}` and wired increments in `StrategyRunnerService._load_strategies()`.

## 3) Validator & Monitoring
- Issue: Persistent `redis_connectivity_error` warnings for Zerodha signal_generation in logs while Redis health check passes.
- Likely causes:
  - Redis get/parse exceptions (e.g., JSON or decode handling) cause the catch‑all except block to mark the stage as `redis_connectivity_error`.
  - Gating not applied when no strategies target a broker during market hours.
- Recommended actions:
  - Gating first: before reporting signal_generation warnings, check if `strategies_count(broker) == 0` (already implemented in `PipelineValidator._validate_signal_generation`). Ensure StrategyRunner always sets per‑broker counts on startup; re‑verify key names match `MetricsRegistry`.
  - Exception hygiene: narrow exception handling in validator to decode/parse separately, and report `no_recent_data` instead of `redis_connectivity_error` when Redis is healthy but keys are absent or unparsable.
  - Add a validator log for the computed `active_strategies` per broker to explain suppression.
  - Prometheus: add counters for validator warnings by stage and broker to track drift.

Status: COMPLETED (Phase 5)

Changes implemented:
- Robust Redis decoding and timestamp parsing helpers added in `PipelineValidator`.
- Clear issue types returned instead of generic `redis_connectivity_error`:
  - `redis_unavailable` for Redis operation failures
  - `metrics_parse_error` for decode/JSON/timestamp parsing issues
  - `validation_error` for unexpected internal errors
- Applied across market data, signals, risk, orders, and portfolio validators.
- Added Prometheus counter: `validator_warnings_total{stage,broker,issue}` (increments on warnings like high latency/no signals).

## 4) Trading Service Lifecycle (Paper/Zerodha)
- Issue: Lifecycle logs inconsistent; shutdown shows `ZerodhaTrading stopped` without a visible `starting` log in the sample.
- Recommended actions:
  - Startup gating:
    - Confirm `app/main.py` gating runs before service start: only start `PaperTradingService` when `TRADING__PAPER__ENABLED == true` and `paper` is in `ACTIVE_BROKERS`; only start `ZerodhaTradingService` when `TRADING__ZERODHA__ENABLED == true` and `zerodha` is in `ACTIVE_BROKERS`.
    - Log a single “Skipping <service> (disabled by flags or broker not active)” for clarity.
  - Lifecycle logs: ensure both trading services log `Starting…` and `Started…` (post orchestrator start) so dashboards can correlate.
  - Prometheus: set `trading_last_activity_timestamp_unix{service,stage,broker}` on service start to avoid empty panels.

## 5) Topic Routing & Isolation
- Strategy Runner emits to `{broker}.signals.raw`; Risk Manager consumes `{broker}.signals.raw` and emits `{broker}.signals.validated`; trading services consume only `{broker}.signals.validated`.
- Actions:
  - Verify all services use `TopicMap(broker)` helpers (they do) and `PartitioningKeys` for ordering.
  - Ensure unique consumer groups per service and per topic role (present in code).
  - Add early checks for `TopicValidator.validate_broker_topic_pair(topic, broker)` where applicable (already in StrategyRunner emission).

## 6) Event Envelope & Producer Rules
- The producer correctly requires `event_type` for non‑market topics and defaults to `market_tick` only for `market.*.ticks`.
- Actions:
  - Audit all producer calls for explicit `event_type` (StrategyRunner, Risk Manager, Trading services comply).
  - Ensure `broker` is always provided to `MessageProducer.send()` (complies).
  - Consider adding a static lint/test that fails pushes if any producer call omits `event_type` for non‑market topics.

## 7) Logging & Observability
- Issue: Channel files (`trading.log`, `market_data.log`, `api.log`, etc.) are empty while `alpha_panda.log` and `error.log` collect entries.
- Hypotheses:
  - ChannelFilter requires the `channel` attribute; some logs may be using non‑channel loggers.
  - QueueHandler/QueueListener wiring may replace root handlers and miss channel handlers if not attached to component loggers.
- Actions:
  - Verify that all service loggers use channel‑aware helpers (`get_trading_logger_safe`, `get_market_data_logger_safe`, etc.) — they mostly do; sweep remaining modules.
  - At `configure_enhanced_logging`, log a one‑time summary of channel handlers attached and their target files to `alpha_panda.log` for quick diagnostics.
  - Add a smoke test that writes one INFO per channel and asserts non‑zero file size for each configured channel file under `logs/`.
    - Implementation details: write a tiny test or script that obtains each channel logger via `core.logging.enhanced_logging` helpers (`get_trading_logger`, `get_market_data_logger`, `get_api_logger`, `get_error_logger`, etc.), emits one `INFO` per channel, flushes handlers (or sleeps briefly), and asserts each of `logs/trading.log`, `logs/market_data.log`, `logs/api.log`, `logs/error.log`, `logs/application.log`, `logs/monitoring.log`, `logs/performance.log`, `logs/audit.log` are > 0 bytes.
    - This catches ChannelFilter miswiring and QueueListener routing regressions immediately.
  - Ensure API/uvicorn/fastapi are routed to `api.log` with `propagate=False` (code already sets this; verify with the smoke test).

## 8) Health Checks & Startup Sequence
- Improve accuracy of “Strategy Config” health:
  - Add a follow‑up health record “Strategy Runtime” that reflects registered/ready strategies count per broker (sources: StrategyRunner summary and Redis keys).
- Fail‑fast in production for missing model files or required topic mismatches; allow warnings in development.

- Preflight system evolution (highlight):
  - Consolidate and expand preflight checks in `app/pre_flight_checks.py` to be the authoritative startup gate for infra, auth, model readiness, and routing/observability sanity.
  - Add a single preflight summary log with per‑check status, and a machine‑readable artifact (JSON) to `logs/` for audit.
  - Define blocking policy by environment: production blocks on critical failures; development warns where safe.

Action items (preflight):
- Implement ML models preflight and Kafka runtime compatibility checks in `app/pre_flight_checks.py` and wire providers in `app/containers.py`.
- Write a one‑shot preflight summary JSON to `logs/preflight_summary.json` (include per‑check status, durations, failure reasons, and environment policy applied).
- Expand README Quick Start with a “Preflight fails: common causes and fixes” mini‑guide (auth credentials, missing model artifacts, missing topics, Redis/Kafka not running, invalid bootstrap strings, file permissions on logs/).

## 9) Metrics & Tracing
- Add ML‑specific Prometheus metrics:
  - Counters: `ml_model_load_success_total`, `ml_model_load_failure_total`, `ml_inference_total`.
  - Histogram: `ml_inference_latency_seconds{strategy}`.
- Ensure `broker_context` is always passed to `PipelineMetricsCollector` for multi‑broker services to prevent key collisions (most paths do this; sweep for consistency).
- Add span attributes for strategy ID and instrument in critical spans (`strategy.process_tick`, `strategy.emit_signal`) — already present; ensure consistent usage.

- Market feed latency histograms:
  - Verify MarketFeed publishes Prometheus histograms `market_tick_enqueue_delay_seconds` and `market_tick_emit_latency_seconds` (documented in repo guidelines) and that bucket overrides via `MonitoringSettings.prometheus_buckets` are honored.
  - If not currently instrumented, add timing around the queue enqueue path (callback → queue) and producer send (queue → Kafka) with the two histogram names above.

- Kafka/runtime health:
  - Add a health check for `kafka_runtime_compatibility` that validates aiokafka version vs Python and presence of `bootstrap_servers` before starting producers/consumers; log effective consumer `group_id`s and assigned partitions per service at startup.
  - Optionally document enabling a consumer-lag exporter in non‑dev deployments and add a note in the main README for turning on the exporter.

## 10) DLQ & Reliability
- Per‑topic `.dlq` suffix is standardized; `StreamServiceBuilder` wires DLQ to Prometheus via `record_dlq_message()`.
- Actions:
  - DONE: Added unit test that triggers DLQ and asserts `.dlq` topic publish and Prometheus `trading_dlq_messages_total` counter increment; verifies `dlq=true` log tag.

## 11) Documentation & Examples Hygiene
- Remove lingering references to deprecated `BROKER_NAMESPACE` and `ZERODHA__ENABLED` outside archived docs (keep historical docs untouched under `docs/archive/`).
- Update `strategies/README.md` and `strategies/models/README.md` with clear guidance on model filenames and where to place them.
- Document degraded‑mode policy for ML strategies and how StrategyRunner treats them.

- Model metadata and auditability:
  - Extend strategy parameters and logs to include `model_name`, `model_version`, and a `feature_schema_hash` for each ML strategy. Bind these into signal metadata for audit and reproducible replays.
  - Consider writing a small `models/<name>.json` sidecar with metadata (created_on, trainer_version, feature_schema_hash) next to each `.joblib` and load/bind it via `ModelLoader`.

## 12) Testing Improvements
- Unit tests:
  - `ModelLoader` path normalization and error handling.
  - Strategy processor contracts: confirm presence of `load_model`, `extract_features`, `predict_signal`.
  - Producer enforcement of `event_type` for non‑market topics (static lint/test).
- Integration tests:
  - End‑to‑end smoke with sample ML models to exercise the full pipeline (ticks → signals → validated → orders → PnL).
  - Validator gating with no strategies targeting a broker (suppression of warnings).
  - Channel logging smoke test.

## Quick Fix Checklist (Suggested Order)
1) Fix ML model paths: add/rename artifacts or update YAMLs. — DONE
2) Decide degraded‑mode semantics and align StrategyRunner registration logic and processor logs. — DONE (Disabled mode)
3) Harden validator: suppress when zero strategies for a broker; narrow exception handling; avoid mislabeling as `redis_connectivity_error`. — DONE
4) Verify trading service gating logs and start conditions; add explicit “skipping” logs. — DONE
5) Validate channel logging via a smoke test; attach missing channel handlers if any. — DONE
6) Add ML metrics and StrategyRunner post‑registration summary to health/monitoring. — DONE (counters added; summary present)
7) Add Kafka/runtime compatibility health check and log consumer group/partition assignments. — DONE (compat check present; partitions logging added)
8) Ensure MarketFeed records enqueue/emit latency histograms and expose bucket overrides via settings. — DONE

Status: COMPLETED — All planned improvements implemented or documented with tests and dashboards.

## Code Pointers
- ML loading and factories: `strategies/ml_utils/model_loader.py`, `strategies/implementations/ml_*.py`, `strategies/core/factory.py`.
- Strategy runner (registration, emit): `services/strategy_runner/service.py`, `services/strategy_runner/factory.py`.
- Validator/monitor: `core/monitoring/pipeline_validator.py`, `core/monitoring/pipeline_monitor.py`, `core/monitoring/pipeline_metrics.py`, `core/monitoring/metrics_registry.py`.
- Topics/producer: `core/schemas/topics.py`, `core/streaming/infrastructure/message_producer.py`.
- Logging: `core/logging/enhanced_logging.py`, `core/logging/channels.py`, `core/logging/__init__.py`.
- Gating and DI: `app/main.py`, `app/containers.py`, `core/config/settings.py`.
