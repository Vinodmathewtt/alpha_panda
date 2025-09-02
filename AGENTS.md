# Repository Guidelines

## Project Structure & Module Organization
- `api/`: FastAPI app (`main.py`, routers, middleware, schemas). See `api/README.md`.
- `core/`: Domain models, schemas, streaming patterns, utils. See `core/README.md`.
- `services/`: Stream processors (Kafka/Redis/DB), topic‑aware handlers. See `services/README.md`.
- `strategies/`: Pure strategy logic (no infra access). See `strategies/README.md`.
- `app/`: DI container and app wiring. See `app/README.md`.
- `tests/`: Unit, integration, e2e, performance (`unit`, `integration`, `e2e`, `performance`, `chaos`). See `docs/testing/INFRASTRUCTURE_INTEGRATION_TESTING_POLICY.md`.
- `scripts/`: Ops/testing helpers (e.g., `scripts/test-infrastructure.sh`).
- `migrations/`, `docs/`, `examples/`, `dashboard/`, `config/` as named. See `examples/README.md`.

## Architecture Overview
- **Unified Log**: Redpanda is the source of truth; aiokafka clients. See `docs/architecture/MULTI_BROKER_ARCHITECTURE.md`.
- **Hybrid Multi‑Broker (Emphasis)**: A single deployment handles multiple brokers (typically `paper` and `zerodha`) with hard isolation via broker‑prefixed topics and Redis key prefixes. Strategies fan‑out signals to all configured brokers; trading engines execute per broker; portfolio managers maintain isolated portfolios per broker. One consumer group per service processes all broker topics.
- **Topic Naming**: `{broker}.{domain}.{event_type}[.dlq]` (e.g., `paper.signals.validated`).
- **Event Envelope**: All messages use `EventEnvelope` (id, type, ts, key, source, version, data). Details: `core/schemas/README.md`.
- **Namespace Note**: `BROKER_NAMESPACE` env is removed; `broker_namespace` remains only for metrics namespacing/compat and should not drive routing.
  - Forward plan: any architecture that relies on a central `broker_namespace` to steer behavior is transitional and should be refactored to explicit per‑broker topic routing and context.
- **Market Data**: Single Zerodha feed publishes `market.ticks` for all brokers.

## Recent Improvements
- Trading flags: unified on `TRADING__PAPER__ENABLED` and `TRADING__ZERODHA__ENABLED`; legacy `PAPER_TRADING__ENABLED` removed from runtime gating.
- Validator: market‑closed becomes `idle`, order/portfolio checks are skipped for disabled brokers, and no‑signal messages are suppressed when no strategies target a broker.
- Market feed performance: configurable queue (`MARKET_FEED__QUEUE_MAXSIZE`, `MARKET_FEED__ENQUEUE_BLOCK_TIMEOUT_MS`), subscription batching (`MARKET_FEED__SUBSCRIPTION_BATCH_SIZE`).
- New Prometheus histograms: `market_tick_enqueue_delay_seconds` and `market_tick_emit_latency_seconds`; optional bucket tuning via `MONITORING__PROMETHEUS_BUCKETS__*`.
- Logging: access logs include route templates; optional INFO sampling via `LOGGING__INFO_SAMPLING_RATIO` for API channel.
- DLQ logs now include `dlq=true` for consistent tagging.

### Service Enablement Flags (Updated)
- **Trading service flags**:
  - `TRADING__PAPER__ENABLED` (bool): controls only the paper trading service lifecycle.
  - `TRADING__ZERODHA__ENABLED` (bool): controls only the Zerodha trading service lifecycle (order placement path).
- **Zerodha auth & market feed**: Always required/started; do NOT gate these with a flag.
  - The legacy `ZERODHA__ENABLED` variable is deprecated and should not control runtime behavior.
- **ACTIVE_BROKERS (Transition)**: Remains in `.env` for now and is used by multi‑broker services (strategy runner, risk manager) to determine broker fan‑out/subscriptions. Plan to remove after refactoring those services to rely purely on per‑service enablement and explicit topic routing.

