## Surgical Changes to Namespace System

The namespace system provides significant benefits, particularly in a production environment. What you're proposing is a **hybrid approach**, and it's a very practical and valid architecture.

This model keeps the clear data segregation of namespaces at the topic level while enabling a single, unified service deployment. It's a great middle-ground that balances operational simplicity with infrastructure clarity.

Here is a detailed plan for how to implement this, removing the `BROKER_NAMESPACE` dependency while keeping topic namespaces.

---

### \#\# **The Hybrid Plan: Single Deployment, Multiple Namespaces**

The goal is to make your services **namespace-aware** rather than being configured for a **single namespace** at startup. A single `TradingEngine` service, for example, will listen to `paper.signals.validated` and `zerodha.signals.validated` simultaneously.

Here is the step-by-step implementation guide:

---

### \#\#\# **Phase 1: Configuration and Service Initialization**

We'll start by teaching the application which brokers it needs to manage.

#### **1. Update `settings.py` to Define Active Brokers**

First, remove the single `broker_namespace` and replace it with a list of all brokers this deployment instance should handle.

**File**: `alphap14/core/config/settings.py`

**FROM:**

```python
class Settings(BaseSettings):
    # ...
    broker_namespace: Literal["paper", "zerodha"] = Field(
        default="paper",
        description="Broker namespace for this deployment instance",
        validation_alias="BROKER_NAMESPACE"
    )
    # ...
```

**TO:**

```python
from typing import List

class Settings(BaseSettings):
    # ...
    # NEW: A list of all broker namespaces this instance will manage
    active_brokers: List[str] = ["paper", "zerodha"]
    # ...
```

This is the only change needed in your environment configuration. You no longer need `BROKER_NAMESPACE`.

---

### \#\#\# **Phase 2: Dynamic, Multi-Namespace Service Logic**

Next, we refactor the services to handle multiple brokers dynamically during runtime.

#### **1. Modify Services to Subscribe to Multiple Topics**

The core change happens in services like `TradingEngineService`. Instead of subscribing to a single topic, it will now subscribe to a list of topics, one for each active broker.

**File**: `alphap14/services/trading_engine/service.py`

**FROM:**

```python
# ...
        topics = TopicMap(settings.broker_namespace)

        self.orchestrator = (StreamServiceBuilder("trading_engine", config, settings)
            # ...
            .add_consumer_handler(
                topics=[topics.signals_validated()], # Consumes ONE topic
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.signals",
                handler_func=self._handle_validated_signal
            )
            # ...
        )
# ...
```

**TO:**

```python
# ...
        # No single TopicMap instance needed here anymore.

        # 1. Generate a list of topics to subscribe to
        all_signal_topics = [
            f"{broker}.signals.validated" for broker in self.settings.active_brokers
        ]

        self.orchestrator = (StreamServiceBuilder("trading_engine", config, settings)
            # ...
            .add_consumer_handler(
                topics=all_signal_topics, # Consumes a LIST of topics
                # The consumer group is now unified
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.signals",
                handler_func=self._handle_validated_signal
            )
            # ...
        )
# ...
```

Your `_handle_validated_signal` function will now receive messages from both `paper.signals.validated` and `zerodha.signals.validated`.

#### **2. Adapt Message Handlers to Be Namespace-Aware**

Since the handler receives messages from multiple topics, it needs to know which broker the message is for. The topic name itself provides this context.

**File**: `alphap14/services/trading_engine/service.py`

You will need to slightly modify how handlers are called to pass the topic context. Assuming your `StreamServiceBuilder` can provide the topic of the incoming message to your handler:

```python
# The handler signature is updated to accept the topic
async def _handle_validated_signal(self, message: Dict[str, Any], topic: str) -> None:
    # 2. Extract the broker from the topic name
    broker = topic.split('.')[0] # e.g., "paper" or "zerodha"

    # ... existing handler logic ...

    # When routing, you use the extracted broker
    signal = TradingSignal(**original_signal)

    # The ExecutionRouter now determines which trader to use based on the source broker
    # (This logic might be simple or complex depending on your routing rules)
    target_trader = self.execution_router.get_target_trader(signal, source_broker=broker)

    await self._execute_on_trader(signal, target_trader)
```

#### **3. Adapt Producers to Publish to Specific Namespaces**

When producing a message, services must now dynamically choose the correct namespaced topic.

**File**: `alphap14/services/trading_engine/service.py`

**FROM (in `_emit_execution_result`):**

```python
# ...
        elif namespace == "paper":
            event_type = EventType.ORDER_FILLED
            topic = self.topics.orders_filled() # Uses the service's single namespace
        else:  # zerodha or other live trading
            event_type = EventType.ORDER_PLACED
            topic = self.topics.orders_submitted()
# ...
```

**TO (in `_emit_execution_result`):**

