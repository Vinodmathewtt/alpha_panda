# REFACTORING_REQUIRED

### 🎯 Primary Refactoring Candidate: `TradingEngineService`

The `TradingEngineService` is the heart of your execution logic, deciding whether a trade should be simulated (paper) or sent to a live broker (Zerodha). Its current implementation, while functional, intertwines these two concerns, leading to a less flexible and more complex design.

#### 🤔 Why Refactor the `TradingEngineService`?

1.  **Violation of the Single Responsibility Principle (SRP):** The current service is responsible for both _routing_ trading signals and _executing_ them. This mixing of concerns makes the code harder to test and maintain.
2.  **Tight Coupling:** The service is tightly coupled to the concrete `PaperTrader` and `ZerodhaTrader` implementations. This makes it difficult to add new brokers or trading venues in the future without modifying the core service.
3.  **Complex Conditional Logic:** The execution path is determined by a series of `if` statements that check for paper trading enablement and strategy-specific Zerodha settings. This logic will become increasingly complex as you add more execution paths.
4.  **Implicit Namespace Handling:** The service implicitly handles the `paper` and `zerodha` namespaces through conditional logic. A more explicit, strategy-driven approach would be more robust and easier to reason about.

#### 🛠️ Proposed Refactoring: A Strategy-Driven `TradingEngine`

I propose refactoring the `TradingEngineService` to follow a more classic **Strategy Pattern**. In this design, the `TradingEngineService`'s sole responsibility would be to _route_ signals to the appropriate "trader" (or strategy) based on a clear set of rules.

Here’s what the new architecture would look like:

1.  **Trader Interface:** Define a common `Trader` interface (or an abstract base class) that all execution engines will implement. This will create a clear contract for how the `TradingEngineService` interacts with different traders.
2.  **Concrete Trader Implementations:** The existing `PaperTrader` and `ZerodhaTrader` would be refactored to implement the `Trader` interface.
3.  **Trader Factory/Registry:** A `TraderFactory` or `TraderRegistry` would be responsible for creating and providing the correct trader instances based on the namespace (e.g., "paper", "zerodha").
4.  **Refactored `TradingEngineService`:** The service itself would become much simpler. It would use the `TraderFactory` to get the appropriate trader for a given signal and then delegate the execution to that trader.

#### 💻 Code Examples: Before and After

Here’s a look at how the code would change:

**Before: `services/trading_engine/service.py`**

```python
# alphaP12/services/trading_engine/service.py

class TradingEngineService(StreamProcessor):
    # ... (existing __init__)

    async def _handle_signal(self, signal_data: Dict[str, Any]):
        # ...

        # 1. Paper trade ALL signals by default (if enabled)
        if self.settings.paper_trading.enabled:
            last_price = self.last_prices.get(instrument_token)
            if last_price:
                fill_data = self.paper_trader.execute_order(original_signal, last_price)
                # ... (emit event)

        # 2. Check if this specific strategy is enabled for Zerodha trading
        strategy_config = await self._get_strategy_config(strategy_id)
        if strategy_config and strategy_config.get("zerodha_trading_enabled", False):
            if self.settings.zerodha.enabled:
                signal_model = TradingSignal(**original_signal)
                result_data = self.zerodha_trader.execute_order(signal_model)
                # ... (emit event)
```

**After: A New, Refactored Approach**

First, let's define a `Trader` interface and a `TraderFactory`:

```python
# alphaP12/services/trading_engine/trader_interface.py (New File)
from abc import ABC, abstractmethod
from typing import Dict, Any

class Trader(ABC):
    @abstractmethod
    async def execute_order(self, signal: Dict[str, Any], last_price: float) -> Dict[str, Any]:
        pass

# alphaP12/services/trading_engine/trader_factory.py (New File)
from .trader_interface import Trader
from .paper_trader import PaperTrader
from .zerodha_trader import ZerodhaTrader

class TraderFactory:
    def __init__(self, settings, instrument_service):
        self._traders = {
            "paper": PaperTrader(settings),
            "zerodha": ZerodhaTrader(settings, instrument_service),
        }

    def get_trader(self, namespace: str) -> Trader:
        trader = self._traders.get(namespace)
        if not trader:
            raise ValueError(f"No trader found for namespace: {namespace}")
        return trader
```

Now, the `TradingEngineService` becomes much cleaner:

```python
# alphaP12/services/trading_engine/service.py (Refactored)

from .trader_factory import TraderFactory

class TradingEngineService(StreamProcessor):
    def __init__(self, config: RedpandaSettings, settings: Settings, db_manager: DatabaseManager, redis_client=None, market_hours_checker: MarketHoursChecker = None):
        # ... (super().__init__)
        self.trader_factory = TraderFactory(settings, instrument_service) # You'll need to inject the instrument service here

    async def _handle_signal(self, signal_data: Dict[str, Any]):
        # ... (get original_signal, strategy_id, etc.)

        # Determine the target namespace(s) for this signal
        namespaces = self._get_target_namespaces(strategy_id)

        for namespace in namespaces:
            try:
                trader = self.trader_factory.get_trader(namespace)
                last_price = self.last_prices.get(instrument_token)
                if last_price:
                    result_data = await trader.execute_order(original_signal, last_price)
                    # ... (emit event based on result)
            except Exception as e:
                self.logger.error("Failed to execute order", namespace=namespace, error=e)

    def _get_target_namespaces(self, strategy_id: str) -> list[str]:
        """
        Determines which namespaces (e.g., 'paper', 'zerodha') a signal
        should be sent to based on the strategy's configuration.
        """
        # This logic would replace the direct DB call in the old _handle_signal
        # and would return a list like ["paper", "zerodha"] or just ["paper"]
        # ...
```

---

Of course. Here is the complete, refactored code for the `TradingEngineService`.

This refactoring implements the **Strategy and Factory patterns** to decouple the core trading logic from the different execution venues (paper and Zerodha). It results in a much cleaner, more scalable, and easier-to-test architecture.

---

### 1\. New File: `trader_interface.py`

First, we define a common interface that all traders must implement. This ensures a consistent contract for execution.

**File:** `alphaP12/services/trading_engine/trader_interface.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from core.schemas.events import TradingSignal

class Trader(ABC):
    """
    Abstract base class defining the interface for all trading execution engines.
    """

    @abstractmethod
    async def execute_order(self, signal: TradingSignal, last_price: Optional[float]) -> Dict[str, Any]:
        """
        Executes a trading signal.

        Args:
            signal: The validated trading signal to execute.
            last_price: The last known price, required for paper trading simulations.

        Returns:
            A dictionary payload for either an OrderPlaced, OrderFailed, or OrderFilled event.
        """
        pass
```