#### Multi‑Broker Operation and Defaults
- The system remains multi‑broker: when both trading flags are enabled, it trades with both brokers concurrently with strict topic isolation.
- Default posture: if both trading flags are missing (unset), the effective behavior defaults to `TRADING__PAPER__ENABLED=true` and `TRADING__ZERODHA__ENABLED=false` for safety.
- Explicit false wins: if a trading flag is explicitly set to `false`, do not override via defaults/legacy. If both are explicitly false, no trading services start (auth/feed still run) and a startup warning is logged.
- Legacy `PAPER_TRADING__ENABLED` has been removed from runtime gating; use `TRADING__PAPER__ENABLED` exclusively.

### Recent Architecture/Operational Updates
- **Event IDs**: Centralized ID generation via `core/utils/ids.py` (`generate_event_id()`). Legacy `generate_uuid7()` now delegates to this helper.
- **DLQ Convention**: Standardize on per-topic `.dlq` suffix (e.g., `paper.orders.filled.dlq`). `TopicNames.DEAD_LETTER_QUEUE` is deprecated for new uses.
- **Metrics Namespacing**: When recording pipeline metrics, always pass an explicit `broker_context` for multi-broker services to avoid key collisions.
- **Kafka Runtime Gate**: Health checker includes `kafka_runtime_compatibility` (verifies `aiokafka` vs Python version and `bootstrap_servers` presence).
- **MarketTick Schema**: `core/schemas/events.MarketTick` includes optional `symbol` to match usage in Strategy Runner.
 - **Producer Envelope Rules**: `MessageProducer.send()` auto-wraps payloads into `EventEnvelope`. It only defaults `type=market_tick` when sending to `market.ticks` (shared); for all other topics an explicit `event_type` is required.
 - **DLQ Metrics Hook**: StreamServiceBuilder wires DLQ publisher callbacks to Prometheus via `PrometheusMetricsCollector.record_dlq_message(service, broker)`.
 - **Shared Prometheus Registry**: API exposes `/metrics` using a shared registry from the DI container so service collectors can register to a common scrape endpoint.
 - **Service Gating (Planned Rollout)**: DI will always start auth/market feed; trading services start based on `TRADING__{BROKER}__ENABLED` in conjunction with `ACTIVE_BROKERS` during transition. Validator will skip order‑stage warnings for disabled trading services and respect market‑hours “idle” state.

### Transition Plan (Towards per‑service flags)
- Phase 1: Add `TRADING__PAPER__ENABLED` and `TRADING__ZERODHA__ENABLED`. Keep `ACTIVE_BROKERS` and gate trading services by (flag && broker in ACTIVE_BROKERS). Auth/market feed always on. Log effective config and sources at startup.
- Phase 2: Gradually refactor services that rely on `ACTIVE_BROKERS` for fan‑out/subscriptions to use local enablement + explicit topic routing.
- Phase 3: Gradually remove `ACTIVE_BROKERS` from runtime and `.env` after refactoring multi-broker services (strategy runner, risk manager) to rely on per‑service flags and explicit routing. Legacy `PAPER_TRADING__ENABLED` has already been removed from runtime gating.

### Trading Services Migration (Completed)
- **Broker‑Scoped Trading**: Legacy `trading_engine` and `portfolio_manager` have been replaced by `services/paper_trading` and `services/zerodha_trading`.
- **Subscriptions**: Each broker service subscribes only to its `{broker}.signals.validated` topics.
- **Emissions**: New services emit `{broker}.orders.*` and `{broker}.pnl.snapshots`.
- **DI/Lifecycle**: App starts `paper_trading_service` and `zerodha_trading_service` only; legacy services removed.
- **Observability**: Prometheus adds `trading_last_activity_timestamp_unix{service,stage,broker}`; Grafana dashboard includes panels for events, DLQ, inactivity, and consumer lag per trading service.

### Trading Services: Scope & Integration
- **Paper Trading (Simulated/Virtual)**
  - Purpose-built for safe experimentation and utility — no broker calls.
  - Free to add features that increase usefulness: slippage/commission models, latency simulation, partial fills, bracket/oco simulation, sandbox risk overlays, scenario/backtest replays, deterministic seeds for reproducibility.
  - Cleanly separated from broker SDKs; emits realistic order/PnL events to exercise downstream systems.