```python
# The `namespace` variable here is now the specific broker_id, e.g., "paper"
async def _emit_execution_result(self, signal: TradingSignal, result_data: Dict[str, Any], broker_id: str):
    # ...
    # 3. Dynamically generate the correct topic name
    if "error_message" in result_data:
        event_type = EventType.ORDER_FAILED
        topic = f"{broker_id}.orders.failed"
    elif broker_id == "paper":
        event_type = EventType.ORDER_FILLED
        topic = f"{broker_id}.orders.filled"
    else:  # zerodha or other live trading
        event_type = EventType.ORDER_PLACED
        topic = f"{broker_id}.orders.submitted"

    await producer.send(
        topic=topic,
        # ...
    )
```

---

### \#\#\# **Benefits and Trade-Offs of This Hybrid Approach**

You were right that the namespace system has benefits. Here’s how this hybrid model stacks up:

| **Feature**                | **Hybrid Model (Your Proposal)**                                                                                                                                     | **Unified Topic Model (Previous Plan)**                                                                                       |
| :------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------- |
| **Data Isolation**         | **Excellent**. Data is separated at the infrastructure level. You can use tools like `rpk` to inspect the `zerodha.orders.filled` topic without seeing paper trades. | **Good**. Relies on application logic. All data is in one topic (`orders.filled`), separated by a `broker_id` in the payload. |
| **Operational Simplicity** | **Excellent**. Single deployment for all services. No more `BROKER_NAMESPACE` environment variable.                                                                  | **Excellent**. Also a single deployment.                                                                                      |
| **Topic Management**       | **Moderate**. The number of topics is still proportional to the number of brokers (e.g., 2 brokers = 2x topics).                                                     | **Simple**. A fixed, small number of topics regardless of how many brokers are added.                                         |
| **Debugging**              | **Easier**. You can trace a flow by just watching the topics for a specific broker.                                                                                  | **Harder**. Requires inspecting message payloads to filter for the broker you are debugging.                                  |
| **Flexibility**            | **Good**. Adding a new broker requires updating the `active_brokers` list in the config and ensuring topics are created.                                             | **Excellent**. Adding a new broker requires no changes to topics or service subscriptions.                                    |

**Conclusion**: Your proposed hybrid model is a very strong choice. It significantly simplifies your operations by eliminating environment-specific deployments while retaining the powerful data segregation and debugging advantages of using namespaces. It's a pragmatic and robust solution for a multi-broker trading system.

## Detailed Plan

Of course. Here is the detailed, step-by-step implementation of **Plan B: Hybrid/Multiple Namespaces**.

This plan refactors the system to remove the `BROKER_NAMESPACE` dependency, allowing a single service instance to manage multiple brokers by listening on all relevant namespaced topics simultaneously.

---

### \#\# Step 1: Update Application Configuration (`settings.py`)

First, we'll modify the main `Settings` class. We remove the single `broker_namespace` and replace it with `active_brokers`, a list of all namespaces this application instance will manage.

**File Location**: `alphap14/core/config/settings.py`

#### **Code Replacement for `settings.py`**

