## App Module Full Refactoring

The current `app` module is functional but minimalistic. A simple lifecycle manager is fine for getting started, but a robust orchestrator needs a **pre-trade check system**. It should validate that all external dependencies are available and that the configuration is sane _before_ attempting to start the core trading logic. Failing fast is a critical principle for reliable systems.

Here is a complete refactoring plan for the `app` module and a new `core/health.py` module to build this robust, self-validating startup process.

---

### 1\. New Module: The Health Check Engine (`core/health.py`)

First, we'll create a new, dedicated module for all health-checking logic. This keeps the concern of "validating system state" separate from the concern of "running the application."

**File**: `alphaP/core/health.py` **(New)**

```python
# alphaP/core/health.py

import asyncio
from typing import List, Any, Dict
from pydantic import BaseModel
from abc import ABC, abstractmethod

from core.database.connection import DatabaseManager
from core.config.settings import Settings
from aiokafka.admin import AIOKafkaAdminClient
import redis.asyncio as redis

class HealthCheckResult(BaseModel):
    """Standardized result for a health check."""
    component: str
    passed: bool
    message: str

class HealthCheck(ABC):
    """Abstract base class for a single health check."""
    @abstractmethod
    async def check(self) -> HealthCheckResult:
        ...

class DatabaseHealthCheck(HealthCheck):
    """Checks the PostgreSQL database connection."""
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    async def check(self) -> HealthCheckResult:
        try:
            async with self.db_manager.get_session() as session:
                await session.execute(text("SELECT 1"))
            return HealthCheckResult(component="PostgreSQL", passed=True, message="Connection successful.")
        except Exception as e:
            return HealthCheckResult(component="PostgreSQL", passed=False, message=f"Connection failed: {e}")

class RedisHealthCheck(HealthCheck):
    """Checks the Redis connection."""
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client

    async def check(self) -> HealthCheckResult:
        try:
            await self.redis_client.ping()
            return HealthCheckResult(component="Redis", passed=True, message="Connection successful.")
        except Exception as e:
            return HealthCheckResult(component="Redis", passed=False, message=f"Connection failed: {e}")

class RedpandaHealthCheck(HealthCheck):
    """Checks the Redpanda/Kafka connection."""
    def __init__(self, settings: Settings):
        self.settings = settings

    async def check(self) -> HealthCheckResult:
        admin_client = None
        try:
            admin_client = AIOKafkaAdminClient(
                bootstrap_servers=self.settings.redpanda.bootstrap_servers
            )
            await admin_client.start()
            await admin_client.describe_cluster()
            return HealthCheckResult(component="Redpanda", passed=True, message="Connection successful.")
        except Exception as e:
            return HealthCheckResult(component="Redpanda", passed=False, message=f"Connection failed: {e}")
        finally:
            if admin_client:
                await admin_client.close()

class ZerodhaCredentialsCheck(HealthCheck):
    """Checks that Zerodha credentials are provided if enabled."""
    def __init__(self, settings: Settings):
        self.settings = settings

    async def check(self) -> HealthCheckResult:
        if self.settings.zerodha.enabled:
            if not self.settings.zerodha.api_key or not self.settings.zerodha.api_secret:
                return HealthCheckResult(
                    component="Zerodha Config",
                    passed=False,
                    message="Zerodha is enabled, but API_KEY or API_SECRET is missing in config."
                )
        return HealthCheckResult(component="Zerodha Config", passed=True, message="Configuration is valid.")


class SystemHealthMonitor:
    """Orchestrator for running all system health checks."""
    def __init__(self, checks: List[HealthCheck]):
        self.checks = checks
        self.is_healthy = False
        self.results: List[HealthCheckResult] = []

    async def run_checks(self) -> bool:
        """Runs all registered health checks concurrently."""
        self.results = await asyncio.gather(*(check.check() for check in self.checks))
        self.is_healthy = all(result.passed for result in self.results)
        return self.is_healthy

```

---

### 2\. Refactored Application Orchestrator (`app/main.py`)

The main application orchestrator is now refactored to use the `SystemHealthMonitor`. Its `startup` sequence now begins with the pre-flight checks, and it will exit gracefully if any check fails, printing a detailed report.

**File**: `alphaP/app/main.py` **(Refactored)**

