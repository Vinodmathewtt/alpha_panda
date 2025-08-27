"""
Simple configuration for instrument data module without external dependencies.
"""
import os
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class InstrumentDataConfig:
    """Enhanced configuration for instrument data module."""
    
    # Market timing configuration
    market_open_hour: int = 8
    market_open_minute: int = 30
    
    # Database configuration
    db_batch_size: int = 1000
    db_max_retries: int = 3
    valid_exchanges: List[str] = None
    
    # Redis configuration
    redis_key_prefix: str = "instruments:registry"
    redis_download_prefix: str = "instruments:download"
    redis_expiry_days: int = 7
    
    # Download configuration
    download_retry_attempts: int = 3
    download_retry_base_delay: int = 1000
    download_retry_max_delay: int = 5000
    download_force_hours: int = 24
    
    # File paths
    target_tokens_file: str = "./instrument_data/config/target_instruments.txt"
    download_dir: str = "./data/instruments"
    
    # Timezone
    india_offset_minutes: int = 330
    
    # Feature flags
    enable_redis_caching: bool = True
    enable_smart_scheduling: bool = True
    enable_zerodha_api: bool = True
    
    def __post_init__(self):
        if self.valid_exchanges is None:
            self.valid_exchanges = ["NSE", "BSE", "NFO", "BFO", "CDS", "MCX", "NCO"]
        
        # Apply environment variable overrides
        self._apply_env_overrides()
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides."""
        env_mappings = {
            "INSTRUMENT_DATA_MARKET_OPEN_HOUR": ("market_open_hour", int),
            "INSTRUMENT_DATA_MARKET_OPEN_MINUTE": ("market_open_minute", int),
            "INSTRUMENT_DATA_DB_BATCH_SIZE": ("db_batch_size", int),
            "INSTRUMENT_DATA_DB_MAX_RETRIES": ("db_max_retries", int),
            "INSTRUMENT_DATA_REDIS_KEY_PREFIX": ("redis_key_prefix", str),
            "INSTRUMENT_DATA_REDIS_DOWNLOAD_PREFIX": ("redis_download_prefix", str),
            "INSTRUMENT_DATA_REDIS_EXPIRY_DAYS": ("redis_expiry_days", int),
            "INSTRUMENT_DATA_DOWNLOAD_RETRY_ATTEMPTS": ("download_retry_attempts", int),
            "INSTRUMENT_DATA_DOWNLOAD_RETRY_BASE_DELAY": ("download_retry_base_delay", int),
            "INSTRUMENT_DATA_DOWNLOAD_RETRY_MAX_DELAY": ("download_retry_max_delay", int),
            "INSTRUMENT_DATA_DOWNLOAD_FORCE_HOURS": ("download_force_hours", int),
            "INSTRUMENT_DATA_TARGET_TOKENS_FILE": ("target_tokens_file", str),
            "INSTRUMENT_DATA_DOWNLOAD_DIR": ("download_dir", str),
            "INSTRUMENT_DATA_INDIA_OFFSET_MINUTES": ("india_offset_minutes", int),
            "INSTRUMENT_DATA_ENABLE_REDIS_CACHING": ("enable_redis_caching", bool),
            "INSTRUMENT_DATA_ENABLE_SMART_SCHEDULING": ("enable_smart_scheduling", bool),
            "INSTRUMENT_DATA_ENABLE_ZERODHA_API": ("enable_zerodha_api", bool)
        }
        
        for env_var, (attr_name, type_func) in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                try:
                    if type_func == bool:
                        value = env_value.lower() in ('true', '1', 'yes', 'on')
                    elif type_func == list:
                        value = env_value.split(',')
                    else:
                        value = type_func(env_value)
                    
                    setattr(self, attr_name, value)
                except (ValueError, TypeError) as e:
                    print(f"Warning: Invalid value for {env_var}: {env_value} ({e})")
    
    def dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "market_open_hour": self.market_open_hour,
            "market_open_minute": self.market_open_minute,
            "db_batch_size": self.db_batch_size,
            "db_max_retries": self.db_max_retries,
            "valid_exchanges": self.valid_exchanges,
            "redis_key_prefix": self.redis_key_prefix,
            "redis_download_prefix": self.redis_download_prefix,
            "redis_expiry_days": self.redis_expiry_days,
            "download_retry_attempts": self.download_retry_attempts,
            "download_retry_base_delay": self.download_retry_base_delay,
            "download_retry_max_delay": self.download_retry_max_delay,
            "download_force_hours": self.download_force_hours,
            "target_tokens_file": self.target_tokens_file,
            "download_dir": self.download_dir,
            "india_offset_minutes": self.india_offset_minutes,
            "enable_redis_caching": self.enable_redis_caching,
            "enable_smart_scheduling": self.enable_smart_scheduling,
            "enable_zerodha_api": self.enable_zerodha_api
        }


def get_instrument_data_config() -> InstrumentDataConfig:
    """Get instrument data configuration with environment overrides."""
    return InstrumentDataConfig()


def validate_config(config: InstrumentDataConfig) -> Dict[str, Any]:
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