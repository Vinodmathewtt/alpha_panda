#Strategy Runner Service

This service is the brain of your trading system. It's where your pure, mathematical strategy logic meets the live, real-time flow of market data. The design is highly scalable and resilient, as each individual strategy runs in its own isolated `StrategyRunner` instance.

The service's core responsibilities are:

1.  **Loading** strategy configurations from the database.
2.  **Consuming** real-time market ticks and order fill events from Redpanda.
3.  **Executing** the pure strategy logic.
4.  **Publishing** any resulting trading signals back into the Redpanda unified log.

---

### 1\. `services/strategy_runner/factory.py`

This new file is a crucial part of the design. It's a factory that knows how to build any type of pure strategy based on a configuration. This decouples the service's orchestration logic from the specific strategy implementations, making it easy to add new strategies in the future.

```python
# AlphasPT_v2/services/strategy_runner/factory.py

from typing import Dict, Any, Type
from strategies.base import BaseStrategy

# --- Import all your concrete, pure strategy classes here ---
from strategies.momentum import SimpleMomentumStrategy
from strategies.mean_reversion import MeanReversionStrategy
# Add other strategies as you create them...


class StrategyFactory:
    """
    Creates pure strategy instances based on a registered type name.
    """
    def __init__(self):
        self._strategies: Dict[str, Type[BaseStrategy]] = {}
        self._register_strategies()

    def _register_strategies(self):
        """A central place to register all available strategy types."""
        self.register_strategy("SimpleMomentumStrategy", SimpleMomentumStrategy)
        self.register_strategy("MeanReversionStrategy", MeanReversionStrategy)
        # Register other strategies here...

    def register_strategy(self, strategy_type: str, strategy_class: Type[BaseStrategy]):
        """Registers a strategy class with a given type name."""
        self._strategies[strategy_type] = strategy_class

    def create_strategy(
        self,
        strategy_config: Dict[str, Any]
    ) -> BaseStrategy:
        """
        Creates a pure strategy instance from its database configuration.

        Args:
            strategy_config: The configuration dictionary for a single strategy.

        Returns:
            An instance of a class derived from BaseStrategy.
        """
        strategy_id = strategy_config.get("id")
        strategy_type = strategy_config.get("strategy_type")

        if not strategy_type:
            raise ValueError(f"Strategy config for '{strategy_id}' is missing 'strategy_type'.")

        strategy_class = self._strategies.get(strategy_type)
        if not strategy_class:
            raise ValueError(f"Strategy type '{strategy_type}' is not registered in the factory.")

        parameters = strategy_config.get("parameters", {})
        return strategy_class(strategy_id=strategy_id, parameters=parameters)

```

**Explanation:**

- **Dynamic Creation**: The factory uses the `strategy_type` string from the database configuration to look up the correct Python class and create an instance of it.
- **Centralized Registration**: All available strategies are registered in one place. To add a new strategy to the system, you simply import it here and add one line to the `_register_strategies` method.
- **Decoupling**: The main service doesn't need to know about `SimpleMomentumStrategy` or any other specific strategy. It just asks the factory to "create this strategy for me," making the system incredibly modular.

---

### 2\. `services/strategy_runner/runner.py`

This is a new and vital component. An instance of this class is created for **every single active strategy**. It acts as a "host" or "container" for the pure strategy logic, connecting it to the live Redpanda event streams.

```python
# AlphasPT_v2/services/strategy_runner/runner.py

import asyncio
from typing import Dict, Any

from core.streaming.clients import RedpandaProducer, RedpandaConsumer
from core.config.settings import RedpandaSettings
from strategies.base import BaseStrategy, MarketData, PortfolioContext

class StrategyRunner:
    """
    Hosts and manages the lifecycle of a single, isolated strategy instance.

    It acts as the bridge between the pure strategy logic and the live
    application infrastructure (Redpanda).
    """
    def __init__(
        self,
        strategy: BaseStrategy,
        config: Dict[str, Any],
        producer: RedpandaProducer,
        consumer_config: RedpandaSettings,
    ):
        self.strategy = strategy
        self.config = config
        self.producer = producer

        self.instruments = self.config.get("instruments", [])
        self.topics = [f"market.ticks.{token}" for token in self.instruments]
        # TODO: Add 'orders.filled' topic to update portfolio

        self.consumer = RedpandaConsumer(consumer_config, self.topics)
        self.portfolio_context = PortfolioContext(positions={}, cash=100000.0) # Placeholder
        self._is_running = False
        self._task = None

    async def start(self):
        """Starts the consumer loop for this specific strategy."""
        if not self.instruments:
            print(f"Strategy '{self.strategy.strategy_id}' has no instruments; not starting runner.")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._consume_loop())
        print(f"Runner for strategy '{self.strategy.strategy_id}' started.")

    async def stop(self):
        """Stops the consumer loop."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.consumer.close()
        print(f"Runner for strategy '{self.strategy.strategy_id}' stopped.")

    async def _consume_loop(self):
        """The main loop that consumes messages and executes the strategy."""
        while self._is_running:
            try:
                msg = self.consumer.consume(timeout=1.0)
                if msg is None:
                    await asyncio.sleep(0.01) # Yield control if no message
                    continue

                # Here you would add logic to differentiate between message types
                # (e.g., market ticks vs. order fills)
                market_data = MarketData(**msg)

                # Execute the strategy's pure logic
                for signal in self.strategy.on_market_data(market_data, self.portfolio_context):
                    # The runner is responsible for publishing the signal
                    self.producer.produce("trading.signals.generated", signal.model_dump())

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in consumer loop for '{self.strategy.strategy_id}': {e}")
                await asyncio.sleep(5) # Wait before retrying on error

```

