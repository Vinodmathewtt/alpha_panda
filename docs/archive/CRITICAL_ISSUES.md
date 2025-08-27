# CRITICAL ISSUES

- Stack: PostgreSQL via asyncpg, SQLAlchemy Async ORM (Base in core/
  database/connection.py), DI container wires a shared DatabaseManager.
- Tables: Auth/session (trading_sessions), config
  (strategy_configurations), state (portfolio_snapshots, trading_events),
  instruments (instruments, instrument_registry).
- Usage: Auth persists Zerodha sessions; PortfolioManager persists
  snapshots; Strategy lookups in TradingEngine; Instruments CRUD via
  repositories. No migration tooling present; tables created on startup
  with Base.metadata.create_all.

Critical Issues

- Broken upsert target (PortfolioSnapshot): services/portfolio_manager/
  service.py uses ON CONFLICT (portfolio_id) but portfolio_id is not
  unique/PK in core/database/models.PortfolioSnapshot. This will fail at
  runtime or silently not dedupe. Fix by adding a unique constraint/index
  on portfolio_id (or a composite like (broker_namespace, portfolio_id)),
  or change upsert to a real unique target.
- Auth health-check orchestration: Pre-flight health runs
  ZerodhaAuthenticationCheck before db_manager.init() and before
  AuthService.start() (which performs interactive or token-based auth).
  On a fresh run, Zerodha auth will always fail and block startup; session
  load might hit a missing table. Reorder to initialize DB, then run/
  authenticate (or let the health check drive initialization).
- Session duplication risk (trading_sessions): No uniqueness
  on user_id. Concurrent logins can insert duplicates;
  subsequent .scalar_one_or_none() may raise due to multiple rows.
  Add UNIQUE(user_id) and use an upsert; or make user_id the PK if
  appropriate.

Schema & Constraints

- PortfolioSnapshot: Add unique (portfolio_id) or (broker_namespace,
  portfolio_id). Consider index on (broker_namespace, snapshot_time DESC)
  to accelerate recovery.
- TradingSession: Add UNIQUE(user_id); consider INDEX(updated_at) since
  it’s used for ordering. If only one active session per user is allowed,
  enforce via unique partial index UNIQUE (user_id) WHERE is_active.
- TradingEvent: If querying by recency, add index (broker_namespace,
  event_timestamp) and on (correlation_id).
- StrategyConfiguration: Column rename note: model
  uses zerodha_trading_enabled (comment says “fixed from
  live_trading_enabled”). Without migrations, existing DBs will be out of
  sync. Add a migration to rename or backfill.
- InstrumentRegistry: instrument_token is unique=True but no FK to
  instruments.instrument_token. Add FK with ON DELETE CASCADE/RESTRICT to
  maintain referential integrity.
- JSON types: Using generic JSON. Prefer Postgres JSONB for event_data,
  positions, and session_data to index/filter efficiently.

Session/Transaction Management

- Mixed commit responsibilities: DatabaseManager.get_session()
  auto-commits on context exit while repositories/services also call
  session.commit() and rollback(). This double-commit pattern is
  inconsistent, can hide multi-step failures, and makes transactional
  boundaries unclear.
- Unit of Work: Adopt a UoW style—remove auto-commit from the context
  manager, manage commit/rollback explicitly at the service layer;
  repositories should avoid committing, returning control to the
  orchestrating service.
- Context typing: get_session() annotated as returning AsyncSession,
  but it’s an async context manager; use AsyncContextManager[AsyncSession]
  for clarity.
- Engine settings: No pool_pre_ping=True, pool_size, max_overflow, or
  pool_recycle. Add to prevent stale connections and tune for workload.

Concurrency & Race Conditions

- Session save race: Two processes could both not find a session for a
  user and insert simultaneously; without a UNIQUE(user_id) upsert, this
  can create duplicates and break subsequent saves.
- Bulk upsert inefficiency: InstrumentRepository.bulk_upsert_instruments
  calls upsert_instrument which commits per item; batching then commits
  again. This defeats batching and increases contention. Use a single bulk
  INSERT ... ON CONFLICT DO UPDATE per batch; avoid per-record commits.
- Portfolio snapshots multi-writer: Multiple instances may snapshot
  the same portfolio_id; upsert requires a unique constraint to be safe.
  Without it, duplicate rows occur and latest snapshot detection degrades.

Performance & Indexing

