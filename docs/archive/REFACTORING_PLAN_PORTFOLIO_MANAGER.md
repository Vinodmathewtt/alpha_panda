# Portfolio Manager Service Refactoring Plan

## Overview

The current `PortfolioManagerService` treats paper and live trading as variations of the same portfolio management logic. This refactoring separates them into distinct, specialized portfolio managers that acknowledge the fundamental differences between simulation and real trading.

## Current Issues

1. **Mixed Concerns**: Single service handles both paper and live portfolio logic
2. **Inadequate Separation**: Paper and live portfolios have vastly different requirements
3. **Source of Truth Confusion**: Unclear reconciliation between app state and broker state
4. **Scalability Issues**: Single service becomes complex as broker integrations grow
5. **Testing Complexity**: Hard to test paper and live logic independently

## Target Architecture

### New Components Structure
```
services/portfolio_manager/
├── __init__.py
├── interfaces/
│   └── base_portfolio_manager.py    # New: Common interface
├── managers/
│   ├── __init__.py
│   ├── paper_manager.py             # New: Paper-specific logic
│   ├── zerodha_manager.py           # New: Live trading logic
│   └── manager_factory.py           # New: Manager factory
├── reconciliation/
│   ├── __init__.py
│   ├── broker_reconciler.py         # New: Broker state reconciliation
│   └── position_matcher.py          # New: Position matching logic
├── persistence/
│   ├── __init__.py
│   ├── database_persister.py        # New: Database persistence
│   └── cache_manager.py             # Enhanced: Cache management
└── service.py                       # Refactored: Router service
```

## Phase 1: Base Interface & Factory

### Step 1.1: Create Base Portfolio Manager Interface

**File**: `services/portfolio_manager/interfaces/base_portfolio_manager.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class BasePortfolioManager(ABC):
    """Abstract base class for all portfolio managers."""
    
    @abstractmethod
    async def handle_fill(self, fill_data: Dict[str, Any]) -> None:
        """Process an order fill event."""
        pass
    
    @abstractmethod  
    async def handle_tick(self, tick_data: Dict[str, Any]) -> None:
        """Process market tick for unrealized P&L updates."""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Initialize the portfolio manager."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Shutdown and cleanup portfolio manager."""
        pass
    
    @abstractmethod
    async def get_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Retrieve portfolio state."""
        pass
    
    @abstractmethod
    async def reconcile_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Reconcile portfolio state with external sources."""
        pass
```

### Step 1.2: Create Manager Factory

**File**: `services/portfolio_manager/managers/manager_factory.py`

```python
from typing import Dict
from core.config.settings import Settings
from core.database.connection import DatabaseManager
from ..interfaces.base_portfolio_manager import BasePortfolioManager
from .paper_manager import PaperPortfolioManager
from .zerodha_manager import ZerodhaPortfolioManager

class PortfolioManagerFactory:
    """Factory for creating portfolio managers by execution mode."""
    
    def __init__(self, settings: Settings, redis_client, db_manager: DatabaseManager):
        self._settings = settings
        self._redis_client = redis_client
        self._db_manager = db_manager
        self._managers: Dict[str, BasePortfolioManager] = {}
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize all portfolio managers."""
        if self._initialized:
            return
        
        # Create manager instances
        self._managers = {
            "paper": PaperPortfolioManager(
                self._settings, 
                self._redis_client
            ),
            "zerodha": ZerodhaPortfolioManager(
                self._settings, 
                self._redis_client, 
                self._db_manager
            ),
        }
        
        # Initialize each manager
        for execution_mode, manager in self._managers.items():
            await manager.start()
            logger.info(f"Initialized {execution_mode} portfolio manager")
        
        self._initialized = True
    
    def get_manager(self, execution_mode: str) -> BasePortfolioManager:
        """Get manager for execution mode."""
        if not self._initialized:
            raise RuntimeError("PortfolioManagerFactory not initialized")
            
        manager = self._managers.get(execution_mode)
        if not manager:
            raise ValueError(f"No portfolio manager for execution mode: {execution_mode}")
        return manager
    
    async def shutdown(self) -> None:
        """Shutdown all managers."""
        for manager in self._managers.values():
            await manager.stop()
```

## Phase 2: Paper Portfolio Manager

### Step 2.1: Implement Paper Portfolio Manager

**File**: `services/portfolio_manager/managers/paper_manager.py`

