# Trading Engine Service Refactoring Plan

## Overview

The current `TradingEngineService` violates the Single Responsibility Principle by handling both signal routing and execution logic. This refactoring implements the **Strategy Pattern** to create a clean separation between routing decisions and execution implementations.

## Current Issues

1. **Mixed Responsibilities**: Service handles both routing logic and execution details
2. **Tight Coupling**: Direct dependencies on `PaperTrader` and `ZerodhaTrader` 
3. **Complex Conditional Logic**: Growing `if/else` chains for execution path determination
4. **Hard to Test**: Business logic tightly coupled to streaming infrastructure
5. **Difficult to Extend**: Adding new brokers requires modifying core service

## Target Architecture

### New Components Structure
```
services/trading_engine/
├── __init__.py
├── interfaces/
│   └── trader_interface.py          # New: Common Trader interface
├── traders/
│   ├── __init__.py
│   ├── paper_trader.py              # Refactored: Implements Trader interface
│   ├── zerodha_trader.py            # Refactored: Implements Trader interface
│   └── trader_factory.py            # New: Factory for trader instances
├── routing/
│   └── execution_router.py          # New: Strategy execution routing logic
└── service.py                       # Refactored: Clean, focused service
```

## Phase 1: Interface & Factory Implementation

### Step 1.1: Create Trader Interface

**File**: `services/trading_engine/interfaces/trader_interface.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from core.schemas.events import TradingSignal

class Trader(ABC):
    """Abstract base class for all trading execution engines."""
    
    @abstractmethod
    async def execute_order(self, signal: TradingSignal, last_price: Optional[float]) -> Dict[str, Any]:
        """Execute a trading signal and return result payload."""
        pass
    
    @abstractmethod
    def get_execution_mode(self) -> str:
        """Return the execution mode identifier (e.g., 'paper', 'zerodha')."""
        pass
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the trader. Returns True if successful."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Cleanup trader resources."""
        pass
```

### Step 1.2: Create Trader Factory

**File**: `services/trading_engine/traders/trader_factory.py`

```python
from typing import Dict
from core.config.settings import Settings
from services.instrument_data.instrument_registry_service import InstrumentRegistryService
from ..interfaces.trader_interface import Trader
from .paper_trader import PaperTrader
from .zerodha_trader import ZerodhaTrader

class TraderFactory:
    """Factory for creating and managing trader instances."""
    
    def __init__(self, settings: Settings, instrument_service: InstrumentRegistryService):
        self._settings = settings
        self._instrument_service = instrument_service
        self._traders: Dict[str, Trader] = {}
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize all available traders."""
        if self._initialized:
            return
            
        # Create trader instances
        self._traders = {
            "paper": PaperTrader(self._settings),
            "zerodha": ZerodhaTrader(self._settings, self._instrument_service),
        }
        
        # Initialize each trader
        for namespace, trader in self._traders.items():
            try:
                success = await trader.initialize()
                if not success:
                    logger.warning(f"Failed to initialize {namespace} trader")
            except Exception as e:
                logger.error(f"Error initializing {namespace} trader: {e}")
        
        self._initialized = True
    
    def get_trader(self, namespace: str) -> Trader:
        """Get trader instance for namespace."""
        if not self._initialized:
            raise RuntimeError("TraderFactory not initialized")
            
        trader = self._traders.get(namespace)
        if not trader:
            raise ValueError(f"No trader found for namespace: {namespace}")
        return trader
    
    async def shutdown(self) -> None:
        """Shutdown all traders."""
        for trader in self._traders.values():
            await trader.shutdown()
```

### Step 1.3: Refactor Paper Trader

**File**: `services/trading_engine/traders/paper_trader.py`

