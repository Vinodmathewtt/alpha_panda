# Strategies Documentation

## Strategy Framework Evolution

Alpha Panda now supports **two strategy architectures** - the modern composition-based framework (recommended) and the legacy inheritance-based pattern (maintained for backward compatibility).

## Modern Architecture: Composition-Based Strategies

### Composition Pattern (Recommended)
The new composition-based architecture provides superior performance, testability, and modularity:
- **Protocol-Based Contracts**: Uses `typing.Protocol` for duck typing instead of inheritance
- **Pure Functions**: Strategy logic as pure functions with no side effects
- **Immutable Configuration**: Value objects for strategy parameters
- **Dependency Composition**: Strategies composed from processors, validators, and executors
- **O(1) Performance**: Optimized instrument routing and memory management
- **Full Type Safety**: Protocol compliance with runtime validation

### Modular Strategy Architecture

```
strategies/
├── README.md                 # This documentation file
├── __init__.py              # Main strategy exports and framework entry point
├── base/                    # Base strategy foundation components
│   ├── __init__.py         # Base component exports
│   └── base.py             # BaseStrategy class (foundation for legacy strategies)
├── legacy/                  # Inheritance-based strategies (production active)
│   ├── __init__.py         # Legacy strategy exports
│   ├── compatibility.py    # Backward compatibility adapter for legacy strategies
│   ├── momentum.py         # SimpleMomentumStrategy (currently used)
│   └── mean_reversion.py   # MeanReversionStrategy (currently used)
├── core/                    # Core composition framework components
│   ├── __init__.py         # Core framework exports
│   ├── protocols.py        # Protocol definitions (StrategyProcessor, StrategyValidator)
│   ├── config.py           # Configuration value objects (StrategyConfig, ExecutionContext)
│   ├── executor.py         # Strategy executor using composition
│   └── factory.py          # Strategy factory for creating composed strategies
├── implementations/         # Modern strategy implementations (composition-based)
│   ├── __init__.py
│   ├── momentum.py         # MomentumProcessor (pure function)
│   └── mean_reversion.py   # MeanReversionProcessor (pure function)
├── validation/              # Validation logic components
│   ├── __init__.py
│   └── standard_validator.py # Standard strategy validation logic
└── configs/                 # YAML configuration files and templates
    ├── momentum_strategy.yaml
    └── mean_reversion_strategy.yaml
```

## Legacy Architecture: Inheritance-Based Strategies

### Pure Strategy Pattern (Legacy)
- **Inherit from BaseStrategy**: Legacy strategies extend `BaseStrategy` class  
- **Generator Functions**: Strategies receive `MarketData`, yield `TradingSignal` objects
- **No Infrastructure Access**: Strategies cannot directly access Kafka, database, etc.
- **Internal History Management**: Strategies maintain their own market data history with configurable limits
- **Schema Integration**: Uses standardized `core.schemas.events` for all data models

## Strategy Implementation Examples

### Modern Composition-Based Strategy

```python
from decimal import Decimal
from typing import List, Optional
from strategies.core.protocols import StrategyProcessor, SignalResult  
from core.schemas.events import MarketTick as MarketData

class MyMomentumProcessor:
    """Pure strategy logic - no inheritance"""
    
    def __init__(self, momentum_threshold: Decimal, lookback_periods: int):
        self.momentum_threshold = momentum_threshold
        self.lookback_periods = lookback_periods
    
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """Pure function - no side effects"""
        if len(history) < self.lookback_periods:
            return None
        
        current_price = tick.last_price
        lookback_price = history[-self.lookback_periods].last_price
        momentum = (current_price - lookback_price) / lookback_price
        
        if momentum > self.momentum_threshold:
            return SignalResult(
                signal_type="BUY",
                confidence=min(float(abs(momentum) * 100), 100.0),
                quantity=100,
                price=current_price,
                reasoning=f"Strong momentum detected: {momentum:.2%}"
            )
        return None
    
    def get_required_history_length(self) -> int:
        return self.lookback_periods

# Usage with factory
from strategies.core import StrategyFactory, StrategyConfig, ExecutionContext

factory = StrategyFactory()
config = StrategyConfig(
    strategy_id="momentum_v2",
    strategy_type="momentum", 
    parameters={"momentum_threshold": "0.02", "lookback_periods": 10},
    active_brokers=["paper", "zerodha"],
    instrument_tokens=[12345],
    max_position_size=Decimal("10000"),
    risk_multiplier=Decimal("1.0")
)

context = ExecutionContext(
    broker="paper",
    portfolio_state={},
    market_session="regular",
    risk_limits={}
)

executor = factory.create_executor(config, context)
signal = executor.process_tick(market_tick)  # O(1) performance
```

