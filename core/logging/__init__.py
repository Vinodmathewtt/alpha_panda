# Enhanced structured logging with multi-channel support
import sys
import logging
import structlog
from typing import Optional, Dict, Any

from core.config.settings import Settings

# Global flag to prevent duplicate logging configuration
_logging_configured = False

# Try to import enhanced logging, fallback to basic if not available
try:
    from .enhanced_logging import (
        configure_enhanced_logging,
        get_enhanced_logger,
        get_channel_logger,
        get_logging_statistics,
        get_trading_logger,
        get_market_data_logger,
        get_api_logger,
        get_audit_logger,
        get_performance_logger,
        get_monitoring_logger,
        get_error_logger,
    )
    from .channels import LogChannel
    ENHANCED_LOGGING_AVAILABLE = True
except ImportError:
    ENHANCED_LOGGING_AVAILABLE = False
    LogChannel = None


def configure_logging(settings: Settings) -> None:
    """Configure logging system with enhanced features if available."""
    global _logging_configured
    
    # Prevent duplicate configuration
    if _logging_configured:
        return
    
    if ENHANCED_LOGGING_AVAILABLE and hasattr(settings, 'logging'):
        # Use enhanced logging with configurable formats
        configure_enhanced_logging(settings)
    else:
        # Fallback to basic structlog configuration
        level = getattr(settings, 'log_level', 'INFO')
        
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=level.upper(),
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
    
    _logging_configured = True


def get_logger(name: str, component: Optional[str] = None) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    if ENHANCED_LOGGING_AVAILABLE:
        return get_enhanced_logger(name, component)
    else:
        return structlog.get_logger(name)


def get_logger_safe(name: str, component: Optional[str] = None) -> structlog.BoundLogger:
    """Get a structured logger instance safely (alias for get_logger)."""
    return get_logger(name, component)


# Enhanced logging functions (available only if enhanced logging is loaded)
if ENHANCED_LOGGING_AVAILABLE:
    # Export enhanced logging functions
    def get_statistics() -> Dict[str, Any]:
        """Get logging system statistics."""
        return get_logging_statistics()
        
    # Channel-specific logger functions
    def get_trading_logger_safe(name: str) -> structlog.BoundLogger:
        """Get a trading logger safely."""
        return get_trading_logger(name)
        
    def get_market_data_logger_safe(name: str) -> structlog.BoundLogger:
        """Get a market data logger safely."""
        return get_market_data_logger(name)
        
    def get_api_logger_safe(name: str) -> structlog.BoundLogger:
        """Get an API logger safely."""
        return get_api_logger(name)
        
    def get_audit_logger_safe(name: str) -> structlog.BoundLogger:
        """Get an audit logger safely."""
        return get_audit_logger(name)
        
    def get_performance_logger_safe(name: str) -> structlog.BoundLogger:
        """Get a performance logger safely."""
        return get_performance_logger(name)
        
    def get_monitoring_logger_safe(name: str) -> structlog.BoundLogger:
        """Get a monitoring logger safely."""
        return get_monitoring_logger(name)
        
    def get_error_logger_safe(name: str) -> structlog.BoundLogger:
        """Get an error logger safely."""
        return get_error_logger(name)
        
else:
    # Fallback functions that use basic logging
    def get_statistics() -> Dict[str, Any]:
        """Get logging system statistics (fallback)."""
        return {"error": "Enhanced logging not available"}
        
    def get_trading_logger_safe(name: str) -> structlog.BoundLogger:
        return get_logger(name)
        
    def get_market_data_logger_safe(name: str) -> structlog.BoundLogger:
        return get_logger(name)
        
    def get_api_logger_safe(name: str) -> structlog.BoundLogger:
        return get_logger(name)
        
    def get_audit_logger_safe(name: str) -> structlog.BoundLogger:
        return get_logger(name)
        
    def get_performance_logger_safe(name: str) -> structlog.BoundLogger:
        return get_logger(name)
        
    def get_monitoring_logger_safe(name: str) -> structlog.BoundLogger:
        return get_logger(name)
        
    def get_error_logger_safe(name: str) -> structlog.BoundLogger:
        return get_logger(name)


# Export all functions
__all__ = [
    "configure_logging",
    "get_logger",
    "get_logger_safe",
    "get_statistics",
    "get_trading_logger_safe",
    "get_market_data_logger_safe",
    "get_api_logger_safe",
    "get_audit_logger_safe",
    "get_performance_logger_safe",
    "get_monitoring_logger_safe", 
    "get_error_logger_safe",
    "ENHANCED_LOGGING_AVAILABLE",
]

# Add enhanced exports if available
if ENHANCED_LOGGING_AVAILABLE:
    __all__.extend([
        "LogChannel",
        "get_channel_logger",
        "get_trading_logger",
        "get_market_data_logger",
        "get_api_logger",
        "get_audit_logger",
        "get_performance_logger",
        "get_monitoring_logger",
        "get_error_logger",
    ])