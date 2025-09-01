# Complete settings with ALL required sections
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Literal, List, Any, Union
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
    # Asynchronous logging
    queue_enabled: bool = True
    queue_maxsize: int = 10000
    
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
    # Redaction
    redact_keys: list[str] = [
        "authorization", "access_token", "refresh_token", "api_key", "api-secret",
        "api_secret", "password", "secret", "token", "set-cookie"
    ]


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


class TracingSettings(BaseModel):
    """OpenTelemetry tracing configuration"""
    enabled: bool = False
    exporter: str = "none"  # none|otlp
    otlp_endpoint: str = "http://localhost:4317"  # OTLP gRPC default
    service_name: str | None = None
    sampling_ratio: float = 1.0


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
    
    @field_validator('cors_origins')
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

    # Multi-broker support configuration
    active_brokers: Union[str, List[str]] = Field(
        default="paper,zerodha",
        description="List of active broker namespaces for this deployment instance"
    )
    
    @field_validator('active_brokers', mode='before')
    @classmethod
    def parse_active_brokers(cls, v):
        """Parse comma-separated string or return list as-is"""
        if isinstance(v, str):
            brokers = [broker.strip() for broker in v.split(',') if broker.strip()]
            return brokers
        return v
    
    @field_validator('active_brokers')
    @classmethod
    def validate_active_brokers(cls, v):
        """Validate that all brokers are supported"""
        # Ensure v is a list at this point
        if isinstance(v, str):
            v = [broker.strip() for broker in v.split(',') if broker.strip()]
            
        supported_brokers = {"paper", "zerodha"}
        invalid_brokers = set(v) - supported_brokers
        if invalid_brokers:
            raise ValueError(f"Unsupported brokers: {invalid_brokers}")
        if not v:
            raise ValueError("At least one active broker is required")
        return v
    
    app_name: str = "Alpha Panda"
    version: str = "2.1.0"
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
    tracing: TracingSettings = TracingSettings()

    # Kafka producer tuning (config-driven, per service)
    class ProducerTuning(BaseModel):
        linger_ms: int | None = None
        compression_type: str | None = None  # gzip|snappy|lz4|zstd
        batch_size: int | None = None
        request_timeout_ms: int | None = None
        max_in_flight_requests: int | None = None

    # Map service_name -> ProducerTuning; e.g., {"market_feed": {"linger_ms": 2, "compression_type": "zstd"}}
    producer_tuning: dict[str, ProducerTuning] = {}
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