```python
# alphaP/app/main.py

import asyncio
import signal
import sys
import logging

from core.logging import configure_logging, get_logger
from app.containers import AppContainer
from core.health import SystemHealthMonitor

class ApplicationOrchestrator:
    """Main application orchestrator with pre-flight health checks."""

    def __init__(self):
        self.container = AppContainer()
        # Wire the container to the modules that need DI
        self.container.wire(modules=[__name__, "core.health", "api.dependencies"])

        self.settings = self.container.settings()
        configure_logging(self.settings)
        self.logger = get_logger("alpha_panda.main")

        self.health_monitor: SystemHealthMonitor = self.container.system_health_monitor()
        self._shutdown_event = asyncio.Event()

    async def startup(self):
        """Initialize application after running pre-flight checks."""
        self.logger.info("🚀 Conducting system pre-flight health checks...")

        # --- PRE-FLIGHT CHECKS ---
        is_healthy = await self.health_monitor.run_checks()

        for result in self.health_monitor.results:
            if result.passed:
                self.logger.info(f"✅ Health check PASSED for {result.component}: {result.message}")
            else:
                self.logger.error(f"❌ Health check FAILED for {result.component}: {result.message}")

        if not is_healthy:
            self.logger.critical("System health checks failed. Application will not start.")
            self.logger.critical("Please fix the configuration or infrastructure issues above and restart.")
            sys.exit(1) # Exit with a non-zero code to indicate failure

        self.logger.info("✅ All health checks passed. Proceeding with service startup...")

        # --- SERVICE STARTUP (only if checks pass) ---
        db_manager = self.container.db_manager()
        await db_manager.init()

        services = self.container.lifespan_services()
        await asyncio.gather(*(service.start() for service in services if service))
        self.logger.info("✅ All services started successfully.")

    async def shutdown(self):
        """Gracefully shutdown application."""
        self.logger.info("🛑 Shutting down Alpha Panda application...")

        services = self.container.lifespan_services()
        await asyncio.gather(*(service.stop() for service in reversed(services) if service))

        db_manager = self.container.db_manager()
        await db_manager.shutdown()

        self.logger.info("✅ Alpha Panda application shutdown complete.")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received shutdown signal: {signal.strsignal(signum)}")
        self._shutdown_event.set()

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

### 3\. Wiring the Health Checks in the DI Container (`app/containers.py`)

Finally, we need to update the container to build our new health check components and inject them into the application orchestrator.

**File**: `alphaP/app/containers.py` **(Updated)**

```python
# alphaP/app/containers.py

from dependency_injector import containers, providers
from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.streaming.clients import RedpandaProducer
# New imports for health checks
from core.health import (
    SystemHealthMonitor,
    DatabaseHealthCheck,
    RedisHealthCheck,
    RedpandaHealthCheck,
    ZerodhaCredentialsCheck,
)
# ... other service imports
import redis.asyncio as redis


class AppContainer(containers.DeclarativeContainer):
    """Application dependency injection container"""

    # --- Core Infrastructure ---
    settings = providers.Singleton(Settings)

    db_manager = providers.Singleton(
        DatabaseManager,
        db_url=settings.provided.database.postgres_url
    )

    redis_client = providers.Singleton(
        redis.from_url,
        settings.provided.redis.url,
        decode_responses=True
    )

    # --- Health Check Providers ---
    db_health_check = providers.Singleton(DatabaseHealthCheck, db_manager=db_manager)
    redis_health_check = providers.Singleton(RedisHealthCheck, redis_client=redis_client)
    redpanda_health_check = providers.Singleton(RedpandaHealthCheck, settings=settings)
    zerodha_creds_check = providers.Singleton(ZerodhaCredentialsCheck, settings=settings)

    health_checks_list = providers.List(
        db_health_check,
        redis_health_check,
        redpanda_health_check,
        zerodha_creds_check
    )

    system_health_monitor = providers.Singleton(
        SystemHealthMonitor,
        checks=health_checks_list
    )

    # ... (other service providers like portfolio_cache, auth_service, etc.)

    # --- Application Orchestrator ---
    # The application itself is managed by the container. It's no longer in this file.
```

The `app/services.py` file defining the `LifespanService` protocol is well-structured and does not require changes for this refactoring.

With these changes, your application now has a robust, fail-fast startup sequence that validates its dependencies and configuration, providing clear, actionable feedback if something is wrong.

Yes, the files I provided in the previous response are intended as **full replacements** for `app/main.py` and the new `core/health.py`. The snippets for `app/containers.py` should be integrated into your existing refactored container file.

Regarding your second question, that's an excellent idea and a best practice for a robust system. Separating infrastructure checks (like "is the database up?") from custom logic checks (like "is the market open?") is a great way to keep your code organized.

We can create a dedicated script for these custom pre-flight checks. Let's place it in the `app` module as you suggested.

---

### 1\. New File: Custom Pre-flight Checks (`app/preflight_checks.py`)

This new file will contain application-specific startup validations. Each check will implement the `HealthCheck` protocol we defined in `core/health.py`, ensuring they integrate seamlessly into the `SystemHealthMonitor`.

**File**: `app/preflight_checks.py` **(New)**

```python
# alphaP/app/pre_trading_checks.py

from datetime import datetime, time
import pytz
from typing import List, Any, Dict

from core.health import HealthCheck, HealthCheckResult
from core.database.connection import DatabaseManager
from core.database.models import StrategyConfiguration
from services.auth.service import AuthService
from sqlalchemy import select

