Of course. Here is the complete code and explanations for the `config` module, which is the central point for managing all application settings in your new architecture.

The design uses the **Pydantic** library to create a robust, type-safe, and easy-to-use configuration system. It loads settings from environment variables, which is a best practice for modern, container-friendly applications.

---

### 1\. `core/config/settings.py`

This is the main file for the module. It defines the entire configuration structure for your application, from database URLs to broker API keys.

```python
# AlphasPT_v2/core/config/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field
from enum import Enum
from typing import List

# --- Enumerations for controlled vocabulary ---

class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"

# --- Sub-models for logical grouping of settings ---

class DatabaseSettings(BaseModel):
    postgres_url: str = "postgresql+asyncpg://alphapt:alphapt@localhost:5432/alphapt"

class RedpandaSettings(BaseModel):
    bootstrap_servers: str = "localhost:9092"
    client_id: str = "alphapt-client"
    # Each service should use a unique group_id to consume messages independently
    group_id_prefix: str = "alphapt-group"

class RedisSettings(BaseModel):
    url: str = "redis://localhost:6379"

class AuthSettings(BaseModel):
    secret_key: str = "a_very_secret_key_that_should_be_changed"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

class ZerodhaSettings(BaseModel):
    enabled: bool = True
    api_key: str = "your_zerodha_api_key"
    api_secret: str = "your_zerodha_api_secret"
    # IMPORTANT: The access_token is short-lived and should be updated regularly.
    # In production, this might come from a secure vault or a startup process.
    access_token: str = "your_initial_zerodha_access_token"

class PaperTradingSettings(BaseModel):
    enabled: bool = True
    slippage_percent: float = 0.01  # 0.01% slippage on trades
    commission_percent: float = 0.02 # 0.02% commission on trades

class MarketFeedSettings(BaseModel):
    # List of instrument tokens to subscribe to at startup
    instrument_tokens: List[int] = [256265, 260105] # NIFTY 50, BANKNIFTY

# --- Main Settings Class ---

class Settings(BaseSettings):
    """
    Main application settings, loaded from environment variables.
    Pydantic automatically maps nested models to environment variables.
    For example, to set the Redpanda bootstrap_servers, you would set:
    REDPANDA__BOOTSTRAP_SERVERS="your_redpanda_host:9092"
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__", # Use double underscore to separate nested levels
        case_sensitive=False,
        extra="ignore"
    )

    app_name: str = "AlphaPT_v2"
    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    # Nested configuration models
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redpanda: RedpandaSettings = Field(default_factory=RedpandaSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    zerodha: ZerodhaSettings = Field(default_factory=ZerodhaSettings)
    paper_trading: PaperTradingSettings = Field(default_factory=PaperTradingSettings)
    market_feed: MarketFeedSettings = Field(default_factory=MarketFeedSettings)

```

**Explanation:**

- **Type-Safe and Validated**: Pydantic ensures that all configuration values are of the correct type. If you provide a non-numeric value for `access_token_expire_minutes`, the application will fail to start with a clear error message. This prevents a whole class of common bugs.
- **Logical Grouping**: By breaking the configuration into sub-models like `DatabaseSettings` and `RedpandaSettings`, the code is much cleaner and easier to navigate than a single, flat list of variables.
- **Environment Variable Loading**: The `SettingsConfigDict` tells Pydantic to look for a `.env` file and to override any values with environment variables. The `env_nested_delimiter="__"` is a powerful feature that lets you set nested values easily (e.g., `ZERODHA__API_KEY=...`). This is the standard way to configure modern, cloud-native applications.

---

### 2\. `.env.example`

This file serves as a template for developers. It shows all the environment variables that can be set to configure the application. You should copy this file to `.env` and fill in your actual secrets. The `.env` file itself should **never** be committed to version control.

```dotenv
# AlphasPT_v2/.env.example

# --- Application Settings ---
ENVIRONMENT="development"
LOG_LEVEL="INFO"

# --- PostgreSQL Database ---
DATABASE__POSTGRES_URL="postgresql+asyncpg://alphapt:alphapt@localhost:5432/alphapt"

# --- Redpanda / Kafka ---
REDPANDA__BOOTSTRAP_SERVERS="localhost:9092"

# --- Redis Cache ---
REDIS__URL="redis://localhost:6379"

# --- User Authentication (JWT) ---
# IMPORTANT: Change this in production to a long, random string
AUTH__SECRET_KEY="a_very_secret_key_that_should_be_changed"
AUTH__ACCESS_TOKEN_EXPIRE_MINUTES=60

# --- Broker Credentials (Zerodha) ---
# These should be treated as secrets and managed securely.
ZERODHA__ENABLED=True
ZERODHA__API_KEY="your_api_key"
ZERODHA__API_SECRET="your_api_secret"
ZERODHA__ACCESS_TOKEN="your_access_token" # This needs to be generated regularly

# --- Paper Trading Simulation ---
PAPER_TRADING__ENABLED=True
PAPER_TRADING__SLIPPAGE_PERCENT=0.01
PAPER_TRADING__COMMISSION_PERCENT=0.02

# --- Market Feed Subscriptions ---
# A comma-separated list of instrument tokens
MARKET_FEED__INSTRUMENT_TOKENS="256265,260105"

```

**Explanation:**

- **Template for Configuration**: This file is the single source of truth for what needs to be configured. A new developer can look at this file and immediately understand how to set up their environment.
- **Separation of Config from Code**: Your code only knows about the `Settings` object. It has no idea where the values came from. This allows you to run the exact same application code in development, testing, and production, with the only difference being the environment variables you provide.

With these two files, your `config` module is complete. It provides a robust, secure, and flexible foundation for the entire application.