- **Zerodha Trading (Real Execution)**
  - Tightly integrates with Zerodha’s official Python SDK (Kite Connect, aka pykiteconnect).
  - Reference SDK is vendored for review under: `examples/pykiteconnect-zerodha-python-sdk-for-reference`.
  - Implementation plan: adapters under `services/zerodha_trading/components/` to wrap login/session, order place/modify/cancel, order status/fills, positions/holdings, and streaming (if applicable), with robust error handling, rate limiting, and idempotence.
  - Strict separation of paper vs live paths; no leakage of live credentials into paper flow.

### Logging System (Recent Improvements)
- **ProcessorFormatter**: Pretty console logs and JSON file/channel logs using structlog ProcessorFormatter.
- **Channel Routing**: API/uvicorn/fastapi routed to `logs/api.log` with `propagate=False`; `logs/error.log` collects all ERROR+ globally.
- **Redaction & Context**: Redacts sensitive keys (authorization/tokens/api_key/secret) and binds standard fields (`env`, `service`, `version`).
- **Access Log Enrichment**: Uvicorn access logs enriched with `http_method`, `http_path`, `http_status`, `http_duration_ms`, `access_client_ip`, `user_agent`, plus `request_id` and `correlation_id`.
- **HTTP IDs**: `RequestIdMiddleware` issues `X-Request-ID` and ensures `X-Correlation-ID` per request.
- **SQL/Infra Routing**: `sqlalchemy.*` → `logs/database.log`; `aiokafka`/`kafka` → `logs/application.log` at WARNING.
- **Async Queue Logging**: Non-blocking `QueueHandler` + `QueueListener` with Prometheus metrics:
  - `alpha_panda_logging_queue_size`
  - `alpha_panda_logging_queue_capacity`
  - `alpha_panda_logging_queue_dropped_total`
- **Log Maintenance**: Background archival/compression to `logs/archived/` and retention enforcement per channel.
- **Stats Endpoint**: `/api/v1/logs/stats` exposes queue and handler status.
- **Alerts**: Prometheus alert rules for drops/backpressure in `docs/observability/prometheus/logging_alerts.yml` and wired in `docker-compose.yml`.

### Logging System (Deferred/Planned Improvements)
- **Path Templates**: Enrich access logs with route templates for per-route analytics/SLOs.
- **Broader Logger Normalization**: Convert remaining modules to channel-aware helpers incrementally.
- **Noise Controls**: Sampling/rate limiting for high-frequency INFO beyond current demotions.
- **Per-Channel JSON Overrides**: Optional config for mixed plain vs JSON per channel (default remains JSON).
- **DLQ Error Tagging**: Uniform `dlq=true` tagging across all DLQ error paths for analytics.

### Env Surface (Future Improvements)
- **Tracing envs in `.env.example`**: Add `TRACING__ENABLED`, `TRACING__EXPORTER`, `TRACING__OTLP_ENDPOINT`, `TRACING__SAMPLING_RATIO` for discoverability.
- **Configurable logging via env**: Expose `LOGGING__QUEUE_MAXSIZE`, `LOGGING__FILE_MAX_SIZE`, `LOGGING__FILE_BACKUP_COUNT`, `LOGGING__AUTO_CLEANUP_ENABLED`, `LOGGING__COMPRESSION_ENABLED`, `LOGGING__COMPRESSION_AGE_DAYS` to tune queue/file behavior without code changes.

### Tracing Environment Variables (Added)
- `TRACING__ENABLED` (bool): Enable OpenTelemetry tracing.
- `TRACING__EXPORTER` (string): `none|otlp`.
- `TRACING__OTLP_ENDPOINT` (string): OTLP gRPC endpoint, e.g. `http://localhost:4317`.
- `TRACING__SAMPLING_RATIO` (float): 0.0–1.0 sampling ratio.

### Market Data Clarification
- Market data is published to a single shared topic `market.ticks` by the Zerodha websocket feed. All broker‑scoped services consume broker topics only for signals and orders; market data is not broker‑prefixed.

