"""Main application configuration settings."""

import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings

from core.config.api_config import APIConfig
from core.config.database_config import DatabaseConfig
from core.config.event_config import EventSystemConfig
from core.config.market_data_config import MarketDataConfig
from core.config.monitoring_config import MonitoringConfig
from core.config.risk_config import RiskConfig
from core.config.trading_config import TradingConfig


class Environment(str, Enum):
    """Application environment types."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Log level types."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """Main application settings."""

    # Application settings
    app_name: str = Field(default="AlphaPT", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    environment: Environment = Field(default=Environment.DEVELOPMENT, description="Application environment")
    debug: bool = Field(default=True, description="Debug mode")
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Log level")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Apply production-safe defaults based on environment
        if self.environment == Environment.PRODUCTION:
            self._apply_production_defaults()
    
    def _apply_production_defaults(self):
        """Apply production-safe defaults."""
        # Security settings
        if self.debug is True:  # Only override if default
            self.debug = False
        if self.json_logs is False:  # Enable structured logging in production
            self.json_logs = True
        
        # Performance settings  
        if self.log_level == LogLevel.DEBUG:  # Reduce log verbosity
            self.log_level = LogLevel.INFO

    # API settings
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_prefix: str = Field(default="/api/v1", description="API prefix")
    api_docs_url: Optional[str] = Field(default="/docs", description="API docs URL")
    api_redoc_url: Optional[str] = Field(default="/redoc", description="API redoc URL")

    # Security settings
    secret_key: str = Field(..., description="Secret key for JWT tokens")
    access_token_expire_minutes: int = Field(default=30, description="Access token expire minutes")
    algorithm: str = Field(default="HS256", description="JWT algorithm")

    # NATS settings
    nats_url: str = Field(default="nats://localhost:4222", description="NATS server URL")
    nats_user: Optional[str] = Field(default=None, description="NATS username")
    nats_password: Optional[str] = Field(default=None, description="NATS password")
    nats_max_reconnect_attempts: int = Field(default=10, description="NATS max reconnect attempts")
    nats_reconnect_time_wait: float = Field(default=2.0, description="NATS reconnect wait time")

    # Redis settings
    redis_url: str = Field(default="redis://localhost:6379", description="Redis URL")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_max_connections: int = Field(default=10, description="Redis max connections")

    # File paths
    base_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent.parent)
    config_dir: Path = Field(default_factory=lambda: Path(__file__).parent)
    logs_dir: Path = Field(default_factory=lambda: Path(__file__).parent.parent.parent / "logs")

    # Sub-configurations
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    market_data: MarketDataConfig = Field(default_factory=MarketDataConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    event_system: EventSystemConfig = Field(default_factory=EventSystemConfig)

    # Market data settings
    market_data_buffer_size: int = Field(default=1000, description="Market data buffer size")
    market_data_batch_size: int = Field(default=100, description="Market data batch processing size")
    market_data_flush_interval: float = Field(default=1.0, description="Market data flush interval in seconds")

    # Market Feed Settings
    mock_market_feed: bool = Field(default=False, description="Enable mock market feed for development/testing")
    mock_tick_interval_ms: int = Field(default=1000, description="Mock feed tick interval in milliseconds")
    mock_enable_market_hours_check: bool = Field(default=True, description="Respect market hours in mock feed")
    mock_market_24x7: bool = Field(default=True, description="Run mock market 24x7 for development")
    mock_instruments_count: int = Field(default=5, description="Number of mock instruments to generate")
    mock_base_volatility: float = Field(default=0.02, description="Base volatility for mock data (2%)")

    # Trading Engine Settings
    paper_trading_enabled: bool = Field(default=True, description="Enable paper trading engine")
    zerodha_trading_enabled: bool = Field(default=False, description="Enable Zerodha live trading engine")

    # Development Controls
    json_logs: bool = Field(default=False, description="Enable JSON formatted logs")
    auth_session_expiry_hours: int = Field(default=24, description="Extended session expiry for development")

    # Paper Trading Realism
    paper_transaction_cost: float = Field(default=0.05, description="Transaction cost percentage")
    paper_slippage: float = Field(default=0.01, description="Market slippage percentage")
    paper_enable_stop_loss: bool = Field(default=True, description="Enable stop loss simulation")
    paper_stop_loss_percentage: float = Field(default=2.0, description="Default stop loss percentage")

    model_config = ConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_nested_delimiter="__", case_sensitive=False
    )

    @field_validator("logs_dir")
    @classmethod
    def create_logs_dir(cls, v: Path) -> Path:
        """Create logs directory if it doesn't exist."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, v):
        """Validate environment variable."""
        if isinstance(v, str):
            return v.lower()
        return v

    def get_database_url(self, database_type: str = "postgresql") -> str:
        """Get database URL for specified database type."""
        if database_type == "postgresql":
            return self.database.postgres_url
        elif database_type == "clickhouse":
            return self.database.clickhouse_url
        else:
            raise ValueError(f"Unsupported database type: {database_type}")

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == Environment.PRODUCTION

    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == Environment.DEVELOPMENT

    def is_testing(self) -> bool:
        """Check if running in testing environment."""
        return self.environment == Environment.TESTING


    def get_mock_tick_interval_seconds(self) -> float:
        """Get mock tick interval in seconds."""
        return self.mock_tick_interval_ms / 1000.0

    def is_paper_trading_mode(self) -> bool:
        """Check if paper trading is enabled."""
        return self.paper_trading_enabled

    def is_zerodha_trading_mode(self) -> bool:
        """Check if Zerodha trading is enabled."""
        return self.zerodha_trading_enabled

    def get_effective_json_logs(self) -> bool:
        """Get effective JSON logs setting (prioritize json_logs over monitoring setting)."""
        return self.json_logs or self.monitoring.log_json_format


def get_settings() -> Optional[Settings]:
    """Get application settings instance with error handling."""
    try:
        return Settings()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to create settings: {e}")
        return None


# Global settings instance with fallback
_settings_instance: Optional[Settings] = None

def get_global_settings() -> Optional[Settings]:
    """Get global settings instance with lazy initialization."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = get_settings()
    return _settings_instance

# Initialize global settings
settings = get_global_settings()
