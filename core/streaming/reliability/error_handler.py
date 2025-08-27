"""Enhanced error handler for the reliability layer."""

from typing import Dict, Any, Optional, Callable
from ..error_handling import (
    ErrorHandler as BaseErrorHandler,
    ErrorClassifier,
    DLQPublisher,
    RetryConfig,
    ErrorType
)


class ErrorHandler(BaseErrorHandler):
    """Enhanced error handler for the reliability layer with additional features."""
    
    def __init__(
        self, 
        service_name: str,
        dlq_publisher: DLQPublisher,
        default_retry_config: Optional[RetryConfig] = None,
        custom_error_mappings: Optional[Dict[str, ErrorType]] = None
    ):
        super().__init__(service_name, dlq_publisher, default_retry_config)
        
        # Allow custom error mappings per service
        if custom_error_mappings:
            self.error_classifier.ERROR_MAPPINGS.update(custom_error_mappings)
    
    async def handle_processing_error_async(
        self,
        message: Dict[str, Any],
        error: Exception,
        processing_func: Callable,
        commit_func: Optional[Callable] = None,
        context: Optional[Dict[str, Any]] = None,
        broker_context: Optional[str] = None
    ) -> bool:
        """
        Enhanced async error handling with context support.
        
        Args:
            message: The message dict that failed to process
            error: Exception that occurred
            processing_func: Function to retry processing with
            commit_func: Optional function to commit offset after success/DLQ
            context: Additional context for error handling decisions
            broker_context: Optional broker context for error logging
            
        Returns:
            True if handled successfully (including DLQ), False if should be reprocessed
        """
        # Convert dict message to object-like structure for compatibility
        class MessageObj:
            def __init__(self, msg_dict: Dict[str, Any]):
                self.topic = msg_dict.get('topic', 'unknown')
                self.partition = msg_dict.get('partition', -1)
                self.offset = msg_dict.get('offset', -1)
                self.value = msg_dict.get('value', {})
                self.key = msg_dict.get('key', '')
                self.timestamp = msg_dict.get('timestamp', 0)
        
        message_obj = MessageObj(message)
        
        # Enhance context with broker information
        enhanced_context = context or {}
        if broker_context:
            enhanced_context['broker'] = broker_context
        
        return await super().handle_processing_error(
            message_obj, error, processing_func, commit_func
        )