```python
from typing import Dict, Any, Optional
from ..interfaces.trader_interface import Trader
from core.schemas.events import TradingSignal, OrderFilled, SignalType
# ... existing imports

class PaperTrader(Trader):
    """Simulated trading execution implementing Trader interface."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize paper trader (always succeeds)."""
        self._initialized = True
        self.logger.info("Paper trader initialized")
        return True
    
    async def shutdown(self) -> None:
        """Cleanup paper trader resources."""
        self.logger.info("Paper trader shutdown")
    
    def get_execution_mode(self) -> str:
        return "paper"
    
    async def execute_order(self, signal: TradingSignal, last_price: Optional[float]) -> Dict[str, Any]:
        """Execute simulated order."""
        if not self._initialized:
            raise RuntimeError("PaperTrader not initialized")
            
        if last_price is None:
            return self._create_failure_payload(signal, "Last price required for paper trading")
        
        # ... existing execution logic with proper error handling
        
        return fill_data.model_dump(mode='json')
    
    def _create_failure_payload(self, signal: TradingSignal, error_message: str) -> Dict[str, Any]:
        """Create failure event payload."""
        # Implementation similar to zerodha trader
```

### Step 1.4: Refactor Zerodha Trader

**File**: `services/trading_engine/traders/zerodha_trader.py`

```python
# Similar refactoring to implement Trader interface
# Add proper initialization, shutdown, and execution mode methods
```

## Phase 2: Execution Routing Logic

### Step 2.1: Create Execution Router

**File**: `services/trading_engine/routing/execution_router.py`

```python
from typing import List, Dict, Any
from core.config.settings import Settings
from core.database.connection import DatabaseManager

class ExecutionRouter:
    """Determines execution targets for trading signals."""
    
    def __init__(self, settings: Settings, db_manager: DatabaseManager):
        self.settings = settings
        self.db_manager = db_manager
    
    async def get_target_namespaces(self, strategy_id: str) -> List[str]:
        """Determine which execution namespaces to target."""
        namespaces = []
        
        # Paper trading (if enabled globally)
        if self.settings.paper_trading.enabled:
            namespaces.append("paper")
        
        # Live trading (if enabled for strategy)
        strategy_config = await self._get_strategy_config(strategy_id)
        if (strategy_config.get("zerodha_trading_enabled", False) and 
            self.settings.zerodha.enabled):
            namespaces.append("zerodha")
        
        return namespaces
    
    async def _get_strategy_config(self, strategy_id: str) -> Dict[str, Any]:
        """Fetch strategy configuration from database."""
        # Implementation from current service
```

## Phase 3: Refactored Service

### Step 3.1: New Service Implementation

**File**: `services/trading_engine/service.py`

