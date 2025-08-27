Of course. Here are the complete code and explanations for two classic example strategies, `momentum.py` and `mean_reversion.py`, refactored to fit the new "pure" strategy design.

These files would be placed in your new `strategies/` directory. They are completely decoupled from the application's infrastructure, making them highly testable and reusable.

### Prerequisite: `strategies/base.py`

First, we need to define the common building blocks that all strategies will use. This includes the abstract base class and the Pydantic data models for communication.

```python
# AlphasPT_v2/strategies/base.py

from abc import ABC, abstractmethod
from typing import Generator, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from collections import deque

# --- Data Models for Communication ---

class MarketData(BaseModel):
    """
    A standardized, immutable representation of a single market data tick.
    """
    instrument_token: int
    timestamp: datetime
    last_price: float

class TradingSignal(BaseModel):
    """
    A standardized, immutable representation of a trading signal.
    This is the primary output of a strategy.
    """
    strategy_id: str
    instrument_token: int
    signal_type: str  # 'BUY' or 'SELL'
    quantity: int
    order_type: str   # e.g., 'MARKET', 'LIMIT'
    price: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class PortfolioContext(BaseModel):
    """
    A read-only snapshot of the current portfolio state, passed to the
    strategy on every tick.
    """
    positions: Dict[int, int] = Field(default_factory=dict) # instrument_token -> quantity
    cash: float

# --- Abstract Base Class for All Strategies ---

class BaseStrategy(ABC):
    """
    The pure, abstract base class for all trading strategies.

    A strategy's sole responsibility is to process market and portfolio
    data and yield trading signals. It is completely decoupled from the
    live infrastructure (event bus, trading engines).
    """
    def __init__(self, strategy_id: str, parameters: Dict[str, Any]):
        self.strategy_id = strategy_id
        self.parameters = parameters

    @abstractmethod
    def on_market_data(
        self,
        data: MarketData,
        portfolio: PortfolioContext
    ) -> Generator[TradingSignal, None, None]:
        """
        Processes a new piece of market data and yields trading signals.

        Args:
            data: The latest market data event for a subscribed instrument.
            portfolio: A read-only snapshot of the current portfolio state.

        Yields:
            Zero or more TradingSignal objects.
        """
        yield # This makes the method a generator

```

**Explanation:**

- **Data Contracts**: The Pydantic models (`MarketData`, `TradingSignal`, `PortfolioContext`) act as strict data contracts. This ensures that data flowing between the infrastructure (the `StrategyRunner`) and the pure logic (the `Strategy`) is always in a predictable format.
- **`BaseStrategy`**: This abstract class defines the required interface for any strategy. The `on_market_data` method is the core entry point where the strategy's logic is executed.

---

### 1\. `strategies/momentum.py`

This strategy implements a simple momentum logic: "If the price has gone up by X% over the last N ticks, buy. If it has gone down by X%, sell."

```python
# AlphasPT_v2/strategies/momentum.py

from collections import deque
from typing import Generator, Dict, Any

from .base import BaseStrategy, MarketData, PortfolioContext, TradingSignal

class SimpleMomentumStrategy(BaseStrategy):
    """
    A pure momentum strategy that generates signals based on price changes.

    This strategy is completely decoupled from the live trading infrastructure.
    It maintains its own state and yields signals when its logic is triggered.
    """
    def __init__(self, strategy_id: str, parameters: Dict[str, Any]):
        super().__init__(strategy_id, parameters)

        # Validate and extract parameters with defaults
        self.lookback_period = int(parameters.get("lookback_period", 20))
        self.momentum_threshold = float(parameters.get("momentum_threshold", 0.01)) # 1%

        # Internal state for the strategy
        self.price_history = deque(maxlen=self.lookback_period)

    def on_market_data(
        self,
        data: MarketData,
        portfolio: PortfolioContext
    ) -> Generator[TradingSignal, None, None]:
        """
        Processes a market tick and yields a trading signal if momentum is detected.
        """
        current_price = data.last_price
        self.price_history.append(current_price)

        # Wait until we have enough data to calculate momentum
        if len(self.price_history) < self.lookback_period:
            return

        oldest_price = self.price_history[0]
        price_change_pct = (current_price - oldest_price) / oldest_price

        # --- Buy Signal Logic ---
        # If momentum is positive and we don't have a long position
        if price_change_pct > self.momentum_threshold:
            current_position = portfolio.positions.get(data.instrument_token, 0)
            if current_position <= 0:
                yield TradingSignal(
                    strategy_id=self.strategy_id,
                    instrument_token=data.instrument_token,
                    signal_type='BUY',
                    quantity=10,
                    order_type='MARKET'
                )

        # --- Sell Signal Logic ---
        # If momentum is negative and we have a long position to close
        elif price_change_pct < -self.momentum_threshold:
            current_position = portfolio.positions.get(data.instrument_token, 0)
            if current_position > 0:
                yield TradingSignal(
                    strategy_id=self.strategy_id,
                    instrument_token=data.instrument_token,
                    signal_type='SELL',
                    quantity=current_position, # Sell the entire position
                    order_type='MARKET'
                )
```

