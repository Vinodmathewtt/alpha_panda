# Issues Review and Fix Plan — 2025-09-04

## Summary
- Observed repeated stream processing failures in `strategy_runner` and `risk_manager` immediately after startup.
- Root cause: invalid logging call in `core/streaming/reliability/metrics_collector.py` passing an unsupported keyword argument to the standard library logger.
- Impact: successful message processing attempts error out, affected ticks are pushed to `market.ticks.dlq`, and normal downstream processing is skipped.
- Preflight checks for infra (DB/Redis/Redpanda/Zerodha) passed. Market was closed, monitoring correctly reported idle.

## Critical Issue: Logging kwarg breaks processing
### Symptoms
- Errors in both services on handling `market.ticks`.
- Dead-letter queue activity for `market.ticks.dlq`.

### Evidence (files and excerpts)
- `logs/error.log` and `logs/alpha_panda.log` contain repeated entries with the same stack trace:
  - `TypeError: Logger._log() got an unexpected keyword argument 'duration_ms'`
  - Trace points to `core/streaming/reliability/metrics_collector.py:50` during `record_success`:

```
logger.debug(f"Success recorded for {broker_context}",
            duration_ms=processing_duration * 1000)
```

- DLQ warnings in `logs/alpha_panda.log` with `dlq=true` and topic `market.ticks.dlq`.
- Consumer partition assignments are healthy (no Kafka assignment issues) prior to the failures.

### Impact
- Messages that would otherwise be considered successful are treated as failures due to the logging error.
- At least 40 DLQ publishes recorded for this run; 120 error-level entries per consolidated/error logs.
- Strategy and risk pipelines do not progress for those messages.

### Root Cause
- CPython `logging.Logger.debug/info/...` do not accept arbitrary keyword arguments. Passing `duration_ms=...` raises a `TypeError` in Python 3.13 (and prior). Structured fields must be passed via the `extra={}` parameter (or by using a structured logger like `structlog`).

### Fix
- Change the offending call to use `extra` or include the value in the message. Minimal change preferred.

Recommended minimal patch (keep stdlib logging):

```python
# core/streaming/reliability/metrics_collector.py
# before
logger.debug(f"Success recorded for {broker_context}",
             duration_ms=processing_duration * 1000)

# after
logger.debug(
    "Success recorded for %s", broker_context,
    extra={"duration_ms": processing_duration * 1000}
)
```

Alternative (if migrating to structlog later):

```python
log = structlog.get_logger(__name__).bind(service=self.service_name)
log.debug(
    "success_recorded",
    broker=broker_context,
    duration_ms=processing_duration * 1000,
)
```

## Secondary Observations
- Zerodha trading disabled by config: `TRADING__ZERODHA__ENABLED=false` → service correctly skipped; informational entries present.
- Market closed: monitoring marks pipeline idle (expected); no order flow expected.
- Quiet channels: `api.log`, `application.log`, `database.log`, `performance.log`, `audit.log` are empty because those paths were not exercised.

## Validation Plan (post-fix)
1. Apply the patch to `MetricsCollector.record_success` and restart services.
2. Reproduce message flow (market feed or replay) and verify:
   - No new `TypeError` stack traces in `logs/error.log` or `logs/alpha_panda.log`.
   - No new DLQ entries for `market.ticks.dlq` tied to the logging error.
   - Normal processing logs appear for `strategy_runner`/`risk_manager`.
   - `monitoring.log` continues to report idle when market closed (unchanged behavior).
3. Optional: clear or replay DLQ depending on policy.
   - If safe, replay affected offsets from `market.ticks.dlq` back to `market.ticks` (out of scope here; follow DLQ replay procedure).

## Prevention and Hardening
- Logging usage guideline: when using stdlib `logging`, never pass arbitrary kwargs; put structured fields in `extra={}`.
- Consider adopting structured logging consistently (e.g., structlog) with a thin wrapper to avoid kwarg misuse.
- Add a lightweight unit test for `MetricsCollector.record_success` to ensure it does not raise and logs as expected.
- Optional CI lint: grep for `logger.(debug|info|warning|error)\(.*\,\s*\w+\s*=` as a heuristic to catch direct kwargs to logging calls.

