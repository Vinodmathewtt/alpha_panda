# CRITICAL Improvements and Hardening Plan

This document consolidates the most important findings from the end‑to‑end review of Alpha Panda and prescribes concrete, phased fixes to harden correctness, reliability, observability, and operability. It is meant to be actionable and traceable to the codebase.

Audience: Tech leads, maintainers, contributors.


## 1) Executive Summary

- Architecture is sound: event‑driven unified log, multi‑broker isolation by topics, composition pattern for services, DI wiring, structured logging, and Redis‑backed pipeline metrics. No ground‑up redesign is required.
- Priority issues to fix now:
  - Schema mismatch in Strategy Runner constructing `MarketTick` with a `symbol` field that does not exist in `core/schemas/events.MarketTick`.
  - UUID/ID generation relies on a custom “uuid7” fallback that does not guarantee real v7 properties.
  - DLQ conventions are split (global vs “.dlq” per topic) — consolidate.
  - Inconsistent metrics namespacing causing fragmented dashboards.
  - Runtime compatibility risk with Python 3.13 + aiokafka; add checks/pins.
  - Two producer/consumer stacks increase drift; document or consolidate usage.
  - Topic configs are dev‑biased (RF=1), lacking prod overlays for partitions/replication/retention.
  - Schema evolution lacks a wire‑level registry (Avro/Protobuf) despite a Schema Registry port being exposed.

Conclusion: Evolve, don’t redesign. Address the above via the plan below.


## 1.1 Status At A Glance (End of Session)

- Implemented: MarketTick schema fix, centralized IDs, DLQ convention, metrics namespacing, Kafka runtime compatibility probe, Prometheus /metrics endpoint, topic overlays for bootstrap, Schema Registry scaffolding (Avro) with CI checks, Kafka topic existence health check.
- Pending (high‑value next):
  1) OpenTelemetry tracing: expand coverage and exporter configuration.

Deferred (revisit closer to production)
- Optional Avro runtime feature flag and rollout (keep runtime JSON; continue CI contract checks only).
- Production secrets enforcement (fail‑fast on defaults/empty; keep guidance for now).


## 1.2 Quick Validation Cheatsheet

- Start/Run
  - `make dev && make up && make bootstrap && make run`
  - Prometheus metrics: `curl http://localhost:8000/metrics`
- Schema Registry
  - `python scripts/register_schemas.py`
  - `python scripts/validate_schema_compatibility.py`
  - Env: `SCHEMA_REGISTRY_URL=http://localhost:8082` (dev) or `:8081` (CI)
- Topic Overlays
  - `export SETTINGS__ENVIRONMENT=production REDPANDA_BROKER_COUNT=3 TOPIC_PARTITIONS_MULTIPLIER=1.5 CREATE_DLQ_FOR_ALL=true && make bootstrap`
- Health Checks
  - Pre‑flight includes DB/Redis/Redpanda/Zerodha Auth/Broker Topics; runtime includes Kafka runtime compatibility.



## 2) Immediate Hotfixes (0–2 days)

1. Fix `MarketTick` schema mismatch
   - Symptom: `services/strategy_runner/service.py` instantiates `MarketTick(..., symbol=...)` but `core/schemas/events.MarketTick` has no `symbol` field.
   - Options:
     - A) Add `symbol: Optional[str]` to `MarketTick` in `core/schemas/events.py` (recommended; future‑proof and harmless).
     - B) Remove `symbol` argument at call site(s).
   - Action: Choose A, add the field, add a unit test, and run quick unit suite.
   - Status: COMPLETED
     - Change: Added `symbol: Optional[str]` to `MarketTick` in `core/schemas/events.py`.
     - Affected: `services/strategy_runner/service.py` calls now match schema.

2. Stabilize Event IDs
   - Replace `generate_uuid7()` fallback with a vetted ID generator:
     - Option A: real UUID v7 library (preferred) or
     - Option B: ULID for monotonic ordering properties.
   - Action: Introduce `core/utils/ids.py` with a single `generate_event_id()` and refactor envelope creation to use it. Add property‑based tests for monotonic ordering across a short time window.
   - Status: COMPLETED (initial implementation)
     - Change: Added `core/utils/ids.py` with `generate_event_id()`; attempts real uuid7 via optional deps, falls back to time‑prefixed UUID4.
     - Refactor: `EventEnvelope` now uses `generate_event_id()` for `id` and `trace_id`.
     - Refactor: `core/streaming/infrastructure/message_producer.py` uses `generate_event_id()` for new envelopes and correlation IDs.
     - Note: `generate_uuid7()` remains as a shim delegating to the new helper (backward compatibility).

