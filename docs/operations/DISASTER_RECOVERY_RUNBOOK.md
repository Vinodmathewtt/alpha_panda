Disaster Recovery Runbook
=========================

Scope
- Broker outages, data retention breaches, and consumer stalls.

Checklist
- Verify cluster health: rpk cluster info; brokers up; partitions status.
- Check consumer lag dashboards; identify stuck groups.
- Inspect DLQs: per-topic .dlq volumes and failure reasons.
- Validate schema compatibility if deployments changed.

Recovery Steps
1) Increase retention temporarily if at risk of losing reprocessing window.
2) Pause affected consumers; drain or replay DLQs using scripts/dlq_replay.py (dry-run first).
3) Recreate missing topics using scripts/bootstrap_topics.py with overlays (ensure RF/partitions adequate).
4) Restart services in dependency order: DB/Redis -> Auth -> Feed -> Strategy -> Risk -> Engine -> Portfolio.

Post-Recovery
- Audit DLQ reasons and fix root causes.
- Reduce retained data if increased during incident.
- Add alerts if thresholds were exceeded without notification.

