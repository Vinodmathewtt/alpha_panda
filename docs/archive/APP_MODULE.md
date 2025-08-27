Of course. Here is the complete code for the refactored `app` module, with explanations for each file, provided directly in the chat.

The main idea behind this refactoring is to use a **Dependency Injection (DI) container**. This moves the responsibility of creating and connecting services out of your main application logic and into a dedicated "assembly line." This makes your code much cleaner, more modular, and easier to test.

---

### 1\. `app/services.py`

This new file defines a clear and simple contract for any service that has a lifecycle (i.e., it needs to be started and stopped). This ensures all your services behave consistently.

```python
# AlphasPT_v2/app/services.py

from typing import Protocol, runtime_checkable
from abc import ABC, abstractmethod


@runtime_checkable
class LifespanService(Protocol):
    """
    A protocol defining the contract for any service with a managed lifecycle.

    This ensures that the main application orchestrator can start and stop any
    service in a consistent way, without needing to know the specifics of its
    implementation.
    """

    async def start(self) -> None:
        """Starts the service and any long-running tasks."""
        ...

    async def stop(self) -> None:
        """Gracefully stops the service and cleans up resources."""
        ...


class StreamProcessor(ABC, LifespanService):
    """
    An abstract base class for all services that process data streams.

    This class provides a standardized run loop for connecting to the
    event stream, processing messages, and handling graceful shutdowns.
    Concrete implementations only need to define their specific message
    handling logic.
    """

    @abstractmethod
    async def process_message(self, message: dict) -> None:
        """The core logic for processing a single message from the stream."""
        ...

    async def start(self) -> None:
        """Initializes the stream consumer and starts the processing loop."""
        # In a real implementation, this would start the Redpanda/Kafka consumer
        # and subscribe to the relevant topics.
        print(f"Starting stream processor: {self.__class__.__name__}")
        # Placeholder for starting the consumer loop in the background
        # asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        """Stops the stream consumer."""
        print(f"Stopping stream processor: {self.__class__.__name__}")

```

**Explanation:**

- **`LifespanService`**: This is a formal contract. Any class that has `start` and `stop` methods will be treated as a `LifespanService`.
- **`StreamProcessor`**: This is a helper base class for your main services (like `RiskManager`, `TradingEngine`). It provides a common structure, reducing repetitive code in each service.

---

### 2\. `app/containers.py`

This is the new heart of your application. The container defines every component and its dependencies in one place. It's the "assembly line" that builds your application.

```python
# AlphasPT_v2/app/containers.py

from dependency_injector import containers, providers

# Import core infrastructure components
from core.config.settings import Settings
from core.database.connection import DatabaseManager  # Assuming you have this
from core.streaming.clients import RedpandaProducer, RedpandaConsumer # Assuming these exist

# Import all independent services
# Note: In a real app, these would be imported from the 'services' directory
# from services.market_feed.service import MarketFeedService
# ... and so on for all other services

# Main application entry point
from .main import Application


class AppContainer(containers.DeclarativeContainer):
    """
    The main dependency injection container for the AlphaPT application.

    This container defines how all components of the system are created,
    configured, and wired together. It manages the lifecycle of singletons
    and provides dependencies to the services that need them.
    """

    # --- Core Infrastructure ---

    # 1. Configuration
    # The settings object is a singleton, read once and used everywhere.
    settings = providers.Singleton(Settings)

    # 2. Database (for Application State)
    # The database manager is a resource, meaning the container will handle
    # its initialization and shutdown automatically.
    db_manager = providers.Resource(
        DatabaseManager,
        db_url=settings.provided.database.postgres_url
    )

    # 3. Streaming (for Event Data)
    # A single producer instance can be shared across the application.
    redpanda_producer = providers.Singleton(
        RedpandaProducer,
        config=settings.provided.redpanda
    )

    # --- Independent Services (Placeholders) ---
    # Each service is defined as a singleton. The container will create one
    # instance of each and inject its dependencies.
    # NOTE: You would replace these placeholders with your actual service classes.

    # market_feed_service = providers.Singleton(...)
    # strategy_runner_service = providers.Singleton(...)
    # risk_manager_service = providers.Singleton(...)
    # trading_engine_service = providers.Singleton(...)
    # portfolio_manager_service = providers.Singleton(...)


    # --- Application Orchestrator ---

    # A list of all services that have a managed lifecycle (start/stop).
    lifespan_services = providers.List(
        # market_feed_service,
        # strategy_runner_service,
        # risk_manager_service,
        # trading_engine_service,
        # portfolio_manager_service,
    )

    # The main application class itself is also managed by the container.
    # It receives the list of services to orchestrate.
    application = providers.Singleton(
        Application,
        settings=settings,
        lifespan_services=lifespan_services,
    )
```