3. Unify DLQ strategy
   - Settle on per‑topic `.dlq` topics (already used in error handler). Remove/avoid `TopicNames.DEAD_LETTER_QUEUE` global unless you need a catch‑all.
   - Action: Document the convention here and in `core/schemas/topics.py` and keep registry provisioning consistent. Ensure monitoring scrapes per‑topic DLQs.
   - Status: COMPLETED (documentation and code comment)
     - Change: Marked `TopicNames.DEAD_LETTER_QUEUE` as DEPRECATED in `core/schemas/topics.py` with guidance to prefer per‑topic `.dlq`.
     - Convention: `TopicNames.get_dlq_topic()` remains the standard helper (suffix approach).

4. Metrics namespacing consistency
   - Ensure `PipelineMetricsCollector` always records with an explicit broker namespace for multi‑broker stages. Avoid “shared” unless the metric is semantically shared (market feed count only).
   - Action: Audit all `PipelineMetricsCollector` instantiations and calls; standardize to pass broker context per event/stage.
   - Status: COMPLETED (code updates)
     - Changes:
       - `core/monitoring/pipeline_metrics.py`: Methods now accept optional `broker_context` to override instance namespace for per‑broker metrics.
       - Updated calls:
         - Strategy Runner: `record_signal_generated(..., broker_context=broker)`
         - Risk Manager: `record_signal_validated(..., broker_context=broker)`
         - Trading Engine: `record_order_processed(..., broker_context=broker)`
         - Portfolio Manager: `record_portfolio_update(..., broker_context=broker)`

5. Runtime compatibility gate
   - Add a startup health probe that asserts aiokafka compatibility with the current Python version and basic config readiness.
   - Action: Added a lightweight compatibility check in `ServiceHealthChecker`.
   - Status: COMPLETED (compatibility probe; connectivity checks remain via producer/consumer health checks)
     - Changes:
       - `core/health/health_checker.py`: New check `kafka_runtime_compatibility` validates aiokafka import/version vs Python version, and verifies `bootstrap_servers` is configured.


## 3) Architecture & Tech Stack Assessment (context)

- Strengths: Composition‑based service orchestration (`StreamServiceBuilder`), topic‑aware routing, explicit idempotent producers + manual commits, good DI boundaries, strong logging and pipeline metrics, fail‑fast checks in `app/main.py` and API `main.py`.
- Risks: ID monotonicity assumptions; mixed DLQ conventions; metrics namespace drift; prod topic configs; dual producer stacks; lack of wire‑level schema registry.


## 4) Detailed Issues and Recommended Fixes

### 4.1 Schemas and Contracts
- Issue: `MarketTick` mismatch with `symbol` usage.
  - Fix: Add `symbol: Optional[str]` to `MarketTick` (see Immediate Hotfixes).

- Issue: Event ID generation not truly UUID v7.
  - Fix: Introduce vetted UUID v7 or ULID; centralize in `core/utils/ids.py`; refactor `EventEnvelope`.

- Issue: No wire‑level schema enforcement across services.
  - Fix: Adopt Schema Registry with Avro or Protobuf for key event types (Envelope, MarketTick, TradingSignal, ValidatedSignal, Order events, PnL Snapshot). Add CI step to validate compatibility.

### 4.2 Streaming Reliability & Error Handling
- Issue: DLQ strategy split between global and “.dlq per topic”.
  - Fix: Standardize on topic‑suffix `.dlq`. Update docs and provisioning scripts to create DLQ topics with reasonable retention.

- Issue: Two producer/consumer stacks (`core/streaming/infrastructure` vs `core/streaming/clients.py`).
  - Fix: Prefer the infrastructure/Builder path for services. Keep `clients.py` only for direct, simple publishing use‑cases with explicit docs or deprecate after migration.

- Issue: Backoff and retry coverage is strong in ReliabilityLayer, but direct wrappers still have TODOs.
  - Fix: Route all service paths through the ReliabilityLayer (which you already do in main services).

