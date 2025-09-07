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
- **Broker Context (Required)**: `BROKER_NAMESPACE` env is removed. All routing derives from topic prefixes. For metrics, pass an explicit `broker_context` to `PipelineMetricsCollector` on every call (use `shared` for `market.ticks`). Any remaining references to a global `broker_namespace` are considered deprecated and should be refactored to per‑broker context.
  - Forward plan: remove remaining `broker_namespace` mentions outside of archives; ensure dashboards/keys are broker‑scoped using `pipeline:{stage}:{broker}:{last|count}`.
- **Market Data**: Single Zerodha feed publishes `market.ticks` for all brokers.
 - **Strategy Broker Routing**: One broker per strategy. Paper by default; set `zerodha_trading_enabled=true` on the strategy DB row to route only to Zerodha.

### Market Data And Broker Context
- **Single Source (Shared)**: Market data is published to a single shared topic `market.ticks`. Do not attach a per-broker context to market data events or logs.
- **Envelope Broker**: For `market.ticks`, set the envelope `broker` to `shared` to reflect the shared feed (not paper/zerodha). This prevents duplication and enforces a single market data stream.
- **Metrics Namespace**: When recording pipeline metrics for market data, always pass `broker_context="shared"`. Keys should follow `pipeline:market_ticks:shared:{last|count}` (legacy compatibility keys may be present during transition).
- **Brokerization Boundary**: Broker context begins at strategy signal generation. The Strategy Runner emits `{broker}.signals.raw` and all downstream services (risk manager, trading engines, portfolios) remain broker‑scoped with `{broker}.…` topics and per‑broker metrics.
- **Logging**: Market feed channel logs remain unbrokered (no `broker` field). Per‑broker logs are appropriate only once signals are generated and the pipeline forks by broker.

Recommended follow‑ups (non‑blocking):
- **Key standardization**: Consolidate any remaining market tick Redis keys to `pipeline:market_ticks:shared:{last|count}` and maintain a deprecation window for legacy aliases.
- **Noise control**: During extended market closures, consider demoting repetitive “idle (market closed)” validator logs to DEBUG or applying sampling to reduce log noise while keeping visibility.
- **Guardrails**: Add a lightweight CI/doc lint to discourage attaching broker context to market data paths and to enforce explicit `broker_context` on all pipeline metrics calls.

### Preflight Checks (Startup Gate)
- Purpose: enforce a comprehensive readiness gate before any service starts.
- Location: `app/pre_flight_checks.py`; executed by `ApplicationOrchestrator.startup()`.
- Current scope: DB/Redis/Redpanda connectivity, mandatory Zerodha auth, active strategies check, ML model artifact existence for active ML strategies (fail‑fast in prod), topic coverage per broker, market hours info.
- Summary artifact: writes `logs/preflight_summary.json` capturing per‑check status, durations, failure reasons, and environment policy.
- Roadmap:
  - Kafka runtime compatibility (aiokafka/Python, bootstrap servers) and startup logs for consumer groups/partitions (compat check present; partition assignment logs added on consumer start).
  - Strategy readiness counts per broker (registered/ready), published to Redis for validator suppression logic.
  - Logging channel/observability checks (channel handlers attached, files writable, Prom registry present).
  - Clear policy: blocking in production on critical failures; dev mode relaxed where safe.

