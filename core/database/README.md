# Core Database Module

## Overview

The `core/database/` module provides PostgreSQL database integration with async SQLAlchemy support, connection management, and data models for Alpha Panda's persistent storage needs.

## Components

### `connection.py`
Database connection manager with async SQLAlchemy integration:

- **DatabaseManager**: Main class for managing PostgreSQL connections
- **Async Engine**: SQLAlchemy async engine with connection pooling
- **Session Management**: Async session factory and context managers
- **Schema Management**: Automatic table creation and migration support
- **Connection Pooling**: Optimized connection pool configuration
- **Health Checking**: Database connectivity validation

### `models.py`
SQLAlchemy ORM models for application data:

- **User**: User authentication and account management
- **TradingSession**: Trading session persistence and authentication state
- **Strategy**: Strategy configuration and metadata storage
- **Instrument**: Financial instrument definitions and mappings
- **PortfolioSnapshot**: Historical portfolio state snapshots

## Key Features

- **Async Support**: Full asyncio compatibility with SQLAlchemy async
- **Connection Pooling**: Optimized pool configuration for high concurrency
- **Schema Management**: Automatic table creation with migration support
- **Type Safety**: Pydantic model integration with SQLAlchemy
- **Performance Logging**: Database operation monitoring and metrics
- **Health Checks**: Connection status monitoring and validation
- **Transaction Support**: Context managers for database transactions

## Usage

### Database Connection
```python
from core.database.connection import DatabaseManager
from core.config.settings import get_settings

# Initialize database manager
settings = get_settings()
db_manager = DatabaseManager(
    db_url=settings.database.postgres_url,
    environment="development",
    schema_management="auto"
)

# Start database connection
await db_manager.connect()

# Get database session
async with db_manager.get_session() as session:
    # Perform database operations
    result = await session.execute(text("SELECT 1"))
```

### Model Usage
```python
from core.database.models import User, TradingSession
from core.database.connection import DatabaseManager

# Create new user
async with db_manager.get_session() as session:
    user = User(username="trader", hashed_password="hash")
    session.add(user)
    await session.commit()

# Query users
async with db_manager.get_session() as session:
    users = await session.execute(
        select(User).where(User.username == "trader")
    )
    user = users.scalar_one_or_none()
```

### Health Checking
```python
# Check database connectivity
health_status = await db_manager.health_check()
if health_status["status"] == "healthy":
    print("Database connection is healthy")
```

## Data Models

### User Model
- **id**: Primary key
- **username**: Unique username for authentication
- **hashed_password**: Secure password hash
- **created_at**: Account creation timestamp

### TradingSession Model
- **session_id**: Unique session identifier
- **user_id**: Associated user ID
- **start_time/end_time**: Session lifetime
- **is_active**: Session active status
- **session_data**: JSON session metadata

### Strategy Model
- **strategy_id**: Unique strategy identifier
- **name**: Strategy name
- **config**: Strategy configuration (JSONB)
- **active_brokers**: List of enabled brokers
- **parameters**: Strategy-specific parameters

### Instrument Model
- **instrument_token**: Unique instrument identifier
- **trading_symbol**: Human-readable symbol
- **name**: Full instrument name
- **segment**: Market segment (NSE, BSE, etc.)
- **instrument_type**: Type (EQ, FUT, OPT, etc.)

## Architecture Patterns

- **Async Context Managers**: All database operations use async context managers
- **Connection Pooling**: Efficient connection reuse and management
- **Transaction Boundaries**: Clear transaction scoping with rollback support
- **Schema Versioning**: Migration support for production deployments
- **Performance Monitoring**: Automatic query performance tracking
- **Error Handling**: Structured database error handling and logging

## Configuration

Database configuration through settings:

```python
# Database settings in core/config/settings.py
class DatabaseSettings(BaseModel):
    postgres_url: str = "postgresql+asyncpg://user:pass@localhost:5432/db"
    schema_management: str = "auto"  # auto, create_all, migrations_only
    verify_migrations: bool = True
```

## Best Practices

1. **Use Async Sessions**: Always use async session context managers
2. **Transaction Scoping**: Keep transactions as short as possible
3. **Connection Pooling**: Rely on connection pool for performance
4. **Error Handling**: Handle database exceptions gracefully
5. **Schema Migrations**: Use proper migration tools for production
6. **Performance Monitoring**: Monitor query performance and connection health

## Dependencies

- **SQLAlchemy**: Async ORM with PostgreSQL support
- **asyncpg**: High-performance PostgreSQL async driver
- **Pydantic**: Type validation and settings management
- **PostgreSQL**: Primary database backend