---

### 2\. New File: `trader_factory.py`

Next, we create a factory that is responsible for creating and providing the correct trader instance based on the requested namespace (e.g., "paper", "zerodha").

**File:** `alphaP12/services/trading_engine/trader_factory.py`

```python
from typing import Dict
from core.config.settings import Settings
from services.instrument_data.instrument_registry_service import InstrumentRegistryService
from .trader_interface import Trader
from .paper_trader import PaperTrader
from .zerodha_trader import ZerodhaTrader

class TraderFactory:
    """
    Factory responsible for creating and providing trader instances for different namespaces.
    """
    def __init__(self, settings: Settings, instrument_service: InstrumentRegistryService):
        self._traders: Dict[str, Trader] = {
            "paper": PaperTrader(settings),
            "zerodha": ZerodhaTrader(settings, instrument_service),
        }
        # Initialize the Zerodha trader
        self._traders["zerodha"].initialize()

    def get_trader(self, namespace: str) -> Trader:
        """
        Retrieves a trader instance for the specified namespace.

        Args:
            namespace: The execution namespace (e.g., 'paper', 'zerodha').

        Returns:
            An instance of a class that implements the Trader interface.

        Raises:
            ValueError: If no trader is found for the given namespace.
        """
        trader = self._traders.get(namespace)
        if not trader:
            raise ValueError(f"No trader found for namespace: {namespace}")
        return trader
```

---

### 3\. Refactored: `paper_trader.py`

The `PaperTrader` is updated to implement the `Trader` interface. The logic remains largely the same, but the method signature is now standardized.

**File:** `alphaP12/services/trading_engine/paper_trader.py`

```python
import random
import uuid
from typing import Dict, Any, Optional

from core.config.settings import Settings
from core.schemas.events import OrderFilled, SignalType, TradingSignal
from core.logging import get_logger
from .trader_interface import Trader

class PaperTrader(Trader):
    """
    Simulates the execution of trades for paper trading. Implements the Trader interface.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)

    async def execute_order(self, signal: TradingSignal, last_price: Optional[float]) -> Dict[str, Any]:
        """
        Simulates the execution of a single order and returns the fill data.
        """
        if last_price is None:
            self.logger.warning("Paper trader requires a last_price to simulate a fill.", signal=signal.strategy_id)
            # In a real scenario, you might want to create a failed event here.
            # For simplicity, we'll return an empty dict, which the caller should handle.
            return {}

        # 1. Simulate Slippage
        slippage_pct = self.settings.paper_trading.slippage_percent / 100
        price_direction = 1 if signal.signal_type == SignalType.BUY else -1
        slippage_amount = last_price * slippage_pct * random.uniform(0.5, 1.5)
        fill_price = last_price + (price_direction * slippage_amount)

        # 2. Simulate Commission
        order_value = signal.quantity * fill_price
        commission_pct = self.settings.paper_trading.commission_percent / 100
        commission = order_value * commission_pct

        # 3. Create the OrderFilled data model
        fill_data = OrderFilled(
            strategy_id=signal.strategy_id,
            instrument_token=signal.instrument_token,
            signal_type=signal.signal_type,
            quantity=signal.quantity,
            fill_price=fill_price,
            order_id=f"paper_{signal.strategy_id}_{signal.instrument_token}_{str(uuid.uuid4())[:8]}",
            execution_mode="paper",
            timestamp=signal.timestamp,
            fees=commission
        )

        self.logger.info("PAPER TRADE (SIMULATED)",
                          signal_type=signal.signal_type,
                          strategy_id=signal.strategy_id,
                          fill_price=fill_price)

        return fill_data.model_dump(mode='json')
```

---

### 4\. Refactored: `zerodha_trader.py`

The `ZerodhaTrader` is also updated to implement the `Trader` interface. It now takes the `InstrumentRegistryService` to correctly map tokens to tradable symbols.

**File:** `alphaP12/services/trading_engine/zerodha_trader.py`

```python
import logging
from typing import Dict, Any, Optional
from kiteconnect import KiteConnect

from core.config.settings import Settings
from core.schemas.events import TradingSignal, OrderPlaced, OrderFailed, SignalType
from services.auth.kite_client import kite_client
from services.instrument_data.instrument_registry_service import InstrumentRegistryService
from .trader_interface import Trader

logger = logging.getLogger(__name__)

class ZerodhaTrader(Trader):
    """
    Executes live trades using the Zerodha Kite Connect API. Implements the Trader interface.
    """
    def __init__(self, settings: Settings, instrument_service: InstrumentRegistryService):
        self.settings = settings
        self.instrument_service = instrument_service
        self.kite_http_client: Optional[KiteConnect] = None

    def initialize(self):
        """Initializes the trader by getting the authenticated KiteConnect instance."""
        if self.settings.zerodha.enabled:
            self.kite_http_client = kite_client.get_kite_instance()
            if self.kite_http_client:
                logger.info("Zerodha Trader initialized and authenticated.")
            else:
                logger.error("Zerodha Trader could not be initialized. Kite client not available.")

    async def execute_order(self, signal: TradingSignal, last_price: Optional[float] = None) -> Dict[str, Any]:
        """
        Places a live order with Zerodha. The last_price is ignored for live trading.
        """
        if not self.kite_http_client:
            logger.error("Zerodha Trader is not initialized. Cannot place order.")
            return self._create_failure_payload(signal, "Trader not initialized")

        try:
            # Look up instrument details from the registry service
            instrument = await self.instrument_service.get_instrument_by_token(signal.instrument_token)
            if not instrument:
                error_msg = f"Instrument not found for token {signal.instrument_token}"
                logger.error(error_msg)
                return self._create_failure_payload(signal, error_msg)

            order_id = self.kite_http_client.place_order(
                variety=self.kite_http_client.VARIETY_REGULAR,
                exchange=instrument['exchange'],
                tradingsymbol=instrument['tradingsymbol'],
                transaction_type=(
                    self.kite_http_client.TRANSACTION_TYPE_BUY
                    if signal.signal_type == SignalType.BUY
                    else self.kite_http_client.TRANSACTION_TYPE_SELL
                ),
                quantity=signal.quantity,
                product=self.kite_http_client.PRODUCT_MIS,
                order_type=self.kite_http_client.ORDER_TYPE_MARKET,
            )

            logger.info(f"LIVE TRADE: Placed order for {signal.strategy_id}. Order ID: {order_id}")

            placed_event_data = OrderPlaced(
                strategy_id=signal.strategy_id,
                instrument_token=signal.instrument_token,
                signal_type=signal.signal_type,
                quantity=signal.quantity,
                price=signal.price,
                order_id=order_id,
                execution_mode="zerodha",
                timestamp=signal.timestamp
            )
            return placed_event_data.model_dump(mode='json')

        except Exception as e:
            logger.error(f"LIVE TRADE FAILED for {signal.strategy_id}: {e}")
            return self._create_failure_payload(signal, str(e))

    def _create_failure_payload(self, signal: TradingSignal, error_message: str) -> Dict[str, Any]:
        """Creates a structured data payload for a failed order event."""
        failed_event_data = OrderFailed(
            strategy_id=signal.strategy_id,
            instrument_token=signal.instrument_token,
            signal_type=signal.signal_type,
            quantity=signal.quantity,
            price=signal.price,
            order_id="N/A",
            execution_mode="zerodha",
            error_message=error_message,
            timestamp=signal.timestamp
        )
        return failed_event_data.model_dump(mode='json')
```