## Recent Improvements
- Trading flags: unified on `TRADING__PAPER__ENABLED` and `TRADING__ZERODHA__ENABLED`; legacy `PAPER_TRADING__ENABLED` removed from runtime gating.
- Validator: market‑closed becomes `idle`, order/portfolio checks are skipped for disabled brokers, and no‑signal messages are suppressed when no strategies target a broker.
- Market feed performance: configurable queue (`MARKET_FEED__QUEUE_MAXSIZE`, `MARKET_FEED__ENQUEUE_BLOCK_TIMEOUT_MS`), subscription batching (`MARKET_FEED__SUBSCRIPTION_BATCH_SIZE`).
- New Prometheus histograms: `market_tick_enqueue_delay_seconds` and `market_tick_emit_latency_seconds`; optional bucket tuning via `MONITORING__PROMETHEUS_BUCKETS__*`.
- Logging: access logs include route templates; optional INFO sampling via `LOGGING__INFO_SAMPLING_RATIO` for API channel.
- DLQ logs now include `dlq=true` for consistent tagging.
- Preflight ML model check: startup fails in production when artifacts are missing; writes preflight summary JSON.
- Preflight ML feature compatibility: added check to compare extracted feature length vs `model.n_features_in_` (warn in dev/test; block in prod on mismatch).
- Strategy modules updated: composition‑only runner/processors; ML processors perform feature‑shape validation and avoid duplicate model loads; config templates document `parameters.expected_feature_count`.
- Validator warnings counter: `validator_warnings_total{stage,broker,issue}` to track warning conditions.
- Consumer startup logs include group id/topic/partition assignments for visibility.
- Channel logging: one‑time summary event lists attached handlers; fixed channel filter for structlog event dicts.
- Paper trading (Phase 1–3) implemented:
  - Phase 1: slippage/commission models, optional latency simulation, deterministic RNG per event for reproducibility.
  - Phase 2: partial fills (probabilistic split), order types (market/limit with `limit_price`), time‑in‑force (IOC/FOK/DAY), idempotence for duplicate validated signals, `order_failed` emissions with reasons.
  - Phase 3: bracket/OCO exits via `market.ticks` (TP/SL in signal metadata), in‑memory portfolio (qty/avg_price), cash balance and buy/sell constraints (no shorting, cash checks), unrealized/realized PnL snapshots.
  - Metrics (nice‑to‑have): `paper_fill_latency_seconds`, `paper_slippage_bps`, `paper_cash_balance`.
  - Replay helper: `scripts/replay_paper_demo.py` for bracket demo or JSONL replays.

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
  - Implemented features:
    - Slippage/commission models; optional latency; deterministic RNG per event.
    - Partial fills; order types (market/limit); TIF (IOC/FOK/DAY); idempotence; `order_failed` on unfillable.
    - Bracket/OCO exits driven by `market.ticks` (TP/SL via signal metadata).
    - Portfolio (qty/avg_price), cash balance, unrealized/realized PnL snapshots; buy/sell constraints (no shorting).
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
  - Integration: includes paper trading flow and bracket/OCO exit tests.
- More: `docs/development/DEVELOPMENT_GUIDE.md`, repo `README.md`.
 - Env: Always activate venv before Python; keep `.env`/`.env.example` tracked (do not remove).

## Observability & Metrics
- **Prometheus**: API exposes `/metrics` (Prometheus exposition). Dependency: `prometheus-client`.
  - Next: Register service counters/gauges via `core/monitoring/prometheus_metrics.py` and shared app registry.
- **Pipeline Metrics**: Use `PipelineMetricsCollector` with `broker_context` where applicable.
- **Paper Trading Metrics** (added):
  - `paper_fill_latency_seconds{strategy_id,broker}` — validated → fill latency.
  - `paper_slippage_bps{side,broker}` — absolute slippage per fill in bps.
  - `paper_cash_balance{strategy_id,broker}` — simulated cash balances.
- **Tracing**: `trace_id`/`correlation_id` are included in envelopes; OpenTelemetry instrumentation is present for producer/consumer and key service paths (strategy processing, risk validation, trading execution). Sampling ratio is configurable via `TRACING__SAMPLING_RATIO`.
- **DLQ Metrics**: `trading_dlq_messages_total{service,broker}` counter increments on DLQ publishes.
- **Dashboards**: Grafana JSONs available for service metrics and consumer lag under `docs/observability/grafana/`.
- **Turnkey Stack**: Prometheus and Kafka exporter are packaged in `docker-compose.yml` under the `observability` profile.
  - See root `README.md` for quick start (Turnkey Observability and Grafana sections); no separate observability guide required.

### API Docs (Future)
- Add OpenAPI parameter descriptions for the new `broker` query param on monitoring endpoints to improve Swagger UI clarity:
  - `GET /api/v1/monitoring/pipeline?broker=paper|zerodha|shared`
  - `POST /api/v1/monitoring/pipeline/reset?broker=...`
  - `GET /api/v1/monitoring/metrics?broker=...`

## Future Roadmap (Gradual Rollout)