### 4.3 Observability & Metrics
- Issue: Broker namespace inconsistencies in metrics
  - Fix: Make broker namespace explicit on every record; add a lint/test that asserts keys include broker context for multi‑broker stages.

- Issue: Limited tracing beyond correlation IDs.
  - Fix: Add OpenTelemetry tracing; wrap producers/consumers to create spans, propagate `trace_id`/`correlation_id` via headers, export to OTEL collector and Jaeger/Tempo.

### 4.4 Topic Provisioning & Capacity
- Issue: Dev partitions/replication in `TopicConfig` (RF=1, static partitions/retention).
  - Fix: Introduce environment overlays (dev/test/prod). For prod:
    - Replication factor >= 3
    - Partitions sized by throughput (market ticks > strategies > orders)
    - Explicit retention aligned with recovery/SLA
  - Add `scripts/bootstrap_topics.py` to honor overlays; verify via CI.

### 4.5 Security & Config
- Issue: Zerodha credentials required but not strictly enforced in config when enabled.
  - Fix: In `validate_startup_configuration`, if `zerodha.enabled=True` and creds blank, fail fast with clear remediation steps.

- Issue: Secrets in `.env` for dev; ensure prod never pulls from tracked files.
  - Fix: In prod mode, require env‑injected secrets; guard against default secret keys (already partially implemented). [Deferred until production hardening]

### 4.6 Performance
- Serialization: Consider `orjson` for faster JSON and `uvloop` for the API.
- Kafka producer tuning: Re‑evaluate `linger_ms`, `compression_type` per stage. For high‑frequency ticks, small linger and gzip may be acceptable; consider zstd if enabled.
- Redis metrics batching: Batch updates where it doesn’t hurt recency.
- Thread/async handoff in Market Feed: keep bounded queue; ensure reconnection paths do not leak callbacks; add soak tests.

### 4.7 Testing & CI/CD
- Contract tests: Add schema round‑trip tests against the registry.
- Topic routing tests: Validate for both brokers plus shared topics (market.*).
- Performance tests: Validate sustained throughput, consumer lag, backpressure limits.
- CI health‑gating: `docker compose ... wait`, then integration + E2E; cache wheels for speed.


## 5) Phased Roadmap

### Phase 1: Correctness & Stability (Week 1)
- Add `symbol` to `MarketTick` and tests; run unit suite.
- Introduce `core/utils/ids.py` with real UUID v7/ULID; refactor `EventEnvelope` and `MessageProducer` to use it.
- Standardize DLQ to per‑topic `.dlq`; update docs and `scripts/bootstrap_topics.py`.
- Enforce metrics broker namespace; quick lint/check script.
- Add runtime compatibility health check for Kafka client + Python version.

### Phase 2: Schema & Observability (Weeks 2–3)
- Define Avro/Protobuf schemas for Envelope + key payloads; add registry bootstrap.
- Add schema compatibility checks in CI; add contract tests.
- Integrate OpenTelemetry tracing; propagate `trace_id`/`correlation_id` via headers; export to Jaeger/Tempo.

### Phase 3: Productionization (Weeks 3–4)
- Topic overlays: partitions/retention/replication per environment (dev/test/prod). RF>=3 in prod.
- Performance tuning pass (orjson, uvloop, producer config, Redis batching).
- Harden Market Feed reconnect path (additional soak tests; ensure no callback leaks).
- Consolidate producer/consumer usage guidance; deprecate `clients.py` for services or document explicit scope.

### Phase 4: Safety Nets & Tooling (Week 5)
- DLQ replay tooling (manual gated) and dashboards.
- Consumer lag dashboard per broker/stage; alerts on thresholds.
- Disaster recovery runbook (retention, reprocessing, data audits).


## 6) Redesign vs Evolve Decision

- Decision: Evolve. The core architectural choices are modern and appropriate. Tactical fixes above remove sharp edges without churn.
- Rationale: Unified log with topic‑aware multi‑broker routing, composition builder, DI, and reliability layer already align with best practices for 2025 Python microservices. A rewrite would not materially improve outcomes relative to disciplined hardening.


## 7) Actionable Checklist (traceable)