```python
# Complete settings with ALL required sections
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field, validator
from enum import Enum
from typing import Literal, List
from pathlib import Path


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class DatabaseSettings(BaseModel):
    postgres_url: str = "postgresql+asyncpg://alpha_panda:alpha_panda@localhost:5432/alpha_panda"
    schema_management: str = Field(
        default="auto",  # auto, create_all, migrations_only
        description="Database schema management strategy"
    )
    verify_migrations: bool = Field(
        default=True,
        description="Verify migrations are current in production"
    )


class RedpandaSettings(BaseModel):
    bootstrap_servers: str = "localhost:9092"
    client_id: str = "alpha-panda-client"
    group_id_prefix: str = "alpha-panda"  # Unique groups per service


class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379/0"


class AuthSettings(BaseModel):
    secret_key: str = "your-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # Control which auth system to use
    enable_user_auth: bool = False  # Disabled in development, enabled in production
    primary_auth_provider: str = "zerodha"  # "zerodha" for development, "user" for production


class PaperTradingSettings(BaseModel):
    enabled: bool = True
    slippage_percent: float = 0.05  # 0.05% slippage
    commission_percent: float = 0.1  # 0.1% commission
    starting_cash: float = 1_000_000.0  # Starting cash for paper portfolios


class ZerodhaSettings(BaseModel):
    enabled: bool = True   # Enabled by default for development
    api_key: str = ""
    api_secret: str = ""
    starting_cash: float = 1_000_000.0  # Starting cash for Zerodha portfolios


class LoggingSettings(BaseModel):
    # Core logging settings
    level: str = "INFO"
    structured: bool = True
    json_format: bool = True

    # Console logging
    console_enabled: bool = True
    console_json_format: bool = False  # Plain text for console by default

    # File logging
    file_enabled: bool = True
    logs_dir: str = "logs"
    file_max_size: str = "100MB"
    file_backup_count: int = 5

    # Multi-channel logging
    multi_channel_enabled: bool = True
    audit_retention_days: int = 365
    performance_retention_days: int = 30

    # Channel-specific levels
    database_level: str = "WARNING"
    trading_level: str = "INFO"
    api_level: str = "INFO"
    market_data_level: str = "INFO"

    # Log management
    auto_cleanup_enabled: bool = True
    compression_enabled: bool = True
    compression_age_days: int = 7


class ReconnectionSettings(BaseModel):
    """Market feed reconnection configuration"""
    max_attempts: int = 5
    base_delay_seconds: int = 1
    max_delay_seconds: int = 60
    backoff_multiplier: float = 2.0
    timeout_seconds: int = 30


class PortfolioManagerSettings(BaseModel):
    """Portfolio manager service configuration"""
    snapshot_interval_seconds: int = 300  # 5 minutes
    max_portfolio_locks: int = 1000  # Limit memory usage for locks
    reconciliation_interval_seconds: int = 3600  # 1 hour for Zerodha reconciliation


class HealthCheckSettings(BaseModel):
    """Health check configuration"""
    market_ticks_max_age_seconds: int = 30
    portfolio_snapshot_max_age_seconds: int = 300
    redis_connection_timeout_seconds: float = 5.0
    database_connection_timeout_seconds: float = 10.0


class MonitoringSettings(BaseModel):
    # Health checks
    health_check_enabled: bool = True
    health_check_interval: float = 30.0
    health_check_timeout: float = 5.0

    # Metrics collection
    metrics_enabled: bool = True
    performance_monitoring_enabled: bool = True

    # Alert thresholds
    memory_alert_threshold: float = 0.9
    cpu_alert_threshold: float = 0.8
    disk_alert_threshold: float = 0.9

    # Pipeline monitoring
    pipeline_flow_monitoring_enabled: bool = True
    consumer_lag_threshold: int = 1000
    market_data_latency_threshold: float = 1.0
    startup_grace_period_seconds: float = 30.0


class APISettings(BaseModel):
    # CORS settings
    cors_origins: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins"
    )
    cors_methods: List[str] = Field(
        default=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        description="Allowed CORS methods"
    )
    cors_headers: List[str] = Field(
        default=["Authorization", "Content-Type", "X-Request-ID"],
        description="Allowed CORS headers"
    )
    cors_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests"
    )

    @validator('cors_origins')
    def validate_cors_origins(cls, v):
        """Validate CORS origins configuration"""
        if "*" in v and len(v) > 1:
            raise ValueError("Cannot mix '*' with specific origins")
        return v


class Settings(BaseSettings):
    """Main application settings, loaded from environment variables"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore"
    )

    # --- REFACTORED ---
    # REMOVED: broker_namespace
    # ADDED: active_brokers to define all brokers managed by this instance.
    # This removes the need for the BROKER_NAMESPACE environment variable.
    active_brokers: List[str] = Field(
        default=["paper", "zerodha"],
        description="List of active broker namespaces for this deployment instance"
    )

    app_name: str = "Alpha Panda"
    environment: Environment = Environment.DEVELOPMENT

    # Legacy log_level for backward compatibility
    log_level: str = "INFO"

    database: DatabaseSettings = DatabaseSettings()
    redpanda: RedpandaSettings = RedpandaSettings()
    redis: RedisSettings = RedisSettings()
    auth: AuthSettings = AuthSettings()
    paper_trading: PaperTradingSettings = PaperTradingSettings()
    zerodha: ZerodhaSettings = ZerodhaSettings()
    logging: LoggingSettings = LoggingSettings()
    monitoring: MonitoringSettings = MonitoringSettings()
    reconnection: ReconnectionSettings = ReconnectionSettings()
    portfolio_manager: PortfolioManagerSettings = PortfolioManagerSettings()
    health_checks: HealthCheckSettings = HealthCheckSettings()
    api: APISettings = APISettings()


    @property
    def logs_dir(self) -> str:
        """Get absolute path to logs directory"""
        return self.logging.logs_dir

    @property
    def base_dir(self) -> str:
        """Get base application directory dynamically"""
        # Go up 2 levels from core/config/settings.py to reach project root
        return str(Path(__file__).resolve().parents[2])


# No global settings instance - use dependency injection instead
```

---

### \#\# Step 2: Update Application Entrypoint (`main.py`)

We'll update the startup log message in the orchestrator to show the list of active brokers, which improves visibility.

**File Location**: `alphap14/app/main.py`

#### **Code Replacement for `main.py`**

