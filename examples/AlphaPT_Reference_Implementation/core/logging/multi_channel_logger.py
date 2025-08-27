"""Multi-channel logger implementation for AlphaPT."""

import logging
import logging.handlers
from typing import Dict, Optional, Any
from pathlib import Path
import structlog

from core.logging.log_channels import (
    LogChannel, 
    get_channel_for_component, 
    get_channel_config,
    create_log_directory_structure
)
from core.logging.base_logger import (
    StructuredLogger,
    JSONRenderer,
    ConsoleRenderer,
    TimestampProcessor,
    ComponentProcessor
)


class MultiChannelLoggerManager:
    """Manages multiple logging channels with dedicated files."""
    
    def __init__(self, settings):
        self.settings = settings
        self.channel_handlers: Dict[LogChannel, logging.Handler] = {}
        self.configured_loggers: Dict[str, structlog.BoundLogger] = {}
        self._setup_channels()
    
    def _setup_channels(self) -> None:
        """Setup all logging channels with dedicated file handlers."""
        # Create log directory structure
        create_log_directory_structure(self.settings.logs_dir)
        
        # Setup handlers for each channel
        for channel in LogChannel:
            config = get_channel_config(channel)
            handler = self._create_channel_handler(channel, config)
            self.channel_handlers[channel] = handler
    
    def _create_channel_handler(
        self, 
        channel: LogChannel, 
        config
    ) -> logging.Handler:
        """Create a file handler for a specific channel."""
        log_file = config.get_file_path(self.settings.logs_dir)
        
        # Parse max bytes
        max_bytes = self._parse_size(config.max_bytes)
        
        # Create rotating file handler
        handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8"
        )
        
        # Set log level for this channel
        handler.setLevel(getattr(logging, config.level))
        
        # Set formatter (always use JSON for files)
        if config.json_format:
            formatter = logging.Formatter("%(message)s")
        else:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        handler.setFormatter(formatter)
        
        return handler
    
    def _parse_size(self, size_str: str) -> int:
        """Parse size string (e.g., '100MB') to bytes."""
        size_str = size_str.upper()
        
        if size_str.endswith("B"):
            size_str = size_str[:-1]
        
        multipliers = {
            "K": 1024,
            "M": 1024 * 1024,
            "G": 1024 * 1024 * 1024,
        }
        
        for suffix, multiplier in multipliers.items():
            if size_str.endswith(suffix):
                return int(float(size_str[:-1]) * multiplier)
        
        return int(size_str)
    
    def get_channel_logger(
        self, 
        name: str, 
        component: Optional[str] = None,
        force_channel: Optional[LogChannel] = None
    ) -> structlog.BoundLogger:
        """Get a logger configured for the appropriate channel."""
        
        # Determine channel based on component name
        if force_channel:
            channel = force_channel
        else:
            channel = get_channel_for_component(component or name)
        
        # Create unique logger key
        logger_key = f"{channel.value}:{name}"
        
        # Return cached logger if exists
        if logger_key in self.configured_loggers:
            return self.configured_loggers[logger_key]
        
        # Create new structlog logger
        logger = structlog.get_logger(f"{channel.value}.{name}")
        
        # Bind component information
        if component:
            logger = logger.bind(component=component, channel=channel.value)
        
        # Add channel-specific handler to the underlying Python logger
        python_logger = logger._logger
        if hasattr(python_logger, 'addHandler'):
            channel_handler = self.channel_handlers[channel]
            python_logger.addHandler(channel_handler)
            
            # Set logger level to match channel
            config = get_channel_config(channel)
            python_logger.setLevel(getattr(logging, config.level))
        
        # Cache the logger
        self.configured_loggers[logger_key] = logger
        
        return logger


