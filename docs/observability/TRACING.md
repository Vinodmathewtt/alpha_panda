OpenTelemetry Tracing (Optional)

Overview
- Tracing is feature‑flagged and safe to enable/disable at runtime via settings.
- Producers add a span around Kafka send and inject trace context into headers.
- Consumers extract context from headers and create a span around processing.
- When disabled, all helpers are no‑ops with zero runtime cost.

Enable Tracing
- Env vars (pydantic nested):
  - `TRACING__ENABLED=true`
  - `TRACING__EXPORTER=otlp` (or `none` for local SDK only)
  - `TRACING__OTLP_ENDPOINT=http://localhost:4317` (default)
  - `TRACING__SERVICE_NAME=alpha-panda` (optional; defaults per component)
  - `TRACING__SAMPLING_RATIO=1.0`

What gets instrumented
- Kafka Producer: span `kafka.produce` with attributes (destination topic, key, event.type, broker); injects `traceparent` and `correlation_id` headers.
- Kafka Consumer: span `kafka.consume` with attributes (source topic, broker, event.id, event.type); extracts header context.
- Services:
  - Strategy Runner: `strategy.process_tick`, `strategy.emit_signal`
  - Risk Manager: `risk.validate_signal`, `risk.emit_validated`, `risk.emit_rejected`
  - Trading Engine: `trading.execute`, `trading.emit_result`
- FastAPI: initializes tracing during app startup if enabled.

Files
- `core/observability/tracing.py` — initialization helpers and safe shims
- `core/streaming/infrastructure/message_producer.py` — producer spans + header injection
- `core/streaming/reliability/reliability_layer.py` — consumer spans + context extraction
- `api/main.py` — tracing init during app creation

Collector Setup (Dev)
- Run an OTLP collector (Jaeger/Tempo/OTel Collector) that listens on gRPC `4317`.
- Set `TRACING__EXPORTER=otlp` and `TRACING__OTLP_ENDPOINT=http://localhost:4317`.

Notes
- No code changes required to enable/disable. All config‑driven.
- Keep sampling at 1.0 during development; reduce in production.
 - Sampling ratio is configurable via `TRACING__SAMPLING_RATIO` (0.0–1.0) when the SDK supports ratio-based sampling.
