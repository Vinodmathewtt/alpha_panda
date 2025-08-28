"""
Correlation ID system for distributed tracing across Alpha Panda services.
Provides request tracking and log correlation capabilities.
"""

import uuid
import contextvars
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# Context variable to store correlation ID for the current request/operation
_correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'correlation_id', default=None
)

# Context variable to store additional correlation context
_correlation_context: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    'correlation_context', default={}
)


class CorrelationIdManager:
    """Manager for correlation ID lifecycle and context propagation"""
    
    @staticmethod
    def generate_correlation_id() -> str:
        """
        Generate a new correlation ID using UUID4.
        
        Returns:
            New correlation ID string
        """
        return str(uuid.uuid4())
    
    @staticmethod
    def set_correlation_id(correlation_id: str) -> str:
        """
        Set the correlation ID for the current context.
        
        Args:
            correlation_id: Correlation ID to set
            
        Returns:
            The correlation ID that was set
        """
        _correlation_id.set(correlation_id)
        return correlation_id
    
    @staticmethod
    def get_correlation_id() -> Optional[str]:
        """
        Get the current correlation ID from context.
        
        Returns:
            Current correlation ID or None if not set
        """
        return _correlation_id.get()
    
    @staticmethod
    def ensure_correlation_id() -> str:
        """
        Ensure a correlation ID exists, generating one if needed.
        
        Returns:
            Current or newly generated correlation ID
        """
        current_id = _correlation_id.get()
        if current_id is None:
            current_id = CorrelationIdManager.generate_correlation_id()
            _correlation_id.set(current_id)
        return current_id
    
    @staticmethod
    def set_correlation_context(**kwargs) -> Dict[str, Any]:
        """
        Set additional correlation context data.
        
        Args:
            **kwargs: Key-value pairs to add to correlation context
            
        Returns:
            Updated correlation context
        """
        current_context = _correlation_context.get().copy()
        current_context.update(kwargs)
        _correlation_context.set(current_context)
        return current_context
    
    @staticmethod
    def get_correlation_context() -> Dict[str, Any]:
        """
        Get the current correlation context.
        
        Returns:
            Current correlation context dictionary
        """
        return _correlation_context.get().copy()
    
    @staticmethod
    def clear_correlation() -> None:
        """Clear correlation ID and context from current context"""
        _correlation_id.set(None)
        _correlation_context.set({})
    
    @staticmethod
    def get_full_correlation_info() -> Dict[str, Any]:
        """
        Get complete correlation information for logging.
        
        Returns:
            Dictionary with correlation ID and context
        """
        return {
            "correlation_id": _correlation_id.get(),
            "correlation_context": _correlation_context.get(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


def with_correlation_id(correlation_id: Optional[str] = None):
    """
    Decorator to ensure a function runs with a correlation ID.
    
    Args:
        correlation_id: Optional correlation ID to use, generates new one if None
    """
    def decorator(func):
        if hasattr(func, '__call__'):
            async def async_wrapper(*args, **kwargs):
                # Set correlation ID for this operation
                if correlation_id:
                    CorrelationIdManager.set_correlation_id(correlation_id)
                else:
                    CorrelationIdManager.ensure_correlation_id()
                
                try:
                    return await func(*args, **kwargs)
                finally:
                    # Don't clear correlation ID as it might be needed by parent context
                    pass
            
            def sync_wrapper(*args, **kwargs):
                # Set correlation ID for this operation
                if correlation_id:
                    CorrelationIdManager.set_correlation_id(correlation_id)
                else:
                    CorrelationIdManager.ensure_correlation_id()
                
                try:
                    return func(*args, **kwargs)
                finally:
                    # Don't clear correlation ID as it might be needed by parent context
                    pass
            
            # Return appropriate wrapper based on function type
            import asyncio
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
        return func
    return decorator


def create_correlation_context(
    service: str,
    operation: str,
    broker: Optional[str] = None,
    user_id: Optional[str] = None,
    **additional_context
) -> str:
    """
    Create a new correlation context for an operation.
    
    Args:
        service: Name of the service
        operation: Name of the operation
        broker: Optional broker namespace
        user_id: Optional user identifier
        **additional_context: Additional context key-value pairs
        
    Returns:
        Correlation ID for the created context
    """
    correlation_id = CorrelationIdManager.ensure_correlation_id()
    
    context = {
        "service": service,
        "operation": operation,
        "started_at": datetime.now(timezone.utc).isoformat()
    }
    
    if broker:
        context["broker"] = broker
    if user_id:
        context["user_id"] = user_id
    
    context.update(additional_context)
    
    CorrelationIdManager.set_correlation_context(**context)
    
    return correlation_id


def propagate_correlation_to_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """
    Propagate correlation information to a message for inter-service communication.
    
    Args:
        message: Message dictionary to enhance with correlation info
        
    Returns:
        Enhanced message with correlation information
    """
    correlation_id = CorrelationIdManager.get_correlation_id()
    correlation_context = CorrelationIdManager.get_correlation_context()
    
    if correlation_id:
        if "metadata" not in message:
            message["metadata"] = {}
        
        message["metadata"]["correlation_id"] = correlation_id
        message["metadata"]["correlation_context"] = correlation_context
    
    return message


def extract_correlation_from_message(message: Dict[str, Any]) -> Optional[str]:
    """
    Extract correlation information from a message and set in current context.
    
    Args:
        message: Message dictionary that may contain correlation info
        
    Returns:
        Extracted correlation ID or None if not found
    """
    metadata = message.get("metadata", {})
    correlation_id = metadata.get("correlation_id")
    correlation_context = metadata.get("correlation_context", {})
    
    if correlation_id:
        CorrelationIdManager.set_correlation_id(correlation_id)
        if correlation_context:
            CorrelationIdManager.set_correlation_context(**correlation_context)
    
    return correlation_id


class CorrelatedLogger:
    """Logger wrapper that automatically includes correlation information"""
    
    def __init__(self, logger):
        self.logger = logger
    
    def _add_correlation_info(self, **kwargs):
        """Add correlation information to log kwargs"""
        correlation_info = CorrelationIdManager.get_full_correlation_info()
        kwargs.update(correlation_info)
        return kwargs
    
    def debug(self, message, **kwargs):
        """Log debug message with correlation info"""
        kwargs = self._add_correlation_info(**kwargs)
        return self.logger.debug(message, **kwargs)
    
    def info(self, message, **kwargs):
        """Log info message with correlation info"""
        kwargs = self._add_correlation_info(**kwargs)
        return self.logger.info(message, **kwargs)
    
    def warning(self, message, **kwargs):
        """Log warning message with correlation info"""
        kwargs = self._add_correlation_info(**kwargs)
        return self.logger.warning(message, **kwargs)
    
    def error(self, message, **kwargs):
        """Log error message with correlation info"""
        kwargs = self._add_correlation_info(**kwargs)
        return self.logger.error(message, **kwargs)
    
    def critical(self, message, **kwargs):
        """Log critical message with correlation info"""
        kwargs = self._add_correlation_info(**kwargs)
        return self.logger.critical(message, **kwargs)
    
    def bind(self, **kwargs):
        """Bind additional context to the logger"""
        return CorrelatedLogger(self.logger.bind(**kwargs))


def get_correlated_logger(logger):
    """
    Wrap a logger to automatically include correlation information.
    
    Args:
        logger: Logger instance to wrap
        
    Returns:
        CorrelatedLogger instance
    """
    return CorrelatedLogger(logger)