- Schemas/Contracts
  - [x] Add `symbol` to `MarketTick` (core/schemas/events.py) and unit test
  - [x] Centralize ID generation; replace `generate_uuid7()` uses (shim retained)
  - [ ] Define Avro/Protobuf schemas for Envelope, MarketTick, TradingSignal, ValidatedSignal, Orders, PnL
  - [ ] Add schema registry bootstrap + CI compatibility check

- Reliability & DLQ
  - [x] Standardize `.dlq` suffix; remove/confine global DLQ constant (deprecated constant, helper retained)
  - [ ] Provision DLQ topics with retention; add monitoring of DLQ counts
  - [ ] Ensure all service consumers run through ReliabilityLayer

- Metrics & Observability
  - [x] Enforce broker namespace on all `PipelineMetricsCollector` calls
  - [x] Expose Prometheus `/metrics` endpoint in API (FastAPI)
  - [x] Add OTEL tracing scaffolding (feature‑flagged); propagate trace/correlation via Kafka headers; basic spans on produce/consume
  - [ ] Consumer lag dashboards (requires Kafka exporter) — pending
  - [x] Basic Grafana dashboard for stage health and rates (docs/observability/grafana)
  - [x] Wire PrometheusMetricsCollector to app state registry; instrument StrategyRunner, MarketFeed, RiskManager, TradingEngine

- Topics & Capacity
  - [ ] Create environment overlays for partitions/retention/RF
  - [x] Update `bootstrap_topics.py` to apply overlays; document expected throughput

- Security & Config
  - [ ] Fail on `zerodha.enabled=True` with empty creds; improve remediation logs
  - [ ] Deferred: Enforce secret sourcing in prod; forbid default secrets

- Performance
  - [x] Swap JSON serializer to `orjson` where safe; add `uvloop` for API
  - [x] Tune Kafka producer configs per stage (config-driven knobs; defaults unchanged)
  - [x] Batch Redis metric updates using pipelines to reduce round-trips

- Testing & CI/CD
  - [ ] Add contract tests vs schema registry
  - [ ] Add topic routing tests for both brokers + shared topics
  - [ ] Ensure CI health‑gates infra; run integration + E2E by profile

## 8) Next Session TODOs (Prioritized)

- Metrics (Prometheus)
  - Wire `core/monitoring/prometheus_metrics.py` collectors to the shared FastAPI registry and register counters/gauges in services where appropriate (signals, orders, pipeline health).
  - Provide a minimal Grafana dashboard JSON for quick insights.

- Tracing
  - Add OpenTelemetry SDK; wrap producer/consumer handlers to create spans and propagate `trace_id`/`correlation_id` via headers.
  - Export traces to local Jaeger/Tempo in dev and CI optional job.

- Topic Health Extensions
  - Extend BrokerTopicHealthCheck to assert partition count >= configured minimum and replication factor in production.
  - Print remediation suggestions (run bootstrap with overlays) when violated.

- Avro Rollout Plan — Deferred
  - Keep runtime JSON; do not add a runtime feature flag now.
  - Continue using Avro schemas + CI register/validate for contract checks.
  - Revisit runtime rollout when contracts stabilize and multi‑language consumers appear.

- Tests
  - Add contract tests that produce/consume with schemas for selected topics in a sandbox job.
  - Add topic routing unit tests to validate `TopicMap` and `TopicValidator` across brokers and shared topics.

## 12) Schema Registry Scaffolding (Avro) — IMPLEMENTED

Status: Initial scaffolding completed; runtime still JSON. The goal is to establish registry contracts and CI compatibility checks before switching serialization.

- Added Avro schemas (schemas/avro/):
  - event_envelope.avsc (envelope with JSON-encoded data field for flexibility)
  - market_tick.avsc, trading_signal.avsc, validated_signal.avsc, order_filled.avsc, pnl_snapshot.avsc