```python
from typing import Dict, Any
from core.streaming.clients import StreamProcessor
from .traders.trader_factory import TraderFactory
from .routing.execution_router import ExecutionRouter

class TradingEngineService(StreamProcessor):
    """Clean, focused trading engine service with composition."""
    
    def __init__(self, config: RedpandaSettings, settings: Settings, 
                 db_manager: DatabaseManager, redis_client=None, 
                 market_hours_checker: MarketHoursChecker = None, 
                 instrument_service: InstrumentRegistryService = None):
        
        super().__init__(
            name="trading_engine",
            config=config,
            consume_topics=[
                TopicMap(settings.broker_namespace).signals_validated(),
                TopicNames.MARKET_TICKS
            ],
            group_id=f"{settings.redpanda.group_id_prefix}.trading_engine",
            redis_client=redis_client
        )
        
        # Composed components
        self.trader_factory = TraderFactory(settings, instrument_service)
        self.execution_router = ExecutionRouter(settings, db_manager)
        self.market_hours_checker = market_hours_checker or MarketHoursChecker()
        
        # State management
        self.last_prices: Dict[int, float] = {}
        self.topics = TopicMap(settings.broker_namespace)
        
        # Logging
        self.logger = get_trading_logger_safe("trading_engine")
    
    async def start(self):
        """Initialize all components and start processing."""
        await self.trader_factory.initialize()
        await super().start()
        self.logger.info("Trading Engine Service started")
    
    async def stop(self):
        """Shutdown all components."""
        await super().stop()
        await self.trader_factory.shutdown()
        self.logger.info("Trading Engine Service stopped")
    
    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Route messages to appropriate handlers."""
        event_type = message.get('type')
        data = message.get('data', {})
        
        if topic == self.topics.signals_validated():
            if event_type == EventType.VALIDATED_SIGNAL:
                await self._handle_validated_signal(data)
        elif topic == TopicNames.MARKET_TICKS:
            if event_type == EventType.MARKET_TICK:
                await self._handle_market_tick(data)
    
    async def _handle_validated_signal(self, signal_data: Dict[str, Any]):
        """Process validated signal with clean routing logic."""
        if not self.market_hours_checker.is_market_open():
            self.logger.debug("Market closed - ignoring signal")
            return
        
        original_signal = signal_data.get('original_signal')
        if not original_signal:
            self.logger.error("Missing original_signal in validated signal")
            return
        
        signal = TradingSignal(**original_signal)
        
        # Get execution targets
        target_namespaces = await self.execution_router.get_target_namespaces(signal.strategy_id)
        
        # Execute on each target
        for namespace in target_namespaces:
            await self._execute_on_trader(signal, namespace)
    
    async def _execute_on_trader(self, signal: TradingSignal, namespace: str):
        """Execute signal on specific trader."""
        try:
            trader = self.trader_factory.get_trader(namespace)
            last_price = self.last_prices.get(signal.instrument_token)
            
            result_data = await trader.execute_order(signal, last_price)
            
            # Emit appropriate event based on result
            await self._emit_execution_result(signal, result_data, namespace)
            
        except Exception as e:
            self.logger.error(f"Execution failed on {namespace}", 
                            strategy_id=signal.strategy_id, error=str(e))
    
    async def _handle_market_tick(self, tick_data: Dict[str, Any]):
        """Update last price cache."""
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')
        
        if instrument_token and last_price:
            self.last_prices[instrument_token] = last_price
```

## Phase 4: Testing Strategy

### Unit Testing Approach

1. **Trader Interface Tests**: Test each trader implementation in isolation
2. **Factory Tests**: Verify correct trader instantiation and initialization
3. **Router Tests**: Test execution target determination logic
4. **Service Tests**: Test message routing and coordination

### Integration Testing

1. **End-to-End Signal Flow**: Validate complete signal processing
2. **Error Handling**: Test failure scenarios and recovery
3. **Configuration Changes**: Test dynamic configuration updates

## Migration Strategy

### Phase 1: Parallel Implementation
- Implement new components alongside existing code
- Add feature flags to switch between old and new implementations
- Comprehensive testing of new components

### Phase 2: Gradual Migration  
- Deploy new implementation in test environment
- Run A/B testing with production traffic
- Monitor performance and error rates

### Phase 3: Full Migration
- Switch production traffic to new implementation
- Remove old code and cleanup
- Update documentation and monitoring

## Benefits

1. **Separation of Concerns**: Clear boundaries between routing and execution
2. **Testability**: Each component can be tested in isolation
3. **Extensibility**: Easy to add new trader types
4. **Maintainability**: Simpler, focused components
5. **Configuration-Driven**: Easy to modify execution rules
6. **Error Isolation**: Failures in one trader don't affect others

## Risk Mitigation

1. **Backward Compatibility**: Maintain existing APIs during transition
2. **Feature Flags**: Ability to rollback to old implementation
3. **Comprehensive Testing**: Unit, integration, and load testing
4. **Monitoring**: Enhanced metrics and alerting for new components
5. **Gradual Rollout**: Phased deployment with traffic splitting

## Success Metrics

1. **Code Quality**: Reduced cyclomatic complexity, improved test coverage
2. **Performance**: No degradation in signal processing latency
3. **Reliability**: Reduced error rates and improved recovery
4. **Extensibility**: Time to add new trader types
5. **Maintainability**: Developer velocity for feature additions