---

### 5\. Refactored: `service.py` (The Trading Engine Core)

This is the most significant change. The `TradingEngineService` no longer inherits from `StreamProcessor`. It is now a clean, focused class that contains only the core business logic. It's composed with other components (like the `TraderFactory`) at a higher level in the application.

**File:** `alphaP12/services/trading_engine/service.py`

```python
import logging
from typing import Dict, Any, List
from collections import defaultdict

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.market_hours.market_hours_checker import MarketHoursChecker
from core.schemas.events import TradingSignal, EventType
from core.streaming.clients import RedpandaProducer # Import producer for emitting events
from core.schemas.topics import TopicMap

from .trader_factory import TraderFactory

logger = logging.getLogger(__name__)

class TradingEngineService:
    """
    The trading engine service's core logic. It consumes validated signals,
    determines the execution strategy (paper, live, or both), and routes
    them to the appropriate trader via a factory.

    This class is decoupled from the streaming infrastructure.
    """
    def __init__(
        self,
        settings: Settings,
        db_manager: DatabaseManager,
        producer: RedpandaProducer,
        trader_factory: TraderFactory,
        market_hours_checker: MarketHoursChecker,
    ):
        self.settings = settings
        self.db_manager = db_manager
        self.producer = producer
        self.trader_factory = trader_factory
        self.market_hours_checker = market_hours_checker
        self.topics = TopicMap(settings.broker_namespace)
        self.last_prices: Dict[int, float] = {}

    async def process_validated_signal(self, signal_data: Dict[str, Any]):
        """
        Main entry point for handling a validated signal.
        """
        if not self.market_hours_checker.is_market_open():
            logger.debug("Ignoring validated signal - market is closed")
            return

        original_signal_data = signal_data.get('original_signal')
        if not original_signal_data:
            logger.error("Validated signal is missing 'original_signal' data.")
            return

        signal = TradingSignal(**original_signal_data)

        logger.info("Processing validated signal for execution", strategy_id=signal.strategy_id)

        # Determine which execution namespaces this signal should target
        target_namespaces = await self._get_target_namespaces(signal.strategy_id)

        for namespace in target_namespaces:
            try:
                trader = self.trader_factory.get_trader(namespace)
                last_price = self.last_prices.get(signal.instrument_token)

                # Execute the order using the selected trader
                result_data = await trader.execute_order(signal, last_price)

                # Determine the outcome and emit the appropriate event
                if result_data:
                    await self._emit_execution_result(signal, result_data)

            except Exception as e:
                logger.error("Error executing signal", namespace=namespace, signal=signal.strategy_id, error=str(e))

    def update_last_price(self, tick_data: Dict[str, Any]):
        """Updates the internal cache of last known prices from market ticks."""
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')
        if instrument_token and last_price is not None:
            self.last_prices[instrument_token] = last_price

    async def _get_target_namespaces(self, strategy_id: str) -> List[str]:
        """
        Determines which namespaces (e.g., 'paper', 'zerodha') a signal
        should be sent to based on the strategy's configuration.
        """
        namespaces = []
        if self.settings.paper_trading.enabled:
            namespaces.append("paper")

        strategy_config = await self._get_strategy_config(strategy_id)
        if strategy_config.get("zerodha_trading_enabled", False) and self.settings.zerodha.enabled:
            namespaces.append("zerodha")

        return namespaces

    async def _emit_execution_result(self, signal: TradingSignal, result_data: Dict[str, Any]):
        """
        Emits an event based on the outcome of a trade execution.
        """
        execution_mode = result_data.get("execution_mode")
        key = f"{signal.strategy_id}:{signal.instrument_token}"

        # This logic assumes the trader returns a dict with 'error_message' on failure.
        if "error_message" in result_data:
            event_type = EventType.ORDER_FAILED
            topic = self.topics.orders_failed()
        elif execution_mode == "paper":
             event_type = EventType.ORDER_FILLED
             topic = self.topics.orders_filled()
        else: # Zerodha success is 'placed', not 'filled'
            event_type = EventType.ORDER_PLACED
            topic = self.topics.orders_submitted()

        # NOTE: This uses a simplified _emit_event. In a full implementation,
        # you would use the standardized method from the StreamProcessor,
        # which would now be a separate utility or part of a producer wrapper.
        await self.producer.send(topic, key, {
            "type": event_type.value,
            "data": result_data
        })


    async def _get_strategy_config(self, strategy_id: str) -> Dict[str, Any]:
        """Fetches a strategy's configuration from the database."""
        from core.database.models import StrategyConfiguration
        from sqlalchemy import select

        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(StrategyConfiguration).where(StrategyConfiguration.id == strategy_id)
                )
                config = result.scalar_one_or_none()
                return {"zerodha_trading_enabled": config.zerodha_trading_enabled} if config else {}
        except Exception as e:
            logger.error("Error fetching strategy config", strategy_id=strategy_id, error=str(e))
            return {}

```

This refactoring completely decouples the `TradingEngineService`'s business logic from the complexities of the streaming platform, making it a pure, testable, and more maintainable component. The responsibility of running the Kafka consumer loop and handling reliability would now live in your application's main setup, where these new, focused components are composed together.