- Missing targeted indexes: Add indexes to match queries: - PortfolioSnapshot(broker_namespace, snapshot_time DESC) - TradingSession(updated_at) if used for recent selection - TradingEvent(broker_namespace, event_timestamp),
  TradingEvent(correlation_id)
- Query shapes: SessionManager.load_session() does fetchall() then picks
  first. Change to limit(1) to avoid unnecessary row materialization.
- Instrument bulk load: Replace looped upserts with set-based statements
  or COPY for large CSV loads.

Orchestration & Flow

- Initialization order: Ensure all model modules are imported before
  create_all(). Currently, AppContainer imports InstrumentRegistryService
  which imports the instrument models, so they are registered—but
  this is fragile. Prefer a central “models import” module imported by
  DatabaseManager.init() or eliminate create_all in favor of migrations.
- Create-all in production: Base.metadata.create_all at startup
  risks schema drift and concurrent DDL. Gate it for dev/test only; use
  migrations for prod.
- Session cleanup: SessionManager.start() is never invoked, so
  \_cleanup_expired_sessions background task never runs. Either start it
  where intended or remove to avoid dead code expectations.

Security & Operations

- Token at rest: Access tokens stored in plaintext
  (trading_sessions.session_data). Encrypt at rest or use a secrets store.
  At minimum, avoid logging tokens and consider column-level encryption.
- Logging in DB manager: Replace print() with structured logging for
  consistency and observability.
- Connection string: Consider TLS (sslmode=require) for production, and
  secrets via env/secret store.

Testing & Tooling

- Migrations: No Alembic setup. Add migrations to support schema
  evolution (e.g., zerodha_trading_enabled rename, new unique
  constraints).
- Out-of-date tests: tests/integration/test_api.py still calls
  deprecated user auth flow and will fail under the new design. Update
  tests to the token-based Zerodha auth and DB schema.

Recommendations

- Migrations & Schema - Add Alembic; generate initial migration matching current models. - Add unique constraints: PortfolioSnapshot(portfolio_id) or
  (broker_namespace, portfolio_id), and TradingSession(user_id). Add
  needed indexes listed above. - For Postgres, switch JSON fields to JSONB. - Add FK instrument_registry.instrument_token ->
  instruments.instrument_token. - Add FK instrument_registry.instrument_token ->
  instruments.instrument_token.
- Transactions & Sessions - Remove auto-commit from DatabaseManager.get_session() and
  centralize commit at service boundaries, or ensure repositories never
  call commit/rollback when using the auto-commit context to avoid
  duplication. - Standardize on sqlalchemy.select (not sqlalchemy.future.select)
  across code.
- Concurrency Hardening - Use INSERT ... ON CONFLICT (user_id) DO UPDATE for sessions to
  ensure idempotency. - Rework instrument bulk upsert to a set-based upsert per batch;
  commit once per batch.
- Orchestration - Reorder startup: initialize DB, then run AuthService.start() (to
  establish or prompt auth), then run health checks (which verify the
  now-initialized/authenticated state), then start other services. - Limit create_all() to dev/test; rely on migrations for prod.
- Performance - Optimize queries (limit(1) for session load), add indexes for hot
- Security - Encrypt sensitive session data at rest; mask tokens in logs. - Add TLS to DB connections in prod environments.
- Operational Hygiene - Add structured logs in DatabaseManager. - Implement periodic pruning for trading_events if it will grow
  unbounded (table partitioning or TTL job).

# Validation of issues and fixes

### 1\. Critical Issue: Broken Upsert Target in `PortfolioSnapshot`

**Validation:**
You are correct; the upsert operation in `services/portfolio_manager/service.py` is flawed. The code attempts an `ON CONFLICT` action targeting the `portfolio_id` column. However, as defined in `core/database/models.py`, the `portfolio_id` column in the `PortfolioSnapshot` table lacks a `UNIQUE` constraint, which is necessary for the `ON CONFLICT` clause to work correctly.

**Recommendation:**
To resolve this, you need to enforce uniqueness on the `portfolio_id`. The most straightforward approach is to add a `UNIQUE` constraint to the `portfolio_id` column in the `PortfolioSnapshot` model.

Here is how you can modify the `core/database/models.py` file:

