# Logging Improvements Plan

This document captures a comprehensive review of the logging infrastructure and a prioritized plan to improve reliability, clarity, and operational usefulness across the Alpha Panda application.

## Objectives
- Eliminate noisy or misleading logs and off-hours false positives.
- Ensure clean, machine-parseable file logs (no ANSI/emoji) and correct channel routing.
- Standardize structures, fields, and redaction across all logs.
- Improve performance and resilience of logging under load.
- Make API/access/database/infra logs easy to analyze and ship.

---

## Current State (Summary)
- Structured logging via structlog with an enhanced manager: `core/logging/enhanced_logging.py`.
- Multi-channel routing with `LogChannel` → per-channel files in `logs/` via `core/logging/channels.py`.
- Services mostly use channel-aware helpers (e.g., `get_trading_logger_safe`).
- Uvicorn/FastAPI logs were not routed to `api.log`; file logs included ANSI/emoji.

## Issues Observed From Logs
- Market-closed false positives: `pipeline_monitor` records “Market data latency too high …” while markets are closed.
- File logs contained ANSI color codes and emojis; hard for ingestion and search.
- `api.log` and `error.log` were empty or underused due to missing handler wiring.
- Chatty INFO logs from market feed startup (“Tick data richness/Market depth”) clutter logs.
- Mixed logger usage in a few modules (raw `logging.getLogger`) without channel context.

---

## Quick Wins Already Implemented
- File sanitization: file handlers now strip ANSI escape codes and non-ASCII characters (emojis) to keep files clean.
- API/error routing: API channel wired to `uvicorn`, `uvicorn.error`, `uvicorn.access`, and `fastapi` loggers; ERROR channel attached to root at `ERROR+`.
- API logger usage: API server uses the API logger; logging configured during app creation (idempotent).

Files touched:
- `core/logging/enhanced_logging.py` (added `AnsiStrippingFormatter`, wired API/ERROR handlers).
- `api/main.py` (use API logger, ensure logging configured for API context).

---

## Recommended Fixes & Improvements

### 1) Market-Hours Gating for Alerts (High Impact)
- In `core/monitoring/pipeline_validator.py`, gate market-data latency checks using `MarketHoursChecker` and recent tick rate thresholds.
- During closed hours (or below minimal tick rate), skip or downgrade to INFO a structured note: `reason="market_closed"`.

### 2) Proper Per-Handler Rendering with ProcessorFormatter
- Replace sanitizer-based formatting with `structlog.stdlib.ProcessorFormatter` so:
  - Console handler uses `ConsoleRenderer` (pretty, colorized).
  - File/channel handlers use `JSONRenderer` for machine parsing (or compact plain format when `logging.json_format=False`).
- Honor `LoggingSettings.json_format` for files. Avoid ANSI entirely in files without post-processing.

Implementation sketch:
- Introduce a common `foreign_pre_chain` (e.g., `add_log_level`, `add_logger_name`, `TimeStamper`).
- Console: `ProcessorFormatter(processor=ConsoleRenderer())`.
- Files: `ProcessorFormatter(processor=JSONRenderer())`.

### 3) Queue-Based Logging for Resilience
- Use `logging.handlers.QueueHandler` on the root logger and a `QueueListener` owning all file handlers.
- Benefits: non-blocking logging on hot paths (ticks/orders), better resilience on spikes.
- Config toggles: `LoggingSettings.queue_enabled: bool = True`, `queue_maxsize: int = 10000`.

### 4) Channel Filters and Propagation Control
- Create `ChannelFilter(expected)` to ensure each channel file handler only receives matching events (bound `channel`).
- For `uvicorn.*` and other third-party loggers, attach the API handler and set `propagate=False` to avoid duplicates via root.

### 5) Uvicorn/FastAPI Log Config and Structured Access Logs
- Provide `log_config` to `uvicorn.run(...)` to integrate with ProcessorFormatter for both error and access logs.
- Access log fields: `ts`, `method`, `path`, `status`, `duration_ms`, `client_ip`, `user_agent`, `request_id`, `correlation_id`.
- Redact sensitive query params automatically (see Redaction below).

### 6) SQL and Infra Logger Routing
- Attach `sqlalchemy.*` and `aiokafka.*` loggers to `DATABASE` or `APPLICATION` channels.
- Defaults: level WARNING; allow raising to INFO during debugging via settings.

### 7) Error Context Standardization
- Ensure `exc_info=True` logs produce JSON with keys: `error_type`, `error_message`, `stack`.
- Tag DLQ-related errors with `dlq=true` for easy filtering and alerts.

### 8) Standard Fields in Every Log
- Add a processor to bind `service`, `env`, `version` from `Settings` at logger configuration time.
- Encourage consistent inclusion of: `broker`, `topic`, `group_id`, `correlation_id`, `trace_id` on event logs.

### 9) Redaction Processor (Security)
- Add a processor to redact secrets/PII from events and context:
  - Keys: `authorization`, `access_token`, `api_key`, `password`, `secret`, etc.
  - Apply to header maps and nested dicts.
- Configurable via `LoggingSettings.redact_keys: list[str]`.

### 10) Volume Management and Level Hygiene
- Demote noisy startup and per-tick details to DEBUG.
- Sampling for repetitive info (e.g., at most once per symbol per N seconds).
- Aggregate repetitive confirmations (e.g., subscription counts) instead of per-item logs.