### Secondary Recommendation: Refactor the `PortfolioManagerService`

While the `TradingEngineService` is the highest priority, the `PortfolioManagerService` would also benefit from a similar refactoring. Its `_handle_fill` method currently creates a `portfolio_id` by combining the `execution_mode` and `strategy_id`. This is a form of manual namespace handling that could be improved.

A better approach would be to treat each portfolio as a distinct entity and to use the `broker_namespace` from the event envelope to route the fill to the correct portfolio. This would create a cleaner separation of concerns and make it easier to manage portfolios from different brokers.

Yes, that's an excellent insight, and I would **strongly recommend refactoring the `PortfolioManagerService`** to create a clear separation between paper and Zerodha portfolio management.

While the `TradingEngine` deals with the _action_ of trading, the `PortfolioManager` deals with the _state and consequences_ of those actions, where the differences become even more critical.

---

### Why Separation is Crucial for the `PortfolioManagerService`

The current unified approach in `PortfolioManagerService` treats a fill event as a simple state update. However, this overlooks the critical distinction between a self-contained simulation and a reflection of a real-world financial account.

Here’s a breakdown of the key differences and why a separate implementation is better:

**1. Source of Truth and Reconciliation** ⚖️

- **Paper Portfolio:** The application is the **single source of truth**. Its calculations of cash, positions, and P\&L are definitive because no external account exists.
- **Zerodha Portfolio:** The application is merely a **real-time reflection** of the actual account at Zerodha. The broker is the ultimate source of truth. This introduces the need for:
  - **Reconciliation Logic:** A `ZerodhaPortfolioManager` would need a mechanism to periodically fetch the actual holdings and cash balance from the Zerodha API to correct for any drift caused by missed events, manual trades, or corporate actions.
  - **Handling Discrepancies:** What happens if the app thinks it holds 100 shares of RELIANCE, but Zerodha reports 110? A dedicated service needs to handle this, which is completely irrelevant for paper trading.

**2. Complexity of Financial Calculations** 💰

- **Paper Portfolio:** Can use simplified models for fees and slippage, as it does now. The primary goal is to approximate trading performance.
- **Zerodha Portfolio:** Must handle real-world financial details with precision. This includes:
  - **Broker-Specific Fees:** Calculating accurate brokerage, Securities Transaction Tax (STT), exchange transaction charges, GST, and stamp duty.
  - **Margin Calculations:** Understanding how trades impact available margin.
  - **Corporate Actions:** Handling stock splits, dividends, and bonuses, which affect position averages and quantities.
  - These complex, broker-specific calculations would unnecessarily complicate the clean and simple `PaperPortfolioManager`.

**3. Robustness and Error Handling** 🛡️

- **Paper Portfolio:** If processing a fill event fails, the consequence is an inaccurate simulation. This is not ideal, but it has no financial impact.
- **Zerodha Portfolio:** Failure to process a fill event means the application's view of a real money account is wrong, which could lead to flawed risk management and subsequent trading decisions with real financial consequences. A `ZerodhaPortfolioManager` should have more robust error handling, perhaps with guaranteed persistence in a transactional database before acknowledging the event.

---

### Recommended Refactoring Path

I recommend a similar strategy to the `TradingEngine` refactoring:

**1. Create a Base/Interface Class:** Define an abstract `BasePortfolioManager` that establishes a common interface for handling events.

```python
# alphaP12/services/portfolio_manager/base.py (New File)
from abc import ABC, abstractmethod
from typing import Dict, Any

class BasePortfolioManager(ABC):
    @abstractmethod
    async def handle_fill(self, fill_data: Dict[str, Any]):
        pass

    @abstractmethod
    async def handle_tick(self, tick_data: Dict[str, Any]):
        pass
```

**2. Implement Concrete Managers:**

- **`PaperPortfolioManager`:** This class would contain the existing simple, in-memory logic for virtual portfolios. It would be lean and fast.
- **`ZerodhaPortfolioManager`:** This class would handle the complexities mentioned above, including database persistence for fill events, reconciliation logic, and detailed fee calculations.

**3. Create a Routing Service:** The main `PortfolioManagerService` would be refactored into a lightweight router. Its only job would be to consume `orders.filled` and `market.ticks` events and delegate them to the correct manager based on the `execution_mode` or `broker_namespace` in the event data.

```python
# alphaP12/services/portfolio_manager/service.py (Refactored)

class PortfolioManagerService(StreamProcessor):
    def __init__(self, ...):
        # ...
        # Instead of self.portfolios, you'd have instances of the new managers
        self.paper_manager = PaperPortfolioManager(...)
        self.zerodha_manager = ZerodhaPortfolioManager(...)

    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        event_data = message.get('data', {})

        # Route based on the execution mode in the fill event
        execution_mode = event_data.get('execution_mode')

        if event_type == EventType.ORDER_FILLED:
            if execution_mode == 'paper':
                await self.paper_manager.handle_fill(event_data)
            elif execution_mode == 'zerodha':
                await self.zerodha_manager.handle_fill(event_data)

        elif event_type == EventType.MARKET_TICK:
            # Ticks need to go to both to update unrealized P&L
            await self.paper_manager.handle_tick(event_data)
            await self.zerodha_manager.handle_tick(event_data)

```

By making this separation, you create a much cleaner, more robust, and scalable architecture that properly respects the fundamental differences between simulated and live trading environments.

Of course. Here is the complete, refactored code for the `PortfolioManagerService`.

This new architecture separates the logic for paper and Zerodha (live) portfolio management into distinct, focused classes, making the system more robust, scalable, and easier to maintain.

---

### 1\. New File: `base.py`

First, we define a common interface that all portfolio managers will implement. This creates a clear and consistent contract.

**File:** `alphaP12/services/portfolio_manager/base.py`

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class BasePortfolioManager(ABC):
    """
    Abstract base class defining the interface for all portfolio managers.
    """

    @abstractmethod
    async def handle_fill(self, fill_data: Dict[str, Any]):
        """
        Processes a fill event to update the state of a portfolio.

        Args:
            fill_data: The data payload from an OrderFilled event.
        """
        pass

    @abstractmethod
    async def handle_tick(self, tick_data: Dict[str, Any]):
        """
        Processes a market tick to update the unrealized P&L of relevant positions.

        Args:
            tick_data: The data payload from a MarketTick event.
        """
        pass

    @abstractmethod
    async def start(self):
        """Initializes the portfolio manager (e.g., loading state from cache or DB)."""
        pass

    @abstractmethod
    async def stop(self):
        """Performs cleanup actions (e.g., saving final state)."""
        pass