```python
# File: alphaP/core/database/models.py

from sqlalchemy import Column, Integer, String, Float, JSON, Boolean, DateTime, Text, UniqueConstraint
from sqlalchemy.sql import func
from .connection import Base

# ... (other models)

class PortfolioSnapshot(Base):
    """Persistent storage of portfolio states for paper trading continuity"""
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    # Ensure portfolio_id is unique for upserts to function correctly
    portfolio_id = Column(String, nullable=False, index=True, unique=True)
    broker_namespace = Column(String, nullable=False, index=True)
    strategy_id = Column(String, nullable=False, index=True)

    # ... (rest of the model)

```

By adding `unique=True` to the `portfolio_id` column definition, you provide the necessary constraint for the upsert operation in `PortfolioManagerService` to function as intended.

---

### 2\. Schema & Constraints: `JSON` vs. `JSONB`

**Validation:**
The analysis is accurate. The models in `core/database/models.py` use the generic `JSON` type for several columns (`positions`, `event_data`, `session_data`). While functional, this is not optimal for performance.

**Recommendation:**
For enhanced performance and to enable indexing of JSON data, you should use the `JSONB` data type, which is specific to PostgreSQL.

Here is an example of how you can update the `PortfolioSnapshot` model:

```python
# File: alphaP/core/database/models.py

from sqlalchemy import Column, Integer, String, Float, JSON, Boolean, DateTime, Text
# Import JSONB from the postgresql dialects
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from .connection import Base

# ... (other models)

class PortfolioSnapshot(Base):
    """Persistent storage of portfolio states for paper trading continuity"""
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(String, nullable=False, index=True, unique=True)
    broker_namespace = Column(String, nullable=False, index=True)
    strategy_id = Column(String, nullable=False, index=True)

    # Use JSONB for positions for better performance and indexing capabilities
    positions = Column(JSONB, nullable=False)  # {instrument_token: Position dict}
    total_realized_pnl = Column(Float, default=0.0, nullable=False)
    total_unrealized_pnl = Column(Float, default=0.0, nullable=False)
    total_pnl = Column(Float, default=0.0, nullable=False)
    cash = Column(Float, default=1_000_000.0, nullable=False)

    snapshot_time = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

You should apply this change to all columns currently using the `JSON` type, such as `event_data` in the `TradingEvent` model and `session_data` in the `TradingSession` model, to leverage the benefits of `JSONB`.

### 3\. Critical Issue: Flawed Application Startup Orchestration

**Validation:**
The current startup sequence in `app/main.py` is problematic. It runs health checks, including the `ZerodhaAuthenticationCheck`, _before_ initializing the database or starting the authentication service. On a fresh run, this will cause the `ZerodhaAuthenticationCheck` to fail, preventing the application from starting.

**Recommendation:**
You need to adjust the application's startup logic to ensure that the database is initialized and the `AuthService` is started _before_ running the health checks. This ensures that when the health checks are performed, all necessary services are already operational.

Here’s the recommended change in `app/main.py`:

```python
# File: alphaP/app/main.py

# ... (imports)

class ApplicationOrchestrator:
    # ... (other methods)

    async def startup(self):
        """Initialize application after running pre-flight checks."""
        self.logger.info("🚀 Initializing core services before health checks...")

        # --- SERVICE STARTUP ---
        # Initialize the database first
        db_manager = self.container.db_manager()
        await db_manager.init()

        # Start the authentication service to establish a session if possible
        auth_service = self.container.auth_service()
        await auth_service.start()

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
            await self._cleanup_partial_initialization()
            sys.exit(1)

        self.logger.info("✅ All health checks passed. Proceeding with remaining service startup...")

        # --- START REMAINING SERVICES ---
        all_services = self.container.lifespan_services()
        # Filter out the auth_service since it's already started
        other_services = [s for s in all_services if s is not auth_service]
        await asyncio.gather(*(service.start() for service in other_services if service))

        self.logger.info("✅ All services started successfully.")

```

### 4\. Concurrency Issue: Session Duplication Risk

**Validation:**
The `save_session` method in `services/auth/session_manager.py` is susceptible to a race condition. If two processes attempt to save a new session for the same user simultaneously, both could find that no session exists and then both could proceed to create one, resulting in duplicate entries. This is problematic because other parts of the system expect `scalar_one_or_none()` to return a single result.

**Recommendation:**
To prevent this, you should enforce a `UNIQUE` constraint on the `user_id` column in the `trading_sessions` table and modify the `save_session` method to use an "upsert" operation. This will ensure that if a session for the user already exists, it gets updated; otherwise, a new one is created.

First, update the `TradingSession` model in `core/database/models.py`:

```python
# File: alphaP/core/database/models.py