- Added registry scripts (scripts/):
  - register_schemas.py: Registers subjects ("<topic>-value") with Redpanda Schema Registry (default http://localhost:8082)
  - validate_schema_compatibility.py: Validates local schemas vs latest registry versions; sets global compatibility (default BACKWARD)
- CI guidance: Start registry (via docker-compose), run register then validate as part of infra job.

CI integration:
- GitHub Actions workflow updated to register and validate schemas during integration tests:
  - Uses `SCHEMA_REGISTRY_URL=http://localhost:8081` (matches Redpanda container flags)
  - Registers with `scripts/register_schemas.py`, then validates with `scripts/validate_schema_compatibility.py`

Next steps:
- Deferred: Runtime Avro enablement via feature flag; keep JSON at runtime and continue registry validation in CI only.

Change Log (Schema Registry)
- 2025-08-30
  - Added Avro schema files for core event types.
  - Added scripts to register and validate schemas against Redpanda Schema Registry.

## 13) Kafka Connectivity & Topic Health — IMPLEMENTED

- Implemented topic existence and capacity checks using Kafka Admin client:
  - `core/health/multi_broker_health_checks.py` checks required topics per broker via `list_topics()` and validates partitions and replication factor via `describe_topics()`.
  - Integrated into pre-flight health checks (DI container includes `BrokerTopicHealthCheck`).
- Behavior:
  - On admin client error, the check reports topics as missing or capacity unknown to ensure visibility and fail-fast behavior.
  - When capacity is below expectation, result includes remediation hints and example `make bootstrap` overlays.

## 10) Change Log (Metrics & Runtime Checks)

- 2025‑08‑30
  - Metrics namespacing: Extended `PipelineMetricsCollector` with `broker_context`; updated services to pass broker for per‑broker metrics.
  - Kafka runtime probe: Added `kafka_runtime_compatibility` health check in `ServiceHealthChecker` (aiokafka import/version vs Python, and bootstrap_servers sanity).
  - Prometheus: Added API `/metrics` endpoint using a shared registry; added `prometheus-client` dependency.
  - Prometheus service metrics: StrategyRunner, MarketFeed, RiskManager, TradingEngine emit baseline counters/gauges.
  - Grafana: Added basic dashboard JSON at `docs/observability/grafana/alpha_panda_prometheus_dashboard.json`.
  - Tracing: Added optional OpenTelemetry tracing (feature flag via settings); producer adds `traceparent` and IDs to headers; consumer creates spans and continues context.
  - Prometheus wiring: Shared `CollectorRegistry` provided via DI; `StrategyRunnerService` emits baseline counters (events processed + signals generated) and pipeline health gauges per broker.
  - Kafka producer tuning: Added config-driven per-service producer tuning via `Settings.producer_tuning`; StreamServiceBuilder passes overrides to `MessageProducer`.
  - Redis batching: `PipelineMetricsCollector` uses Redis pipelines for combined INCR + SETEX to reduce network round-trips.

## 11) Change Log (Topic Overlays)

- 2025‑08‑30
  - scripts/bootstrap_topics.py:
    - Added environment overlays using `Settings.environment`, `REDPANDA_BROKER_COUNT`, and `TOPIC_PARTITIONS_MULTIPLIER`.
    - Production defaults RF to >=3 (capped by broker count). Partitions scale by multiplier.
    - Optionally creates per-topic `.dlq` via `CREATE_DLQ_FOR_ALL` (default true).


## 9) Change Log (Quick Fixes Applied)

- 2025‑08‑30
  - MarketTick schema: Added `symbol: Optional[str]` in `core/schemas/events.py`.
  - Centralized IDs: Added `core/utils/ids.py` with `generate_event_id()`; updated `EventEnvelope` and `MessageProducer` to use it; kept `generate_uuid7()` as shim.
  - DLQ convention: Deprecated `TopicNames.DEAD_LETTER_QUEUE` in `core/schemas/topics.py`; reaffirmed per‑topic `.dlq` standard and `get_dlq_topic()` helper.


## 8) References (files to review/change)

- `services/strategy_runner/service.py` — MarketTick creation; remove `symbol` arg or add to schema
- `core/schemas/events.py` — Add `symbol` to `MarketTick`; refactor ID generation
- `core/utils/ids.py` (new) — Centralized event ID generation
- `core/streaming/error_handling.py` — DLQ `.dlq` behavior; leave as standard
- `core/schemas/topics.py` — Topic config overlays; DLQ docs; prod RF/partitions
- `core/monitoring/pipeline_metrics.py` — Broker namespace enforcement
- `app/main.py` / `core/health/*` — Add Kafka runtime compatibility health probe
- `scripts/bootstrap_topics.py` — Partitions/retention/RF overlays, DLQ topics
- `requirements*.txt` / `constraints.txt` — Ensure compatible versions (aiokafka/Python)


---

Status: living document; update as each checklist item completes with PR links and test evidence.