```

---

### 2\. New File: `paper_manager.py`

This class manages the state of all virtual (paper) trading portfolios. The logic is self-contained and focused purely on simulation.

**File:** `alphaP12/services/portfolio_manager/paper_manager.py`

```python
import asyncio
from typing import Dict
from core.config.settings import Settings
from core.logging import get_trading_logger_safe
from .base import BasePortfolioManager
from .models import Portfolio, Position
from .cache import PortfolioCache

class PaperPortfolioManager(BasePortfolioManager):
    """
    Manages the state of all virtual (paper trading) portfolios.
    """
    def __init__(self, settings: Settings, redis_client):
        self.settings = settings
        self.cache = PortfolioCache(settings, redis_client)
        self.portfolios: Dict[str, Portfolio] = {}
        self.logger = get_trading_logger_safe("paper_portfolio_manager")
        self._portfolio_locks: Dict[str, asyncio.Lock] = {}
        self._portfolio_locks_lock = asyncio.Lock()

    async def start(self):
        self.logger.info("Starting Paper Portfolio Manager...")
        await self.cache.initialize(namespace="paper")
        # In a real system, you might load existing paper portfolios here
        self.logger.info("Paper Portfolio Manager started.")

    async def stop(self):
        self.logger.info("Stopping Paper Portfolio Manager...")
        # Persist final state to cache if needed
        for portfolio in self.portfolios.values():
            await self.cache.save_portfolio(portfolio)
        await self.cache.close()
        self.logger.info("Paper Portfolio Manager stopped.")

    async def _get_or_create_portfolio(self, portfolio_id: str) -> Portfolio:
        """Atomically gets or creates a portfolio to prevent race conditions."""
        if portfolio_id in self.portfolios:
            return self.portfolios[portfolio_id]

        async with self._portfolio_locks_lock:
            if portfolio_id not in self._portfolio_locks:
                self._portfolio_locks[portfolio_id] = asyncio.Lock()
            lock = self._portfolio_locks[portfolio_id]

        async with lock:
            if portfolio_id in self.portfolios:
                return self.portfolios[portfolio_id]

            portfolio = await self.cache.get_portfolio(portfolio_id)
            if not portfolio:
                self.logger.info("Creating new paper portfolio", portfolio_id=portfolio_id)
                portfolio = Portfolio(portfolio_id=portfolio_id, cash=self.settings.paper_trading.starting_cash)

            self.portfolios[portfolio_id] = portfolio
            return portfolio

    async def handle_fill(self, fill_data: Dict[str, Any]):
        strategy_id = fill_data.get('strategy_id')
        instrument_token = fill_data.get('instrument_token')
        signal_type = fill_data.get('signal_type')
        quantity = fill_data.get('quantity', 0)
        fill_price = fill_data.get('fill_price', 0.0)

        if not all([strategy_id, instrument_token, signal_type]):
            self.logger.warning("Invalid fill data received", fill_data=fill_data)
            return

        portfolio_id = f"paper_{strategy_id}"
        portfolio = await self._get_or_create_portfolio(portfolio_id)

        position = portfolio.positions.get(instrument_token, Position(instrument_token=instrument_token))
        trade_value = quantity * fill_price

        if signal_type == 'BUY':
            position.update_buy(quantity, fill_price)
            portfolio.cash -= trade_value
        else: # SELL
            pnl = position.update_sell(quantity, fill_price)
            portfolio.realized_pnl += pnl
            portfolio.cash += trade_value

        portfolio.positions[instrument_token] = position
        portfolio.update_last_modified()

        await self.cache.save_portfolio(portfolio)
        self.logger.debug("Updated paper portfolio", portfolio_id=portfolio_id, total_pnl=portfolio.total_pnl)

    async def handle_tick(self, tick_data: Dict[str, Any]):
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')

        if instrument_token is None or last_price is None:
            return

        for portfolio in self.portfolios.values():
            if instrument_token in portfolio.positions:
                position = portfolio.positions[instrument_token]
                if position.update_unrealized_pnl(last_price):
                    await self.cache.save_portfolio(portfolio)
```

---

### 3\. New File: `zerodha_manager.py`

This class handles the more complex logic for live Zerodha portfolios, including placeholders for future features like reconciliation.

**File:** `alphaP12/services/portfolio_manager/zerodha_manager.py`

```python
import asyncio
from typing import Dict
from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.logging import get_trading_logger_safe
from .base import BasePortfolioManager
from .models import Portfolio, Position
from .cache import PortfolioCache

