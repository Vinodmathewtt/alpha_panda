"""Configuration for Zerodha market feed."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ZerodhaFeedConfig:
    """Configuration for Zerodha market feed manager."""
    
    # Data streaming settings
    enable_tick_storage: bool = True
    enable_depth_storage: bool = True
    default_mode: str = "quote"  # quote, ltp, full
    
    # Batch processing settings
    batch_size: int = 50
    batch_timeout: float = 5.0
    max_buffer_size: int = 5000
    
    # Connection settings
    max_instruments_per_request: int = 3000
    connection_timeout: int = 30
    reconnect_attempts: int = 5
    reconnect_delay: float = 2.0
    
    # Performance settings
    memory_pressure_threshold: float = 0.8
    slow_operation_threshold_ms: float = 10.0
    
    def __post_init__(self):
        """Validate configuration values."""
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.batch_timeout <= 0:
            raise ValueError("batch_timeout must be positive")
        if self.max_buffer_size <= 0:
            raise ValueError("max_buffer_size must be positive")
        if self.default_mode not in ["quote", "ltp", "full"]:
            raise ValueError("default_mode must be one of: quote, ltp, full")