### High-Value Now
- Auth refresh hardening: Prevent live outages; add retries/metrics; low risk.
- Secrets policy enforcement: Fail-fast on missing/blank prod secrets; tighten security.
- DLQ replay tooling (scoped): Ops must-have for recovery; CLI with dry-run and filters.
- Liveness/Readiness endpoints: Useful for orchestration/K8s; trivial to add.
- OpenAPI broker param docs: Low effort; reduces user/API confusion quickly.
- Metrics regression tests: Guard normalized Redis keys; prevent silent drift.
- Operator runbook: Fast win for on-call; document DLQ/lag/auth playbooks.

### Defer (Avoid Overengineering Now)
- Paper state persistence: Adds complexity; useful later for restart continuity/backtesting replay.
- DB rename broker_namespace→broker: Migration risk with thin returns; do alongside planned schema work.
- Circuit breakers/rate limiting (Zerodha): Great for high-volume prod; defer unless live trading is imminent.
- End-to-end backpressure in Risk/Strategy: Implement after observing sustained lag; measure first.
- Producer tuning auto-profiles: Fine-tune when metrics show bottlenecks; current tuning is adequate.
- Trace propagation via headers: Nice polish; defer unless distributed tracing is actively used for investigations.
- Market feed auto-tune for batching: Add after load tests confirm a need.
- Strategy hot-reload: Valuable but non-trivial; implement when explicitly requested by ops.

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
- Standardize example bundles on `LOGGING__LEVEL` for enhanced logging and keep `LOG_LEVEL` only as a fallback. Update k8s manifests, docker-compose, and example READMEs to reflect this (in progress).
- Runtime Avro enablement behind a feature flag with controlled rollout; keep JSON at runtime until contracts stabilize.
- Production secrets sourcing enforcement (fail-fast if defaults/empties detected in prod and forbid sourcing from tracked files).
- Kafka consumer lag exporter and alerting are environment concerns; dashboards provided, infra enablement left to deployment.
- Documentation hygiene (gradual): broader doc sweep in non-archival docs to remove any lingering legacy mentions (e.g., `BROKER_NAMESPACE`, `ZERODHA__ENABLED`). Note: `AGENTS.md` already marks `ZERODHA__ENABLED` deprecated.

## Logging Policy (General)
- Efficiency first: prioritize application efficiency over log aesthetics; avoid extra complexity purely to make logs pretty.
- JSON by default: JSON logs are the primary format across the application for richness and machine parsing. Keep JSON enabled for files and channels; disable JSON only for terminal output.
- Terminal is secondary: terminal logs are not a priority; correctness, performance, and file/channel logs take precedence.

## Pending Tasks
- ML-only cleanup (non-runtime): Sweep and update or remove scripts and docs that reference legacy/non-ML strategies to avoid confusion and broken examples. Targets include (non-exhaustive): `scripts/seed_strategies.py`, `scripts/validate_composition_migration.py`, root `README.md`, and select docs under `docs/`. Leave runtime modules as-is (already ML-only).  
 - Optional: Add admin “reload strategies” command/endpoint to refresh from DB without restart.

- Logging split follow-up (gradual): Reduce `alpha_panda.log` size and clarify roles by fully relying on channel files.
  - Phase 1 (done):
    - Bind `channel` for component loggers and prevent propagation to root to avoid duplication in `alpha_panda.log`.
    - Route `alpha_panda.main` to `application` channel.
    - Set root file (`alpha_panda.log`) to `WARNING+` when `multi_channel_enabled=true`.
  - Phase 2:
    - Audit remaining loggers not bound to a component and migrate them to appropriate channels (e.g., `application`, `monitoring`, `database`).
    - Consider disabling the root file handler (`alpha_panda.log`) entirely when `multi_channel_enabled=true`, or limit it to `WARNING+`.
  - Phase 3:
    - Optional sub-channels or finer files if needed (e.g., `streaming.log`, `orchestration.log`) and documented retention per channel.
    - Update README/docs to declare `application.log` as the primary consolidated app log and mark `alpha_panda.log` as deprecated when channels are enabled.