```python
# alphaP/app/main.py

import asyncio
import signal
import sys
import logging

from core.logging import configure_logging, get_logger
from app.containers import AppContainer
from core.health import SystemHealthMonitor
from core.config.validator import validate_startup_configuration

class ApplicationOrchestrator:
    """Main application orchestrator with pre-flight health checks."""

    def __init__(self):
        self.container = AppContainer()
        self._shutdown_event = asyncio.Event()

        # Provide the shutdown event to the container
        self.container.shutdown_event.override(self._shutdown_event)

        # Wire the container to the modules that need DI
        self.container.wire(modules=[__name__, "core.health", "api.dependencies"])

        self.settings = self.container.settings()
        configure_logging(self.settings)
        self.logger = get_logger("alpha_panda.main")

        # --- REFACTORED ---
        # Log active broker namespaces for deployment visibility
        self.logger.info(f"🏢 Managing active brokers: {self.settings.active_brokers}")

        self.health_monitor: SystemHealthMonitor = self.container.system_health_monitor()

    async def startup(self):
        """Initialize application with proper startup sequence."""
        self.logger.info("🚀 Initializing application with comprehensive validation...")

        # CRITICAL ADDITION: Validate configuration before proceeding
        try:
            config_valid = await validate_startup_configuration(self.settings)
            if not config_valid:
                self.logger.error("❌ Configuration validation failed - cannot proceed with startup")
                # Clean up any resources created during container wiring
                await self._cleanup_partial_initialization()
                raise RuntimeError("Configuration validation failed - check logs for details")
        except Exception as e:
            # If validation itself fails, still try cleanup
            await self._cleanup_partial_initialization()
            raise

        self.logger.info("✅ Configuration validation passed")

        # --- CRITICAL FIX: Initialize database and auth service BEFORE health checks ---
        # This fixes the authentication startup order issue

        # Step 1: Initialize database first
        db_manager = self.container.db_manager()
        await db_manager.init()
        self.logger.info("✅ Database initialized")

        # Step 2: Start auth service to establish/load session
        auth_service = self.container.auth_service()
        await auth_service.start()
        self.logger.info("✅ Authentication service started")

        # Step 3: Now run health checks (auth service can properly check session)
        self.logger.info("🚀 Conducting system pre-flight health checks...")
        is_healthy = await self.health_monitor.run_checks()

        for result in self.health_monitor.results:
            if result.passed:
                self.logger.info(f"✅ Health check PASSED for {result.component}: {result.message}")
            else:
                self.logger.error(f"❌ Health check FAILED for {result.component}: {result.message}")

        if not is_healthy:
            self.logger.critical("System health checks failed. Application will not start.")
            self.logger.critical("Please fix the configuration or infrastructure issues above and restart.")
            # Clean up any resources that may have been initialized during DI container wiring
            await self._cleanup_partial_initialization()
            sys.exit(1) # Exit with a non-zero code to indicate failure

        self.logger.info("✅ All health checks passed. Proceeding with remaining service startup...")

        # --- START REMAINING SERVICES (auth service already started) ---
        all_services = self.container.lifespan_services()
        # Filter out auth_service since it's already started
        remaining_services = [s for s in all_services if s is not auth_service]
        await asyncio.gather(*(service.start() for service in remaining_services if service))
        self.logger.info("✅ All services started successfully.")

    async def _cleanup_partial_initialization(self):
        """Clean up resources that may have been initialized during container wiring."""
        self.logger.info("🧹 Cleaning up partially initialized resources...")

        cleanup_tasks = []

        try:
            # Try to get services that might have been partially initialized
            services = []
            try:
                services = self.container.lifespan_services()
            except Exception:
                pass  # Container might not be fully initialized

            # Stop any services that were created (in reverse order)
            for service in reversed(services):
                if service and hasattr(service, 'stop'):
                    cleanup_tasks.append(self._safe_service_stop(service, type(service).__name__))

            # Clean up database manager if it was initialized
            try:
                db_manager = self.container.db_manager()
                if db_manager and hasattr(db_manager, 'shutdown'):
                    cleanup_tasks.append(self._safe_db_shutdown(db_manager))
            except Exception:
                pass  # DB manager might not be initialized

            # Wait for all cleanup tasks with timeout
            if cleanup_tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*cleanup_tasks, return_exceptions=True), timeout=10.0)
                except asyncio.TimeoutError:
                    self.logger.warning("⚠️ Cleanup timeout - some resources may not be fully cleaned up")

        except Exception as e:
            self.logger.warning(f"Error during partial initialization cleanup: {e}")

        self.logger.info("✅ Partial cleanup completed")

    async def _safe_service_stop(self, service, service_name: str):
        """Safely stop a service with proper error handling."""
        try:
            await service.stop()
            self.logger.info(f"✅ Stopped {service_name} during cleanup")
        except Exception as e:
            self.logger.warning(f"⚠️ Error stopping {service_name} during cleanup: {e}")

    async def _safe_db_shutdown(self, db_manager):
        """Safely shutdown database manager with proper error handling."""
        try:
            await db_manager.shutdown()
            self.logger.info("✅ Database manager shutdown during cleanup")
        except Exception as e:
            self.logger.warning(f"⚠️ Error shutting down database during cleanup: {e}")

    async def shutdown(self):
        """Gracefully shutdown application."""
        self.logger.info("🛑 Shutting down Alpha Panda application...")

        services = self.container.lifespan_services()
        try:
            await asyncio.gather(*(service.stop() for service in reversed(services) if service))
        except asyncio.CancelledError:
            self.logger.warning("Shutdown process was cancelled. Attempting to force stop services.")
            for service in reversed(services):
                if service and hasattr(service, 'stop'):
                    try:
                        await service.stop()
                    except Exception as e:
                        self.logger.warning(f"Error during forced service shutdown: {e}")
        except Exception as e:
            self.logger.error(f"Error during service shutdown: {e}")
        finally:
            try:
                db_manager = self.container.db_manager()
                await db_manager.shutdown()
                self.logger.info("✅ Alpha Panda application shutdown complete.")
            except Exception as e:
                self.logger.error(f"Error during database shutdown: {e}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        try:
            self.logger.info(f"Received shutdown signal: {signal.strsignal(signum)}")
            self._shutdown_event.set()
        except Exception as e:
            # Fallback to stderr if logging fails during shutdown
            print(f"Error in signal handler: {e}", file=sys.stderr)
            self._shutdown_event.set()  # Still try to trigger shutdown

    async def run(self):
        """Run the application until shutdown."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            await self.startup()
            self.logger.info("Application is now running. Press Ctrl+C to exit.")
            await self._shutdown_event.wait()
        finally:
            await self.shutdown()

async def main():
    """Application entry point"""
    app = ApplicationOrchestrator()
    await app.run()

if __name__ == "__main__":
    asyncio.run(main())
```

