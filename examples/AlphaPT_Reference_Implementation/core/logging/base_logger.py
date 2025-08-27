"""Base logger components shared between logging modules."""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog
from structlog import get_logger as structlog_get_logger


@dataclass
class LogContext:
    """Log context information."""

    correlation_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    component: Optional[str] = None
    operation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class TimestampProcessor:
    """Processor to add timestamp to log records."""

    def __call__(self, logger, method_name, event_dict):
        event_dict["timestamp"] = datetime.now(timezone.utc).isoformat()
        return event_dict


class ComponentProcessor:
    """Processor to add component information."""

    def __init__(self, component_name: str):
        self.component_name = component_name

    def __call__(self, logger, method_name, event_dict):
        event_dict["component"] = self.component_name
        return event_dict


class JSONRenderer:
    """Custom JSON renderer for structured logs."""

    def __call__(self, logger, name, event_dict):
        # Ensure we have a message
        if "event" not in event_dict:
            event_dict["event"] = "log_message"

        # Move 'event' to 'message' for consistency
        event_dict["message"] = event_dict.pop("event")

        # Add log level
        event_dict["level"] = name.upper()

        return json.dumps(event_dict, default=str, sort_keys=True)


class ConsoleRenderer:
    """Human-readable console renderer."""

    def __call__(self, logger, name, event_dict):
        timestamp = event_dict.pop("timestamp", "")
        level = name.upper()
        component = event_dict.pop("component", "")
        correlation_id = event_dict.pop("correlation_id", "")
        message = event_dict.pop("event", event_dict.pop("message", ""))

        # Format base message
        base_parts = [timestamp, level]
        if component:
            base_parts.append(f"[{component}]")
        if correlation_id:
            base_parts.append(f"({correlation_id[:8]})")

        base_msg = " ".join(filter(None, base_parts))

        # Add main message
        if message:
            base_msg += f" - {message}"

        # Add additional fields
        if event_dict:
            extras = ", ".join(f"{k}={v}" for k, v in event_dict.items())
            base_msg += f" | {extras}"

        return base_msg


class StructuredLogger:
    """Enhanced structured logger with additional context."""

    def __init__(self, name: str, component: Optional[str] = None):
        self.logger = structlog_get_logger(name)
        if component:
            self.logger = self.logger.bind(component=component)
        self.component = component

    def with_context(self, **kwargs) -> "StructuredLogger":
        """Create logger with additional context."""
        new_logger = StructuredLogger(self.logger._logger.name, self.component)
        new_logger.logger = self.logger.bind(**kwargs)
        return new_logger

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(message, **kwargs)

    def error(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """Log error message."""
        if error:
            kwargs["error_type"] = type(error).__name__
            kwargs["error_message"] = str(error)
            import traceback
            kwargs["traceback"] = traceback.format_exc()

        self.logger.error(message, **kwargs)

    def critical(self, message: str, error: Optional[Exception] = None, **kwargs) -> None:
        """Log critical message."""
        if error:
            kwargs["error_type"] = type(error).__name__
            kwargs["error_message"] = str(error)
            import traceback
            kwargs["traceback"] = traceback.format_exc()

        self.logger.critical(message, **kwargs)