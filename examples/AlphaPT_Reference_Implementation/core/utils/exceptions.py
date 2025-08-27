"""Custom exceptions for AlphaPT application."""

from typing import Any, Dict, Optional


class AlphaPTException(Exception):
    """Base exception class for AlphaPT application."""

    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}

    def __str__(self) -> str:
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary."""
        return {
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details,
            "exception_type": self.__class__.__name__,
        }


class ConfigurationError(AlphaPTException):
    """Configuration related errors."""

    pass


class DatabaseError(AlphaPTException):
    """Database related errors."""

    pass


class AuthenticationError(AlphaPTException):
    """Authentication related errors."""

    pass


class TradingError(AlphaPTException):
    """Trading related errors."""

    pass


class MarketDataError(AlphaPTException):
    """Market data related errors."""

    pass


class RiskManagementError(AlphaPTException):
    """Risk management related errors."""

    pass


class StrategyError(AlphaPTException):
    """Strategy execution related errors."""

    pass


class EventError(AlphaPTException):
    """Event system related errors."""

    pass


class MonitoringError(AlphaPTException):
    """Monitoring and observability related errors."""

    pass


class ValidationError(AlphaPTException):
    """Data validation related errors."""

    pass


class ConnectionError(AlphaPTException):
    """Connection related errors."""

    pass


class TimeoutError(AlphaPTException):
    """Timeout related errors."""

    pass


class FeedError(AlphaPTException):
    """Market feed related errors."""

    pass


class CacheError(AlphaPTException):
    """Cache related errors."""

    pass