---

### \#\# Step 3: Refactor the Trading Engine Service (`service.py`)

This is the most important part of the refactoring. The `TradingEngineService` will be updated to:

1.  Subscribe to a **list of topics**, one for each broker in `settings.active_brokers`.
2.  Use a **unified consumer group ID** for all broker topics.
3.  **Infer the broker** from the topic name of the incoming message.
4.  **Dynamically construct** the correct namespaced topic when producing results.

**File Location**: `alphap14/services/trading_engine/service.py`

#### **Code Replacement for `service.py`**

```python
from typing import Dict, Any
from core.config.settings import RedpandaSettings, Settings
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.schemas.topics import TopicMap, TopicNames
from core.schemas.events import EventType, TradingSignal
from core.logging import get_trading_logger_safe, get_performance_logger_safe, get_error_logger_safe
from core.market_hours.market_hours_checker import MarketHoursChecker
from datetime import datetime, timezone
from collections import defaultdict

from .traders.trader_factory import TraderFactory
from .routing.execution_router import ExecutionRouter


class TradingEngineService:
    """Refactored trading engine using composition over inheritance."""

    def __init__(
        self,
        config: RedpandaSettings,
        settings: Settings,
        redis_client,
        trader_factory: TraderFactory,
        execution_router: ExecutionRouter,
        market_hours_checker: MarketHoursChecker
    ):
        self.settings = settings
        self.trader_factory = trader_factory
        self.execution_router = execution_router
        self.market_hours_checker = market_hours_checker

        # State management
        self.last_prices: Dict[int, float] = {}
        self.pending_signals: Dict[int, list] = defaultdict(list)
        self.warmed_up_instruments: set[int] = set()

        # Metrics
        self.processed_count = 0
        self.error_count = 0

        # Enhanced logging setup
        self.logger = get_trading_logger_safe("trading_engine")
        self.perf_logger = get_performance_logger_safe("trading_engine_performance")
        self.error_logger = get_error_logger_safe("trading_engine_errors")

        # --- REFACTORED ---
        # Build service to handle multiple brokers in a single instance.

        # 1. Generate a list of topics to subscribe to based on active_brokers
        validated_signal_topics = [
            TopicMap(broker).signals_validated() for broker in settings.active_brokers
        ]

        self.orchestrator = (StreamServiceBuilder("trading_engine", config, settings)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                # 2. Subscribe to the list of topics
                topics=validated_signal_topics,
                # 3. Use a unified consumer group ID
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.signals",
                # NOTE: The handler function signature now accepts 'topic'
                handler_func=self._handle_validated_signal
            )
            .add_consumer_handler(
                topics=[TopicNames.MARKET_TICKS], # Market ticks are already unified
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.ticks",
                handler_func=self._handle_market_tick
            )
            .build()
        )

    async def start(self) -> None:
        """Start the service."""
        self.logger.info("Starting Trading Engine Service", brokers=self.settings.active_brokers)
        await self.trader_factory.initialize()
        await self.orchestrator.start()
        self.logger.info("Trading Engine Service started")

    async def stop(self) -> None:
        """Stop the service."""
        self.logger.info("Stopping Trading Engine Service")
        await self.orchestrator.stop()
        await self.trader_factory.shutdown()
        self.logger.info("Trading Engine Service stopped")

    # --- REFACTORED ---
    # The handler now accepts the 'topic' argument. This requires a minor
    # modification in the consumer loop (within StreamServiceBuilder or its
    # underlying consumer) to pass `message.topic` along with the message value.
    async def _handle_validated_signal(self, message: Dict[str, Any], topic: str) -> None:
        """Handle validated signal - pure business logic."""
        # 4. Infer the broker from the topic name (e.g., "paper.signals.validated" -> "paper")
        broker = topic.split('.')[0]

        if message.get('type') != EventType.VALIDATED_SIGNAL:
            return

        if not self.market_hours_checker.is_market_open():
            self.logger.debug("Ignoring validated signal - market is closed", broker=broker)
            return

        data = message.get('data', {})
        original_signal = data.get('original_signal')
        if not original_signal:
            self.error_logger.error("Validated signal is missing 'original_signal' payload.",
                                  broker=broker)
            return

        strategy_id = original_signal.get('strategy_id')
        instrument_token = original_signal.get('instrument_token')
        signal_type = original_signal.get('signal_type')
        quantity = original_signal.get('quantity')

        if not strategy_id or not instrument_token:
            self.error_logger.error("Invalid signal: missing strategy_id or instrument_token",
                                  broker=broker)
            return

        if instrument_token not in self.warmed_up_instruments:
            self.pending_signals[instrument_token].append((data, broker)) # Also store broker
            self.logger.info("Signal queued - waiting for market data",
                           strategy_id=strategy_id,
                           instrument_token=instrument_token,
                           signal_type=signal_type,
                           broker=broker)
            return

        self.logger.info("Processing validated signal for execution",
                        strategy_id=strategy_id,
                        instrument_token=instrument_token,
                        signal_type=signal_type,
                        quantity=quantity,
                        broker=broker)

        signal = TradingSignal(**original_signal)
        # The execution router might have logic to route cross-broker, but for now
        # we execute on the broker that sourced the signal.
        await self._execute_on_trader(signal, broker)

        self.processed_count += 1

    async def _handle_market_tick(self, message: Dict[str, Any], topic: str) -> None:
        """Handle market tick - pure business logic."""
        if message.get('type') != EventType.MARKET_TICK:
            return

        data = message.get('data', {})
        instrument_token = data.get('instrument_token')
        last_price = data.get('last_price')

        if instrument_token and last_price:
            self.last_prices[instrument_token] = last_price

            if instrument_token not in self.warmed_up_instruments:
                self.warmed_up_instruments.add(instrument_token)
                await self._process_pending_signals(instrument_token)
                self.logger.info("Instrument warmed up with market data",
                               instrument_token=instrument_token)

    async def _execute_on_trader(self, signal: TradingSignal, broker: str) -> None:
        """Execute signal on the trader for the specified broker."""
        try:
            trader = self.trader_factory.get_trader(broker)
            last_price = self.last_prices.get(signal.instrument_token)

            result_data = await trader.execute_order(signal, last_price)

            await self._emit_execution_result(signal, result_data, broker)

        except Exception as e:
            self.error_count += 1
            self.error_logger.error(f"Execution failed on {broker}",
                                  strategy_id=signal.strategy_id,
                                  error=str(e))

    # --- REFACTORED ---
    # The method now accepts `broker_id` to dynamically construct the topic name.
    async def _emit_execution_result(self, signal: TradingSignal, result_data: Dict[str, Any], broker_id: str):
        """Emit appropriate event based on execution result."""
        if not self.orchestrator.producers or len(self.orchestrator.producers) == 0:
            self.error_logger.error("No producers available for emitting events")
            return

        producer = self.orchestrator.producers[0]

        strategy_id = signal.strategy_id
        instrument_token = signal.instrument_token
        key = f"{strategy_id}:{instrument_token}"

        # 5. Dynamically construct the output topic based on the broker
        topics = TopicMap(broker_id)

        if "error_message" in result_data:
            event_type = EventType.ORDER_FAILED
            topic = topics.orders_failed()
        elif broker_id == "paper":
            event_type = EventType.ORDER_FILLED
            topic = topics.orders_filled()
        else:  # zerodha or other live trading
            event_type = EventType.ORDER_PLACED
            topic = topics.orders_submitted()

        await producer.send(
            topic=topic,
            key=key,
            data=result_data,
            event_type=event_type,
        )

    async def _process_pending_signals(self, instrument_token: int):
        """Process all pending signals for an instrument."""
        pending = self.pending_signals.pop(instrument_token, [])
        if not pending:
            return

        self.logger.info("Processing pending signals",
                        instrument_token=instrument_token,
                        pending_count=len(pending))

        for signal_data, broker in pending:
            original_signal = signal_data.get('original_signal')
            if not original_signal:
                continue

            signal = TradingSignal(**original_signal)
            await self._execute_on_trader(signal, broker)

    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "service_name": "trading_engine",
            "active_brokers": self.settings.active_brokers,
            "orchestrator_status": self.orchestrator.get_status(),
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "warmed_up_instruments": len(self.warmed_up_instruments),
            "pending_signals": sum(len(signals) for signals in self.pending_signals.values())
        }
```