```python
import asyncio
from typing import Dict
from core.config.settings import Settings
from core.logging import get_trading_logger_safe
from ..interfaces.base_portfolio_manager import BasePortfolioManager
from ..models import Portfolio, Position
from ..cache import PortfolioCache

class PaperPortfolioManager(BasePortfolioManager):
    """Manages virtual (paper trading) portfolios with simple, fast logic."""
    
    def __init__(self, settings: Settings, redis_client):
        self.settings = settings
        self.cache = PortfolioCache(settings, redis_client)
        self.portfolios: Dict[str, Portfolio] = {}
        self.logger = get_trading_logger_safe("paper_portfolio_manager")
        
        # Concurrency control
        self._portfolio_locks: Dict[str, asyncio.Lock] = {}
        self._portfolio_locks_lock = asyncio.Lock()
    
    async def start(self) -> None:
        """Initialize paper portfolio manager."""
        self.logger.info("Starting Paper Portfolio Manager")
        await self.cache.initialize(namespace="paper")
        
        # Load existing paper portfolios from cache
        await self._load_portfolios_from_cache()
        
        self.logger.info("Paper Portfolio Manager started")
    
    async def stop(self) -> None:
        """Shutdown paper portfolio manager."""
        self.logger.info("Stopping Paper Portfolio Manager")
        
        # Persist final state to cache
        for portfolio in self.portfolios.values():
            await self.cache.save_portfolio(portfolio)
        
        await self.cache.close()
        self.logger.info("Paper Portfolio Manager stopped")
    
    async def handle_fill(self, fill_data: Dict[str, Any]) -> None:
        """Process fill event for paper portfolio."""
        strategy_id = fill_data.get('strategy_id')
        if not strategy_id:
            self.logger.warning("Fill missing strategy_id", fill_data=fill_data)
            return
        
        portfolio_id = f"paper_{strategy_id}"
        portfolio = await self._get_or_create_portfolio(portfolio_id)
        
        # Process fill with simplified paper trading logic
        await self._process_fill(portfolio, fill_data)
        
        # Save to cache immediately
        await self.cache.save_portfolio(portfolio)
        
        self.logger.info("Updated paper portfolio", 
                        portfolio_id=portfolio_id,
                        total_pnl=portfolio.total_pnl)
    
    async def handle_tick(self, tick_data: Dict[str, Any]) -> None:
        """Update unrealized P&L for all paper portfolios."""
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')
        
        if not all([instrument_token, last_price]):
            return
        
        updated_portfolios = []
        for portfolio in self.portfolios.values():
            if instrument_token in portfolio.positions:
                position = portfolio.positions[instrument_token]
                if position.update_unrealized_pnl(last_price):
                    portfolio.update_totals()
                    updated_portfolios.append(portfolio)
        
        # Batch save updated portfolios
        for portfolio in updated_portfolios:
            await self.cache.save_portfolio(portfolio)
    
    async def get_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Get portfolio state."""
        portfolio = await self._get_or_create_portfolio(portfolio_id)
        return portfolio.model_dump()
    
    async def reconcile_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """For paper portfolios, reconciliation is a no-op."""
        self.logger.debug("Paper portfolio reconciliation not required", 
                         portfolio_id=portfolio_id)
        return {"status": "no_reconciliation_needed", "reason": "paper_trading"}
    
    async def _get_or_create_portfolio(self, portfolio_id: str) -> Portfolio:
        """Thread-safe portfolio creation."""
        # Fast path: portfolio exists
        if portfolio_id in self.portfolios:
            return self.portfolios[portfolio_id]
        
        # Get or create lock
        async with self._portfolio_locks_lock:
            if portfolio_id not in self._portfolio_locks:
                self._portfolio_locks[portfolio_id] = asyncio.Lock()
            lock = self._portfolio_locks[portfolio_id]
        
        # Create portfolio under lock
        async with lock:
            if portfolio_id not in self.portfolios:
                portfolio = await self.cache.get_portfolio(portfolio_id)
                if not portfolio:
                    portfolio = Portfolio(
                        portfolio_id=portfolio_id,
                        cash=self.settings.paper_trading.starting_cash
                    )
                    self.logger.info("Created new paper portfolio", 
                                   portfolio_id=portfolio_id)
                
                self.portfolios[portfolio_id] = portfolio
            
            return self.portfolios[portfolio_id]
    
    async def _process_fill(self, portfolio: Portfolio, fill_data: Dict[str, Any]) -> None:
        """Process fill with paper trading specific logic."""
        instrument_token = fill_data.get('instrument_token')
        signal_type = fill_data.get('signal_type')
        quantity = fill_data.get('quantity', 0)
        fill_price = fill_data.get('fill_price', 0.0)
        
        position = portfolio.positions.get(
            instrument_token, 
            Position(instrument_token=instrument_token)
        )
        
        trade_value = quantity * fill_price
        
        if signal_type == 'BUY':
            position.update_buy(quantity, fill_price)
            portfolio.cash -= trade_value
        else:  # SELL
            pnl = position.update_sell(quantity, fill_price)
            portfolio.realized_pnl += pnl
            portfolio.cash += trade_value
        
        portfolio.positions[instrument_token] = position
        portfolio.update_last_modified()
    
    async def _load_portfolios_from_cache(self) -> None:
        """Load existing paper portfolios from cache on startup."""
        # Implementation depends on cache design
        pass
```