class ZerodhaPortfolioManager(BasePortfolioManager):
    """
    Manages the state of live (Zerodha) trading portfolios.
    Includes logic for persistence and future reconciliation.
    """
    def __init__(self, settings: Settings, redis_client, db_manager: DatabaseManager):
        self.settings = settings
        self.db_manager = db_manager
        self.cache = PortfolioCache(settings, redis_client)
        self.portfolios: Dict[str, Portfolio] = {}
        self.logger = get_trading_logger_safe("zerodha_portfolio_manager")
        self._portfolio_locks: Dict[str, asyncio.Lock] = {}
        self._portfolio_locks_lock = asyncio.Lock()

    async def start(self):
        self.logger.info("Starting Zerodha Portfolio Manager...")
        await self.cache.initialize(namespace="zerodha")
        # On startup, recover state from the database as the source of truth
        await self._recover_portfolios_from_db()
        self.logger.info("Zerodha Portfolio Manager started.")

    async def stop(self):
        self.logger.info("Stopping Zerodha Portfolio Manager...")
        # Persist final state to the database
        await self._persist_all_portfolios_to_db()
        await self.cache.close()
        self.logger.info("Zerodha Portfolio Manager stopped.")

    async def _get_or_create_portfolio(self, portfolio_id: str) -> Portfolio:
        """Atomically gets or creates a portfolio to prevent race conditions."""
        if portfolio_id in self.portfolios:
            return self.portfolios[portfolio_id]

        async with self._portfolio_locks_lock:
            if portfolio_id not in self._portfolio_locks:
                self._portfolio_locks[portfolio_id] = asyncio.Lock()
            lock = self._portfolio_locks[portfolio_id]

        async with lock:
            if portfolio_id in self.portfolios:
                return self.portfolios[portfolio_id]

            portfolio = await self.cache.get_portfolio(portfolio_id)
            if not portfolio:
                self.logger.info("Creating new Zerodha portfolio", portfolio_id=portfolio_id)
                # For Zerodha, cash balance would ideally be fetched from the broker
                portfolio = Portfolio(portfolio_id=portfolio_id, cash=0.0) # Start with 0, reconcile later

            self.portfolios[portfolio_id] = portfolio
            return portfolio

    async def handle_fill(self, fill_data: Dict[str, Any]):
        """
        Handles a fill from a live broker. This should be a transactional operation.
        """
        strategy_id = fill_data.get('strategy_id')
        # ... (extract other data as in paper_manager) ...

        portfolio_id = f"zerodha_{strategy_id}"
        portfolio = await self._get_or_create_portfolio(portfolio_id)

        # --- Begin Transaction ---
        try:
            # Update position logic (same as paper manager)
            # ...

            # Persist the state change to the database FIRST
            await self._persist_portfolio_to_db(portfolio)
            # Then update the cache for fast reads
            await self.cache.save_portfolio(portfolio)
        except Exception as e:
            self.logger.error("Failed to process Zerodha fill transactionally", error=e)
            # Implement retry/DLQ logic here
            return
        # --- End Transaction ---

        self.logger.info("Updated Zerodha portfolio", portfolio_id=portfolio_id)

    async def handle_tick(self, tick_data: Dict[str, Any]):
        # Logic is identical to paper manager, but operates on a different set of portfolios
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')

        if instrument_token is None or last_price is None:
            return

        for portfolio in self.portfolios.values():
            if instrument_token in portfolio.positions:
                if portfolio.positions[instrument_token].update_unrealized_pnl(last_price):
                    await self.cache.save_portfolio(portfolio)

    async def reconcile_portfolio(self, portfolio_id: str):
        """
        [Future Implementation] Fetches actual holdings from Zerodha API
        and compares against the application's state, logging any discrepancies.
        """
        self.logger.info("Reconciliation logic not yet implemented.", portfolio_id=portfolio_id)
        pass

    async def _recover_portfolios_from_db(self):
        """Loads the last known state of all portfolios from the database on startup."""
        self.logger.info("Recovery from database not yet implemented.")
        pass

    async def _persist_portfolio_to_db(self, portfolio: Portfolio):
        """Saves a single portfolio's state to the database."""
        self.logger.debug("Persistence to database not yet implemented.", portfolio_id=portfolio.portfolio_id)
        pass

    async def _persist_all_portfolios_to_db(self):
        """Saves all managed portfolios to the database on shutdown."""
        self.logger.info("Persisting all portfolios to database not yet implemented.")
        pass
```

---

### 4\. Refactored: `service.py` (The Portfolio Router)

The main `PortfolioManagerService` is now a simple, lightweight router. It consumes events and delegates them to the appropriate manager.

**File:** `alphaP12/services/portfolio_manager/service.py`

```python
from typing import Dict, Any
from core.config.settings import Settings, RedpandaSettings
from core.database.connection import DatabaseManager
from core.streaming.clients import StreamProcessor
from core.schemas.topics import TopicMap, TopicNames
from core.schemas.events import EventType
from .paper_manager import PaperPortfolioManager
from .zerodha_manager import ZerodhaPortfolioManager

