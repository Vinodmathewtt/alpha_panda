# Issues, Fixes, and Recommendations

This document captures the end‑to‑end review results for Alpha Panda. It lists concrete issues, impacts, and focused fix plans to keep implementation precise and aligned with the current architecture.


## Scope
- Source reviewed: configuration, schemas, services, DI, logging/metrics/tracing, health checks, docs.
- Key references: `core/`, `services/`, `app/`, `api/`, `docs/`, `tests/`.


## Critical Issues (Fix First)

### 1) Zerodha auth gating uses deprecated flag (`ZERODHA__ENABLED`)
- Files:
  - `services/auth/auth_manager.py` (initialize() refuses to proceed unless `settings.zerodha.enabled`)
  - `app/README.md` (requires `ZERODHA__ENABLED=true`)
  - `docker-compose.test.yml` (sets `ZERODHA__ENABLED=false`)
- Observed Behavior:
  - Auth startup is gated on a legacy flag. Logs instruct users to set `ZERODHA__ENABLED=true`.
- Why It’s Wrong:
  - Architecture mandates Zerodha auth/market feed are always required and must not be gated by flags. Trading enablement is controlled by `TRADING__{BROKER}__ENABLED` plus `ACTIVE_BROKERS`.
- Impact:
  - Startup failures or inconsistent behavior; conflicts with `.env.example` and current docs; tests/settings can drift.
- Fix Plan:
  - Code: Remove gating on `settings.zerodha.enabled` from `AuthManager.initialize()`; validate only presence of `ZERODHA__API_KEY`/`ZERODHA__API_SECRET` and fail fast when missing and `zerodha` is in `ACTIVE_BROKERS`.
  - Docs: Remove `ZERODHA__ENABLED` from `app/README.md` and `docker-compose.test.yml`; clarify that auth/feed are always-on, trading path is gated by `TRADING__ZERODHA__ENABLED`.
  - Tests/Compose: If tests should run without live auth, add an explicit mock/bypass mode for testing instead of using `ZERODHA__ENABLED`.

### 2) Inconsistent broker label for shared topics (market.ticks)
- Files:
  - `core/streaming/clients.py` (`StreamProcessor._emit_event` assigns `broker='market'` for `market.ticks`)
  - `services/market_feed/service.py` uses `broker="shared"` when producing ticks.
  - Tests assert `broker == "shared"` for market topics.
- Observed Behavior:
  - Mixed use of `market` vs `shared` for the envelope `broker` on shared topics.
- Impact:
  - Schema/contract inconsistencies; potential consumer/test breakage.
- Fix Plan:
  - Standardize on `broker="shared"` for all shared market topics. Update `StreamProcessor._emit_event` accordingly and add/adjust tests if needed.


## Important Inconsistencies (Clean Up Next)

### 3) Documentation promotes legacy gating knobs
- Files:
  - `app/README.md` (multiple mentions of `ZERODHA__ENABLED`, mock mode section)
  - `docs/implementation/IMPLEMENTATION_GUIDELINES.md` (mentions `settings.paper_trading.enabled`/`settings.zerodha.enabled` for routing)
- Problem:
  - Contradicts the transition guidance: use `TRADING__PAPER__ENABLED` and `TRADING__ZERODHA__ENABLED` for trading; auth/feed always-on.
- Fix Plan:
  - Update docs to align with current flags and transition plan; clearly mark legacy flags as deprecated and non-functional for runtime gating.

### 4) `PaperTradingSettings.enabled` remains in settings (potential confusion)
- File: `core/config/settings.py`
- Problem:
  - Field exists but is not used for runtime gating; preferred flags are `TRADING__PAPER__ENABLED`/`TRADING__ZERODHA__ENABLED`.
- Fix Plan:
  - Mark as deprecated in the code comments now; plan removal once all references are eliminated (or after a short deprecation window).

### 5) `docker-compose.test.yml` carries legacy flag
- File: `docker-compose.test.yml`
- Problem:
  - Sets `ZERODHA__ENABLED=false` which is deprecated and conflicts with guidance that auth is always-on.
- Fix Plan:
  - Remove `ZERODHA__ENABLED`; if tests require no live auth, prefer explicit test mode or provide mock auth/fixtures rather than gating auth via a flag.


## Validations That Look Correct (Keep As-Is)

- Trading service gating in `app/main.py`:
  - Uses `Settings.is_paper_trading_enabled()` and `is_zerodha_trading_enabled()` with `ACTIVE_BROKERS`. Correct for transition phase; logs effective config.