## Phase 3: Live Portfolio Manager (Zerodha)

### Step 3.1: Implement Zerodha Portfolio Manager

**File**: `services/portfolio_manager/managers/zerodha_manager.py`

```python
import asyncio
from typing import Dict
from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.logging import get_trading_logger_safe
from ..interfaces.base_portfolio_manager import BasePortfolioManager
from ..models import Portfolio, Position
from ..cache import PortfolioCache
from ..reconciliation.broker_reconciler import BrokerReconciler

class ZerodhaPortfolioManager(BasePortfolioManager):
    """Manages live Zerodha portfolios with robust persistence and reconciliation."""
    
    def __init__(self, settings: Settings, redis_client, db_manager: DatabaseManager):
        self.settings = settings
        self.db_manager = db_manager
        self.cache = PortfolioCache(settings, redis_client)
        self.portfolios: Dict[str, Portfolio] = {}
        self.logger = get_trading_logger_safe("zerodha_portfolio_manager")
        
        # Reconciliation component
        self.reconciler = BrokerReconciler(settings)
        
        # Concurrency control
        self._portfolio_locks: Dict[str, asyncio.Lock] = {}
        self._portfolio_locks_lock = asyncio.Lock()
        
        # Persistence settings
        self.auto_persist = True
        self.reconciliation_interval = settings.portfolio_manager.reconciliation_interval_seconds
        self._reconciliation_task = None
    
    async def start(self) -> None:
        """Initialize Zerodha portfolio manager."""
        self.logger.info("Starting Zerodha Portfolio Manager")
        await self.cache.initialize(namespace="zerodha")
        
        # Recovery from database
        await self._recover_portfolios_from_database()
        
        # Start reconciliation task
        if self.reconciliation_interval > 0:
            self._reconciliation_task = asyncio.create_task(
                self._periodic_reconciliation_loop()
            )
        
        self.logger.info("Zerodha Portfolio Manager started")
    
    async def stop(self) -> None:
        """Shutdown Zerodha portfolio manager."""
        self.logger.info("Stopping Zerodha Portfolio Manager")
        
        # Cancel reconciliation task
        if self._reconciliation_task:
            self._reconciliation_task.cancel()
            try:
                await self._reconciliation_task
            except asyncio.CancelledError:
                pass
        
        # Persist final state
        await self._persist_all_portfolios()
        await self.cache.close()
        
        self.logger.info("Zerodha Portfolio Manager stopped")
    
    async def handle_fill(self, fill_data: Dict[str, Any]) -> None:
        """Process fill event with transactional persistence."""
        strategy_id = fill_data.get('strategy_id')
        if not strategy_id:
            self.logger.warning("Fill missing strategy_id", fill_data=fill_data)
            return
        
        portfolio_id = f"zerodha_{strategy_id}"
        portfolio = await self._get_or_create_portfolio(portfolio_id)
        
        # Transactional processing
        try:
            # Update portfolio state
            await self._process_fill(portfolio, fill_data)
            
            # Persist to database first (source of truth)
            if self.auto_persist:
                await self._persist_portfolio(portfolio)
            
            # Then update cache for fast reads
            await self.cache.save_portfolio(portfolio)
            
            self.logger.info("Updated Zerodha portfolio", 
                           portfolio_id=portfolio_id,
                           total_pnl=portfolio.total_pnl)
            
        except Exception as e:
            self.logger.error("Failed to process Zerodha fill", 
                            portfolio_id=portfolio_id, error=str(e))
            # Implement retry/DLQ logic here
            raise
    
    async def handle_tick(self, tick_data: Dict[str, Any]) -> None:
        """Update unrealized P&L (cache only for performance)."""
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')
        
        if not all([instrument_token, last_price]):
            return
        
        updated_portfolios = []
        for portfolio in self.portfolios.values():
            if instrument_token in portfolio.positions:
                position = portfolio.positions[instrument_token]
                if position.update_unrealized_pnl(last_price):
                    portfolio.update_totals()
                    updated_portfolios.append(portfolio)
        
        # Only cache update for ticks (database persistence handled separately)
        for portfolio in updated_portfolios:
            await self.cache.save_portfolio(portfolio)
    
    async def get_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Get portfolio with option to reconcile."""
        portfolio = await self._get_or_create_portfolio(portfolio_id)
        return portfolio.model_dump()
    
    async def reconcile_portfolio(self, portfolio_id: str) -> Dict[str, Any]:
        """Reconcile portfolio with Zerodha broker state."""
        try:
            portfolio = await self._get_or_create_portfolio(portfolio_id)
            reconciliation_result = await self.reconciler.reconcile_portfolio(
                portfolio_id, portfolio
            )
            
            if reconciliation_result.get("discrepancies_found"):
                # Update portfolio with reconciled data
                reconciled_portfolio = reconciliation_result.get("reconciled_portfolio")
                if reconciled_portfolio:
                    self.portfolios[portfolio_id] = reconciled_portfolio
                    await self._persist_portfolio(reconciled_portfolio)
                    await self.cache.save_portfolio(reconciled_portfolio)
                    
                    self.logger.warning("Portfolio reconciliation found discrepancies",
                                      portfolio_id=portfolio_id,
                                      discrepancies=reconciliation_result.get("discrepancies"))
            
            return reconciliation_result
            
        except Exception as e:
            self.logger.error("Portfolio reconciliation failed",
                            portfolio_id=portfolio_id, error=str(e))
            return {"status": "reconciliation_failed", "error": str(e)}
    
    async def _periodic_reconciliation_loop(self) -> None:
        """Periodic reconciliation with broker."""
        while True:
            try:
                await asyncio.sleep(self.reconciliation_interval)
                
                for portfolio_id in list(self.portfolios.keys()):
                    await self.reconcile_portfolio(portfolio_id)
                    # Small delay between reconciliations to avoid rate limits
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in reconciliation loop", error=str(e))
    
    # ... additional methods for persistence, recovery, etc.
```

