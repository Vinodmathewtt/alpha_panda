## Core Module

`core` module, designed to be the foundational layer for your new Unified Log architecture.

The `core` module contains all the shared, cross-cutting concerns of your application. Its purpose is to provide robust, reusable components for configuration, database access, and stream processing, so that your individual services can focus solely on their business logic.

---

### 1\. `core/config/settings.py`

This file is responsible for loading and validating all application configurations. We use Pydantic for its excellent data validation and ability to load settings from environment variables, which is a best practice for modern applications.

```python
# AlphasPT_v2/core/config/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel
from enum import Enum


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class DatabaseSettings(BaseModel):
    postgres_url: str = "postgresql+asyncpg://alphapt:alphapt@localhost:5432/alphapt"


class RedpandaSettings(BaseModel):
    bootstrap_servers: str = "localhost:9092"
    client_id: str = "alphapt-client"
    group_id: str = "alphapt-group"


class Settings(BaseSettings):
    """
    Main application settings, loaded from environment variables.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore"
    )

    app_name: str = "AlphaPT_v2"
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    database: DatabaseSettings = DatabaseSettings()
    redpanda: RedpandaSettings = RedpandaSettings()

```

**Explanation:**

- **Pydantic `BaseSettings`**: This class automatically reads configuration from environment variables. For example, to set the Redpanda server, you would set an environment variable like `REDPANDA__BOOTSTRAP_SERVERS=your_redpanda_host:9092`.
- **Type Safe**: Pydantic ensures that your configuration values are of the correct type (e.g., strings, numbers), preventing common errors.
- **Centralized**: All configuration for the entire application is defined and loaded from this single place, making it easy to manage.

---

### 2\. `core/database/connection.py`

This file manages the lifecycle of the PostgreSQL connection. It's designed as a resource that can be automatically managed by the dependency injection container.

```python
# AlphasPT_v2/core/database/connection.py

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

# The base class for all your SQLAlchemy models
Base = declarative_base()


class DatabaseManager:
    """
    Manages the connection to the PostgreSQL database.
    """

    def __init__(self, db_url: str):
        self._engine = create_async_engine(db_url, echo=False)
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession
        )

    async def init(self):
        """Initializes the database connection and creates tables."""
        async with self._engine.begin() as conn:
            # This will create all tables that inherit from the Base model
            await conn.run_sync(Base.metadata.create_all)
        print("Database initialized and tables created.")

    async def shutdown(self):
        """Closes the database connection pool."""
        await self._engine.dispose()
        print("Database connection pool closed.")

    def get_session(self) -> AsyncSession:
        """Provides a new database session."""
        return self._session_factory()

```

**Explanation:**

- **Async First**: The code uses `asyncpg` and `SQLAlchemy`'s async support, which is essential for a high-performance, non-blocking application.
- **Connection Pool**: `create_async_engine` creates a pool of database connections, which is much more efficient than creating a new connection for every query.
- **Session Management**: The `get_session` method provides a clean way for services to get a database session to perform their queries.

---

### 3\. `core/database/models.py`

Here, you define the database tables for your **application state** data using SQLAlchemy's ORM.

```python
# AlphasPT_v2/core/database/models.py

from sqlalchemy import Column, Integer, String, Float, JSON, Boolean
from .connection import Base


class StrategyConfiguration(Base):
    """
    Represents the master configuration for a single trading strategy.
    """
    __tablename__ = "strategy_configurations"

    id = Column(String, primary_key=True, index=True) # e.g., "Momentum_NIFTY_1"
    strategy_type = Column(String, nullable=False)   # e.g., "SimpleMomentumStrategy"
    instruments = Column(JSON, nullable=False)       # e.g., [738561, 2714625]
    parameters = Column(JSON, nullable=False)        # e.g., {"lookback_period": 20}
    is_active = Column(Boolean, default=True, nullable=False)


class User(Base):
    """
    Represents a user account for managing the application.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

# You would add other models here, e.g., for RiskProfiles, BrokerCredentials etc.

```

