"""
Optional OpenTelemetry tracing helpers with safe fallbacks.
Enabled via Settings.tracing.enabled. No-ops if OTEL is unavailable.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Callable

try:
    from opentelemetry import trace, propagate
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    try:
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except Exception:  # pragma: no cover
        TraceIdRatioBased = None  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    trace = None  # type: ignore
    propagate = None  # type: ignore
    TracerProvider = None  # type: ignore
    BatchSpanProcessor = None  # type: ignore
    Resource = None  # type: ignore
    OTLPSpanExporter = None  # type: ignore


_TRACING_ENABLED = False


def init_tracing(settings, service_name: str) -> None:
    """Initialize OTEL tracing if enabled and deps present.

    - Uses OTLP exporter when configured; otherwise keeps SDK local-only or no-op.
    - Safe to call multiple times; subsequent calls are ignored.
    """
    global _TRACING_ENABLED
    try:
        if not getattr(settings, "tracing", None) or not settings.tracing.enabled:
            _TRACING_ENABLED = False
            return
        if trace is None or TracerProvider is None:
            _TRACING_ENABLED = False
            return

        resource = Resource.create({
            "service.name": settings.tracing.service_name or service_name,
            "service.namespace": "alpha-panda",
        })
        sampler = None
        try:
            ratio = float(getattr(settings.tracing, "sampling_ratio", 1.0))
            if TraceIdRatioBased is not None and 0.0 <= ratio < 1.0:
                sampler = TraceIdRatioBased(ratio)
        except Exception:
            sampler = None

        provider = TracerProvider(resource=resource, sampler=sampler)

        if settings.tracing.exporter.lower() == "otlp" and OTLPSpanExporter is not None:
            exporter = OTLPSpanExporter(endpoint=settings.tracing.otlp_endpoint)
            processor = BatchSpanProcessor(exporter)
            provider.add_span_processor(processor)

        trace.set_tracer_provider(provider)
        _TRACING_ENABLED = True
    except Exception:
        _TRACING_ENABLED = False


def get_tracer(component: str):
    """Get tracer or a no-op shim if disabled."""
    if not _TRACING_ENABLED or trace is None:
        return _NoopTracer()
    return trace.get_tracer(component)


def inject_headers(carrier: Dict[str, str]) -> Dict[str, str]:
    """Inject current context into carrier as headers; returns carrier."""
    if not _TRACING_ENABLED or propagate is None:
        return carrier
    try:
        propagate.inject(carrier)  # adds traceparent/tracestate
    except Exception:
        pass
    return carrier


def extract_headers(headers: Dict[str, str]) -> None:
    """Extract context from headers into current context."""
    if not _TRACING_ENABLED or propagate is None:
        return
    try:
        propagate.extract(headers)
    except Exception:
        pass


class _NoopSpan:
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def set_attribute(self, *args, **kwargs):
        return self


class _NoopTracer:
    def start_as_current_span(self, name: str):  # type: ignore
        return _NoopSpan()