**Explanation:**

- **`providers.Singleton`**: Ensures only one instance of a class (like `Settings`) is created and shared everywhere.
- **`providers.Resource`**: Perfect for managing resources like database connections. The container automatically handles its setup and teardown.
- **Dependency Injection in Action**: Notice how `db_manager` gets its URL from `settings`. The container handles this wiring automatically. When you define your real services, you'll inject dependencies like the `redpanda_producer` in the same way.

---

### 3\. `app/main.py`

Finally, the main entry point of your application becomes incredibly simple. Its only job is to use the container to build and run the application. All the complex setup logic is gone.

```python
# AlphasPT_v2/app/main.py

import asyncio
import signal
import sys
from pathlib import Path
from typing import List

# Add project root to Python path to allow for absolute imports
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.containers import AppContainer
from app.services import LifespanService
from core.config.settings import Settings
from core.logging import get_logger, configure_logging


class Application:
    """
    The main application orchestrator for the AlphaPT system.

    This class is responsible for managing the overall lifecycle of all registered
    services, handling graceful startup and shutdown procedures.
    """

    def __init__(self, settings: Settings, lifespan_services: List[LifespanService]):
        self.settings = settings
        self.lifespan_services = lifespan_services
        configure_logging(settings)
        self.logger = get_logger(__name__)
        self.shutdown_event = asyncio.Event()

    def _setup_signal_handlers(self):
        """Sets up signal handlers to trigger a graceful shutdown."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.shutdown_event.set)

    async def start(self):
        """Starts all registered services concurrently."""
        self.logger.info("🚀 Starting all application services...")
        try:
            await asyncio.gather(*(service.start() for service in self.lifespan_services))
            self.logger.info("✅ All services started successfully.")
        except Exception as e:
            self.logger.error("❌ A critical error occurred during service startup.", exc_info=e)
            self.shutdown_event.set() # Trigger shutdown on startup failure

    async def stop(self):
        """Stops all registered services gracefully, in reverse order."""
        self.logger.info("🛑 Stopping all application services...")
        # Stop services in reverse order of startup to respect dependencies
        reversed_services = reversed(self.lifespan_services)
        results = await asyncio.gather(*(service.stop() for service in reversed_services), return_exceptions=True)

        for result, service in zip(results, reversed(self.lifespan_services)):
            if isinstance(result, Exception):
                self.logger.error(f"Error stopping service {type(service).__name__}", exc_info=result)
        self.logger.info("✅ All services stopped.")

    async def run(self):
        """Runs the main application loop, waiting for a shutdown signal."""
        self._setup_signal_handlers()
        await self.start()

        if not self.shutdown_event.is_set():
            self.logger.info("Application is now running. Press Ctrl+C to exit.")
            await self.shutdown_event.wait()

        await self.stop()


def main():
    """The main entry point for the AlphaPT application."""
    print("Initializing AlphaPT...")

    # 1. Create the dependency injection container
    container = AppContainer()

    # 2. Get the fully constructed application instance from the container
    app = container.application()

    # 3. Run the application's async lifecycle
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        print("AlphaPT shutdown complete.")


if __name__ == "__main__":
    main()
```

**Explanation:**

- The `Application` class is now a simple orchestrator. It receives a list of services and knows how to start and stop them. It has no idea _what_ those services are or how they were built.
- The `main()` function is now declarative. It says, "I want the application," and lets the container handle the complex work of building it.
