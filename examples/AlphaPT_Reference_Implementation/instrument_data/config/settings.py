# Try to use Pydantic if available, otherwise fall back to simple dataclass
try:
    from pydantic_settings import BaseSettings
    from pydantic import Field
    PYDANTIC_AVAILABLE = True
except ImportError:
    try:
        from pydantic import BaseSettings, Field
        PYDANTIC_AVAILABLE = True
    except ImportError:
        PYDANTIC_AVAILABLE = False

if PYDANTIC_AVAILABLE:
    from typing import Optional, List
    from datetime import time
    import os

    class InstrumentDataConfig(BaseSettings):
        """Enhanced configuration for instrument data module with Pydantic validation."""
        
        # Market timing configuration
        market_open_hour: int = Field(8, description="Market data available hour (IST)")
        market_open_minute: int = Field(30, description="Market data available minute (IST)")
        
        # Database configuration
        db_batch_size: int = Field(1000, description="Database batch size for bulk operations")
        db_max_retries: int = Field(3, description="Maximum database retry attempts")
        valid_exchanges: List[str] = Field(
            ["NSE", "BSE", "NFO", "BFO", "CDS", "MCX", "NCO"],
            description="Valid exchanges for instrument filtering"
        )
        
        # Redis configuration
        redis_key_prefix: str = Field("instruments:registry", description="Redis key prefix")
        redis_download_prefix: str = Field("instruments:download", description="Download tracking prefix")
        redis_expiry_days: int = Field(7, description="Redis key expiry in days")
        
        # Download configuration
        download_retry_attempts: int = Field(3, description="API download retry attempts")
        download_retry_base_delay: int = Field(1000, description="Base retry delay (ms)")
        download_retry_max_delay: int = Field(5000, description="Maximum retry delay (ms)")
        download_force_hours: int = Field(24, description="Force download after hours")
        
        # File paths
        target_tokens_file: str = Field("./instrument_data/config/target_instruments.txt", description="Target tokens file path")
        download_dir: str = Field("./data/instruments", description="Download directory")
        
        # Timezone
        india_offset_minutes: int = Field(330, description="IST offset from UTC (5:30)")
        
        # Feature flags
        enable_redis_caching: bool = Field(True, description="Enable Redis caching")
        enable_smart_scheduling: bool = Field(True, description="Enable smart download scheduling")
        enable_zerodha_api: bool = Field(True, description="Enable Zerodha API downloads")
        
        class Config:
            env_prefix = "INSTRUMENT_DATA_"
            case_sensitive = False

    def get_instrument_data_config() -> InstrumentDataConfig:
        """Get instrument data configuration with environment overrides."""
        return InstrumentDataConfig()

    def validate_config(config: InstrumentDataConfig) -> dict:
        """Validate configuration and return validation results."""
        issues = []
        
        # Validate market timing
        if not (0 <= config.market_open_hour <= 23):
            issues.append("Market open hour must be between 0-23")
        
        if not (0 <= config.market_open_minute <= 59):
            issues.append("Market open minute must be between 0-59")
        
        # Validate database config
        if config.db_batch_size <= 0:
            issues.append("Database batch size must be positive")
        
        if config.db_max_retries < 0:
            issues.append("Database max retries must be non-negative")
        
        if not config.valid_exchanges:
            issues.append("At least one valid exchange must be specified")
        
        # Validate download config
        if config.download_retry_attempts <= 0:
            issues.append("Download retry attempts must be positive")
        
        if config.download_retry_base_delay <= 0:
            issues.append("Download retry base delay must be positive")
        
        if config.download_force_hours <= 0:
            issues.append("Force download hours must be positive")
        
        # Validate Redis config
        if config.redis_expiry_days <= 0:
            issues.append("Redis expiry days must be positive")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "config": config.dict()
        }

else:
    # Fallback to simple implementation without Pydantic
    from .simple_settings import (
        InstrumentDataConfig,
        get_instrument_data_config,
        validate_config
    )