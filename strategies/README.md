# Strategies Documentation

## Overview

- Strategy-agnostic runtime: supports rules-based, ML, and hybrid strategies.
- Composition architecture: strategy processors + validators composed by `StrategyExecutor`.
- DB as source of truth: runtime loads strategies from the database; YAML files are templates for seeding/dev only.

## Layout

```
strategies/
├── __init__.py
├── core/
│  ├── protocols.py      # StrategyProcessor, MLStrategyProcessor, StrategyValidator
│  ├── config.py         # StrategyConfig, ExecutionContext
│  ├── executor.py       # Composition-based executor
│  └── factory.py        # Strategy-agnostic registry + executor factory
├── implementations/
│  ├── momentum.py               # Rules momentum
│  ├── mean_reversion.py         # Rules mean-reversion
│  ├── rsi.py                    # Rules RSI
│  ├── low_frequency_demo.py     # Demo: low-frequency signals for E2E validation
│  ├── ml_momentum.py            # ML momentum
│  ├── ml_mean_reversion.py      # ML mean-reversion
│  ├── ml_breakout.py            # ML breakout
│  ├── hybrid_momentum.py        # Hybrid momentum (rules + ML)
│  └── hybrid_mean_reversion.py  # Hybrid mean-reversion (rules + ML)
├── ml_utils/
│  └── model_loader.py   # Cached model loader
├── validation/
│  └── standard_validator.py
└── configs/
   ├── ml_momentum.yaml         # examples/templates
   ├── ml_mean_reversion.yaml
   ├── ml_breakout.yaml
   └── low_frequency_demo.yaml
```

## Broker Routing (One per strategy)
- Default broker: Paper.
- Zerodha-only: set `zerodha_trading_enabled=true` in DB; runner routes signals only to Zerodha for that strategy.

## Implementing a Strategy
1) Implement a `StrategyProcessor` with `process_tick`, and required methods (`get_required_history_length`, `supports_instrument`, `get_strategy_name`). Optionally implement ML mixin methods (`load_model`, `extract_features`, `predict_signal`).
2) Register in `strategies/core/factory.py` (strategy-agnostic registry).
3) Create a DB row in `strategy_configurations` with fields:
   - `id` (strategy_name), `strategy_type` (e.g., `momentum`, `ml_momentum`, `hybrid_momentum`), `parameters` (e.g., model_path, lookback_periods, thresholds), `instruments` (list), `is_active`, `zerodha_trading_enabled`.
4) Restart runner or use an admin reload (future). At startup, the runner validates model availability and registers the strategy.

## Seeding and Cleanup (Dev)
- Seed ML strategies from YAML templates:
  - `python scripts/db_seed_ml_strategies.py --files strategies/configs/ml_momentum.yaml strategies/configs/ml_mean_reversion.yaml strategies/configs/ml_breakout.yaml`
- Deactivate/delete legacy strategies (non-ML):
  - `python scripts/db_remove_old_strategies.py --mode deactivate` or `--mode delete`

## Naming Convention
- Strategy implementation and config files must share the same base name.
  - Example: `ml_momentum.py` with `ml_momentum.yaml`.

## Testing Tips
- Confidence values are 0.0–1.0.
- Ensure sufficient history length according to `get_required_history_length()`.
- Model artifacts should be placed under `strategies/models/` and referenced by `parameters.model_path`.
- For ML strategies, document the expected feature vector length in config as `parameters.expected_feature_count` (e.g., 5 for `ml_momentum`, 4 for `ml_mean_reversion`/`ml_breakout`).

## Strategy Deployment (Step-by-Step)

Follow these steps to add a new strategy so it loads on next startup:

1) Create the processor
- Add `strategies/implementations/<name>.py` implementing `StrategyProcessor` (and optional ML mixins).
- Keep it pure (no infra access), fast, and light on logging.

2) Register in the factory
- In `strategies/core/factory.py`, add a mapping: `"<name>": "strategies.implementations.<name>.create_<name>_processor"`.

3) Add a YAML template (for seeding)
- Create `strategies/configs/<name>.yaml` with keys:
  - `strategy_name` (unique id),
  - `strategy_type` (must match the factory key; alias `strategy_class` also accepted),
  - `enabled` (bool),
  - `brokers` (e.g., `["paper"]` or `["zerodha"]`),
  - `instrument_tokens` (list[int]),
  - `parameters` (dict for your processor).

4) Seed the database
- Use the generic seeding script (accepts both `strategy_type` and `strategy_class`):
  - `python scripts/db_seed_ml_strategies.py --files strategies/configs/<name>.yaml`
- This upserts a row in `strategy_configurations` so the runner will load it at startup.

5) Restart and verify
- Restart the app (runner loads from DB on startup). Future: an admin reload endpoint will allow hot‑reload.
- Verify logs show the strategy loaded:
  - `Strategy Loading Summary` and `Loaded ... composition strategy: <id>` in `trading.log`.
- Confirm signals on `{broker}.signals.raw` topics and the dashboard.

Tips
- For end‑to‑end validation, the `low_frequency_demo` strategy emits a few daily signals without noise. Seed it via `strategies/configs/low_frequency_demo.yaml` and keep its instrument list small (1–3).
- Demo strategy (low_frequency_demo)
  - Purpose: produce a few signals per day to validate end-to-end flow without flooding downstream services.
  - Default cadence: ~1 signal every 15 minutes per instrument (configurable via `parameters.min_interval_seconds`).
  - Recommend limiting `instrument_tokens` to a small set (1–3) to cap daily signals.
  - Template: `strategies/configs/low_frequency_demo.yaml`.
