"""
Correlation ID propagation system for request tracing across service boundaries.

This module provides correlation context management to enable distributed tracing
across all microservices in the Alpha Panda system.
"""

from contextvars import ContextVar
from typing import Optional, Dict, Any
import uuid
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Context variable to store correlation ID across async calls
correlation_context: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

# Context variable to store causation ID (parent event ID)
causation_context: ContextVar[Optional[str]] = ContextVar('causation_id', default=None)

# Context variable to store request metadata for tracing
request_metadata_context: ContextVar[Optional[Dict[str, Any]]] = ContextVar('request_metadata', default=None)


class CorrelationContext:
    """Manage correlation ID and causation chain across async calls"""
    
    @staticmethod
    def set_correlation_id(correlation_id: str) -> None:
        """Set correlation ID in current context"""
        correlation_context.set(correlation_id)
        logger.debug(f"Set correlation ID: {correlation_id}")
    
    @staticmethod
    def get_correlation_id() -> Optional[str]:
        """Get correlation ID from current context"""
        return correlation_context.get()
    
    @staticmethod
    def set_causation_id(causation_id: str) -> None:
        """Set causation ID (parent event) in current context"""
        causation_context.set(causation_id)
        logger.debug(f"Set causation ID: {causation_id}")
    
    @staticmethod
    def get_causation_id() -> Optional[str]:
        """Get causation ID from current context"""
        return causation_context.get()
    
    @staticmethod
    def set_request_metadata(metadata: Dict[str, Any]) -> None:
        """Set request metadata for tracing"""
        request_metadata_context.set(metadata)
    
    @staticmethod
    def get_request_metadata() -> Optional[Dict[str, Any]]:
        """Get request metadata from current context"""
        return request_metadata_context.get()
    
    @staticmethod
    def generate_correlation_id() -> str:
        """Generate new correlation ID using UUID4"""
        return str(uuid.uuid4())
    
    @staticmethod 
    def ensure_correlation_id() -> str:
        """Get existing or generate new correlation ID"""
        correlation_id = correlation_context.get()
        if not correlation_id:
            correlation_id = CorrelationContext.generate_correlation_id()
            correlation_context.set(correlation_id)
        return correlation_id
    
    @staticmethod
    def start_new_trace(
        service_name: str,
        operation: str,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Start a new correlation trace.
        
        Args:
            service_name: Name of service starting the trace
            operation: Operation being performed
            correlation_id: Optional existing correlation ID
            metadata: Optional trace metadata
            
        Returns:
            Correlation ID for this trace
        """
        # Use provided correlation ID or generate new one
        if correlation_id:
            CorrelationContext.set_correlation_id(correlation_id)
        else:
            correlation_id = CorrelationContext.ensure_correlation_id()
        
        # Set trace metadata
        trace_metadata = {
            "trace_id": correlation_id,
            "root_service": service_name,
            "root_operation": operation,
            "started_at": datetime.utcnow().isoformat(),
            "custom_metadata": metadata or {}
        }
        CorrelationContext.set_request_metadata(trace_metadata)
        
        logger.info(f"Started trace: {correlation_id} for {service_name}.{operation}")
        return correlation_id
    
    @staticmethod
    def continue_trace(
        event_correlation_id: str,
        event_id: str,
        service_name: str,
        operation: str
    ) -> None:
        """
        Continue existing trace from incoming event.
        
        Args:
            event_correlation_id: Correlation ID from incoming event
            event_id: ID of incoming event (becomes causation ID)
            service_name: Current service name
            operation: Current operation
        """
        # Set correlation and causation context
        CorrelationContext.set_correlation_id(event_correlation_id)
        CorrelationContext.set_causation_id(event_id)
        
        # Update metadata
        existing_metadata = CorrelationContext.get_request_metadata() or {}
        existing_metadata.update({
            "current_service": service_name,
            "current_operation": operation,
            "continued_at": datetime.utcnow().isoformat(),
            "parent_event_id": event_id
        })
        CorrelationContext.set_request_metadata(existing_metadata)
        
        logger.debug(f"Continued trace: {event_correlation_id} in {service_name}.{operation}")
    
    @staticmethod
    def get_trace_context() -> Dict[str, Any]:
        """Get complete trace context for propagation"""
        return {
            "correlation_id": CorrelationContext.get_correlation_id(),
            "causation_id": CorrelationContext.get_causation_id(),
            "metadata": CorrelationContext.get_request_metadata()
        }
    
    @staticmethod
    def clear_context() -> None:
        """Clear all context variables"""
        correlation_context.set(None)
        causation_context.set(None)
        request_metadata_context.set(None)


class CorrelationLogger:
    """Logger wrapper that automatically includes correlation context"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = logging.getLogger(f"{service_name}.correlation")
    
    def _get_log_context(self) -> Dict[str, Any]:
        """Get correlation context for logging"""
        context = {
            "service": self.service_name,
            "correlation_id": CorrelationContext.get_correlation_id(),
            "causation_id": CorrelationContext.get_causation_id()
        }
        
        metadata = CorrelationContext.get_request_metadata()
        if metadata:
            context["trace_metadata"] = metadata
        
        return context
    
    def info(self, message: str, **kwargs):
        """Log info with correlation context"""
        context = self._get_log_context()
        context.update(kwargs)
        self.logger.info(message, extra=context)
    
    def debug(self, message: str, **kwargs):
        """Log debug with correlation context"""
        context = self._get_log_context()
        context.update(kwargs)
        self.logger.debug(message, extra=context)
    
    def warning(self, message: str, **kwargs):
        """Log warning with correlation context"""
        context = self._get_log_context()
        context.update(kwargs)
        self.logger.warning(message, extra=context)
    
    def error(self, message: str, **kwargs):
        """Log error with correlation context"""
        context = self._get_log_context()
        context.update(kwargs)
        self.logger.error(message, extra=context)
    
    def critical(self, message: str, **kwargs):
        """Log critical with correlation context"""
        context = self._get_log_context()
        context.update(kwargs)
        self.logger.critical(message, extra=context)


def trace_operation(operation_name: str):
    """
    Decorator to automatically handle correlation context for operations.
    
    Args:
        operation_name: Name of the operation being traced
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Get service name from self if it's a method
            service_name = "unknown"
            if args and hasattr(args[0], 'name'):
                service_name = args[0].name
            elif args and hasattr(args[0], '__class__'):
                service_name = args[0].__class__.__name__
            
            # Start or continue trace
            correlation_id = CorrelationContext.get_correlation_id()
            if not correlation_id:
                CorrelationContext.start_new_trace(service_name, operation_name)
            
            # Create correlation logger
            trace_logger = CorrelationLogger(service_name)
            trace_logger.debug(f"Starting operation: {operation_name}")
            
            try:
                result = await func(*args, **kwargs)
                trace_logger.debug(f"Completed operation: {operation_name}")
                return result
            except Exception as e:
                trace_logger.error(f"Operation failed: {operation_name}", error=str(e))
                raise
        
        return wrapper
    return decorator


class TraceMetrics:
    """Collect metrics for correlation traces"""
    
    def __init__(self):
        self._trace_stats = {
            "active_traces": 0,
            "completed_traces": 0,
            "failed_traces": 0,
            "average_trace_duration": 0.0
        }
        self._active_traces: Dict[str, Dict[str, Any]] = {}
    
    def start_trace_measurement(self, correlation_id: str, service_name: str, operation: str):
        """Start measuring trace metrics"""
        self._trace_stats["active_traces"] += 1
        self._active_traces[correlation_id] = {
            "service": service_name,
            "operation": operation,
            "started_at": datetime.utcnow(),
            "span_count": 1
        }
    
    def add_span(self, correlation_id: str, service_name: str, operation: str):
        """Add span to existing trace"""
        if correlation_id in self._active_traces:
            self._active_traces[correlation_id]["span_count"] += 1
    
    def complete_trace(self, correlation_id: str, success: bool = True):
        """Complete trace measurement"""
        if correlation_id in self._active_traces:
            trace_info = self._active_traces.pop(correlation_id)
            self._trace_stats["active_traces"] -= 1
            
            if success:
                self._trace_stats["completed_traces"] += 1
            else:
                self._trace_stats["failed_traces"] += 1
            
            # Calculate duration
            duration = (datetime.utcnow() - trace_info["started_at"]).total_seconds()
            
            # Update average (simple moving average)
            total_traces = self._trace_stats["completed_traces"] + self._trace_stats["failed_traces"]
            if total_traces > 0:
                current_avg = self._trace_stats["average_trace_duration"]
                self._trace_stats["average_trace_duration"] = (
                    (current_avg * (total_traces - 1) + duration) / total_traces
                )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get trace metrics for monitoring"""
        return {
            **self._trace_stats,
            "active_trace_details": list(self._active_traces.keys())
        }


# Global trace metrics instance
trace_metrics = TraceMetrics()