class ChannelStructuredLogger(StructuredLogger):
    """Enhanced structured logger with channel routing."""
    
    def __init__(
        self, 
        name: str, 
        component: Optional[str] = None,
        channel: Optional[LogChannel] = None,
        manager: Optional[MultiChannelLoggerManager] = None
    ):
        self.channel = channel or get_channel_for_component(component or name)
        self.manager = manager
        
        if manager:
            self.logger = manager.get_channel_logger(name, component, channel)
        else:
            # Fallback to original logger
            super().__init__(name, component)
        
        self.component = component
        self.name = name
    
    def with_context(self, **kwargs) -> "ChannelStructuredLogger":
        """Create logger with additional context."""
        new_logger = ChannelStructuredLogger(
            self.name, 
            self.component, 
            self.channel,
            self.manager
        )
        new_logger.logger = self.logger.bind(**kwargs)
        return new_logger
    
    def get_channel_info(self) -> Dict[str, Any]:
        """Get information about the current logging channel."""
        config = get_channel_config(self.channel)
        return {
            "channel": self.channel.value,
            "file_path": config.file_path,
            "level": config.level,
            "retention_days": config.retention_days
        }


# Global logger manager instance
_logger_manager: Optional[MultiChannelLoggerManager] = None


def initialize_multi_channel_logging(settings) -> MultiChannelLoggerManager:
    """Initialize the multi-channel logging system."""
    global _logger_manager
    _logger_manager = MultiChannelLoggerManager(settings)
    return _logger_manager


def get_channel_logger(
    name: str, 
    component: Optional[str] = None,
    channel: Optional[LogChannel] = None
) -> ChannelStructuredLogger:
    """Get a channel-aware structured logger."""
    if _logger_manager is None:
        # Fallback to basic logger if not initialized
        from core.logging.logger import get_logger
        return ChannelStructuredLogger(name, component, channel)
    
    return ChannelStructuredLogger(name, component, channel, _logger_manager)


def get_component_logger(component_name: str) -> ChannelStructuredLogger:
    """Get a logger routed to appropriate channel based on component name."""
    return get_channel_logger(component_name, component_name)


def get_trading_logger(name: str) -> ChannelStructuredLogger:
    """Get a logger specifically for trading operations."""
    return get_channel_logger(name, "trading", LogChannel.TRADING)


def get_market_data_logger(name: str) -> ChannelStructuredLogger:
    """Get a logger specifically for market data operations."""
    return get_channel_logger(name, "market_data", LogChannel.MARKET_DATA)


def get_database_logger(name: str) -> ChannelStructuredLogger:
    """Get a logger specifically for database operations."""
    return get_channel_logger(name, "database", LogChannel.DATABASE)


def get_audit_logger(name: str) -> ChannelStructuredLogger:
    """Get a logger specifically for audit operations."""
    return get_channel_logger(name, "audit", LogChannel.AUDIT)


def get_performance_logger(name: str) -> ChannelStructuredLogger:
    """Get a logger specifically for performance metrics."""
    return get_channel_logger(name, "performance", LogChannel.PERFORMANCE)


def get_api_logger(name: str) -> ChannelStructuredLogger:
    """Get a logger specifically for API operations."""
    return get_channel_logger(name, "api", LogChannel.API)


def get_monitoring_logger(name: str) -> ChannelStructuredLogger:
    """Get a logger specifically for monitoring operations."""
    return get_channel_logger(name, "monitoring", LogChannel.MONITORING)


def get_error_logger(name: str) -> ChannelStructuredLogger:
    """Get a logger specifically for error conditions."""
    return get_channel_logger(name, "error", LogChannel.ERRORS)


def get_channel_statistics() -> Dict[str, Any]:
    """Get statistics about all logging channels."""
    if not _logger_manager:
        return {"error": "Logger manager not initialized"}
    
    stats = {}
    for channel in LogChannel:
        config = get_channel_config(channel)
        log_file = config.get_file_path(_logger_manager.settings.logs_dir)
        
        file_stats = {}
        if log_file.exists():
            file_stats = {
                "size_bytes": log_file.stat().st_size,
                "size_mb": round(log_file.stat().st_size / 1024 / 1024, 2),
                "exists": True
            }
        else:
            file_stats = {"exists": False}
        
        stats[channel.value] = {
            "config": {
                "file_path": config.file_path,
                "level": config.level,
                "max_bytes": config.max_bytes,
                "backup_count": config.backup_count,
                "retention_days": config.retention_days
            },
            "file_stats": file_stats
        }
    
    return stats