### Market Feed: Performance Recommendations (Future Work)
- Subscription scaling: subscribe/set_mode in batches (e.g., 100–500 tokens per batch) to avoid broker-side limits and reduce connection stress when loading large instrument sets.
- Threaded callback minimalism: consider moving `MarketTick` model validation from the KiteTicker callback thread into the async worker; keep the callback to “format + enqueue” only when CPU contention is observed at high tick rates.
- Backpressure strategy: make queue behavior configurable — allow an optional “block-with-timeout then drop” mode in addition to immediate drop when full; expose `QUEUE_MAXSIZE` and enqueue timeout as settings.
- Latency observability: add Prometheus histograms for “enqueue delay” (callback → queue) and “emit latency” (queue → Kafka) to guide `producer_tuning` (linger, compression, batch size) and detect pressure early.
- Instrument registry: augment CSV-based loading with a managed instrument registry (versioned, hot-reload) for production so subscription changes don’t require restarts.
- Producer tuning: document recommended defaults for market_feed under realistic loads (e.g., small `linger_ms`, `zstd` compression) and validate via metrics before/after changes.

## Build, Test, and Development Commands
- `make dev`: Create `.env` and install with constraints.
- `make up` / `make down`: Start/stop infra. Prefer `docker compose`.
- `make bootstrap` / `make seed`: Create topics, seed data.
  - Topic overlays supported via environment variables:
    - `SETTINGS__ENVIRONMENT` (`development`|`testing`|`production`)
    - `REDPANDA_BROKER_COUNT` (caps replication factor)
    - `TOPIC_PARTITIONS_MULTIPLIER` (scales partitions)
    - `CREATE_DLQ_FOR_ALL` (`true|false`, default true)
- `make run`: Full pipeline (`cli.py run`). API: `uvicorn api.main:create_app --reload`.
- Tests: `make test-unit|test-integration|test-e2e|test-performance|test-chaos`; or `make test-setup && make test-with-env`.
- More: `docs/development/DEVELOPMENT_GUIDE.md`, repo `README.md`.
 - Env: Always activate venv before Python; keep `.env`/`.env.example` tracked (do not remove).

## Observability & Metrics
- **Prometheus**: API exposes `/metrics` (Prometheus exposition). Dependency: `prometheus-client`.
  - Next: Register service counters/gauges via `core/monitoring/prometheus_metrics.py` and shared app registry.
- **Pipeline Metrics**: Use `PipelineMetricsCollector` with `broker_context` where applicable.
- **Tracing**: `trace_id`/`correlation_id` are included in envelopes; OpenTelemetry instrumentation is present for producer/consumer and key service paths (strategy processing, risk validation, trading execution). Sampling ratio is configurable via `TRACING__SAMPLING_RATIO`.
- **DLQ Metrics**: `trading_dlq_messages_total{service,broker}` counter increments on DLQ publishes.
- **Dashboards**: Grafana JSONs available for service metrics and consumer lag under `docs/observability/grafana/`.
- **Turnkey Stack**: Prometheus and Kafka exporter are packaged in `docker-compose.yml` under the `observability` profile.
  - See root `README.md` for quick start (Turnkey Observability and Grafana sections); no separate observability guide required.

## Schema Registry (Scaffolding)
- **Avro Schemas**: See `schemas/avro/` for core event types (envelope, market tick, signals, orders, PnL).
- **Registry Scripts**: 
  - `python scripts/register_schemas.py` registers subjects to Redpanda Schema Registry (default `http://localhost:8082`).
  - `python scripts/validate_schema_compatibility.py` checks compatibility with latest registered schemas (default `BACKWARD`).
- Runtime serialization remains JSON for now; the registry enables contract enforcement and CI checks first.
  - CI already registers and validates schemas during integration tests.
  - Optional integration test validates subjects existence when `SCHEMA_REGISTRY_URL` is provided.

