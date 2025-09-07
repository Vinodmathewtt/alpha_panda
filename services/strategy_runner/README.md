# Strategy Runner Service

## Overview

The Strategy Runner Service loads and executes trading strategies, processing market data ticks and generating trading signals. It is composition-only and strategy-agnostic at runtime (supports rules-based, ML, and hybrid strategies; legacy/classic inheritance-based strategies are not executed).

## Architecture

- **Service Layer**: Main strategy orchestration with stream processing
- **Strategy Factory**: Creates ML-ready composition executors from database configuration
- **Execution Engine**: Executes strategies against market data
- **Signal Generation**: Generates trading signals for risk validation
- **Multi-Broker Support**: Generates signals for all active brokers

## Key Features

- **Strategy Loading**: Dynamic strategy loading from database configuration
- **Market Data Processing**: Consumes market ticks and routes to interested strategies  
- **Signal Generation**: Generates trading signals based on strategy logic
- **Performance Optimization**: O(1) instrument-to-strategy mapping for efficient tick routing
- **Strategy Management**: Hot-swapping and dynamic strategy updates
- **Demo Strategy Option**: Optional low-frequency demo strategy produces a few daily signals to validate end-to-end flow without generating excessive noise.

## Data Flow

1. **Market Ticks**: Consumes `market.ticks` (shared market data)
2. **Strategy Execution**: Routes ticks to strategies based on instrument subscriptions  
3. **Signal Generation**: Strategies generate trading signals
4. **Signal Publishing**: Publishes signals to `{broker}.signals.raw` topics

## Usage

```python
from services.strategy_runner.service import StrategyRunnerService

# Initialize strategy runner
strategy_service = StrategyRunnerService(
    config=settings.redpanda,
    settings=settings,
    redis_client=redis_client,
    db_manager=db_manager
)

# Start service (loads strategies and begins processing ticks)  
await strategy_service.start()
```

## Strategy Framework

### Composition Framework
```python
from strategies.core.executor import StrategyExecutor
from strategies.validation.standard_validator import create_standard_validator
from strategies.implementations.ml_momentum import create_ml_momentum_processor

processor = create_ml_momentum_processor({"model_path": "strategies/models/momentum_v1.joblib"})
executor = StrategyExecutor(
    processor=processor,
    validator=create_standard_validator({}),
    config=strategy_config,
    context=strategy_context,
)
```

### Legacy Support
Not supported at runtime. All strategies must use composition processors composed by `StrategyExecutor` (these can be rules-based, ML, or hybrid).

## Performance Optimization

- **Reverse Mapping**: Instrument-to-strategy mapping for O(1) tick routing
- **Efficient Filtering**: Only strategies interested in an instrument process its ticks
- **Batch Processing**: Efficient strategy execution patterns

## Dependencies

- **core.streaming**: StreamServiceBuilder for market data processing
- **core.database**: Strategy configuration loading (DB only; no YAML fallback at runtime)
- **strategies.core**: Strategy framework and execution patterns
 
## Broker Routing Policy
- One broker per strategy:
  - Default broker: Paper
  - Zerodha-only: set `zerodha_trading_enabled=true` in the DB row for that strategy

## Operations
- Source of truth: `strategy_configurations` table
- Deactivate/delete legacy strategies:
  - `python scripts/db_remove_old_strategies.py --mode deactivate|delete`
- Seed ML strategies from templates during dev:
  - `python scripts/db_seed_ml_strategies.py --files strategies/configs/ml_momentum.yaml strategies/configs/ml_mean_reversion.yaml strategies/configs/ml_breakout.yaml`
- Model validation: At startup, strategies with failing model load are skipped and logged
- ## Demo Strategy for E2E Validation
- The repository includes a low-frequency demo strategy (`strategies/implementations/low_frequency_demo.py`) designed to emit at most one signal per instrument every N seconds (default 900s).
- To try it in development:
  - Seed a DB row based on `strategies/configs/low_frequency_demo.yaml`, keeping `instrument_tokens` small (1–3).
  - Restart the runner and monitor `{broker}.signals.raw` topics for periodic signals.