**Explanation:**

- **Isolation**: Each `StrategyRunner` has its own `RedpandaConsumer` and runs its own independent processing loop (`_consume_loop`). An error or slow performance in one strategy will not affect any other running strategies.
- **Bridge to Infrastructure**: This class is the "impure" part of the system. It handles all the infrastructure concerns: subscribing to topics, consuming messages, and publishing the strategy's output.
- **State Management**: It maintains the `PortfolioContext` for its specific strategy, which it would update by listening to `orders.filled` events. This context is then passed to the pure strategy logic on every tick.

---

### 3\. `services/strategy_runner/service.py`

This is the main service file. It acts as an orchestrator, responsible for fetching all active strategy configurations from the database and creating a dedicated `StrategyRunner` for each one.

```python
# AlphasPT_v2/services/strategy_runner/service.py

from app.services import LifespanService
from core.streaming.clients import RedpandaProducer, RedpandaSettings
from core.database.connection import DatabaseManager
from .factory import StrategyFactory
from .runner import StrategyRunner

class StrategyRunnerService(LifespanService):
    """
    The main service that orchestrates all individual strategy runners.
    """

    def __init__(
        self,
        producer: RedpandaProducer,
        db_manager: DatabaseManager,
        consumer_config: RedpandaSettings,
    ):
        self.producer = producer
        self.db_manager = db_manager
        self.consumer_config = consumer_config
        self.strategy_factory = StrategyFactory()
        self.runners = []

    async def start(self):
        """
        Fetches all active strategy configurations from the database,
        creates a runner for each, and starts them all.
        """
        print("🚀 Starting Strategy Runner Service...")

        # 1. Fetch configurations from PostgreSQL
        configs = await self._get_active_strategy_configs()
        print(f"Found {len(configs)} active strategies to run.")

        # 2. Create and start a runner for each configuration
        for config in configs:
            try:
                # 2a. Use the factory to create the pure strategy instance
                strategy_instance = self.strategy_factory.create_strategy(config)

                # 2b. Create a dedicated runner to host the strategy
                runner = StrategyRunner(
                    strategy=strategy_instance,
                    config=config,
                    producer=self.producer,
                    consumer_config=self.consumer_config
                )
                self.runners.append(runner)

                # 2c. Start the runner's async consumer loop
                await runner.start()

            except Exception as e:
                print(f"Failed to initialize strategy '{config.get('id')}': {e}")

        print("✅ Strategy Runner Service started.")

    async def stop(self):
        """Stops all running strategy runners."""
        print("🛑 Stopping Strategy Runner Service...")
        for runner in self.runners:
            await runner.stop()
        print("✅ Strategy Runner Service stopped.")

    async def _get_active_strategy_configs(self) -> list[dict]:
        """
        Fetches all active strategy configurations from the database.
        """
        # In a real application, this would be a SQL query:
        # from core.database.models import StrategyConfiguration
        # from sqlalchemy.future import select
        # async with self.db_manager.get_session() as session:
        #     result = await session.execute(
        #         select(StrategyConfiguration).where(StrategyConfiguration.is_active == True)
        #     )
        #     configs = [row._asdict() for row in result.scalars().all()]
        # return configs

        # For this example, we return a hardcoded list for demonstration.
        return [
            {
                "id": "Momentum_NIFTY50_1",
                "strategy_type": "SimpleMomentumStrategy",
                "instruments": [256265], # NIFTY 50
                "parameters": {"lookback_period": 20, "momentum_threshold": 0.01},
                "is_active": True,
            },
            {
                "id": "MeanReversion_BANKNIFTY_1",
                "strategy_type": "MeanReversionStrategy",
                "instruments": [260105], # BANKNIFTY
                "parameters": {"lookback_period": 50, "deviation_threshold": 1.5},
                "is_active": True,
            },
        ]

```

**Explanation:**

- **Orchestrator Role**: This service's primary job is to manage the _collection_ of runners. It doesn't contain any trading logic itself.
- **Configuration-Driven**: The entire service is driven by the data in your PostgreSQL database. To launch a new strategy, you simply add a new row to the `strategy_configurations` table and restart the service. No code changes are needed.
- **Scalability**: This design scales horizontally. If you have hundreds of strategies, you can run multiple instances of the `StrategyRunnerService` on different machines. Redpanda's consumer groups will automatically balance the strategies among the available service instances.