## Phase 4: Router Service

### Step 4.1: Refactored Portfolio Manager Service

**File**: `services/portfolio_manager/service.py`

```python
from typing import Dict, Any
from core.streaming.clients import StreamProcessor
from core.schemas.topics import TopicMap, TopicNames
from core.schemas.events import EventType
from .managers.manager_factory import PortfolioManagerFactory

class PortfolioManagerService(StreamProcessor):
    """Router service that delegates to appropriate portfolio managers."""
    
    def __init__(self, config: RedpandaSettings, settings: Settings, 
                 redis_client, db_manager: DatabaseManager):
        
        broker = settings.broker_namespace
        topics = TopicMap(broker)
        
        consume_topics = [
            topics.orders_filled(),   # broker-specific fills
            TopicNames.MARKET_TICKS   # shared market data
        ]
        
        super().__init__(
            name="portfolio_manager",
            config=config,
            consume_topics=consume_topics,
            group_id=f"{settings.redpanda.group_id_prefix}.portfolio_manager"
        )
        
        # Factory for managing different portfolio managers
        self.manager_factory = PortfolioManagerFactory(
            settings, redis_client, db_manager
        )
        
        self.logger = get_trading_logger_safe("portfolio_manager_service")
    
    async def start(self):
        """Initialize factory and start service."""
        await self.manager_factory.initialize()
        await super().start()
        self.logger.info("Portfolio Manager Service started")
    
    async def stop(self):
        """Shutdown factory and stop service."""
        await super().stop()
        await self.manager_factory.shutdown()
        self.logger.info("Portfolio Manager Service stopped")
    
    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Route messages to appropriate managers."""
        event_type = message.get('type')
        event_data = message.get('data', {})
        
        if event_type == EventType.ORDER_FILLED:
            await self._route_fill_event(event_data)
        elif event_type == EventType.MARKET_TICK:
            await self._route_tick_event(event_data)
    
    async def _route_fill_event(self, fill_data: Dict[str, Any]):
        """Route fill event to correct portfolio manager."""
        execution_mode = fill_data.get('execution_mode')
        if not execution_mode:
            self.logger.warning("Fill event missing execution_mode", fill_data=fill_data)
            return
        
        try:
            manager = self.manager_factory.get_manager(execution_mode)
            await manager.handle_fill(fill_data)
        except Exception as e:
            self.logger.error("Error routing fill event",
                            execution_mode=execution_mode, error=str(e))
    
    async def _route_tick_event(self, tick_data: Dict[str, Any]):
        """Route tick to all portfolio managers."""
        # Both paper and live portfolios need market data for unrealized P&L
        try:
            paper_manager = self.manager_factory.get_manager("paper")
            await paper_manager.handle_tick(tick_data)
            
            zerodha_manager = self.manager_factory.get_manager("zerodha")
            await zerodha_manager.handle_tick(tick_data)
            
        except Exception as e:
            self.logger.error("Error routing tick event", error=str(e))
```