### Legacy Inheritance-Based Strategy

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

### Modern Composition-Based Strategies (Recommended)

#### 1. MomentumProcessor (`strategies/implementations/momentum.py`)
- **Architecture**: Pure function with no inheritance
- **Logic**: Price momentum detection using lookback periods
- **Performance**: O(1) instrument routing, efficient memory usage
- **Signals**: BUY/SELL based on momentum threshold breaches
- **Parameters**: `momentum_threshold`, `lookback_periods`, `position_size`
- **Testing**: Property-based tests with Hypothesis for invariant validation

#### 2. MeanReversionProcessor (`strategies/implementations/mean_reversion.py`)  
- **Architecture**: Pure function with statistical calculations
- **Logic**: Z-score based overbought/oversold detection
- **Performance**: Efficient statistics computation, minimal memory footprint
- **Signals**: Contrarian trades when price exceeds standard deviation bands
- **Parameters**: `std_dev_threshold`, `lookback_periods`, `position_size`
- **Validation**: Built-in statistical validation and bounds checking

### Current Production Strategies (Inheritance-Based)

#### 1. SimpleMomentumStrategy (`strategies/momentum.py`)
- **Architecture**: Inherits from BaseStrategy 
- **Status**: **Currently Active** - Used in production, tests, and database seeding
- **Logic**: Detects price momentum based on moving averages
- **Signals**: Buy on upward momentum, sell on downward momentum  
- **Parameters**: Configurable lookback periods and thresholds
- **Usage**: Referenced in strategy factory, test suites, and seeding scripts

#### 2. MeanReversionStrategy (`strategies/mean_reversion.py`)
- **Architecture**: Inherits from BaseStrategy
- **Status**: **Currently Active** - Used in production, tests, and database seeding  
- **Logic**: Identifies overbought/oversold conditions using standard deviation
- **Signals**: Contrarian trades when price deviates from mean
- **Parameters**: Standard deviation bands and reversion thresholds
- **Usage**: Referenced in strategy factory, test suites, and seeding scripts

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
from strategies.legacy.momentum import SimpleMomentumStrategy
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

## Migration Path to Composition-Based Architecture

### Current State
- **Active**: Inheritance-based strategies are currently running in production
- **Available**: Composition-based framework is implemented and tested
- **Backward Compatible**: Legacy strategies work seamlessly with new system via compatibility adapter

### Migration Steps (Future)
1. **Parallel Development**: New strategies can be developed using composition-based framework
2. **Testing**: Validate composition-based strategies in paper trading environment
3. **Gradual Migration**: Migrate existing strategies one by one to composition pattern
4. **System Integration**: Update strategy factory and configuration management
5. **Cleanup**: Remove inheritance-based code after full migration

### Compatibility Bridge
The `compatibility.py` module allows legacy strategies to work in the new composition system:

```python
from strategies.legacy.compatibility import CompatibilityAdapter
from strategies.legacy import SimpleMomentumStrategy

# Wrap legacy strategy for use in new system
legacy_strategy = SimpleMomentumStrategy(strategy_id="legacy_momentum", parameters={})
adapter = CompatibilityAdapter(legacy_strategy)

# Adapter implements new protocol contracts
signal = adapter.process_tick(tick, history)
```

## Recent Improvements (2025-08-29)

### Architecture Evolution  
- **Composition Framework**: Implemented protocol-based strategy architecture with performance optimization
- **Dual Architecture Support**: Legacy inheritance and modern composition patterns both supported
- **Advanced Testing**: Property-based testing, fault injection, contract validation, and performance benchmarking
- **Production Monitoring**: Prometheus metrics integration and centralized metrics registry

### Enhanced Robustness & Performance
- **Schema Unification**: Eliminated data model duplication between strategies and core system
- **Confidence Field Integration**: `TradingSignal` now includes confidence scores throughout pipeline
- **Robust Tick Parsing**: Defensive parsing with comprehensive error handling and validation
- **Concurrent Signal Emission**: Parallel signal publishing for improved throughput
- **Pipeline Observability**: Full metrics integration for production monitoring
- **O(1) Performance**: Optimized instrument routing and memory management in composition framework

### Breaking Changes (Backward Compatible)
- Strategies now use `MarketTick` as `MarketData` (alias maintains compatibility)
- `TradingSignal` confidence field available (optional, defaults to None)
- Volume field changed from `volume` to `volume_traded` in MarketTick schema
- Generator pattern for signal emission (yield multiple signals per tick)
- New composition-based framework available alongside existing inheritance pattern