- Logging field standardization (gradual):
  - Ensure multi-broker services include `broker`/`broker_context` on logs that are broker-specific; add small helpers to bind this context at service init.
  - Verify `env`, `service`, `version`, `channel`, and `correlation_id` are present across all logs; extend wrappers where needed.
  - Target modules (runtime):
    - `services/risk_manager/service.py` (risk validation paths, decisions, DLQ/error logs)
    - `services/strategy_runner/service.py` (strategy dispatch, per-broker fan-out)
    - `services/paper_trading/service.py` (order sims, fills, pnl)
    - `services/zerodha_trading/service.py` (order placement/updates, adapter outputs)
    - `core/monitoring/pipeline_monitor.py` and validators (per-broker health lines)
    - `core/streaming/patterns/stream_service_builder.py` (ensure DLQ/metrics callbacks include broker)
  - Implementation plan:
    - Add `bind_broker_context(logger, broker: str, strategy_id: Optional[str]=None)` helper (binds `broker`, `broker_context`, and optional `strategy_id`).
    - Bind once at service init and in per-broker loops; avoid rebinding per log line.
    - Update Prometheus hooks to pass `broker_context` consistently.
  - Acceptance criteria:
    - All per-broker logs across the above services contain `broker` (and `strategy_id` where applicable).
    - DLQ/error logs include `broker` and are visible in channel files without duplication.
    - No perf regressions; log volume unchanged except added fields.

- Emoji/ANSI policy for JSON files (future):
  - Add optional processor to strip emojis and ANSI from JSON file logs (console remains pretty/emoji-rich). Controlled via `LOGGING__STRIP_EMOJI_IN_FILES`.

- Reduce duplicate startup noise (future):
  - Instrument loading: avoid duplicate “Successfully loaded instruments” lines when both registry seeding and market feed subscription load from CSV; consolidate to a single INFO or demote one to DEBUG.
  - Market hours checker: ensure single initialization (unless intentional); demote duplicate initialization log to DEBUG to reduce noise.

## Documentation Maintenance Policy
- Active docs live under `docs/` and module-level READMEs.
- Documents under `docs/archive/` are officially deprecated and are not part of the application’s documentation system; do not maintain or update them when changing behavior.

## Coding Style & Naming Conventions
- Python: 4‑space indent, UTF‑8, LF (`.editorconfig`).
- Format: `black .` (23.11); Lint: `ruff check .`.
- Names: files `snake_case.py`, classes `CamelCase`, funcs/vars `snake_case`, constants `UPPER_SNAKE`.

### Strategy Naming Convention (New)
- Strategy implementation files and their configuration files must share the same base name.
  - Example: `ml_momentum.py` with `ml_momentum.yaml`
- Policy applies to all new strategies. Existing strategies may remain as-is until replaced.
  - ML configs should document `parameters.expected_feature_count` to indicate canonical feature vector length for the processor.

## Implementation Rules (Critical)
- **Avoid overengineering**: Prefer minimal, focused changes aligned to the stated scope; solve the immediate problem well before adding abstractions.
- **Avoid early optimization**: Favor readability and correctness first; optimize only when measurements show a bottleneck.
- **Keys & Ordering**: Set partition keys for ordering; unique consumer groups per service.
- **Idempotent Producers**: Enable acks=all and idempotence; flush on shutdown.
- **Topic‑Aware Routing**: Derive broker from topic; no wildcard subscriptions.
- **Fail‑Fast**: No silent failures; surface errors with logs/metrics and stop on missing dependencies.
- **Segregation**: Never mix paper/live paths; separate traders and topics.
- Full rules: `docs/IMPLEMENTATION_GUIDELINES.md`.
- **Trading Engine**: Include `execution_mode` in events; config‑driven routing; default to paper; distinct `PaperTrader` and `ZerodhaTrader`.

### Execution Mode Naming
- **Use `execution_mode` (not `trading_mode`)**: `execution_mode` unambiguously identifies how an order/event was executed (`paper` or `zerodha`). The legacy `trading_mode` was ambiguous and could be confused with a strategy’s internal mode or with global runtime posture.
- **Schema alignment**: The canonical enum is `ExecutionMode` in `core/schemas/events.py`. Use it for order/PnL events and anywhere the execution path matters.
- **Broker vs mode**: The envelope `broker` field denotes routing/audit namespace (e.g., `paper`, `zerodha`), while `execution_mode` in the event payload denotes how the order was actually executed. Today they align, but keeping both fields avoids ambiguity and supports future scenarios where routing and execution could diverge.
- **Observability**: Prefer tagging metrics/logs/traces with `execution_mode` to distinguish paper vs live execution analysis without overloading the term “trading”.

