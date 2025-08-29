# Strategies Documentation

## Strategy Framework

Alpha Panda implements a **pure strategy pattern** where trading strategies are completely decoupled from infrastructure concerns.

## Strategy Architecture

### Pure Strategy Pattern
- **Inherit from BaseStrategy**: All strategies extend `BaseStrategy` class  
- **Generator Functions**: Strategies receive `MarketData`, yield `TradingSignal` objects
- **No Infrastructure Access**: Strategies cannot directly access Kafka, database, etc.
- **Internal History Management**: Strategies maintain their own market data history with configurable limits
- **Schema Integration**: Uses standardized `core.schemas.events` for all data models

### Strategy Interface

```python
from strategies.base import BaseStrategy, MarketData
from core.schemas.events import TradingSignal, SignalType
from typing import Generator
from decimal import Decimal

class MyStrategy(BaseStrategy):
    def on_market_data(self, data: MarketData) -> Generator[TradingSignal, None, None]:
        """
        Process market tick and yield trading signals.
        
        Args:
            data: Market data tick (MarketTick schema with last_price, timestamp, etc.)
            
        Yields:
            TradingSignal: Generated trading signals with confidence scores
        """
        # Add to internal history
        self._add_market_data(data)
        
        # Implement strategy logic here
        if some_condition:
            yield TradingSignal(
                strategy_id=self.strategy_id,
                instrument_token=data.instrument_token,
                signal_type=SignalType.BUY,
                quantity=100,
                price=data.last_price,
                timestamp=data.timestamp,
                confidence=0.85  # Strategy confidence score (0.0 to 1.0)
            )
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
The Strategy Runner Service (`services/strategy_runner/`) hosts and executes strategies with enhanced reliability:
1. **Load Strategies**: Reads active strategies from database with YAML fallback
2. **Efficient Routing**: Uses O(1) instrument-to-strategies mapping for performance
3. **Robust Parsing**: Defensive tick parsing with comprehensive error handling
4. **Execute Strategy Logic**: Calls `on_market_data()` method with exception isolation
5. **Concurrent Emission**: Publishes signals to `{broker}.signals.raw` topics concurrently
6. **Pipeline Metrics**: Tracks signal generation metrics for monitoring

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
from strategies.momentum import SimpleMomentumStrategy
from core.schemas.events import MarketTick
from decimal import Decimal
from datetime import datetime, timezone

# Unit testing pattern
strategy = SimpleMomentumStrategy(
    strategy_id="test_momentum",
    parameters={"momentum_threshold": 0.02, "position_size": 100},
    brokers=["paper"],
    instrument_tokens=[256265]
)

# Create test market data
tick = MarketTick(
    instrument_token=256265,
    last_price=Decimal("21500.00"),
    timestamp=datetime.now(timezone.utc),
    volume_traded=1000
)

# Test signal generation
signals = list(strategy.on_market_data(tick))
if signals:
    signal = signals[0]
    assert signal.signal_type == "BUY"
    assert signal.confidence is not None
    assert 0.0 <= signal.confidence <= 1.0
```

### Best Practices
- **Keep Pure**: No side effects, external API calls, or state mutation
- **Type Safety**: Use standardized schemas from `core.schemas.events`
- **Error Handling**: Use generators to yield multiple signals, handle exceptions gracefully
- **Confidence Scores**: Include confidence levels (0.0 to 1.0) in trading signals
- **History Management**: Use `_add_market_data()` and `get_history()` for state management
- **Configuration**: Make parameters configurable via YAML/database

## Recent Improvements (2025-08-28)

### Enhanced Robustness & Performance
- **Schema Unification**: Eliminated data model duplication between strategies and core system
- **Confidence Field Integration**: `TradingSignal` now includes confidence scores throughout pipeline
- **Robust Tick Parsing**: Defensive parsing with comprehensive error handling and validation
- **Concurrent Signal Emission**: Parallel signal publishing for improved throughput
- **Pipeline Observability**: Full metrics integration for production monitoring

### Breaking Changes (Backward Compatible)
- Strategies now use `MarketTick` as `MarketData` (alias maintains compatibility)
- `TradingSignal` confidence field available (optional, defaults to None)
- Volume field changed from `volume` to `volume_traded` in MarketTick schema
- Generator pattern for signal emission (yield multiple signals per tick)