# Observability Guide

A practical, end‑to‑end guide for running local observability for Alpha Panda. This covers metrics, dashboards, consumer lag, tracing, and how the pieces fit together.

## Components
- Prometheus: Scrapes metrics and powers dashboards/alerts.
- Kafka Exporter: Exposes Kafka/Redpanda consumer lag and offsets as Prometheus metrics.
- Grafana: Visualizes metrics via provisioned dashboards.
- API Metrics: FastAPI exports Prometheus metrics at `/metrics` using a shared app registry.
- Redpanda Admin Metrics: Prometheus‑compatible endpoint for broker metrics.

## Quick Start (Docker Compose)

1) Start core infra (Redpanda, Postgres, Redis):
```bash
docker compose up -d
```

2) Start observability stack (Prometheus, Kafka Exporter, Grafana):
```bash
docker compose --profile observability up -d
```

3) Start the API (for `/metrics`):
```bash
python -m api.main
# or: python cli.py api
```

4) Open the UIs:
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (default admin/admin; change it)
- Redpanda Console (optional profile): http://localhost:8080

## Ports & Targets
- Prometheus: 9090
- Grafana: 3000
- Kafka Exporter: 9308
- Redpanda Admin (metrics): 9644
- API metrics: 8000 (http://host.docker.internal:8000/metrics by default)

Note (Linux): If `host.docker.internal` is unavailable, edit `config/prometheus/prometheus.yml` and replace with your host IP (e.g., `172.17.0.1`). Then restart Prometheus:
```bash
docker compose --profile observability restart prometheus
```

## Dashboards
- Service metrics: `docs/observability/grafana/alpha_panda_prometheus_dashboard.json`
- Service metrics v2 (latency p50/p95 panels): `docs/observability/grafana/alpha_panda_prometheus_dashboard_v2.json`
- Consumer lag: `docs/observability/grafana/consumer_lag_dashboard.json`

### Adding Panels for Paper Trading Metrics
- Orders count: Panel (Stat or Bar) showing `sum by (status) (trading_orders_executed_total{broker="paper"})`.
- Fill latency (paper): Histogram or Heatmap using `paper_fill_latency_seconds{broker="paper"}` with p50/p95.
- Slippage (bps): Histogram over `paper_slippage_bps{broker="paper"}` and a Stat panel for last value.
- Cash balance: Gauge over `paper_cash_balance{broker="paper"}` with `strategy_id` as legend.

Example PromQL:
- Orders filled (paper): `sum by (order_type) (trading_orders_executed_total{broker="paper",status="filled"})`
- Paper fill latency p95: `histogram_quantile(0.95, sum(rate(paper_fill_latency_seconds_bucket[5m])) by (le))`
- Average slippage bps (5m): `avg_over_time(paper_slippage_bps_sum[5m]) / avg_over_time(paper_slippage_bps_count[5m])`
- Cash (per strategy): `paper_cash_balance{broker="paper"}`

Grafana is configured to auto‑load dashboard JSONs from the dashboards folder. Changes are picked up automatically within ~10 seconds.

## Prometheus Scrapes
Configured in `config/prometheus/prometheus.yml`:
- Redpanda admin metrics: `redpanda:9644`
- Kafka Exporter: `kafka-exporter:9308`
- API metrics: `host.docker.internal:8000/metrics` (or host IP on Linux)

### Adjusting Scrapes
- To change scrape intervals or add/remove targets, edit the YAML and restart Prometheus.

## Metrics You Should See
- Business:
  - `trading_signals_generated_total{strategy_id,broker,signal_type}`
  - `trading_orders_executed_total{broker,order_type,status}`
  - `strategy_pnl_current{strategy_id,broker}`
  - `market_ticks_received_total{source}`
  - `market_tick_enqueue_delay_seconds{source}`
  - `market_tick_emit_latency_seconds{service}`
- System:
  - `trading_events_processed_total{service,broker,event_type}`
  - `trading_processing_latency_seconds{service,event_type}`
  - `trading_pipeline_stage_healthy{stage,broker}`
  - `trading_connection_status{connection_type,broker}`
- DLQ:
  - `trading_dlq_messages_total{service,broker}`
- Logging (new):
  - `alpha_panda_logging_queue_size`
  - `alpha_panda_logging_queue_capacity`
  - `alpha_panda_logging_queue_dropped_total`
- Consumer Lag (Kafka Exporter):
  - `kafka_consumergroup_lag{consumergroup,topic,partition}`
  - `kafka_consumergroup_current_offset{consumergroup,topic,partition}`

## Adding New Metrics
Use `PrometheusMetricsCollector` and the shared registry (DI container provides one). Examples:
```python
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector

# Increment an event processed counter
metrics.record_event_processed(service="risk_manager", broker="paper", event_type="validated_signal")

# Observe latency
metrics.record_processing_time(service="strategy_runner", event_type="market_tick", duration_seconds=0.008)

# Record business metrics
metrics.record_signal_generated(strategy_id="momentum_v1", broker="paper", signal_type="BUY")
```

DLQ metrics are recorded automatically by the reliability layer when a message is published to a `.dlq` topic.

### Logging Subsystem Stats (API)
- The API exposes logging subsystem stats at `/api/v1/logs/stats`.
- Returns handler/channel status, queue size/capacity, and drop counts.

### Logging Alerts (Prometheus Rules)
- Import alert rules from `docs/observability/prometheus/logging_alerts.yml`.
- Includes:
  - `LoggingQueueDrops`: triggers on any drops in the last 5m.
  - `LoggingQueueBackpressure`: queue >80% for 5m.
  - `LoggingQueueSaturation`: queue >95% for 1m.

## Consumer Lag
- Metrics are exposed via Kafka Exporter.
- Use the Consumer Lag dashboard JSON; it aggregates lag by group and topic.
- Alerts (suggestion): Page when `sum by (consumergroup) (kafka_consumergroup_lag) > 10_000` for > 5m.
- See `docs/observability/CONSUMER_LAG.md` for setup and alert notes.

## Tracing (Optional)
- Enable via env (examples):
  - `TRACING__ENABLED=true`
  - `TRACING__EXPORTER=otlp`
  - `TRACING__OTLP_ENDPOINT=http://localhost:4317`
  - `TRACING__SAMPLING_RATIO=1.0`
- Instrumentation:
  - Producer: `kafka.produce` spans; headers injected
  - Consumer: `kafka.consume` spans; headers extracted
  - Services: Strategy (`strategy.process_tick`, `strategy.emit_signal`), Risk (`risk.validate_signal`, `risk.emit_validated`, `risk.emit_rejected`), Trading (`trading.execute`, `trading.emit_result`)

## Health Checks
- The API exposes health endpoints and aggregates checks through `ServiceHealthChecker`.
- Validate Redis/DB/Redpanda and pipeline flow via `/api/v1/monitoring/health` or dashboard API endpoints.

## Security Notes
- Change Grafana default credentials after first login.
- Prometheus and Grafana are exposed on localhost; for shared environments, secure via reverse proxies and auth.
- Keep Schema Registry and broker admin APIs internal to your network.

## Troubleshooting
- No API metrics in Prometheus:
  - Ensure the API is running on the host at port 8000.
  - On Linux, replace `host.docker.internal` with host IP in Prometheus config.
- Kafka exporter shows no data:
  - Confirm it can reach `redpanda:29092`.
  - Check container logs: `docker logs alpha-panda-kafka-exporter`.
- Dashboards are empty:
  - Confirm Prometheus targets are `UP` at http://localhost:9090/targets.
  - Ensure Grafana datasource status is `OK` (Configuration → Data sources).

## Production Tips
- Use a centralized Prometheus and managed Grafana if available.
- Set scrape intervals and retention according to data volume and SLOs.
- Add alerts for consumer lag, DLQ spikes, and pipeline health.

## Stopping/Restarting
```bash
# Stop only observability services
docker compose --profile observability down

# Restart Grafana after editing dashboards
docker compose --profile observability restart grafana
```