These changes successfully implement the hybrid approach. Your system will now start a single set of services that are aware of and can process messages for all brokers defined in your settings, all without the need for a deployment-specific environment variable.

Excellent question. The plan you have is solid and covers the most critical service, the `TradingEngine`. To make the refactoring truly complete and robust, we need to apply the same principles to the rest of the ecosystem.

Here are the essential additions to ensure the hybrid model works seamlessly across your entire platform.

---

### \#\# 1. Generalizing the Pattern to Other Services

The changes made to the `TradingEngineService` are a template that must be applied to every other service that consumes or produces broker-specific messages. This includes the `RiskManager`, `PortfolioManager`, and `StrategyRunner`.

#### **Generic Refactoring Steps for a Service:**

1.  **Update Consumer Initialization**: Modify the service's `__init__` method to generate a list of input topics from `settings.active_brokers` and subscribe to all of them using a single, unified consumer group.
2.  **Make Handlers Context-Aware**: Update the message handler function signature to accept the `topic` string as an argument. Inside the handler, parse the broker from the topic name (e.g., `broker = topic.split('.')[0]`).
3.  **Tag Logs with Broker Context**: Add the inferred `broker` to all log messages within the handler for clear, filterable logs.
4.  **Update Producers**: When publishing messages, use the broker context to dynamically construct the correct destination topic (e.g., `f"{broker}.orders.failed"`).

