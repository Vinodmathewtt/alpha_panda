from core.monitoring.prometheus_metrics import PrometheusMetricsCollector
from prometheus_client import CollectorRegistry, generate_latest


class DummyBuckets:
    processing_latency_seconds = [0.001, 0.01]
    market_enqueue_delay_seconds = [0.0001, 0.001]
    market_emit_latency_seconds = [0.0001, 0.001]


class DummyMonitoring:
    def __init__(self):
        self.prometheus_buckets = DummyBuckets()


class DummySettings:
    def __init__(self):
        self.monitoring = DummyMonitoring()


def test_prometheus_collector_accepts_bucket_overrides():
    reg = CollectorRegistry()
    c = PrometheusMetricsCollector(registry=reg, settings=DummySettings())
    # Record a few observations; success indicates metrics were created
    c.record_market_tick("zerodha")
    c.record_market_tick_enqueue_delay("zerodha", 0.0002)
    c.record_market_tick_emit_latency("market_feed", 0.0004)
    out = generate_latest(reg).decode()
    # Ensure our metric names are present in exposition
    assert "market_tick_enqueue_delay_seconds" in out
    assert "market_tick_emit_latency_seconds" in out

