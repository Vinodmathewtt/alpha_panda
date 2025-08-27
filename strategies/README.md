# Strategies Documentation

## Strategy Framework

Alpha Panda implements a **pure strategy pattern** where trading strategies are completely decoupled from infrastructure concerns.

## Strategy Architecture

### Pure Strategy Pattern
- **Inherit from BaseStrategy**: All strategies extend `BaseStrategy` class
- **Pure Functions**: Strategies receive `MarketTick`, return `TradingSignal`
- **No Infrastructure Access**: Strategies cannot directly access Kafka, database, etc.
- **Portfolio Context**: Strategies receive read-only `PortfolioContext` for position awareness

### Strategy Interface

```python
from strategies.base import BaseStrategy
from core.schemas.events import MarketTick, TradingSignal

class MyStrategy(BaseStrategy):
    def on_market_data(self, tick: MarketTick, context: PortfolioContext) -> Optional[TradingSignal]:
        """
        Process market tick and generate trading signal if conditions are met.
        
        Args:
            tick: Market data with OHLC, volume, etc.
            context: Read-only portfolio state and positions
            
        Returns:
            TradingSignal if trade conditions are met, None otherwise
        """
        # Pure strategy logic here
        return signal
```

## Available Strategies

### 1. Momentum Strategy (`strategies/momentum.py`)
- **Logic**: Detects price momentum based on moving averages
- **Signals**: Buy on upward momentum, sell on downward momentum
- **Parameters**: Configurable lookback periods and thresholds

### 2. Mean Reversion Strategy (`strategies/mean_reversion.py`)
- **Logic**: Identifies overbought/oversold conditions
- **Signals**: Contrarian trades when price deviates from mean
- **Parameters**: Standard deviation bands and reversion thresholds

## Strategy Configuration

### Database Configuration
Strategies are configured in PostgreSQL with the following fields:
- **strategy_id**: Unique identifier
- **strategy_class**: Python class name
- **parameters**: JSON configuration parameters
- **instruments**: List of tradeable instruments
- **zerodha_trading_enabled**: Per-strategy opt-in for real trading
- **risk_limits**: Position size and exposure limits

### YAML Configuration Files
Strategy parameters are stored in `strategies/configs/`:
```yaml
# momentum_strategy.yaml
name: "Simple Momentum Strategy"
parameters:
  fast_period: 10
  slow_period: 20
  threshold: 0.02
risk_limits:
  max_position_size: 1000
  max_daily_trades: 10
```

## Strategy Execution

### Strategy Runner Service
The Strategy Runner Service (`services/strategy_runner/`) hosts and executes strategies:
1. **Load Strategies**: Reads active strategies from database
2. **Filter Market Data**: Routes ticks to relevant strategies based on instrument configuration
3. **Execute Strategy Logic**: Calls `on_market_data()` method
4. **Publish Signals**: Emits signals to `{broker}.signals.raw` topic

### Broker Segregation
- **Paper Trading**: All signals go to paper trading by default
- **Zerodha Trading**: Requires explicit `zerodha_trading_enabled=true` flag per strategy
- **Dual Execution**: Same strategy can run on both paper and Zerodha simultaneously

## Development Guidelines

### Adding New Strategies
1. **Create Strategy Class**: Inherit from `BaseStrategy`
2. **Implement Logic**: Pure function in `on_market_data()`
3. **Add Configuration**: Create YAML config file
4. **Database Entry**: Insert strategy configuration
5. **Testing**: Unit test strategy logic with mock data

### Strategy Testing
```python
# Unit testing pattern
strategy = MyStrategy(config)
tick = create_test_tick()
context = create_test_context()

signal = strategy.on_market_data(tick, context)
assert signal.action == "BUY"
```

### Best Practices
- **Keep Pure**: No side effects, external API calls, or state mutation
- **Type Safety**: Use Pydantic models for all data structures
- **Error Handling**: Return None for invalid conditions, don't raise exceptions
- **Logging**: Use correlation IDs for debugging across services
- **Configuration**: Make parameters configurable via YAML/database