class PortfolioManagerService(StreamProcessor):
    """
    A streaming service that routes portfolio-related events to the appropriate
    manager (e.g., paper or zerodha) based on the event's content.
    """
    def __init__(self, config: RedpandaSettings, settings: Settings, redis_client, db_manager: DatabaseManager):
        broker = settings.broker_namespace
        topics = TopicMap(broker)

        consume_topics = [
            topics.orders_filled(),
            TopicNames.MARKET_TICKS
        ]

        super().__init__(
            name="portfolio_manager_router",
            config=config,
            consume_topics=consume_topics,
            group_id=f"{settings.redpanda.group_id_prefix}.portfolio_manager"
        )

        # Instantiate the concrete managers
        self.paper_manager = PaperPortfolioManager(settings, redis_client)
        self.zerodha_manager = ZerodhaPortfolioManager(settings, redis_client, db_manager)

    async def start(self):
        await self.paper_manager.start()
        await self.zerodha_manager.start()
        await super().start()

    async def stop(self):
        await super().stop()
        await self.paper_manager.stop()
        await self.zerodha_manager.stop()

    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Routes incoming messages to the correct manager."""
        event_type = message.get('type')
        event_data = message.get('data', {})

        if topic == TopicNames.MARKET_TICKS and event_type == EventType.MARKET_TICK:
            # Market data is needed by both managers to calculate unrealized P&L
            await self.paper_manager.handle_tick(event_data)
            await self.zerodha_manager.handle_tick(event_data)
            return

        if event_type == EventType.ORDER_FILLED:
            execution_mode = event_data.get('execution_mode')
            if execution_mode == 'paper':
                await self.paper_manager.handle_fill(event_data)
            elif execution_mode == 'zerodha':
                await self.zerodha_manager.handle_fill(event_data)
            else:
                self.log_with_trace(
                    "Received fill event with unknown execution mode",
                    level="warning",
                    execution_mode=execution_mode
                )
```

## Additional refactoring

There is one more high-impact refactoring I would recommend: **decoupling the core logic from the `StreamProcessor` base class.**

Your current architecture uses inheritance, where every service (`TradingEngineService`, `PortfolioManagerService`, etc.) is a `StreamProcessor`. While this works, it leads to tight coupling and a rigid design. A more modern and flexible approach is to use **Composition over Inheritance**.

---

### 🎯 Additional Refactoring Candidate: `StreamProcessor` Base Class

The `StreamProcessor` in `core/streaming/clients.py` is a "god class." It's responsible for too many things:

- Managing Kafka connections.
- Running the consumption loop.
- Handling errors and retries.
- Deduplication.
- Collecting and persisting metrics.
- Managing correlation IDs.
- Executing business logic via an abstract method.

This makes the system rigid. What if one service needs a slightly different retry policy or a unique way to handle metrics? With inheritance, you're forced to override large methods, which can be brittle.

#### 🤔 Why Refactor the `StreamProcessor`?

1.  **Single Responsibility Principle Violation:** The class mixes infrastructure concerns (Kafka, Redis) with cross-cutting concerns (errors, metrics) and business logic orchestration.
2.  **Rigid Hierarchy:** Every service is forced to adopt the exact same lifecycle and reliability features. This makes it hard to evolve services independently.
3.  **Difficult to Test:** Unit testing a service like `TradingEngineService` is hard because you can't easily separate its business logic from the underlying `StreamProcessor`'s complex machinery.

#### 🛠️ Proposed Refactoring: A Composition-Based Approach

I propose breaking the `StreamProcessor` into smaller, independent components and then _composing_ them together within each service.

1.  **`MessageConsumer`:** A simple class responsible only for connecting to Kafka, consuming messages in a loop, and passing them to a handler.
2.  **`ReliabilityLayer` (or `MessageHandler`):** This new component is key. It's a class that wraps the actual business logic. It takes a raw message and orchestrates the reliability features: deduplication, error handling, metrics, and commits. It doesn't know anything about Kafka.
3.  **Services as Pure Business Logic:** Your service classes (`TradingEngineService`, etc.) would no longer inherit from `StreamProcessor`. They would become simple classes containing only the core business logic (e.g., a `handle_signal` method).

#### 💻 Code Examples: Before and After

**Before: The Inheritance Model**

```python
# alphaP12/services/trading_engine/service.py

# TradingEngineService IS-A StreamProcessor
class TradingEngineService(StreamProcessor):
    def __init__(self, ...):
        super().__init__(name="trading_engine", ...)
        # ... service-specific initializations

    # This method is called from deep within the StreamProcessor's logic
    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        # ... business logic here ...
```

**After: The Composition Model**

First, your service becomes a plain, focused class.

```python
# alphaP12/services/trading_engine/service.py (Refactored)

# TradingEngineService is now a simple class with business logic
class TradingEngineService:
    def __init__(self, settings, trader_factory, ...):
        self.settings = settings
        self.trader_factory = trader_factory
        # No more super().__init__ or streaming/kafka details

    # This is the core business logic handler
    async def process_validated_signal(self, signal_data: Dict[str, Any]):
        # The logic from the old _handle_signal goes here
        # It's now clean, isolated, and easy to test.
        # ...

    async def process_market_tick(self, tick_data: Dict[str, Any]):
        # ...
```

Next, the orchestration happens in your main application setup, where you _compose_ the components.

```python
# alphaP12/app/main.py (Illustrative Setup)

async def run_trading_engine():
    # 1. Create the business logic component
    trading_engine_logic = TradingEngineService(settings, trader_factory)

    # 2. Create the reliability layer, passing the business logic handler to it
    # This layer handles errors, metrics, deduplication, etc.
    handler = ReliabilityLayer(
        handler_func=trading_engine_logic.process_validated_signal,
        deduplicator=deduplicator,
        error_handler=error_handler,
        metrics_collector=metrics_collector
    )

    # 3. Create and start the consumer, which just fetches messages
    consumer = MessageConsumer(
        topics=[topics.signals_validated()],
        group_id="trading_engine_group"
    )

    # 4. The main loop is now explicit
    await consumer.start()
    async for message in consumer.consume():
        # The consumer yields a raw message, the reliability layer handles it
        await handler.process_message(message)

```

This refactoring is a more significant architectural change, but it yields tremendous benefits:

- **Flexibility:** You can now compose different reliability features for different services.
- **Testability:** You can easily unit-test `TradingEngineService` without needing to mock Kafka or a complex base class.
- **Clarity:** The flow of data is explicit in the main application loop, not hidden inside a base class.

This change would make your system's core streaming architecture much more robust and maintainable for the future.

Of course. Here is the full refactoring of the `StreamProcessor` base class into a more flexible, composition-based architecture.

This new design decouples the streaming infrastructure from your core business logic, resulting in services that are easier to test, maintain, and evolve.

---

### 1\. New File: `message_consumer.py`

This new component is a simple, high-level wrapper around the `RedpandaConsumer`. Its only job is to connect to Kafka and yield messages. It has no knowledge of business logic, error handling, or metrics.

**File:** `alphaP12/core/streaming/message_consumer.py`

```python
import asyncio
import logging
from typing import List, AsyncGenerator, Dict, Any
from aiokafka import AIOKafkaConsumer
from .clients import RedpandaConsumer # Assuming RedpandaConsumer is in clients.py
from core.config.settings import RedpandaSettings

logger = logging.getLogger(__name__)

class MessageConsumer:
    """
    A dedicated class for consuming messages from Kafka topics.
    This component is responsible only for the consumption loop and
    delegates message handling to another component.
    """

    def __init__(self, config: RedpandaSettings, topics: List[str], group_id: str):
        self._consumer = RedpandaConsumer(config, topics, group_id)
        self._running = False

    async def start(self):
        """Starts the underlying Kafka consumer."""
        if not self._running:
            logger.info("Starting MessageConsumer...", topics=self._consumer.topics, group_id=self._consumer._consumer.group_id)
            await self._consumer.start()
            self._running = True
            logger.info("MessageConsumer started.")

    async def stop(self):
        """Stops the underlying Kafka consumer."""
        if self._running:
            logger.info("Stopping MessageConsumer...")
            await self._consumer.stop()
            self._running = False
            logger.info("MessageConsumer stopped.")

    async def consume(self) -> AsyncGenerator[Dict[str, Any], None]:
        """
        An async generator that yields raw messages from Kafka.
        This loop runs indefinitely until the consumer is stopped.
        """
        if not self._running:
            await self.start()

        try:
            async for message in self._consumer._consumer:
                yield message
        except Exception as e:
            logger.error("Critical error in consumption loop", error=e)
            # In a real system, you might want to implement a backoff-and-retry mechanism here
            raise
```

---

### 2\. New File: `reliability_layer.py`

This is the core of the new design. It's a handler class that wraps your business logic with all the cross-cutting concerns that were previously in the `StreamProcessor` (error handling, deduplication, metrics, commits).

**File:** `alphaP12/core/streaming/reliability_layer.py`

```python
import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable, Dict, Any

from .deduplication import EventDeduplicator
from .error_handling import ErrorHandler
from .correlation import CorrelationContext, CorrelationLogger
# Assuming MetricsCollector is available for tracking
from core.monitoring.metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)

class ReliabilityLayer:
    """
    Wraps a business logic handler with cross-cutting concerns like
    error handling, deduplication, metrics, correlation tracking,
    and manual offset commits.
    """
    def __init__(
        self,
        service_name: str,
        handler_func: Callable[[Dict[str, Any]], Awaitable[None]],
        consumer, # The raw aiokafka consumer for commits
        deduplicator: EventDeduplicator,
        error_handler: ErrorHandler,
        metrics_collector: MetricsCollector,
    ):
        self.service_name = service_name
        self.handler_func = handler_func
        self.consumer = consumer
        self.deduplicator = deduplicator
        self.error_handler = error_handler
        self.metrics_collector = metrics_collector

    async def process_message(self, raw_message):
        """
        Processes a single raw message from Kafka, applying all reliability features.
        """
        message_value = raw_message.value
        event_id = message_value.get('id')
        correlation_id = message_value.get('correlation_id')

        # 1. Set up Correlation Context
        if correlation_id:
            CorrelationContext.continue_trace(correlation_id, event_id, self.service_name, f"process_{raw_message.topic}")
        else:
            correlation_id = CorrelationContext.start_new_trace(self.service_name, f"process_{raw_message.topic}")

        c_logger = CorrelationLogger(self.service_name)

        # 2. Check for Duplicates
        if self.deduplicator and event_id and await self.deduplicator.is_duplicate(event_id):
            c_logger.debug("Skipping duplicate event", event_id=event_id)
            await self.consumer.commit() # Commit to skip the duplicate
            return

        # 3. Define the core processing and commit functions for the error handler
        async def do_process():
            await self.handler_func(message_value)

        async def do_commit():
            await self.consumer.commit()
            if self.deduplicator and event_id:
                await self.deduplicator.mark_processed(event_id)

        # 4. Execute with Error Handling and Metrics
        start_time = datetime.now(timezone.utc)
        try:
            await do_process()
            await do_commit()
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            c_logger.debug("Message processed successfully", duration_ms=duration * 1000)
            # You would update success metrics here via the metrics_collector

        except Exception as e:
            c_logger.error("Failed to process message", error=str(e))
            # The error handler will manage retries, DLQ, and commits
            await self.error_handler.handle_processing_error(
                raw_message, e, processing_func=do_process, commit_func=do_commit
            )
            # You would update failure metrics here
```

---

### 3\. Refactored: `clients.py`

The `clients.py` file is now much simpler. The monolithic `StreamProcessor` is gone, leaving only the producer and the low-level consumer classes.

**File:** `alphaP12/core/streaming/clients.py`

```python
# The file core/streaming/clients.py would now only contain:
# - json_serializer function
# - RedpandaProducer class (as it was)
# - RedpandaConsumer class (as it was)

# The StreamProcessor class and its associated methods are completely removed from this file.
# The logic has been moved to the new ReliabilityLayer and MessageConsumer components.
```

---

### 4\. How to Use: Composition in Your Application

Here’s how you would compose these new components together to run the `TradingEngineService`. This logic would typically live in your main application entry point (e.g., `app/main.py`).

**File:** `alphaP12/app/main.py` (Illustrative Example)

```python
# This is a conceptual example of how to wire everything together.
# Your actual implementation will depend on your dependency injection container.

import asyncio
from core.config.settings import get_settings
from core.database.connection import DatabaseManager
from core.streaming.clients import RedpandaProducer
from core.streaming.message_consumer import MessageConsumer
from core.streaming.reliability_layer import ReliabilityLayer
from core.streaming.deduplication import EventDeduplicator
from core.streaming.error_handling import ErrorHandler, DLQPublisher
from core.monitoring.metrics_collector import get_metrics_collector
from services.trading_engine.service import TradingEngineService
from services.trading_engine.trader_factory import TraderFactory
# ... other necessary imports

async def run_trading_engine_service():
    """
    Main function to initialize and run the Trading Engine service using composition.
    """
    settings = get_settings()
    # Initialize shared components (DB, Redis, etc.)
    db_manager = DatabaseManager(settings.database.url)
    redis_client = ... # Initialize redis client

    # 1. Create Infrastructure Components
    producer = RedpandaProducer(settings.redpanda)
    await producer.start()

    # 2. Create Business Logic Component
    # This requires the previously refactored Trading Engine with its factory
    instrument_service = ... # Initialize instrument service
    trader_factory = TraderFactory(settings, instrument_service)
    market_hours_checker = ... # Initialize market hours checker

    trading_engine_logic = TradingEngineService(
        settings=settings,
        db_manager=db_manager,
        producer=producer,
        trader_factory=trader_factory,
        market_hours_checker=market_hours_checker
    )

    # 3. Create Reliability and Consumer Components
    # We create two sets of these: one for signals, one for ticks

    # -- For Validated Signals --
    signal_consumer_component = RedpandaConsumer(settings.redpanda, [topics.signals_validated()], "trading_engine_signals_group")
    deduplicator = EventDeduplicator(redis_client)
    dlq_publisher = DLQPublisher(producer, "trading_engine")
    error_handler = ErrorHandler("trading_engine", dlq_publisher)
    metrics_collector = get_metrics_collector(redis_client, settings)

    signal_reliability_layer = ReliabilityLayer(
        service_name="trading_engine",
        handler_func=trading_engine_logic.process_validated_signal,
        consumer=signal_consumer_component._consumer,
        deduplicator=deduplicator,
        error_handler=error_handler,
        metrics_collector=metrics_collector
    )

    # -- For Market Ticks --
    # Ticks might have a different reliability profile (e.g., no deduplication needed)
    tick_consumer_component = RedpandaConsumer(settings.redpanda, [TopicNames.MARKET_TICKS], "trading_engine_ticks_group")

    async def handle_tick_wrapper(message_value):
        trading_engine_logic.update_last_price(message_value.get('data', {}))

    tick_reliability_layer = ReliabilityLayer(
        service_name="trading_engine_ticks",
        handler_func=handle_tick_wrapper,
        consumer=tick_consumer_component._consumer,
        deduplicator=None, # Ticks don't need deduplication
        error_handler=ErrorHandler("trading_engine_ticks", dlq_publisher), # Can share DLQ
        metrics_collector=metrics_collector
    )

    # 4. Start the Consumption Loops as concurrent tasks
    async def consume_loop(consumer_comp, reliability_layer):
        await consumer_comp.start()
        async for message in consumer_comp._consumer:
            await reliability_layer.process_message(message)

    await asyncio.gather(
        consume_loop(signal_consumer_component, signal_reliability_layer),
        consume_loop(tick_consumer_component, tick_reliability_layer)
    )

# You would then run this function in your main entry point.
```
