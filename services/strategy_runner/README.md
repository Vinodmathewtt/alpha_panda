# Strategy Runner Service

## Overview

The Strategy Runner Service loads and executes trading strategies, processing market data ticks and generating trading signals. It supports both legacy inheritance-based strategies and modern composition-based strategies.

## Architecture

- **Service Layer**: Main strategy orchestration with stream processing
- **Strategy Factory**: Creates strategy executors from database configuration
- **Execution Engine**: Executes strategies against market data
- **Signal Generation**: Generates trading signals for risk validation
- **Multi-Broker Support**: Generates signals for all active brokers

## Key Features

- **Strategy Loading**: Dynamic strategy loading from database configuration
- **Market Data Processing**: Consumes market ticks and routes to interested strategies  
- **Signal Generation**: Generates trading signals based on strategy logic
- **Performance Optimization**: O(1) instrument-to-strategy mapping for efficient tick routing
- **Strategy Management**: Hot-swapping and dynamic strategy updates

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

### Modern Composition Framework
```python
from strategies.core.factory import StrategyExecutor

class MomentumProcessor:
    def process_market_data(self, data: MarketData) -> List[TradingSignal]:
        # Pure strategy logic
        pass

# Strategy executor uses composition
executor = StrategyExecutor(
    processor=MomentumProcessor(),
    config=strategy_config,
    brokers=["paper", "zerodha"],
    instruments=[256265, 408065]
)
```

### Legacy Support
- Supports existing `BaseStrategy` inheritance-based strategies
- Gradual migration to composition-based framework
- Backward compatibility maintained during transition

## Performance Optimization

- **Reverse Mapping**: Instrument-to-strategy mapping for O(1) tick routing
- **Efficient Filtering**: Only strategies interested in an instrument process its ticks
- **Batch Processing**: Efficient strategy execution patterns

## Dependencies

- **core.streaming**: StreamServiceBuilder for market data processing
- **core.database**: Strategy configuration loading
- **strategies.core**: Strategy framework and execution patterns