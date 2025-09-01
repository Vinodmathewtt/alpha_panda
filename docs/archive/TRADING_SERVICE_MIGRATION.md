# Broker-Scoped Trading Services Migration Plan (ARCHIVED)

This document is archived. The migration has been fully implemented in the codebase.

Summary:
- Legacy services `services/trading_engine/**` and `services/portfolio_manager/**` have been removed.
- Broker-scoped services are live:
  - `services/paper_trading/` (simulated execution; emits paper.orders.* and paper.pnl.snapshots)
  - `services/zerodha_trading/` (real execution; emits zerodha.orders.* and zerodha.pnl.snapshots)
- DI starts only `paper_trading_service` and `zerodha_trading_service`.
- Observability updated (Prometheus last-activity gauge; Grafana panels for trading services, DLQ, inactivity, lag).

For current architecture details, see:
- `AGENTS.md` (Trading Services Migration and scope)
- `services/paper_trading/README.md`
- `services/zerodha_trading/README.md`
- `docs/architecture/README.md`

Note: For the original, detailed step-by-step migration plan, refer to repository history of `docs/TRADING_SERVICE_MIGRATION.md` prior to archival.
