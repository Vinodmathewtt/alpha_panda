"""Multi-channel logging configuration for AlphaPT."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
from pathlib import Path


class LogChannel(Enum):
    """Available logging channels."""
    APPLICATION = "application"
    TRADING = "trading"
    MARKET_DATA = "market_data"
    DATABASE = "database"
    AUDIT = "audit"
    PERFORMANCE = "performance"
    ERRORS = "errors"
    MONITORING = "monitoring"
    API = "api"


@dataclass
class ChannelConfig:
    """Configuration for a logging channel."""
    name: str
    file_path: str
    components: List[str]
    level: str = "INFO"
    max_bytes: str = "100MB"
    backup_count: int = 5
    retention_days: int = 30
    json_format: bool = True
    
    def get_file_path(self, logs_dir: Path) -> Path:
        """Get full file path for this channel."""
        return logs_dir / self.file_path


# Channel configurations mapping
LOG_CHANNELS: Dict[LogChannel, ChannelConfig] = {
    LogChannel.APPLICATION: ChannelConfig(
        name="application",
        file_path="application.log",
        components=[
            "app", "main", "startup", "shutdown", "application",
            "alphaPT.application", "lifecycle"
        ],
        level="INFO",
        max_bytes="50MB",
        backup_count=7,
        retention_days=14
    ),
    
    LogChannel.TRADING: ChannelConfig(
        name="trading",
        file_path="trading.log",
        components=[
            "zerodha_trade", "paper_trade", "strategy_manager", "risk_manager",
            "strategy_factory", "strategy_health_monitor", "base_strategy",
            "parallel_strategy_executor", "strategy.", "trading.", "orders", "positions"
        ],
        level="INFO",
        max_bytes="200MB",
        backup_count=10,
        retention_days=60
    ),
    
    LogChannel.MARKET_DATA: ChannelConfig(
        name="market_data",
        file_path="market_data.log",
        components=[
            "zerodha_market_feed", "mock_feed_manager", "storage_manager",
            "data_quality_monitor", "market_feed", "tick_", "ohlc_",
            "market_depth", "feed_manager", "instrument_data"
        ],
        level="INFO",
        max_bytes="500MB",  # High volume data
        backup_count=5,
        retention_days=7  # Market data doesn't need long retention
    ),
    
    LogChannel.DATABASE: ChannelConfig(
        name="database",
        file_path="database.log",
        components=[
            "clickhouse_manager", "redis_cache_manager", "migration_manager",
            "connection", "database", "repository", "sqlalchemy", 
            "postgres", "clickhouse", "redis"
        ],
        level="WARNING",  # Reduce SQL query noise
        max_bytes="100MB",
        backup_count=3,
        retention_days=7
    ),
    
    LogChannel.AUDIT: ChannelConfig(
        name="audit",
        file_path="audit.log",
        components=[
            "audit", "alphaPT.audit", "trading_audit", "compliance",
            "risk_breach", "order_placed", "order_filled", "position_update"
        ],
        level="INFO",
        max_bytes="100MB",
        backup_count=30,
        retention_days=365,  # Long retention for compliance
        json_format=True  # Always JSON for audit trails
    ),
    
    LogChannel.PERFORMANCE: ChannelConfig(
        name="performance",
        file_path="performance.log",
        components=[
            "performance", "alphaPT.performance", "metrics", "profiler",
            "execution_time", "throughput", "resource_usage", "latency"
        ],
        level="INFO",
        max_bytes="200MB",
        backup_count=7,
        retention_days=30
    ),
    
    LogChannel.ERRORS: ChannelConfig(
        name="errors",
        file_path="errors.log",
        components=[
            "error", "alphaPT.errors", "exception", "traceback",
            "system_error", "trading_error", "data_error"
        ],
        level="ERROR",
        max_bytes="100MB",
        backup_count=15,
        retention_days=90
    ),
    
    LogChannel.MONITORING: ChannelConfig(
        name="monitoring",
        file_path="monitoring.log", 
        components=[
            "monitoring", "health_checker", "metrics_collector", "alert_manager",
            "business_metrics", "observability", "prometheus", "grafana"
        ],
        level="INFO",
        max_bytes="100MB",
        backup_count=7,
        retention_days=30
    ),
    
    LogChannel.API: ChannelConfig(
        name="api",
        file_path="api.log",
        components=[
            "api", "server", "middleware", "routers", "websocket",
            "fastapi", "uvicorn", "auth", "session_manager"
        ],
        level="INFO",
        max_bytes="200MB",
        backup_count=7,
        retention_days=30
    )
}


def get_channel_for_component(component_name: str) -> LogChannel:
    """Determine which log channel a component should use."""
    component_lower = component_name.lower()
    
    # Check each channel's components for matches
    for channel, config in LOG_CHANNELS.items():
        for comp_pattern in config.components:
            if comp_pattern in component_lower:
                return channel
    
    # Default to application channel
    return LogChannel.APPLICATION


def get_channel_config(channel: LogChannel) -> ChannelConfig:
    """Get configuration for a specific channel."""
    return LOG_CHANNELS[channel]


def get_all_channels() -> Dict[LogChannel, ChannelConfig]:
    """Get all channel configurations."""
    return LOG_CHANNELS.copy()


def create_log_directory_structure(logs_dir: Path) -> None:
    """Create the complete log directory structure."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories for organized log storage
    (logs_dir / "archive").mkdir(exist_ok=True)
    (logs_dir / "daily").mkdir(exist_ok=True)
    
    # Create initial log files to ensure they exist
    for channel_config in LOG_CHANNELS.values():
        log_file = logs_dir / channel_config.file_path
        if not log_file.exists():
            log_file.touch()