from sqlalchemy import Column, Integer, String, Float, JSON, Boolean, DateTime, Text, UniqueConstraint
# ... (other imports)

class TradingSession(Base):
    """Trading session storage for authentication persistence"""
    __tablename__ = "trading_sessions"

    session_id = Column(String, primary_key=True, index=True)
    # Add a UNIQUE constraint to user_id to prevent duplicate sessions
    user_id = Column(String, nullable=False, index=True, unique=True)
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    # ... (rest of the model)
```

Next, refactor the `save_session` method in `services/auth/session_manager.py` to perform an upsert:

```python
# File: alphaP/services/auth/session_manager.py
from sqlalchemy.dialects.postgresql import insert as pg_insert

# ... (other code)

async def save_session(self, session_data: SessionData) -> bool:
    """Save session data to PostgreSQL database using an upsert operation."""
    try:
        async with self.db_manager.get_session() as db_session:
            session_data.updated_at = datetime.now(timezone.utc)
            session_data.last_validated = datetime.now(timezone.utc)

            session_dict = {
                "access_token": session_data.access_token,
                "user_name": session_data.user_name,
                # ... (other session data)
            }

            stmt = pg_insert(DBTradingSession).values(
                session_id=session_data.session_id or str(uuid.uuid4()),
                user_id=session_data.user_id,
                end_time=session_data.expires_at,
                is_active=True,
                session_data=session_dict,
                updated_at=session_data.updated_at
            )

            stmt = stmt.on_conflict_do_update(
                index_elements=['user_id'],
                set_={
                    'session_data': stmt.excluded.session_data,
                    'end_time': stmt.excluded.end_time,
                    'is_active': stmt.excluded.is_active,
                    'updated_at': stmt.excluded.updated_at
                }
            )

            await db_session.execute(stmt)
            await db_session.commit()
            self._current_session = session_data
            return True

    except Exception as e:
        logger.error(f"Failed to save session: {e}")
        raise

```

### 5\. Transaction Management: Inconsistent Commits

**Validation:**
There is an inconsistent approach to transaction management. The `DatabaseManager.get_session` context manager in `core/database/connection.py` automatically commits transactions, but repositories like `InstrumentRepository` also contain `session.commit()` calls. This "double commit" pattern can lead to unexpected behavior and makes it difficult to manage transactions that span multiple operations.

**Recommendation:**
Adopt a clear "Unit of Work" pattern. The service layer should be responsible for managing the lifecycle of a transaction (commit or rollback), while the repository layer should only handle data access.

To implement this, first remove the automatic commit from `DatabaseManager`:

```python
# File: alphaP/core/database/connection.py

# ... (imports)

class DatabaseManager:
    # ... (other methods)

    @asynccontextmanager
    async def get_session(self) -> AsyncSession:
        """Provides a new database session context manager."""
        async with self._session_factory() as session:
            try:
                yield session
                # The service layer will now be responsible for committing.
            except Exception:
                await session.rollback()
                raise
```

Then, remove `commit()` and `rollback()` calls from your repositories. For example, in `InstrumentRepository`:

```python
# File: alphaP/services/instrument_data/instrument_repository.py

# ... (imports)

class InstrumentRepository:
    # ... (other methods)

    async def create_instrument(self, instrument: Instrument) -> Instrument:
        """Create a new instrument in the database."""
        try:
            self.session.add(instrument)
            # No commit here. The service layer will handle it.
            await self.session.flush() # Use flush to get the ID without committing
            await self.session.refresh(instrument)
            logger.debug(f"Created instrument", instrument_token=instrument.instrument_token)
            return instrument
        except SQLAlchemyError as e:
            logger.error(f"Failed to create instrument", error=str(e))
            raise

```

Finally, ensure that your service layer, which uses the repository, explicitly commits the transaction.

### 6\. Performance: Inefficient Bulk Upsert

**Validation:**
The `bulk_upsert_instruments` method in `services/instrument_data/instrument_repository.py` is highly inefficient. It iterates through a list of instruments and calls `upsert_instrument` for each one, which in turn performs a `SELECT` followed by either an `INSERT` or `UPDATE`. This results in a large number of database round-trips, negating the benefits of batching.

**Recommendation:**
For a more performant implementation, you should use a single `INSERT ... ON CONFLICT DO UPDATE` statement for each batch of instruments.

Here is the corrected `bulk_upsert_instruments` method:

```python
# File: alphaP/services/instrument_data/instrument_repository.py
from sqlalchemy.dialects.postgresql import insert as pg_insert

