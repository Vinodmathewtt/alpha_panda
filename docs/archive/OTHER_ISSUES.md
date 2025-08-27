# OTHER ISSUES TO BE FIXED

### **1. Lack of Isolation Between Strategies** 🛡️

A critical issue exists in the `StrategyRunnerService`. If a single strategy encounters an unhandled exception, it will crash the entire service, halting all other strategies. This is because the `strategy.execute()` method is called without any error handling.

**Recommendation:**

Isolate strategy execution by wrapping the `strategy.execute()` call in a `try...except` block. This will ensure that a single faulty strategy doesn't bring down the entire system.

```python
# In services/strategy_runner/runner.py

async def process_tick(self, tick: MarketTick):
    # ...
    for strategy in self.strategies:
        if strategy.is_subscribed(tick.instrument_token):
            try:
                await strategy.execute(tick)
            except Exception as e:
                self.logger.error(f"Error executing strategy {strategy.name}: {e}")
```

---

### **2. Non-Persistent Paper Trading State** 💾

The `PaperTrader` service, which is essential for testing strategies without real money, stores its portfolio in memory. This means that if the service restarts for any reason, all paper trading history and positions are lost. This makes long-term testing and simulations impossible.

**Recommendation:**

Persist the `PaperTrader`'s state to a durable storage solution. For a simple implementation, you could use a local file (e.g., JSON or SQLite). For a more robust and scalable solution, consider using a database like PostgreSQL or MongoDB.

---

### **3. Inconsistent Project Structure** 🏗️

The project has a generally good structure, but there are inconsistencies between services. For example, some services define their data models in a dedicated `models.py` file, while others include them directly in the `service.py` file. This can make the codebase harder to navigate and understand.

**Recommendation:**

Establish and enforce a consistent directory and file structure for all services. A good practice is to have a standard set of files for each service, such as:

```
services/
  <service_name>/
    __init__.py
    service.py
    models.py
    schemas.py
```

## STRATEGY IMPROVEMENTS

Of course. Here is a focused, end-to-end review of the strategy runner and the overall strategy functionality, along with recommendations for improvement.

### **1. Review of Current Strategy Functionality**

The current implementation provides a solid, event-driven foundation. The `StrategyRunnerService` consumes market ticks and delegates processing to the `StrategyRunner`, which then invokes the `execute` method on each relevant strategy.

**Key Strengths:**

- **Decoupling:** The use of Redpanda to decouple the `MarketFeedService` from the `StrategyRunnerService` is a strong architectural choice.
- **Simplicity:** The current design is straightforward and easy to understand, which is excellent for getting started.

**Critical Weaknesses:**

- **Synchronous Execution:** The `StrategyRunner` processes all strategies sequentially within the same async event loop. A single slow strategy (e.g., one performing a complex calculation or waiting on I/O) will block all other strategies.
- **Lack of Broker Awareness:** Strategies are not aware of the broker context (`paper` vs. `zerodha`). They emit generic signals that are then processed downstream, but the strategies themselves cannot decide where to send the signal.
- **In-Memory State:** All strategy state is held in memory within the strategy object itself. If the service restarts, this state is lost. This is not viable for strategies that need to maintain state over time (e.g., moving averages, trained ML models).

---

### **2. Recommendations for Improvement**

Here are some recommendations to address the current weaknesses and prepare your system for a large number of ML-focused strategies.

#### **Broker-Aware Signal Emission**

Your strategies should be able to decide which broker(s) to send signals to. This can be achieved by making the broker a part of the strategy's configuration.

**Step 1: Update Strategy Configuration**

### **1. Strategy Configuration**

First, we'll create a structured way to define and configure your strategies using YAML files. This makes it easy to manage a large number of strategies and their parameters without changing the code.

**Step 1: Create a `configs` directory**

Inside your `alphaP/strategies` directory, create a new directory called `configs`.

**Step 2: Create YAML configuration files**

For each strategy, create a corresponding YAML file in the `strategies/configs` directory. For example, for a momentum strategy, you would create `momentum_strategy.yaml`:

```yaml
# alphaP/strategies/configs/momentum_strategy.yaml

strategy_name: 'Momentum'
strategy_class: 'MomentumStrategy' # The name of the strategy class
module_name: 'strategies.momentum' # The module where the class is defined
instrument_tokens: [256265, 260105] # NIFTY 50, BANKNIFTY
parameters:
  window: 20
brokers: ['paper', 'zerodha']
```

