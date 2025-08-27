"""
SLO Monitoring & Alerting Example

Demonstrates OpenTelemetry integration for distributed tracing
and metrics collection with Prometheus/Grafana.
"""

import time
from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc import trace_exporter, metric_exporter

class ServiceMetrics:
    def __init__(self, service_name: str):
        self.meter = metrics.get_meter(service_name)
        self.tracer = trace.get_tracer(service_name)
        
        # SLO metrics
        self.message_processing_latency = self.meter.create_histogram(
            "message_processing_duration_ms",
            description="Time to process message end-to-end"
        )
        
        self.dlq_rate = self.meter.create_counter(
            "dlq_messages_total", 
            description="Messages sent to DLQ"
        )
        
        self.consumer_lag = self.meter.create_gauge(
            "consumer_lag_messages",
            description="Consumer lag per partition"
        )
        
    async def trace_message_processing(self, event: dict):
        """Distributed tracing for message processing"""
        with self.tracer.start_as_current_span("process_message") as span:
            span.set_attribute("event.type", event["type"])
            span.set_attribute("event.source", event["source"])
            span.set_attribute("correlation.id", event["correlation_id"])
            
            start_time = time.time()
            try:
                await self.process_event(event)
                span.set_attribute("success", True)
            except Exception as e:
                span.set_attribute("success", False) 
                span.set_attribute("error.type", type(e).__name__)
                raise
            finally:
                latency_ms = (time.time() - start_time) * 1000
                self.message_processing_latency.record(latency_ms)

# Alert conditions (integrate with Prometheus/Grafana)
ALERTS = {
    "consumer_lag_high": "consumer_lag_messages > 5000",
    "dlq_rate_high": "rate(dlq_messages_total[5m]) > 0.01",  # >1% error rate
    "processing_latency_high": "histogram_quantile(0.95, message_processing_duration_ms) > 5000",  # P95 > 5s
    "service_unhealthy": "up == 0",
}