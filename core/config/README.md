# Core Configuration Module

## Overview

The `core/config/` module provides type-safe configuration management for Alpha Panda using Pydantic Settings. It handles environment variables, validation, and application-wide settings with proper typing and defaults.

## Components

### `settings.py`
Central configuration file containing all application settings organized into logical groups:

- **Environment Management**: Development, production, and testing configurations
- **Database Settings**: PostgreSQL connection and migration management
- **Streaming Settings**: Redpanda/Kafka broker configuration
- **Cache Settings**: Redis connection configuration
- **Authentication Settings**: JWT and broker authentication configuration
- **Trading Settings**: Paper trading and Zerodha configuration
- **Service Settings**: Individual service configuration sections

### `validator.py`
Configuration validation utilities and custom validators for ensuring settings consistency.

## Key Features

- **Type Safety**: All settings use Pydantic models with full type hints
- **Environment Variable Support**: Automatic loading from `.env` files
- **Validation**: Built-in validation for URLs, paths, and configuration consistency
- **Nested Configuration**: Organized into logical sections (database, auth, trading, etc.)
- **Multi-Broker Support**: Configuration for both paper and Zerodha trading modes

## Usage

### Basic Configuration Access
```python
from core.config.settings import get_settings

# Get application settings
settings = get_settings()

# Access database configuration
db_url = settings.database.postgres_url

# Access Redpanda configuration
bootstrap_servers = settings.redpanda.bootstrap_servers

# Access trading configuration
paper_enabled = settings.paper_trading.enabled
```

### Environment Variables
Configuration can be controlled via environment variables:

```bash
# Database configuration
DATABASE__POSTGRES_URL=postgresql+asyncpg://user:pass@host:5432/db

# Redpanda configuration
REDPANDA__BOOTSTRAP_SERVERS=localhost:9092

# Trading configuration
PAPER_TRADING__ENABLED=true
ZERODHA__ENABLED=false
```

### Configuration Sections

#### Database Settings
- **postgres_url**: PostgreSQL connection URL
- **schema_management**: Auto, create_all, or migrations_only
- **verify_migrations**: Verify migration status in production

#### Redpanda Settings
- **bootstrap_servers**: Kafka bootstrap servers
- **client_id**: Kafka client identifier
- **group_id_prefix**: Consumer group prefix

#### Authentication Settings
- **secret_key**: JWT secret key
- **algorithm**: JWT algorithm (HS256)
- **access_token_expire_minutes**: Token expiration time
- **enable_user_auth**: Enable user authentication system
- **primary_auth_provider**: Primary authentication provider

#### Trading Settings
- **Paper Trading**: Slippage, commission, starting cash configuration
- **Zerodha**: API credentials and trading configuration
- **Active Brokers**: List of enabled brokers for multi-broker operation

## Architecture Patterns

- **Settings Singleton**: Single settings instance across application
- **Environment Isolation**: Separate settings for dev/test/prod environments
- **Type-Safe Access**: All configuration access is type-checked
- **Validation on Load**: Settings are validated at application startup
- **Hot Reloading**: Development support for configuration changes

## Configuration Files

- **`.env`**: Main environment configuration file (kept in repository)
- **`.env.example`**: Example configuration with all available settings
- **Environment-specific**: Override settings for different deployment environments

## Best Practices

1. **Use Type Hints**: All configuration values should have proper type annotations
2. **Provide Defaults**: Include sensible defaults for development
3. **Validate Early**: Configuration validation happens at startup
4. **Environment Specific**: Use environment variables for deployment-specific values
5. **Documentation**: Document all configuration options with descriptions