#### **Example: Refactoring the `PortfolioManagerService`**

Let's assume your `PortfolioManagerService` consumes filled and failed order topics. Here’s how you would refactor it:

```python
# In services/portfolio_manager/service.py

class PortfolioManagerService:
    def __init__(self, config: RedpandaSettings, settings: Settings, ...):
        self.settings = settings
        self.logger = get_logger("portfolio_manager")

        # 1. Generate lists of topics for all active brokers
        filled_order_topics = [f"{broker}.orders.filled" for broker in settings.active_brokers]
        failed_order_topics = [f"{broker}.orders.failed" for broker in settings.active_brokers]
        all_topics = filled_order_topics + failed_order_topics

        self.orchestrator = (StreamServiceBuilder("portfolio_manager", config, settings)
            .add_consumer_handler(
                topics=all_topics,
                # Use a unified consumer group
                group_id=f"{settings.redpanda.group_id_prefix}.portfolio_manager.orders",
                handler_func=self._handle_order_event
            )
            # ... other consumers for PNL snapshots etc.
            .build()
        )

    async def _handle_order_event(self, message: Dict[str, Any], topic: str) -> None:
        """Handles any order event and routes internally."""
        # 2. Infer broker from the topic
        broker = topic.split('.')[0]

        # 3. Add broker context to logs
        self.logger.info("Processing order event", broker=broker, topic=topic)

        # Use the broker to update the correct portfolio state
        # (Assuming you have a dictionary of portfolio managers, one per broker)
        manager = self.get_manager_for_broker(broker)

        if topic.endswith(".filled"):
            await manager.process_fill(message.get('data'))
        elif topic.endswith(".failed"):
            await manager.process_failure(message.get('data'))

    # ... rest of the service logic
```

---

### \#\# 2. Enhancing Logging for Multi-Broker Visibility

With a single service handling multiple brokers, it's crucial to distinguish which broker a log entry belongs to. The best practice is to add the `broker` as a standard field to your structured logs.

Your `get_trading_logger_safe` and other loggers likely use a base configuration. You can use `structlog`'s contextvars to automatically inject this. However, the simplest way is to pass it explicitly in every log call, as shown in the examples above.

**Best Practice for Logging:**

```python
# Inside a handler after inferring the broker...
broker = topic.split('.')[0]

self.logger.info(
    "This is a log message.",
    extra_data={"key": "value"},
    broker=broker  # Add broker to the structured log
)
```

This will produce JSON logs like this, which are incredibly powerful for debugging in a multi-broker environment:

```json
{"event": "This is a log message.", "extra_data": {"key": "value"}, "broker": "zerodha"}
{"event": "This is a log message.", "extra_data": {"key": "value"}, "broker": "paper"}
```

---

### \#\# 3. Adapting Health Checks for All Active Brokers

Your startup health checks must be updated to validate the configuration and connectivity for **every broker** listed in `active_brokers`, not just a single hardcoded one.

#### **File Location**: `alphap14/app/containers.py`

In your `AppContainer`, the `health_checks_list` is created. You should dynamically generate broker-specific checks.