# ... (other code)

async def bulk_upsert_instruments(self, instruments_data: List[Dict[str, Any]],
                                  source_file: str = None, batch_size: int = 1000) -> int:
    """Efficiently bulk insert or update instruments using a single upsert statement per batch."""
    total_processed = 0
    try:
        for i in range(0, len(instruments_data), batch_size):
            batch = instruments_data[i:i + batch_size]

            if not batch:
                continue

            stmt = pg_insert(Instrument).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=['instrument_token'],
                set_={
                    'name': stmt.excluded.name,
                    'exchange': stmt.excluded.exchange,
                    # ... other columns to update
                }
            )
            result = await self.session.execute(stmt)
            total_processed += result.rowcount

        logger.info(f"Bulk upsert completed", total_processed=total_processed)
        return total_processed
    except Exception as e:
        logger.error(f"Bulk upsert failed", error=str(e))
        raise

```

### 7\. Security: Plaintext Storage of Access Tokens

**Validation:**
The `trading_sessions.session_data` column stores sensitive information, including access tokens, in plaintext `JSON`. Storing secrets in this manner is a significant security risk.

**Recommendation:**
You should encrypt sensitive data before storing it in the database. The `cryptography` library is an excellent choice for this. Here's a conceptual example of how you could integrate this into your `SessionManager`:

```python
# A conceptual example of how to integrate encryption
from cryptography.fernet import Fernet

# You would generate and store this key securely (e.g., in a secrets manager)
ENCRYPTION_KEY = b'your-super-secret-encryption-key'
cipher_suite = Fernet(ENCRYPTION_KEY)

def encrypt_token(token: str) -> str:
    return cipher_suite.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    return cipher_suite.decrypt(encrypted_token.encode()).decode()

# In SessionManager.save_session:
session_dict["access_token"] = encrypt_token(session_data.access_token)

# In SessionManager.load_session:
access_token = decrypt_token(session_dict.get("access_token", ""))

```

### 8\. Testing: Outdated Integration Tests

**Validation:**
The integration tests in `tests/integration/test_api.py` are outdated. They are designed for a username/password authentication flow, which has been deprecated in favor of Zerodha-based token authentication.

**Recommendation:**
The tests need to be updated to reflect the current authentication mechanism. This involves removing the user creation logic and modifying the API tests to use a valid Zerodha access token for authentication.
Here is an example of how you might update `tests/integration/test_api.py`:

```python
# File: tests/integration/test_api.py
import os
import httpx
import pytest

# It's better to use environment variables for test tokens
ZERODHA_ACCESS_TOKEN = os.environ.get("TEST_ZERODHA_ACCESS_TOKEN")

@pytest.mark.skipif(not ZERODHA_ACCESS_TOKEN, reason="Test Zerodha access token not provided")
async def test_api_endpoints_with_zerodha_auth():
    """Test API endpoints using Zerodha token-based authentication."""
    base_url = "http://localhost:8000"
    headers = {"Authorization": f"Bearer {ZERODHA_ACCESS_TOKEN}"}

    async with httpx.AsyncClient() as client:
        # Test establishing the session (this might be done implicitly by other services)
        # Or you might have an endpoint to explicitly establish the session

        # Test protected portfolio endpoints
        response = await client.get(f"{base_url}/api/v1/portfolios/", headers=headers)
        assert response.status_code == 200
        # ... more assertions
```

By addressing these issues, you will significantly improve the robustness, security, and performance of your application. Let me know if you have any other questions.

### 13\. Streaming Logic: Incomplete Error Handling

**Validation:**
A key component of a robust streaming architecture is a strategy for handling messages that cannot be processed—often called "poison pill" messages. In `services/portfolio_manager/service.py`, the `_handle_processing_error` method contains a `TODO` comment indicating that a Dead Letter Queue (DLQ) pattern has not been implemented. Without a DLQ, a malformed or problematic message could either be repeatedly retried, consuming resources and potentially causing a consumer crash loop, or be discarded, leading to data loss.

**Recommendation:**
You should implement a proper DLQ mechanism. When a message fails processing after a defined number of retries, it should be moved to a separate "dead-letter" topic in Redpanda. This isolates the problematic message for later analysis without halting the main processing pipeline.

Here's how you could modify the error handler in `PortfolioManagerService`:

```python
# File: alphaP/services/portfolio_manager/service.py