## Strategy Loading Policy (Authoritative)
- **Source of truth:** The database table `strategy_configurations` is the only runtime source of strategies. The Strategy Runner loads all active strategies from this table automatically at service startup.
- **No runtime YAML discovery:** YAML files under `strategies/configs/` are templates for seeding and tests only. Do not load strategies directly from YAML at runtime.
- **Startup behavior:**
  - On every start, the Strategy Runner queries the DB and constructs composition executors (rules/ML/hybrid) with O(1) instrument routing.
  - Preflight/health already includes an “active strategies” check; in production, treat zero active strategies as a blocking condition; in development, warn and allow (policy already present in preflight roadmap).
- **Seeding consistency:**
  - Provide a single, generic seeding script (or Make target) that upserts strategies from YAML into the DB. Prefer `make seed` in developer workflows and CI.
  - YAML templates must include `strategy_name`, `strategy_type` (alias `strategy_class` accepted), `enabled`, `instrument_tokens`, `parameters`, and `brokers` (to set `zerodha_trading_enabled`).
  - The repository includes a low‑frequency demo strategy (`low_frequency_demo`) and template to ensure a few signals per day for E2E validation when desired.
- **Environment practices:**
  - Development: Use `make seed` (or `python scripts/db_seed_ml_strategies.py --files ...`) before `make run` to populate strategies. Optionally, an auto‑seed-on-empty mechanism in dev can be introduced behind an env (e.g., `STRATEGY_AUTO_SEED_FILES`) — to be implemented as future work.
  - CI/Integration: Seed via scripts in test setup (`make test-setup`) with deterministic templates.
  - Production: Seed via migrations/ops workflows; never rely on runtime YAML. Zero active strategies should block startup (preflight policy).
- **Hot reload (future):**
  - Add a safe “reload strategies” capability (admin endpoint or CLI) that refreshes the in‑memory registry from DB without restart. Until then, restart the Strategy Runner after DB changes.

## Strategy Deployment Playbook
- Implement: add a pure `StrategyProcessor` in `strategies/implementations/<name>.py` (no infra access; minimal logging; efficient logic).
- Register: map `"<name>"` → `strategies.implementations.<name>.create_<name>_processor` in `strategies/core/factory.py`.
- Template: create `strategies/configs/<name>.yaml` with: `strategy_name`, `strategy_type` (alias `strategy_class`), `enabled`, `brokers` (`["paper"]` or `["zerodha"]`), `instrument_tokens`, `parameters`.
- Seed: upsert into DB with `python scripts/db_seed_ml_strategies.py --files strategies/configs/<name>.yaml` (script accepts `strategy_type` or `strategy_class`). Prefer `make seed` where available.
- Start: restart the app; the Strategy Runner auto‑loads active strategies from DB on startup. Future: add admin “reload strategies” without restart.
- Verify: check `trading.log` for “Strategy Loading Summary” and the per‑strategy “Loaded … composition strategy” log; observe signals on `{broker}.signals.raw` topics.
- E2E validation: use `low_frequency_demo` strategy (included) to produce a few signals per day; keep its instrument list small.

### Optional Conveniences (Future)
- `make seed` wrapper:
  - Provide a Make target that wraps the Python seeding script with a curated list of templates (including the demo).
  - Benefits: consistent developer workflow, fewer mistakes, easier CI integration.
  - Scope: Add `make seed` calling `python scripts/db_seed_ml_strategies.py --files <list>`; document environment assumptions (DB up, `.env` loaded).
- Admin "reload strategies" endpoint/CLI:
  - Add a safe refresh path to reload strategies from DB without a process restart.
  - Considerations: thread-safety (pause tick dispatch, swap mappings atomically), DI-friendly, idempotent, auth-protected (admin-only), structured logging + metrics.
  - Scope: service method `reload_strategies()`, FastAPI route `POST /api/admin/strategies/reload` (or CLI `cli.py strategies-reload`).


Migration Guidance
- **Producers**: replace any `trading_mode` fields in payloads with `execution_mode`.
- **Consumers**: if you need backward compatibility, accept both during a transition and normalize to `execution_mode`.
- **Schemas/validators**: refer to the `ExecutionMode` enum to keep contracts tight and validation explicit.
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
 - Paper trading config (discoverability): see `.env.example` for slippage/commission, latency, partial fills, and starting cash knobs.
