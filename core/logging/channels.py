"""
Logging channel definitions and configuration for Alpha Panda.
Provides multi-channel logging with dedicated files for different components.
"""

from enum import Enum
from typing import Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass


class LogChannel(str, Enum):
    """Logging channels for different components."""
    
    APPLICATION = "application"  # General application logs
    TRADING = "trading"          # Trading operations
    MARKET_DATA = "market_data"  # Market feed and data
    DATABASE = "database"        # Database operations
    API = "api"                  # API requests/responses
    AUDIT = "audit"             # Audit trail
    PERFORMANCE = "performance"  # Performance metrics
    ERROR = "error"             # Error logs
    MONITORING = "monitoring"    # System monitoring


@dataclass
class ChannelConfig:
    """Configuration for a logging channel."""
    
    name: str
    filename: str
    level: str = "INFO"
    max_bytes: str = "50MB"
    backup_count: int = 5
    json_format: bool = True
    retention_days: Optional[int] = None
    
    def get_file_path(self, logs_dir: str) -> Path:
        """Get the full file path for this channel."""
        return Path(logs_dir) / self.filename


# Channel configurations
CHANNEL_CONFIGS: Dict[LogChannel, ChannelConfig] = {
    LogChannel.APPLICATION: ChannelConfig(
        name="application",
        filename="application.log",
        level="INFO",
        max_bytes="100MB",
        backup_count=10,
        retention_days=30
    ),
    LogChannel.TRADING: ChannelConfig(
        name="trading",
        filename="trading.log",
        level="INFO",
        max_bytes="50MB",
        backup_count=20,
        retention_days=365  # Keep trading logs for 1 year
    ),
    LogChannel.MARKET_DATA: ChannelConfig(
        name="market_data",
        filename="market_data.log",
        level="INFO",
        max_bytes="200MB",  # Large due to high volume
        backup_count=5,
        retention_days=7    # High volume, shorter retention
    ),
    LogChannel.DATABASE: ChannelConfig(
        name="database",
        filename="database.log",
        level="WARNING",    # Only warnings and errors
        max_bytes="50MB",
        backup_count=5,
        retention_days=30
    ),
    LogChannel.API: ChannelConfig(
        name="api",
        filename="api.log",
        level="INFO",
        max_bytes="50MB",
        backup_count=10,
        retention_days=30
    ),
    LogChannel.AUDIT: ChannelConfig(
        name="audit",
        filename="audit.log",
        level="INFO",
        max_bytes="100MB",
        backup_count=50,
        retention_days=365  # Keep audit logs for compliance
    ),
    LogChannel.PERFORMANCE: ChannelConfig(
        name="performance",
        filename="performance.log",
        level="INFO",
        max_bytes="50MB",
        backup_count=10,
        retention_days=30
    ),
    LogChannel.ERROR: ChannelConfig(
        name="error",
        filename="error.log",
        level="ERROR",
        max_bytes="50MB",
        backup_count=20,
        retention_days=90   # Keep errors longer for analysis
    ),
    LogChannel.MONITORING: ChannelConfig(
        name="monitoring",
        filename="monitoring.log",
        level="INFO",
        max_bytes="50MB",
        backup_count=10,
        retention_days=30
    ),
}


def get_channel_for_component(component: str) -> LogChannel:
    """Get the appropriate logging channel for a component."""
    component_mapping = {
        # Trading components
        "market_feed": LogChannel.MARKET_DATA,
        "strategy_runner": LogChannel.TRADING,
        "risk_manager": LogChannel.TRADING,
        "trading_engine": LogChannel.TRADING,
        "portfolio_manager": LogChannel.TRADING,
        "paper_trader": LogChannel.TRADING,
        "zerodha_trader": LogChannel.TRADING,
        
        # Infrastructure components
        "database": LogChannel.DATABASE,
        "redis": LogChannel.DATABASE,
        "streaming": LogChannel.APPLICATION,
        
        # API components
        "api": LogChannel.API,
        "auth": LogChannel.API,
        
        # Monitoring
        "health_checker": LogChannel.MONITORING,
        "metrics": LogChannel.MONITORING,
        "performance": LogChannel.PERFORMANCE,
        
        # Audit
        "audit": LogChannel.AUDIT,
    }
    
    return component_mapping.get(component, LogChannel.APPLICATION)


def get_channel_config(channel: LogChannel) -> ChannelConfig:
    """Get configuration for a specific channel."""
    return CHANNEL_CONFIGS[channel]


def create_log_directory_structure(logs_dir: str) -> None:
    """Create the logs directory structure."""
    logs_path = Path(logs_dir)
    logs_path.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories for organized storage
    (logs_path / "archived").mkdir(exist_ok=True)
    (logs_path / "temp").mkdir(exist_ok=True)


def get_channel_statistics() -> Dict[str, Any]:
    """Get statistics about all logging channels."""
    stats = {
        "total_channels": len(LogChannel),
        "channels": {}
    }
    
    for channel in LogChannel:
        config = get_channel_config(channel)
        stats["channels"][channel.value] = {
            "filename": config.filename,
            "level": config.level,
            "max_bytes": config.max_bytes,
            "backup_count": config.backup_count,
            "retention_days": config.retention_days,
        }
    
    return stats