## Phase 5: Broker Reconciliation

### Step 5.1: Broker Reconciler Implementation

**File**: `services/portfolio_manager/reconciliation/broker_reconciler.py`

```python
from typing import Dict, Any, Optional
from core.config.settings import Settings
from services.auth.kite_client import kite_client
from ..models import Portfolio, Position

class BrokerReconciler:
    """Reconciles portfolio state with Zerodha broker."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.kite_client = None
    
    async def initialize(self) -> bool:
        """Initialize broker connection."""
        try:
            self.kite_client = kite_client.get_kite_instance()
            return self.kite_client is not None
        except Exception:
            return False
    
    async def reconcile_portfolio(self, portfolio_id: str, 
                                 app_portfolio: Portfolio) -> Dict[str, Any]:
        """Reconcile app portfolio with broker state."""
        if not self.kite_client:
            return {"status": "no_broker_connection"}
        
        try:
            # Fetch actual positions from Zerodha
            broker_positions = await self._fetch_broker_positions()
            
            # Compare with app portfolio
            discrepancies = self._compare_positions(
                app_portfolio, broker_positions
            )
            
            if discrepancies:
                # Create reconciled portfolio
                reconciled_portfolio = self._create_reconciled_portfolio(
                    app_portfolio, broker_positions
                )
                
                return {
                    "status": "reconciliation_complete",
                    "discrepancies_found": True,
                    "discrepancies": discrepancies,
                    "reconciled_portfolio": reconciled_portfolio
                }
            else:
                return {
                    "status": "reconciliation_complete", 
                    "discrepancies_found": False
                }
                
        except Exception as e:
            return {
                "status": "reconciliation_failed",
                "error": str(e)
            }
    
    async def _fetch_broker_positions(self) -> Dict[str, Any]:
        """Fetch current positions from Zerodha."""
        # Implementation depends on Kite Connect API
        pass
    
    def _compare_positions(self, app_portfolio: Portfolio, 
                          broker_positions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Compare app and broker positions."""
        # Implementation for position comparison
        pass
    
    def _create_reconciled_portfolio(self, app_portfolio: Portfolio,
                                   broker_positions: Dict[str, Any]) -> Portfolio:
        """Create reconciled portfolio using broker as source of truth."""
        # Implementation for reconciliation logic
        pass
```

## Benefits of This Architecture

### 1. Clear Separation of Concerns
- **Paper Manager**: Fast, simple simulation logic
- **Live Manager**: Robust persistence and reconciliation
- **Router Service**: Clean message routing

### 2. Appropriate Complexity
- Paper portfolios: Minimal complexity for simulation
- Live portfolios: Full complexity for real money management

### 3. Independent Evolution
- Each manager can evolve independently
- Easy to add new broker managers
- Different persistence strategies per manager

### 4. Better Testing
- Unit test each manager in isolation  
- Test different failure scenarios per manager type
- Mock broker interactions for live manager testing

### 5. Operational Excellence
- Different monitoring strategies per manager
- Reconciliation only where needed (live portfolios)
- Appropriate error handling per context

## Migration Strategy

### Phase 1: Parallel Implementation (Week 1-2)
- Implement new interfaces and base classes
- Create paper manager with existing logic
- Add comprehensive unit tests

### Phase 2: Live Manager (Week 3-4)  
- Implement Zerodha manager with persistence
- Add reconciliation framework
- Integration testing with test Zerodha account

### Phase 3: Router Migration (Week 5)
- Implement new router service
- Deploy with feature flags for gradual rollout
- Monitor performance and correctness

### Phase 4: Cleanup (Week 6)
- Remove old code
- Update documentation
- Performance optimization

## Success Metrics

1. **Correctness**: Portfolio state matches broker state within tolerance
2. **Performance**: No degradation in tick processing latency
3. **Reliability**: Reduced error rates in portfolio updates
4. **Maintainability**: Faster development of portfolio features
5. **Observability**: Better metrics and alerts for portfolio health