class PortfolioManagerService(StreamProcessor):
    def __init__(self, config: RedpandaSettings, settings: Settings, redis_client, db_manager: DatabaseManager):
        # ... (other initializations)
        # Add a producer for sending to DLQ
        self.dlq_producer = RedpandaProducer(config)
        self.dlq_topic = f"{self.topics.orders_filled()}.dlq" # Example DLQ topic name
        self.max_retries = 3 # Make this configurable

    async def start(self):
        # ...
        await self.dlq_producer.start()
        # ...

    async def stop(self):
        # ...
        await self.dlq_producer.stop()
        # ...

    async def _handle_processing_error(self, message: Dict, error: Exception):
        """Handle processing errors with retry and DLQ logic."""
        self.error_logger.error("Error processing message", error=str(error), message=message)

        # Increment retry count (could be stored in message headers or Redis)
        retries = message.get('__retries', 0) + 1

        if retries > self.max_retries:
            self.error_logger.error("Message exceeded max retries. Sending to DLQ.", message=message)
            try:
                await self.dlq_producer.send_message(
                    topic=self.dlq_topic,
                    key=message.get('id', 'unknown_key'),
                    value={'original_message': message, 'error': str(error)}
                )
            except Exception as e:
                self.error_logger.critical("Failed to send message to DLQ!", error=str(e))
        else:
            # For now, we are just logging. A retry mechanism would go here.
            # In a real system, you might requeue the message with a delay.
            self.logger.warning(f"Processing failed for message. Attempt {retries}/{self.max_retries}.")
```

---

### 14\. Configuration: Hardcoded Values and Magic Strings

**Validation:**
Several configuration values and key strings are hardcoded directly in the service logic. For example, in `services/portfolio_manager/service.py`, the snapshot interval is fixed at `300` seconds, and the event type `'pnl_snapshot'` is used as a raw string with a `TODO` to add it to the `EventType` enum. Hardcoding values makes the application inflexible and error-prone.

**Recommendation:**
All configurable values should be managed through your `Settings` object, and recurring strings should be defined as constants or enum members.

1.  **Move `snapshot_interval` to `Settings`**:

    ```python
    # File: alphaP/core/config/settings.py
    class PortfolioManagerSettings(BaseSettings):
        snapshot_interval_seconds: int = 300

    class Settings(BaseSettings):
        # ...
        portfolio_manager: PortfolioManagerSettings = PortfolioManagerSettings()

    # File: alphaP/services/portfolio_manager/service.py
    # In PortfolioManagerService.__init__:
    self.snapshot_interval = self.settings.portfolio_manager.snapshot_interval_seconds
    ```

2.  **Add `PNL_SNAPSHOT` to `EventType` Enum**:

    ```python
    # File: alphaP/core/schemas/events.py
    class EventType(str, Enum):
        # ... (other event types)
        ORDER_FILLED = "ORDER_FILLED"
        MARKET_TICK = "MARKET_TICK"
        PNL_SNAPSHOT = "PNL_SNAPSHOT" # Add the new event type

    # File: alphaP/services/portfolio_manager/service.py
    # In _handle_message:
    elif topic == self.topics.pnl_snapshots():
        if event_type == EventType.PNL_SNAPSHOT: # Use the enum member
            await self._handle_pnl_snapshot(message.get('data', {}))
    ```

---

### 16\. Logging: Inconsistent Practices

**Validation:**
While most of the application uses a structured logging setup, there are still instances of `print()` statements, notably in `core/database/connection.py`. Using `print()` bypasses the configured logging system, which means these messages will not have consistent formatting, cannot be routed to different outputs (like a log file or a monitoring service), and their verbosity cannot be controlled by log levels.

**Recommendation:**
You should replace all `print()` statements with calls to the appropriate logger. This ensures all application output is standardized and manageable.

```python
# File: alphaP/core/database/connection.py
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
# ...

logger = logging.getLogger(__name__)

class DatabaseManager:
    # ... (other methods)
    async def init(self):
        """Initializes the database connection and creates tables"""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Replace print() with logger.info()
        logger.info("Database initialized and tables created.")

    async def shutdown(self):
        """Closes the database connection pool"""
        await self._engine.dispose()
        # Replace print() with logger.info()
        logger.info("Database connection pool closed.")
```

By addressing these final points, you will have a significantly more robust, maintainable, and production-ready application. This concludes my comprehensive review of your codebase.
