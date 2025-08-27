# Enhanced structured logging with multi-channel support
import sys
import logging
import logging.handlers
from pathlib import Path
from typing import Dict, Optional, Any
import structlog

from core.config.settings import Settings
from .channels import (
    LogChannel, 
    get_channel_for_component, 
    get_channel_config,
    create_log_directory_structure,
    get_channel_statistics
)

# Global logger manager instance
_logger_manager: Optional['EnhancedLoggerManager'] = None

# Global flag to prevent duplicate configuration
_enhanced_logging_configured = False


class EnhancedLoggerManager:
    """Enhanced logging manager with multi-channel support and configurable formats."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.channel_handlers: Dict[LogChannel, logging.Handler] = {}
        self.configured_loggers: Dict[str, structlog.BoundLogger] = {}
        
        # Set up logging
        self._setup_logging()
        
    def _setup_logging(self) -> None:
        """Setup enhanced logging with configurable formats."""
        # Create logs directory
        if self.settings.logging.file_enabled:
            create_log_directory_structure(self.settings.logs_dir)
        
        # Configure console logging
        self._setup_console_logging()
        
        # Configure file logging
        if self.settings.logging.file_enabled:
            self._setup_file_logging()
            
        # Configure multi-channel logging if enabled
        if self.settings.logging.multi_channel_enabled:
            self._setup_multi_channel_logging()
            
        # Configure structlog
        self._configure_structlog()
    
    def _setup_console_logging(self) -> None:
        """Setup console logging with configurable format."""
        if not self.settings.logging.console_enabled:
            return
            
        root_logger = logging.getLogger()
        
        # Check if console handler already exists
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stdout:
                return  # Console handler already configured
            
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.settings.logging.level.upper()))
        
        # Use plain text format for console unless JSON is explicitly requested
        if self.settings.logging.console_json_format:
            formatter = logging.Formatter("%(message)s")
        else:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        
        console_handler.setFormatter(formatter)
        
        # Add to root logger
        root_logger.addHandler(console_handler)
        root_logger.setLevel(getattr(logging, self.settings.logging.level.upper()))
    
    def _setup_file_logging(self) -> None:
        """Setup basic file logging."""
        if not self.settings.logging.file_enabled:
            return
            
        logs_dir = Path(self.settings.logs_dir)
        log_file = logs_dir / "alpha_panda.log"
        
        root_logger = logging.getLogger()
        
        # Check if file handler already exists for this file
        for handler in root_logger.handlers:
            if (isinstance(handler, logging.handlers.RotatingFileHandler) and 
                hasattr(handler, 'baseFilename') and 
                Path(handler.baseFilename) == log_file):
                return  # File handler already configured
        
        max_bytes = self._parse_size(self.settings.logging.file_max_size)
        
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=self.settings.logging.file_backup_count,
            encoding="utf-8"
        )
        
        file_handler.setLevel(getattr(logging, self.settings.logging.level.upper()))
        
        # Always use JSON format for file logging
        formatter = logging.Formatter("%(message)s")
        file_handler.setFormatter(formatter)
        
        # Add to root logger
        root_logger.addHandler(file_handler)
    
    def _setup_multi_channel_logging(self) -> None:
        """Setup multi-channel logging with dedicated files."""
        if not self.settings.logging.multi_channel_enabled:
            return
            
        # Setup handlers for each channel
        for channel in LogChannel:
            config = get_channel_config(channel)
            handler = self._create_channel_handler(channel, config)
            self.channel_handlers[channel] = handler
    
    def _create_channel_handler(self, channel: LogChannel, config) -> logging.Handler:
        """Create a file handler for a specific channel."""
        log_file = config.get_file_path(self.settings.logs_dir)
        max_bytes = self._parse_size(config.max_bytes)
        
        handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8"
        )
        
        handler.setLevel(getattr(logging, config.level))
        
        # Always use JSON format for channel files
        formatter = logging.Formatter("%(message)s")
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
    
    def _configure_structlog(self) -> None:
        """Configure structlog with appropriate processors."""
        processors = [
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]
        
        # Add JSON renderer for structured output
        if self.settings.logging.json_format:
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.append(structlog.dev.ConsoleRenderer())
        
        structlog.configure(
            processors=processors,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    def get_logger(self, name: str, component: Optional[str] = None) -> structlog.BoundLogger:
        """Get a structured logger for a component."""
        if name in self.configured_loggers:
            return self.configured_loggers[name]
            
        logger = structlog.get_logger(name)
        
        # Add component context if provided
        if component:
            logger = logger.bind(component=component)
            
            # If multi-channel logging is enabled, add channel-specific handler
            if self.settings.logging.multi_channel_enabled:
                channel = get_channel_for_component(component)
                if channel in self.channel_handlers:
                    # Add channel-specific logging
                    stdlib_logger = logging.getLogger(name)
                    if self.channel_handlers[channel] not in stdlib_logger.handlers:
                        stdlib_logger.addHandler(self.channel_handlers[channel])
        
        self.configured_loggers[name] = logger
        return logger
    
    def get_channel_logger(self, name: str, channel: LogChannel) -> structlog.BoundLogger:
        """Get a logger for a specific channel."""
        logger = self.get_logger(name)
        
        # Add channel context
        logger = logger.bind(channel=channel.value)
        
        # Add channel-specific handler if available
        if channel in self.channel_handlers:
            stdlib_logger = logging.getLogger(name)
            if self.channel_handlers[channel] not in stdlib_logger.handlers:
                stdlib_logger.addHandler(self.channel_handlers[channel])
        
        return logger
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get logging statistics."""
        stats = {
            "total_loggers": len(self.configured_loggers),
            "multi_channel_enabled": self.settings.logging.multi_channel_enabled,
            "file_logging_enabled": self.settings.logging.file_enabled,
            "console_logging_enabled": self.settings.logging.console_enabled,
            "json_format": self.settings.logging.json_format,
            "console_json_format": self.settings.logging.console_json_format,
            "logs_directory": self.settings.logs_dir,
        }
        
        if self.settings.logging.multi_channel_enabled:
            stats.update(get_channel_statistics())
            
        return stats