class ActiveStrategiesCheck(HealthCheck):
    """Checks if there is at least one active strategy in the database."""
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    async def check(self) -> HealthCheckResult:
        try:
            async with self.db_manager.get_session() as session:
                stmt = select(StrategyConfiguration).where(StrategyConfiguration.is_active == True)
                result = await session.execute(stmt)
                active_strategies = result.scalars().all()

                if not active_strategies:
                    return HealthCheckResult(
                        component="Strategy Config",
                        passed=False,
                        message="No active strategies found in the database. Trading cannot proceed."
                    )

                return HealthCheckResult(
                    component="Strategy Config",
                    passed=True,
                    message=f"Found {len(active_strategies)} active strategies."
                )
        except Exception as e:
            return HealthCheckResult(component="Strategy Config", passed=False, message=f"Database query failed: {e}")


class BrokerApiHealthCheck(HealthCheck):
    """
    Checks if the broker API is responsive by attempting to fetch the user profile.
    This also validates the stored access token.
    """
    def __init__(self, auth_service: AuthService):
        self.auth_service = auth_service

    async def check(self) -> HealthCheckResult:
        if not self.auth_service.is_authenticated():
            return HealthCheckResult(
                component="Zerodha API",
                passed=False,
                message="No authenticated session found. Cannot check broker API health."
            )
        try:
            profile = await self.auth_service.get_current_user_profile()
            if profile:
                return HealthCheckResult(
                    component="Zerodha API",
                    passed=True,
                    message=f"Successfully connected to broker API for user: {profile.user_shortname}."
                )
            else:
                 return HealthCheckResult(
                    component="Zerodha API",
                    passed=False,
                    message="Session is active but failed to fetch user profile. Token may be invalid."
                )
        except Exception as e:
            return HealthCheckResult(component="Zerodha API", passed=False, message=f"API call failed: {e}")


class MarketHoursCheck(HealthCheck):
    """Checks if the current time is within typical Indian market hours."""
    def __init__(self):
        self.market_open = time(9, 15)
        self.market_close = time(15, 30)
        self.ist = pytz.timezone('Asia/Kolkata')

    async def check(self) -> HealthCheckResult:
        now_ist = datetime.now(self.ist)

        # Check if it's a weekday (0=Monday, 6=Sunday)
        if now_ist.weekday() >= 5:
            return HealthCheckResult(component="Market Hours", passed=False, message="Market is closed (weekend).")

        current_time = now_ist.time()
        if self.market_open <= current_time <= self.market_close:
             return HealthCheckResult(component="Market Hours", passed=True, message="Market is open.")
        else:
            return HealthCheckResult(component="Market Hours", passed=False, message="Market is closed (outside 9:15 AM - 3:30 PM IST).")

```

---

### 2\. Update the DI Container to Include the New Checks

Now, we simply need to wire these new checks into our `SystemHealthMonitor`. This is the beauty of the dependency injection pattern—you can easily add new functionality without changing the orchestrator logic.

**File**: `alphaP/app/containers.py` **(Updated)**

```python
# alphaP/app/containers.py

# ... (other imports)
from core.health import (
    SystemHealthMonitor,
    DatabaseHealthCheck,
    RedisHealthCheck,
    RedpandaHealthCheck,
    ZerodhaCredentialsCheck,
)
# Import the new custom checks
from app.pre_trading_checks import (
    ActiveStrategiesCheck,
    BrokerApiHealthCheck,
    MarketHoursCheck,
)
from services.auth.service import AuthService
# ...

class AppContainer(containers.DeclarativeContainer):
    # ... (settings, db_manager, redis_client, auth_service providers)

    # --- Health Check Providers ---
    # Infrastructure Checks
    db_health_check = providers.Singleton(DatabaseHealthCheck, db_manager=db_manager)
    redis_health_check = providers.Singleton(RedisHealthCheck, redis_client=redis_client)
    redpanda_health_check = providers.Singleton(RedpandaHealthCheck, settings=settings)

    # Configuration and Logic Checks
    zerodha_creds_check = providers.Singleton(ZerodhaCredentialsCheck, settings=settings)
    active_strategies_check = providers.Singleton(ActiveStrategiesCheck, db_manager=db_manager)
    broker_api_check = providers.Singleton(BrokerApiHealthCheck, auth_service=auth_service)
    market_hours_check = providers.Singleton(MarketHoursCheck) # No dependencies

    # Aggregate all checks into a single list
    health_checks_list = providers.List(
        # Infrastructure
        db_health_check,
        redis_health_check,
        redpanda_health_check,
        # Config & Logic
        zerodha_creds_check,
        active_strategies_check,
        broker_api_check,
        # (Optional) You can enable/disable checks easily
        # market_hours_check,
    )

    system_health_monitor = providers.Singleton(
        SystemHealthMonitor,
        checks=health_checks_list
    )

    # ... (rest of the service providers)

```

With this structure, you now have a clear separation between foundational infrastructure checks (`core/health.py`) and your own custom application-level pre-flight checks (`app/pre_trading_checks.py`). You can add as many new checks as you need to the `pre_trading_checks.py` file and simply wire them into the `health_checks_list` in the container to have them run automatically at startup.

Please note mareket hours check should only give warning as of now. It should not cause the shut down. Because we are currently developing and hence running application outside of market hours.