```python
# In app/containers.py

class AppContainer(containers.DeclarativeContainer):
    # ...

    @providers.provider
    def dynamic_health_checks(settings, auth_service, db_manager):
        checks = [
            # Core infrastructure checks (run once)
            DatabaseHealthCheck(db_manager=db_manager),
            RedisHealthCheck(redis_client=redis.from_url(settings.redis.url)),
            RedpandaHealthCheck(settings=settings),
            MarketHoursCheck(),
            ActiveStrategiesCheck(db_manager=db_manager),
        ]

        # Dynamically add checks for each active broker
        for broker in settings.active_brokers:
            if broker != "paper": # No external API to check for paper trading
                checks.append(
                    # This check now needs to be broker-aware
                    BrokerApiHealthCheck(auth_service=auth_service, broker_name=broker)
                )
                checks.append(
                    # Authenticate each broker
                    ZerodhaAuthenticationCheck(auth_service=auth_service, broker_name=broker)
                )

        return checks

    system_health_monitor = providers.Singleton(
        SystemHealthMonitor,
        checks=dynamic_health_checks(settings, auth_service, db_manager)
    )
    # ...
```

**_Note:_** This requires a small modification to `BrokerApiHealthCheck` and `ZerodhaAuthenticationCheck` to accept a `broker_name` and check the specific broker's status.

---

### \#\# 4. Final Review and Testing Strategy

Once the code changes are complete, a final review and a revised testing strategy are essential.

1.  **Code Grep**: Do a project-wide search for `broker_namespace`. This string should no longer exist anywhere except perhaps in old documentation or comments.
2.  **Unit Tests**: Your unit tests for services must now be parameterized to run for each broker. You can use `pytest.mark.parametrize` to test the handler logic with different topic names (e.g., `"paper.signals.validated"` and `"zerodha.signals.validated"`) to ensure the broker is correctly inferred.
3.  **Integration Tests**: Your integration tests should be updated to publish messages to topics for _all_ active brokers and assert that the correct downstream messages are produced on the corresponding namespaced topics. For example, a signal on `paper.signals.raw` should result in a fill on `paper.orders.filled`, not `zerodha.orders.filled`.

By including these considerations, your refactoring plan becomes a comprehensive, production-ready strategy that will significantly improve the scalability and maintainability of your system.

That is the final architectural point. The plan is now comprehensive, robust, and covers the full lifecycle of a message from configuration to service logic, health checks, and logging. You have a complete blueprint for the refactoring.

The only remaining piece is to consider the **operational and deployment aspects** that accompany this code change. Think of this as the final checklist before implementation.

### **Final Polish and Operational Readiness**

This isn't a change to the plan itself, but a confirmation of best practices for executing it.

#### ## 1. Topic and DLQ Management Script 📜

While your code will now dynamically use namespaced topics, those topics still need to exist in your Redpanda/Kafka cluster.

- **Recommendation**: Ensure your `scripts/bootstrap_topics.py` is updated to loop through the brokers defined in `TopicConfig` and create all necessary topics (`paper.orders.filled`, `zerodha.orders.filled`) and their corresponding Dead Letter Queues (`paper.orders.filled.dlq`, etc.). This automates your infrastructure setup and prevents runtime errors from missing topics.

---

#### ## 2. State Segregation (Final Check) ✅

This is a final, critical sanity check of your stateful services. With a single service instance handling multiple brokers, any shared state must be rigorously segregated.

- **Redis**: Any key used for caching, idempotency, or state management (like in the `PortfolioCache`) must be prefixed with or include the `broker_id`. For example, instead of `hset("portfolio:positions", ...)`, it must be `hset(f"portfolio:{broker_id}:positions", ...)`.
- **Database**: Ensure that when services query the database, they are filtering by `broker_id` or an equivalent concept if the data is broker-specific.
- **In-Memory State**: For services that hold state in memory (like the `PortfolioManager` might), ensure the state is held in a dictionary keyed by the `broker_id` (e.g., `self.portfolio_managers = {"paper": PaperManager(), "zerodha": ZerodhaManager()}`).

---

#### ## 3. Deployment and Rollout Strategy 🚀

This change is fundamental and affects all services. It cannot be rolled out incrementally; it requires a coordinated deployment.

- **Maintenance Window**: Plan for a brief maintenance window. The system should be fully stopped, the new code deployed, and then everything restarted.
- **Consumer Group Reset**: Your consumer group IDs are changing (e.g., from `...trading_engine.paper` to `...trading_engine.signals`). When the new services start, they will form new groups in Redpanda/Kafka and will, by default, start consuming from the **latest** message on the topics. This is the desired behavior for a trading system as you typically don't want to re-process old signals or orders. Be aware that this "reset" is an expected and normal part of the deployment.

You have a complete and excellent plan. These final points on operations will ensure that its implementation is as smooth and successful as its design.

Note: 'alphap14' stands or 'alpha_panda' in folder paths.