And for a mean reversion strategy:

```yaml
# alphaP/strategies/configs/mean_reversion_strategy.yaml

strategy_name: 'MeanReversion'
strategy_class: 'MeanReversionStrategy'
module_name: 'strategies.mean_reversion'
instrument_tokens: [256265] # NIFTY 50
parameters:
  entry_threshold: 1.5
  exit_threshold: 0.5
brokers: ['paper']
```

---

### **2. The Strategy Factory**

Next, we'll create a "factory" that can read these configuration files and create the corresponding strategy objects.

Create a new file called `factory.py` in the `alphaP/strategies` directory:

```python
# alphaP/strategies/factory.py

import yaml
import importlib
from pathlib import Path
from typing import List
from .base import BaseStrategy

def create_strategies() -> List[BaseStrategy]:
    """
    Loads all strategy configurations from the `configs` directory
    and creates the corresponding strategy objects.
    """
    strategies = []
    config_path = Path(__file__).parent / "configs"

    for config_file in config_path.glob("*.yaml"):
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        strategy_module = importlib.import_module(config["module_name"])
        strategy_class = getattr(strategy_module, config["strategy_class"])

        strategy_instance = strategy_class(
            name=config["strategy_name"],
            instrument_tokens=config["instrument_tokens"],
            brokers=config.get("brokers", ["paper"]), # Default to paper
            **config.get("parameters", {})
        )
        strategies.append(strategy_instance)

    return strategies
```

---

### **3. Broker-Aware Strategies**

Now, let's make your strategies aware of which broker they should send signals to. We'll modify the `BaseStrategy` to handle this.

Update your `alphaP/strategies/base.py` file:

```python
# alphaP/strategies/base.py

from typing import List, Any, Dict
from core.streaming.clients import StreamProcessor
from core.schemas.events import EventType, TradingSignal

class BaseStrategy(StreamProcessor):
    def __init__(self, name: str, instrument_tokens: List[int], brokers: List[str], **kwargs):
        super().__init__(name=name)
        self.name = name
        self.instrument_tokens = instrument_tokens
        self.brokers = brokers

    def is_subscribed(self, instrument_token: int) -> bool:
        """Checks if the strategy is subscribed to a given instrument."""
        return instrument_token in self.instrument_tokens

    async def execute(self, tick: Dict[str, Any]):
        """
        The core logic of the strategy. This method should be implemented
        by each concrete strategy.
        """
        raise NotImplementedError

    async def _emit_signal(self, signal_data: dict):
        """
        Emits a trading signal to the appropriate broker-specific topics.
        """
        for broker in self.brokers:
            topic = f"{broker}.trading.signals"

            # Create a TradingSignal event
            trading_signal = TradingSignal(
                strategy_id=self.name,
                **signal_data
            )

            await self._emit_event(
                topic=topic,
                event_type=EventType.TRADING_SIGNAL,
                data=trading_signal.model_dump(mode='json')
            )
```

---

### **4. An Improved Strategy Runner**

Finally, let's update the `StrategyRunnerService` to use our new factory. This will make it much cleaner and more scalable.

Update your `alphaP/services/strategy_runner/service.py`:

```python
# alphaP/services/strategy_runner/service.py

from core.streaming.clients import StreamProcessor
from core.schemas.topics import TopicNames
from strategies.factory import create_strategies

class StrategyRunnerService(StreamProcessor):
    def __init__(self, config, settings, redis_client=None):
        super().__init__(
            name="strategy_runner",
            config=config,
            consume_topics=[TopicNames.MARKET_TICKS],
            group_id=f"{settings.redpanda.group_id_prefix}.strategy_runner",
            redis_client=redis_client
        )
        self.settings = settings
        self.strategies = create_strategies()
        self.logger.info(f"Loaded {len(self.strategies)} strategies.")

    async def _handle_message(self, topic: str, key: str, message: dict):
        """
        Processes an incoming market tick and passes it to all relevant
        strategies.
        """
        instrument_token = message.get("instrument_token")
        for strategy in self.strategies:
            if strategy.is_subscribed(instrument_token):
                try:
                    await strategy.execute(message)
                except Exception as e:
                    self.logger.error(f"Error executing strategy {strategy.name}: {e}")
```

With these changes, you now have a robust and scalable strategy management system that is easy to configure and extend.