## Future Considerations (Deferred)
- Authentication shortcut: Support a guaranteed `ZERODHA__ACCESS_TOKEN` shortcut to bypass interactive auth when a valid token is present (useful for CI and non-interactive restarts), while keeping auth/feed always-on. (Planned)
- Remove `PaperTradingSettings.enabled` field from Settings once all legacy references are eliminated, to avoid confusion and ensure a single source of truth (`TRADING__PAPER__ENABLED`).
- Scan and clean up any stale references to `PAPER_TRADING__ENABLED` in quickstarts, examples, and scripts; queue doc updates for when we refresh broader documentation.
- Runtime Avro enablement behind a feature flag with controlled rollout; keep JSON at runtime until contracts stabilize.
- Production secrets sourcing enforcement (fail-fast if defaults/empties detected in prod and forbid sourcing from tracked files).
- Kafka consumer lag exporter and alerting are environment concerns; dashboards provided, infra enablement left to deployment.
 - Documentation hygiene (gradual): broader doc sweep in non-archival docs to remove any lingering legacy mentions (e.g., `BROKER_NAMESPACE`, `ZERODHA__ENABLED`). Note: `AGENTS.md` already marks `ZERODHA__ENABLED` deprecated.

## Documentation Maintenance Policy
- Active docs live under `docs/` and module-level READMEs.
- Documents under `docs/archive/` are officially deprecated and are not part of the application’s documentation system; do not maintain or update them when changing behavior.

## Coding Style & Naming Conventions
- Python: 4‑space indent, UTF‑8, LF (`.editorconfig`).
- Format: `black .` (23.11); Lint: `ruff check .`.
- Names: files `snake_case.py`, classes `CamelCase`, funcs/vars `snake_case`, constants `UPPER_SNAKE`.

## Implementation Rules (Critical)
- **Avoid overengineering**: Prefer minimal, focused changes aligned to the stated scope; solve the immediate problem well before adding abstractions.
- **Avoid early optimization**: Favor readability and correctness first; optimize only when measurements show a bottleneck.
- **Keys & Ordering**: Set partition keys for ordering; unique consumer groups per service.
- **Idempotent Producers**: Enable acks=all and idempotence; flush on shutdown.
- **Topic‑Aware Routing**: Derive broker from topic; no wildcard subscriptions.
- **Fail‑Fast**: No silent failures; surface errors with logs/metrics and stop on missing dependencies.
- **Segregation**: Never mix paper/live paths; separate traders and topics.
- Full rules: `docs/IMPLEMENTATION_GUIDELINES.md`.
 - **Trading Engine**: Include `trading_mode` in events; config‑driven routing; default to paper; distinct `PaperTrader` and `ZerodhaTrader`.
 - **Error Handling**: Backoff retries for transient errors; degrade on auth failures with alerts; use core exception hierarchy; monitor DLQs and support replay; always set correlation IDs.
 - **Schema Compliance**: Order events must include all required fields and explicit `broker`; producer envelope must include `broker`; service calls must match interface methods.
 - **API DI**: Verify imports exist; use DI with `@inject` and `Provide[AppContainer.*]` consistently.

## Testing Guidelines
- `pytest` with strict markers/config; prefer real infra for integration.
- Quick unit: `python -m pytest tests/unit/ -v --tb=short`.
- Infra: `make test-setup` (health‑gated) then `make test-with-env` or `make test-integration`.
- Coverage via `./scripts/test-infrastructure.sh unit` (HTML/XML output).
 - Philosophy: Tests should expose real issues; do not change app code just to satisfy incorrect tests.

## Commit & Pull Request Guidelines
- Use Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`). Keep changes scoped; reference issues.
- PRs: describe motivation, link issues, include test plan/results and screenshots when UI/API affected.

## Security & Configuration Tips
- `.env` and `.env.example` are intentionally tracked for dev templates; keep secrets out of Git for prod.
- Brokers: keep `ACTIVE_BROKERS=paper,zerodha` during the transition to per‑service flags. Final state removes `ACTIVE_BROKERS` after refactors.
- Trading services: control execution via `TRADING__PAPER__ENABLED` and `TRADING__ZERODHA__ENABLED`. Use `TRADING__ZERODHA__ENABLED=false` to prevent live order placement while still consuming Zerodha market data.
- Zerodha auth/market feed: always required; do not disable via env. The legacy `ZERODHA__ENABLED` is deprecated.
- Zerodha auth is mandatory for full pipeline; E2E needs `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, `ZERODHA_ACCESS_TOKEN`.
- Production: avoid CORS wildcard in `API__CORS_ORIGINS` (enforced in `api/main.py`).
