"""Centralized error handling patterns and utilities for AlphaPT.

This module provides standardized error handling patterns, retry mechanisms,
and error reporting utilities to ensure consistent error management across
the entire application.
"""

import asyncio
import functools
import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union

from core.utils.exceptions import (
    AlphaPTException,
    AuthenticationError,
    ConfigurationError,
    DatabaseError,
    MarketDataError,
    TradingError,
)


class ErrorSeverity(Enum):
    """Error severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification."""

    DATABASE = "database"
    TRADING = "trading"
    AUTHENTICATION = "authentication"
    MARKET_DATA = "market_data"
    CONFIGURATION = "configuration"
    NETWORK = "network"
    VALIDATION = "validation"
    SYSTEM = "system"
    EXTERNAL_API = "external_api"


@dataclass
class ErrorContext:
    """Context information for error handling."""

    component: str
    operation: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorDetails:
    """Detailed error information."""

    error_id: str
    timestamp: datetime
    severity: ErrorSeverity
    category: ErrorCategory
    error_type: str
    message: str
    context: ErrorContext
    traceback: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 0
    is_recoverable: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class ErrorHandler:
    """Centralized error handler with logging and monitoring integration."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize error handler.

        Args:
            logger: Logger instance to use for error reporting
        """
        self.logger = logger or logging.getLogger(__name__)
        self.error_history: List[ErrorDetails] = []
        self.max_history_size = 1000

        # Error category mapping
        self.error_category_map = {
            DatabaseError: ErrorCategory.DATABASE,
            TradingError: ErrorCategory.TRADING,
            AuthenticationError: ErrorCategory.AUTHENTICATION,
            MarketDataError: ErrorCategory.MARKET_DATA,
            ConfigurationError: ErrorCategory.CONFIGURATION,
            ConnectionError: ErrorCategory.NETWORK,
            TimeoutError: ErrorCategory.NETWORK,
            ValueError: ErrorCategory.VALIDATION,
            KeyError: ErrorCategory.VALIDATION,
            TypeError: ErrorCategory.VALIDATION,
        }

        # Severity mapping
        self.severity_map = {
            AuthenticationError: ErrorSeverity.HIGH,
            TradingError: ErrorSeverity.CRITICAL,
            DatabaseError: ErrorSeverity.HIGH,
            ConfigurationError: ErrorSeverity.HIGH,
            MarketDataError: ErrorSeverity.MEDIUM,
            ConnectionError: ErrorSeverity.MEDIUM,
            TimeoutError: ErrorSeverity.MEDIUM,
            ValueError: ErrorSeverity.LOW,
            KeyError: ErrorSeverity.LOW,
            TypeError: ErrorSeverity.LOW,
        }

    def handle_error(
        self,
        error: Exception,
        context: ErrorContext,
        severity: Optional[ErrorSeverity] = None,
        category: Optional[ErrorCategory] = None,
        is_recoverable: bool = True,
        include_traceback: bool = True,
    ) -> ErrorDetails:
        """Handle an error with comprehensive logging and tracking.

        Args:
            error: The exception that occurred
            context: Context information about where the error occurred
            severity: Override severity level
            category: Override error category
            is_recoverable: Whether the error is recoverable
            include_traceback: Whether to include full traceback

        Returns:
            ErrorDetails: Detailed error information
        """
        import uuid

        # Determine error category and severity
        error_type = type(error)
        error_category = category or self._get_error_category(error_type)
        error_severity = severity or self._get_error_severity(error_type)

        # Generate unique error ID
        error_id = str(uuid.uuid4())[:8]

        # Create error details
        error_details = ErrorDetails(
            error_id=error_id,
            timestamp=datetime.now(timezone.utc),
            severity=error_severity,
            category=error_category,
            error_type=error_type.__name__,
            message=str(error),
            context=context,
            traceback=traceback.format_exc() if include_traceback else None,
            is_recoverable=is_recoverable,
            metadata={
                "original_exception": error,
                "error_args": getattr(error, "args", ()),
            },
        )

        # Log the error
        self._log_error(error_details)

        # Store in history
        self._store_error_history(error_details)

        # Send to monitoring if critical
        if error_severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self._send_to_monitoring(error_details)

        return error_details

    def _get_error_category(self, error_type: Type[Exception]) -> ErrorCategory:
        """Get error category based on exception type."""
        for exc_type, category in self.error_category_map.items():
            if issubclass(error_type, exc_type):
                return category
        return ErrorCategory.SYSTEM

    def _get_error_severity(self, error_type: Type[Exception]) -> ErrorSeverity:
        """Get error severity based on exception type."""
        for exc_type, severity in self.severity_map.items():
            if issubclass(error_type, exc_type):
                return severity
        return ErrorSeverity.MEDIUM

    def _log_error(self, error_details: ErrorDetails) -> None:
        """Log error with appropriate level and formatting."""
        log_data = {
            "error_id": error_details.error_id,
            "severity": error_details.severity.value,
            "category": error_details.category.value,
            "error_type": error_details.error_type,
            "component": error_details.context.component,
            "operation": error_details.context.operation,
            "message": error_details.message,
            "timestamp": error_details.timestamp.isoformat(),
            "is_recoverable": error_details.is_recoverable,
        }

        # Add context data
        if error_details.context.user_id:
            log_data["user_id"] = error_details.context.user_id
        if error_details.context.session_id:
            log_data["session_id"] = error_details.context.session_id
        if error_details.context.request_id:
            log_data["request_id"] = error_details.context.request_id

        # Add additional context data
        log_data.update(error_details.context.additional_data)

        # Choose log level based on severity
        if error_details.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(f"CRITICAL ERROR [{error_details.error_id}]: {error_details.message}", extra=log_data)
        elif error_details.severity == ErrorSeverity.HIGH:
            self.logger.error(f"ERROR [{error_details.error_id}]: {error_details.message}", extra=log_data)
        elif error_details.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(f"WARNING [{error_details.error_id}]: {error_details.message}", extra=log_data)
        else:
            self.logger.info(f"INFO [{error_details.error_id}]: {error_details.message}", extra=log_data)

        # Log traceback for high/critical errors
        if error_details.traceback and error_details.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self.logger.error(f"Traceback for error [{error_details.error_id}]:\n{error_details.traceback}")

    def _store_error_history(self, error_details: ErrorDetails) -> None:
        """Store error in history for analysis."""
        self.error_history.append(error_details)

        # Maintain history size
        if len(self.error_history) > self.max_history_size:
            self.error_history = self.error_history[-self.max_history_size :]

    def _send_to_monitoring(self, error_details: ErrorDetails) -> None:
        """Send critical errors to monitoring system."""
        try:
            # This would integrate with your monitoring system
            # For now, just log that monitoring should be notified
            self.logger.critical(f"MONITORING ALERT: Critical error {error_details.error_id} requires attention")
        except Exception as e:
            self.logger.error(f"Failed to send error to monitoring: {e}")

    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics from history."""
        if not self.error_history:
            return {"total_errors": 0}

        stats = {
            "total_errors": len(self.error_history),
            "by_severity": {},
            "by_category": {},
            "by_component": {},
            "recent_errors": [],
        }

        # Count by severity
        for severity in ErrorSeverity:
            count = sum(1 for e in self.error_history if e.severity == severity)
            stats["by_severity"][severity.value] = count

        # Count by category
        for category in ErrorCategory:
            count = sum(1 for e in self.error_history if e.category == category)
            stats["by_category"][category.value] = count

        # Count by component
        for error in self.error_history:
            component = error.context.component
            stats["by_component"][component] = stats["by_component"].get(component, 0) + 1

        # Recent errors (last 10)
        recent_errors = sorted(self.error_history, key=lambda e: e.timestamp, reverse=True)[:10]
        stats["recent_errors"] = [
            {
                "error_id": e.error_id,
                "timestamp": e.timestamp.isoformat(),
                "severity": e.severity.value,
                "category": e.category.value,
                "message": e.message,
                "component": e.context.component,
            }
            for e in recent_errors
        ]

        return stats


# Global error handler instance
error_handler = ErrorHandler()


def with_error_handling(
    component: str,
    operation: str,
    severity: Optional[ErrorSeverity] = None,
    category: Optional[ErrorCategory] = None,
    reraise: bool = True,
    default_return: Any = None,
):
    """Decorator for standardized error handling.

    Args:
        component: Component name where error occurred
        operation: Operation being performed
        severity: Override error severity
        category: Override error category
        reraise: Whether to reraise the exception after handling
        default_return: Default value to return if error occurs and reraise=False
    """

    def decorator(func):
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = ErrorContext(
                    component=component, operation=operation, additional_data={"args": str(args), "kwargs": str(kwargs)}
                )

                error_handler.handle_error(error=e, context=context, severity=severity, category=category)

                if reraise:
                    raise
                return default_return

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                context = ErrorContext(
                    component=component, operation=operation, additional_data={"args": str(args), "kwargs": str(kwargs)}
                )

                error_handler.handle_error(error=e, context=context, severity=severity, category=category)

                if reraise:
                    raise
                return default_return

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def with_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    component: str = "unknown",
    operation: str = "unknown",
):
    """Decorator for automatic retry with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries
        backoff: Backoff multiplier for delay
        exceptions: Tuple of exceptions to retry on
        component: Component name for error reporting
        operation: Operation name for error reporting
    """

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        # Final attempt failed, handle error
                        context = ErrorContext(
                            component=component,
                            operation=operation,
                            additional_data={"retry_count": attempt, "max_retries": max_retries},
                        )

                        error_details = error_handler.handle_error(error=e, context=context, is_recoverable=False)
                        error_details.retry_count = attempt
                        error_details.max_retries = max_retries

                        raise

                    # Wait before retry with exponential backoff
                    wait_time = delay * (backoff**attempt)
                    await asyncio.sleep(wait_time)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        # Final attempt failed, handle error
                        context = ErrorContext(
                            component=component,
                            operation=operation,
                            additional_data={"retry_count": attempt, "max_retries": max_retries},
                        )

                        error_details = error_handler.handle_error(error=e, context=context, is_recoverable=False)
                        error_details.retry_count = attempt
                        error_details.max_retries = max_retries

                        raise

                    # Wait before retry with exponential backoff
                    wait_time = delay * (backoff**attempt)
                    
                    # Use asyncio.sleep in a sync context via run_in_executor to avoid blocking
                    import time
                    time.sleep(wait_time)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def create_error_context(
    component: str,
    operation: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    **additional_data,
) -> ErrorContext:
    """Create error context for manual error handling.

    Args:
        component: Component name
        operation: Operation being performed
        user_id: User ID if applicable
        session_id: Session ID if applicable
        request_id: Request ID if applicable
        **additional_data: Additional context data

    Returns:
        ErrorContext: Created error context
    """
    return ErrorContext(
        component=component,
        operation=operation,
        user_id=user_id,
        session_id=session_id,
        request_id=request_id,
        additional_data=additional_data,
    )


def handle_error(
    error: Exception,
    context: ErrorContext,
    severity: Optional[ErrorSeverity] = None,
    category: Optional[ErrorCategory] = None,
    is_recoverable: bool = True,
) -> ErrorDetails:
    """Handle an error manually.

    Args:
        error: The exception that occurred
        context: Error context
        severity: Override severity level
        category: Override error category
        is_recoverable: Whether the error is recoverable

    Returns:
        ErrorDetails: Detailed error information
    """
    return error_handler.handle_error(
        error=error, context=context, severity=severity, category=category, is_recoverable=is_recoverable
    )


def get_error_stats() -> Dict[str, Any]:
    """Get error statistics.

    Returns:
        Dict[str, Any]: Error statistics
    """
    return error_handler.get_error_stats()