- EventEnvelope and producer semantics:
  - `MessageProducer.send()` auto-wraps payloads, defaults `type=market_tick` only for market topics, and requires explicit `event_type` otherwise; injects tracing headers.
- Topic naming and routing:
  - `{broker}.{domain}.{event_type}` maintained. `.dlq` suffix for per-topic DLQ is in place. `TopicMap.get_broker_from_topic()` returns `unknown` for shared (`market`) topics.
- Metrics and observability:
  - Prometheus histograms for market feed enqueue delay and emit latency; DLQ counter wired via StreamServiceBuilder; shared registry exposed at `/metrics`.
  - Pipeline metrics use `MetricsRegistry` with consistent key schema; explicit `broker_context` passed across services.
- Health checks and startup:
  - Config validator checks `ACTIVE_BROKERS`, DB/Redis connections, Zerodha creds when `zerodha` is active. Kafka runtime compatibility check present.
- CORS safety:
  - API rejects wildcard `*` origins in production.


## Additional Recommendations (Nice-to-Have)

- Tests: Add/adjust a unit test to pin the broker label for shared topics (ensure `broker == "shared"` for `market.ticks`) in the direct client path (`StreamProcessor._emit_event`).
- Reduce confusion around `RedpandaProducer` (direct client): call out in docs that it does not auto-wrap to `EventEnvelope`. Encourage using the infrastructure `MessageProducer` for most flows.
- Documentation sweep: ensure all docs reference shared `market.ticks` and per-broker isolation; remove legacy topic examples that don’t match current naming.
- Minor cleanup: remove unused imports (e.g., `generate_uuid7` in `core/streaming/clients.py`) when touching files for related fixes.


## Concrete Fix Checklist

- Auth (CRITICAL):
  - [ ] Remove `ZERODHA__ENABLED` checks from `AuthManager.initialize()`.
  - [ ] Validate only `ZERODHA__API_KEY`/`ZERODHA__API_SECRET` and fail fast when `zerodha` is active and creds missing.
  - [ ] Update user‑facing logs to avoid suggesting `ZERODHA__ENABLED`.
  - [ ] Update `app/README.md` and `docker-compose.test.yml` to remove references to `ZERODHA__ENABLED`.

- Shared topic broker label (CRITICAL):
  - [ ] Update `StreamProcessor._emit_event` to set `broker="shared"` for `TopicNames.MARKET_TICKS`.
  - [ ] Add/adjust tests to validate this convention (optional but recommended).

- Docs and settings:
  - [ ] Update docs to consistently use `TRADING__PAPER__ENABLED` and `TRADING__ZERODHA__ENABLED`.
  - [ ] Mark `PaperTradingSettings.enabled` deprecated or remove after audit.

- Compose/testing:
  - [ ] Remove `ZERODHA__ENABLED` from `docker-compose.test.yml` and introduce explicit testing/mocking approach if needed.


## Rollout & Verification Plan

1) Implement code changes in small PRs:
   - PR A: AuthManager gating removal + log/message updates.
   - PR B: Shared broker label fix in `StreamProcessor._emit_event` + test.
   - PR C: Docs updates (`app/README.md`, implementation guide) + compose cleanup.

2) Validation:
   - Unit tests: run `make test-unit` (ensure producer semantics tests pass; add new test for shared broker label if introduced).
   - Integration: `make test-setup && make test-integration` with proper env (`ZERODHA__API_KEY/SECRET`) or mocks.
   - Manual smoke: run `python cli.py run` with safe defaults: `TRADING__PAPER__ENABLED=true`, `TRADING__ZERODHA__ENABLED=false`; verify API `/health` and `/metrics`, and system logs.

3) Observability checks:
   - Confirm Prometheus metrics for market feed enqueue/emit histograms populate when market feed runs.
   - Confirm DLQ counter increments when DLQ paths are triggered (can be simulated in a controlled test).


## References
- Architecture/Guidelines: `AGENTS.md`, `docs/architecture/MULTI_BROKER_ARCHITECTURE.md`
- Schemas: `core/schemas/events.py`, `core/schemas/topics.py`
- Producers/Consumers: `core/streaming/infrastructure/message_producer.py`, `core/streaming/infrastructure/message_consumer.py`
- Metrics/Health: `core/monitoring/*`, `core/health/*`, API `/metrics`
- Services: `services/market_feed/service.py`, `services/strategy_runner/service.py`, `services/risk_manager/service.py`, `services/paper_trading/service.py`, `services/zerodha_trading/service.py`


---
This document is the reference point for implementing the fixes above. Keep changes minimal, targeted, and consistent with the established patterns.

