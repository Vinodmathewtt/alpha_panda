"""Structured logging and audit trails for AlphaPT."""

from core.logging.logger import (
    AuditLogger,
    ErrorLogger,
    PerformanceLogger,
    StructuredLogger,
    configure_logging,
    get_logger,
    get_component_logger_safe,
)

# Import multi-channel logging if available
try:
    from core.logging.multi_channel_logger import (
        get_channel_logger,
        get_component_logger,
        get_trading_logger,
        get_market_data_logger,
        get_database_logger,
        get_audit_logger,
        get_performance_logger,
        get_api_logger,
        get_monitoring_logger,
        get_error_logger,
        get_channel_statistics,
    )
    from core.logging.business_loggers import (
        TradingAuditLogger,
        SystemPerformanceLogger,
        MarketDataQualityLogger,
        SystemErrorLogger,
        trading_audit_logger,
        system_performance_logger,
        market_data_quality_logger,
        system_error_logger,
        log_order_event,
        log_performance_metric,
        log_system_error,
        log_trading_error,
    )
    MULTI_CHANNEL_AVAILABLE = True
except ImportError:
    MULTI_CHANNEL_AVAILABLE = False
    # Stub functions for backward compatibility
    def get_channel_logger(*args, **kwargs):
        return get_logger(*args, **kwargs)
    
    def get_component_logger(*args, **kwargs):
        return get_logger(*args, **kwargs)
    
    def get_trading_logger(*args, **kwargs):
        return get_logger(*args, **kwargs)
    
    def get_channel_statistics():
        return {"error": "Multi-channel logging not available"}

__all__ = [
    "get_logger",
    "get_component_logger_safe",
    "configure_logging",
    "StructuredLogger",
    "AuditLogger",
    "PerformanceLogger",
    "ErrorLogger",
    # Multi-channel exports
    "get_channel_logger",
    "get_component_logger",
    "get_trading_logger",
    "get_market_data_logger",
    "get_database_logger",
    "get_audit_logger",
    "get_performance_logger",
    "get_api_logger",
    "get_monitoring_logger",
    "get_error_logger",
    "get_channel_statistics",
    "MULTI_CHANNEL_AVAILABLE",
]

# Add business loggers to exports if available
if MULTI_CHANNEL_AVAILABLE:
    __all__.extend([
        "TradingAuditLogger",
        "SystemPerformanceLogger",
        "MarketDataQualityLogger",
        "SystemErrorLogger",
        "trading_audit_logger",
        "system_performance_logger",
        "market_data_quality_logger",
        "system_error_logger",
        "log_order_event",
        "log_performance_metric",
        "log_system_error",
        "log_trading_error",
    ])