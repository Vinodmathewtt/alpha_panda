Consumer Lag Monitoring
=======================

Overview
- Monitor per-consumer-group and per-topic lag to catch stalls and backpressure early.
- Use Kafka Exporter (Prometheus) or Redpanda’s built-in metrics, and Grafana panels.

Setup
- Run Kafka Exporter alongside Redpanda.
- Scrape exporter with Prometheus; import the provided Grafana dashboard JSON.

Key Metrics
- kafka_consumergroup_current_offset
- kafka_consumergroup_lag
- kafka_topic_partition_current_offset

Dashboard
- See grafana/consumer_lag_dashboard.json for a starter dashboard.

Alerting
- Alert when lag > threshold per service for N minutes.