### 11) Operations: Rotation, Archival, Compression
- Keep rotation; add optional background task to move old logs to `logs/archived/` and compress after `compression_age_days`.
- Enforce per-channel `retention_days` from `CHANNEL_CONFIGS`.

### 12) Logging Subsystem Health Metrics
- Emit Prometheus metrics:
  - `logging_queue_depth`, `logging_queue_overflows_total`, `logging_handler_errors_total`.
  - Alert on sustained queue backpressure or handler failures.

### 13) Normalize Logger Usage Across Codebase
- Replace raw `logging.getLogger(__name__)` with channel-aware helpers:
  - Market data components → `get_market_data_logger_safe`.
  - Auth/API components → `get_api_logger_safe`.
  - Database/infra → `get_database_logger_safe` or `get_error_logger_safe`.

---

## Concrete Change List (By File)

### core/logging/enhanced_logging.py
- Migrate to `ProcessorFormatter` for console and files.
- Add `QueueHandler`/`QueueListener` when enabled.
- Add `ChannelFilter` and attach to channel handlers.
- Bind standard fields (`service`, `env`, `version`) via a processor.
- Add Redaction processor.

### core/logging/channels.py
- Optionally store per-channel JSON-vs-plain preference and retention policy checks.
- Provide helper to build filtered handlers.

### api/main.py
- Provide an explicit `uvicorn` `log_config` integrating with structlog ProcessorFormatter.
- Set `propagate=False` for `uvicorn.*` after attaching the API handler to prevent duplicates.
- Keep `get_api_logger_safe("api.main")` for app lifecycle logs.

### core/monitoring/pipeline_validator.py
- Gate market-data latency checks using `MarketHoursChecker` and recent tick cadence.
- During closed hours, log a single INFO event indicating checks were skipped.

### services/market_feed/service.py
- Reduce startup verbosity; move per-instrument richness/depth logs to DEBUG or sample once.

### Modules using raw logging
- `services/market_feed/auth.py`, `services/auth/kite_client.py`, and similar: switch to channel-aware `get_*_logger_safe`.

---

## Configuration Additions
Extend `LoggingSettings` in `core/config/settings.py`:
- `json_format: bool` (already exists; honor for files).
- `queue_enabled: bool = True`
- `queue_maxsize: int = 10000`
- `redact_keys: list[str] = ["authorization", "access_token", "api_key", "secret", "password"]`
- Optional per-channel JSON flag (if needed): `channels_json: dict[str, bool]`.

---

## Testing & Verification Plan
- API routing:
  - Start API, hit `/` and `/health`. Expect `logs/api.log` to include startup and access lines in JSON (no ANSI).
- Error capture:
  - Trigger a controlled exception; verify `logs/error.log` contains structured error with stack.
- Market-hours gating:
  - Simulate closed hours; run validator and confirm no latency WARN entries, only a gated INFO note.
- File cleanliness:
  - Grep for ANSI escape codes in `logs/*.log` → none found.
- Volume controls:
  - Enable DEBUG and verify tick logs are present but sampled at INFO.
- Duplicates:
  - Ensure adding handlers + `propagate=False` avoids duplicate API lines.

Command snippets:
- `rg -n "\x1b\[[0-9;]*[A-Za-z]" logs/*.log` → should return nothing.
- `rg -n "\bERROR\b" logs/error.log` → verify structured errors appear.

---

## Rollout Plan
1) Land ProcessorFormatter migration behind a small feature flag if desired.
2) Add redaction processor and standard field bindings.
3) Implement market-hours gating in the validator.
4) Normalize logger usage in outlier modules.
5) Optionally enable QueueHandler/QueueListener in staging; monitor queue metrics.
6) Add archival/compression task and retention enforcement.

---

## Appendix A: Example Uvicorn Log Config (Sketch)
```python
log_config = {
  "version": 1,
  "disable_existing_loggers": False,
  "formatters": {
    "structlog": {
      "()": structlog.stdlib.ProcessorFormatter,
      "processor": structlog.processors.JSONRenderer(),
      "foreign_pre_chain": [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
      ],
    }
  },
  "handlers": {
    "api": {
      "class": "logging.StreamHandler",
      "formatter": "structlog",
      "stream": "ext://sys.stdout",
      "level": "INFO"
    }
  },
  "loggers": {
    "uvicorn": {"handlers": ["api"], "level": "INFO", "propagate": False},
    "uvicorn.error": {"handlers": ["api"], "level": "INFO", "propagate": False},
    "uvicorn.access": {"handlers": ["api"], "level": "INFO", "propagate": False},
  }
}
```

## Appendix B: Redaction Processor (Sketch)
```python
def redact_processor(keys_to_redact):
    def _proc(logger, name, event_dict):
        def _redact(obj):
            if isinstance(obj, dict):
                return {k: ("[REDACTED]" if k.lower() in keys_to_redact else _redact(v)) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_redact(v) for v in obj]
            return obj
        return _redact(event_dict)
    return _proc
```

## Appendix C: Channel Filter (Sketch)
```python
class ChannelFilter(logging.Filter):
    def __init__(self, channel):
        super().__init__()
        self.channel = channel
    def filter(self, record):
        return getattr(record, "channel", None) == self.channel
```

---

By implementing the above, logs will be cleaner, cheaper to store, easier to analyze, and more operationally meaningful — especially during off-hours and under production load.