## Useful Commands (replicate analysis)
- List logs and sizes:
  - `ls -la logs && find logs -maxdepth 1 -type f -printf '%f %s bytes\n' | sort`
- Scan for errors/tracebacks:
  - `rg -n '\\b(ERROR|CRITICAL|Exception|Traceback|WARNING|WARN)\\b' logs/*.log`
- DLQ evidence:
  - `rg -n 'dlq=true|\\.dlq' logs/*.log`
- Partition assignment visibility:
  - `rg -n 'Consumer partition assignment established' logs/alpha_panda.log`

## Action Items
- [ ] Patch `core/streaming/reliability/metrics_collector.py` (use `extra={}`)
- [ ] Quick scan for other logging calls with stray kwargs and fix similarly
- [ ] Decide and execute DLQ replay/drop for affected messages
- [ ] Add a small test for `MetricsCollector` logging behavior

---
Document generated from logs captured at 2025-09-04T20:47Z on development environment.

## Repo‑Wide Scan Findings (Follow‑up)

- Scope: searched for stdlib logging misuse (passing arbitrary keyword arguments to `logging.Logger.*`) across runtime modules. Heuristic used: calls like `logger.(debug|info|warning|error|critical)(..., some_kw=...)` that aren’t using `extra=`/`exc_info=`/`stack_info=`/`stacklevel=`.
- Result summary:
  - Confirmed offending call only in `core/streaming/reliability/metrics_collector.py` (already documented above).
  - Other core streaming modules using stdlib logging pass structured context via `extra={...}` (correct) or use `CorrelationLogger`/channel loggers that safely accept kwargs.
  - Many example and service modules use structlog‑backed loggers (`get_*_logger_safe(...)` or `structlog.get_logger(...)`), where keyword fields are valid.

### Files reviewed (high‑signal hits)
- Problematic (requires fix):
  - `core/streaming/reliability/metrics_collector.py`: `logger.debug(..., duration_ms=...)` → must use `extra={...}` (see fix above).
- Safe usage (no change required):
  - `core/streaming/correlation.py`: stdlib logger used with `extra=context`; wrapper `CorrelationLogger` properly injects context via `extra` and accepts kwargs.
  - `core/streaming/error_handling.py`: uses `extra={"dlq": True}` for DLQ tagging.
  - `core/streaming/reliability/reliability_layer.py`: correlation logger receives kwargs; stdlib logger calls use f‑strings only.
  - `core/database/connection.py`: mixes stdlib logger (message‑only) with channel loggers from `core.logging` (structlog), which accept kwargs safely.
  - `api/main.py`, `services/*`: use `get_*_logger_safe` (structlog), safe to pass keyword fields.

### Additional recommendations (hardening)
- Consistency: prefer the channel loggers from `core.logging` (structlog) for new code. When stdlib logging is necessary, always pass structured fields via `extra={}`.
- Guardrail lint: add CI grep to flag potential stdlib misuse:
  - Pattern example: `logger\.(debug|info|warning|error|critical)\([^)]*\b(?!extra|exc_info|stack_info|stacklevel)[a-zA-Z_]\w*\s*=`
  - Allowlist files under `examples/` if they intentionally use structlog or wrappers.
- Test gap: add a unit test for `MetricsCollector.record_success` to ensure it does not raise under stdlib logging and includes `duration_ms` via `extra`.

## Action Items (Updated)
- [x] Identify and document root cause in `metrics_collector.py`.
- [ ] Apply code fix in `metrics_collector.py` to use `extra={...}` for structured fields when calling stdlib logger.
- [ ] Add unit test for `MetricsCollector.record_success` logging behavior.
- [ ] Add CI heuristic to flag stdlib logging calls with stray keyword args (excluding `extra`/`exc_info`/`stack_info`/`stacklevel`).