def configure_enhanced_logging(settings: Settings) -> None:
    """Configure enhanced logging system."""
    global _logger_manager, _enhanced_logging_configured
    
    # Prevent duplicate configuration
    if _enhanced_logging_configured:
        return
    
    _logger_manager = EnhancedLoggerManager(settings)
    _enhanced_logging_configured = True


def get_enhanced_logger(name: str, component: Optional[str] = None) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    global _logger_manager
    
    if _logger_manager is None:
        # Fallback to basic structlog configuration
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=logging.INFO,
        )
        
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        return structlog.get_logger(name)
    
    return _logger_manager.get_logger(name, component)


def get_channel_logger(name: str, channel: LogChannel) -> structlog.BoundLogger:
    """Get a logger for a specific channel."""
    global _logger_manager
    
    if _logger_manager is None:
        return get_enhanced_logger(name)
        
    return _logger_manager.get_channel_logger(name, channel)


def get_logging_statistics() -> Dict[str, Any]:
    """Get logging system statistics."""
    global _logger_manager
    
    if _logger_manager is None:
        return {"error": "Logger manager not initialized"}
        
    return _logger_manager.get_statistics()


# Convenience functions for specific components
def get_trading_logger(name: str) -> structlog.BoundLogger:
    """Get a trading-specific logger."""
    return get_channel_logger(name, LogChannel.TRADING)


def get_market_data_logger(name: str) -> structlog.BoundLogger:
    """Get a market data logger."""
    return get_channel_logger(name, LogChannel.MARKET_DATA)


def get_api_logger(name: str) -> structlog.BoundLogger:
    """Get an API logger."""
    return get_channel_logger(name, LogChannel.API)


def get_audit_logger(name: str) -> structlog.BoundLogger:
    """Get an audit logger."""
    return get_channel_logger(name, LogChannel.AUDIT)


def get_performance_logger(name: str) -> structlog.BoundLogger:
    """Get a performance logger."""
    return get_channel_logger(name, LogChannel.PERFORMANCE)


def get_monitoring_logger(name: str) -> structlog.BoundLogger:
    """Get a monitoring logger."""
    return get_channel_logger(name, LogChannel.MONITORING)


def get_error_logger(name: str) -> structlog.BoundLogger:
    """Get an error logger."""
    return get_channel_logger(name, LogChannel.ERROR)