**Explanation:**

- **Pure Logic**: Notice there are no `print` statements, no logging, no network calls. This class contains only the mathematical logic for the strategy.
- **Internal State**: It manages its own state using a `deque` (a fast, fixed-size list) to keep track of recent prices.
- **`yield` for Signals**: Instead of publishing an event, it uses `yield` to return a `TradingSignal` object. This makes the function a generator, which the `StrategyRunner` can easily consume.
- **Portfolio Context**: It uses the read-only `portfolio` object to check its current position before issuing a new signal, preventing duplicate buy or sell orders.

---

### 2\. `strategies/mean_reversion.py`

This strategy implements a classic mean reversion logic: "If the price moves too far away from its recent average, bet on it returning to that average."

```python
# AlphasPT_v2/strategies/mean_reversion.py

import numpy as np
from collections import deque
from typing import Generator, Dict, Any

from .base import BaseStrategy, MarketData, PortfolioContext, TradingSignal

class MeanReversionStrategy(BaseStrategy):
    """
    A pure mean reversion strategy that trades on price deviations from a
    moving average.
    """
    def __init__(self, strategy_id: str, parameters: Dict[str, Any]):
        super().__init__(strategy_id, parameters)

        self.lookback_period = int(parameters.get("lookback_period", 50))
        self.deviation_threshold = float(parameters.get("deviation_threshold", 2.0)) # 2 standard deviations

        self.price_history = deque(maxlen=self.lookback_period)

    def on_market_data(
        self,
        data: MarketData,
        portfolio: PortfolioContext
    ) -> Generator[TradingSignal, None, None]:
        """
        Processes a tick and yields a signal if the price has deviated
        significantly from its moving average.
        """
        self.price_history.append(data.last_price)

        if len(self.price_history) < self.lookback_period:
            return

        # Calculate moving average and standard deviation
        prices = np.array(self.price_history)
        moving_avg = np.mean(prices)
        std_dev = np.std(prices)

        if std_dev == 0: # Avoid division by zero
            return

        # --- Sell Signal Logic (Price is too high, expect it to revert down) ---
        if data.last_price > moving_avg + (self.deviation_threshold * std_dev):
            current_position = portfolio.positions.get(data.instrument_token, 0)
            if current_position >= 0: # Not already short
                yield TradingSignal(
                    strategy_id=self.strategy_id,
                    instrument_token=data.instrument_token,
                    signal_type='SELL', # Go short
                    quantity=10,
                    order_type='MARKET'
                )

        # --- Buy Signal Logic (Price is too low, expect it to revert up) ---
        elif data.last_price < moving_avg - (self.deviation_threshold * std_dev):
            current_position = portfolio.positions.get(data.instrument_token, 0)
            if current_position <= 0: # Not already long
                yield TradingSignal(
                    strategy_id=self.strategy_id,
                    instrument_token=data.instrument_token,
                    signal_type='BUY', # Go long
                    quantity=10,
                    order_type='MARKET'
                )
```

**Explanation:**

- **Numerical Computation**: This strategy uses the `numpy` library for efficient calculation of the moving average and standard deviation, which is a common practice.
- **Clear Logic**: The conditions for buying and selling are based on a clear statistical principle: the current price's distance from the mean, measured in standard deviations.
- **Testability**: Like the momentum strategy, this class is trivial to test. You can feed it a pre-defined list of prices and assert that it yields the correct `TradingSignal` at the correct time.