**Explanation:**

- **Declarative Models**: Each class maps directly to a table in your PostgreSQL database.
- **Clear Schema**: This provides a single, clear definition of your database schema, which is easy to read and maintain.
- **Separation of Concerns**: This file is only concerned with the _shape_ of the data, not how it's connected to or queried.

---

### 4\. `core/streaming/clients.py`

This is a critical new component. These classes provide a simple, standardized interface for interacting with Redpanda, hiding the complexity of the underlying Kafka client library.

```python
# AlphasPT_v2/core/streaming/clients.py

import json
from confluent_kafka import Producer, Consumer, KafkaException
from core.config.settings import RedpandaSettings


class RedpandaProducer:
    """
    A standardized wrapper for the Confluent Kafka producer.
    """

    def __init__(self, config: RedpandaSettings):
        self._producer = Producer({
            'bootstrap.servers': config.bootstrap_servers,
            'client.id': config.client_id
        })

    def _delivery_report(self, err, msg):
        """Callback for message delivery reports."""
        if err is not None:
            print(f"Message delivery failed: {err}")
        else:
            # For high-volume, you would typically disable or sample this
            # print(f"Message delivered to {msg.topic()} [{msg.partition()}]")
            pass

    def produce(self, topic: str, message: dict):
        """
        Produces a message to a Redpanda topic.

        Args:
            topic: The name of the topic to produce to.
            message: A dictionary to be sent as the message value (will be JSON encoded).
        """
        self._producer.poll(0)
        self._producer.produce(
            topic,
            value=json.dumps(message).encode('utf-8'),
            callback=self._delivery_report
        )

    def flush(self):
        """Waits for all outstanding messages to be delivered."""
        self._producer.flush()


class RedpandaConsumer:
    """
    A standardized wrapper for the Confluent Kafka consumer.
    """

    def __init__(self, config: RedpandaSettings, topics: list[str]):
        self._consumer = Consumer({
            'bootstrap.servers': config.bootstrap_servers,
            'group.id': config.group_id,
            'auto.offset.reset': 'earliest'
        })
        self._consumer.subscribe(topics)

    def consume(self, timeout: float = 1.0) -> dict | None:
        """
        Consumes a single message from the subscribed topics.

        Args:
            timeout: The time to wait for a message.

        Returns:
            The decoded JSON message as a dictionary, or None if no message
            was received within the timeout.
        """
        msg = self._consumer.poll(timeout)

        if msg is None:
            return None
        if msg.error():
            raise KafkaException(msg.error())

        return json.loads(msg.value().decode('utf-8'))

    def close(self):
        """Closes the consumer connection."""
        self._consumer.close()

```

**Explanation:**

- **Encapsulation**: Your services will use these simple `produce()` and `consume()` methods. They won't need to know anything about the complexities of the `confluent-kafka` library.
- **Standardization**: Every message is automatically encoded to JSON, ensuring consistency across the entire system.
- **Error Handling**: Basic error handling and delivery reports are built-in, making the system more robust.

---

### 5\. `core/logging.py`

This file provides a single function to configure structured logging for the entire application, ensuring all log messages have a consistent format.

```python
# AlphasPT_v2/core/logging.py

import sys
import logging
import structlog
from core.config.settings import Settings


def configure_logging(settings: Settings):
    """
    Configures structured logging for the application using structlog.
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level.upper(),
    )

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> any:
    """
    Returns a structlog logger instance for a given module name.
    """
    return structlog.get_logger(name)

```

**Explanation:**

- **`structlog`**: We use `structlog` because it makes it easy to produce JSON-formatted logs, which are essential for modern monitoring and log analysis tools.
- **Consistent Format**: Every log entry will be a JSON object containing a timestamp, the log level, and the message, making them easy to parse and query.
- **`get_logger`**: A simple helper function so that any module in your application can get a correctly configured logger with a single line of code.
