import logging
from core.logging.enhanced_logging import AccessLogEnricherFilter
from core.logging.correlation import CorrelationIdManager


def test_access_log_enricher_adds_route_template_and_http_fields():
    CorrelationIdManager.set_correlation_context(route_template="/api/v1/items/{id}")
    f = AccessLogEnricherFilter()
    msg = 'h=127.0.0.1 r="GET /api/v1/items/123 HTTP/1.1" s=200 L=0.012 a="pytest"'
    rec = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    ok = f.filter(rec)
    assert ok is True
    assert getattr(rec, "http_method") == "GET"
    assert getattr(rec, "http_path").startswith("/api/v1/items/")
    assert getattr(rec, "http_route_template") == "/api/v1/items/{id}"

