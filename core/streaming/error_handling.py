"""
Comprehensive error handling system with classification, retry logic, and DLQ pattern.

This module provides structured error handling for stream processing services,
replacing the blanket "never raise" approach with production-ready error management.
"""

from enum import Enum
from typing import Dict, Any, Optional, Callable, List
import asyncio
import random
import json
import logging
import base64
from datetime import datetime, timezone
from dataclasses import dataclass

from core.utils.exceptions import (
    AlphaPandaException, TransientError, PermanentError,
    AuthenticationError, BrokerError, InfrastructureError,
    StreamingError, MessageDeserializationError, ValidationError,
    is_retryable_error, get_retry_delay, create_error_context
)

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """Classification of errors for appropriate handling strategies"""
    TRANSIENT = "transient"          # Network issues, temporary unavailability
    POISON = "poison"                # Malformed data, schema violations  
    BUSINESS = "business"            # Strategy logic errors, risk violations
    INFRASTRUCTURE = "infrastructure" # Database, Redis unavailability
    AUTHENTICATION = "authentication" # Broker auth failures
    RATE_LIMIT = "rate_limit"        # API rate limiting


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""
    max_attempts: int = 5
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt using exponential backoff with jitter"""
        delay = min(self.base_delay * (self.exponential_base ** attempt), self.max_delay)
        
        if self.jitter:
            # Add jitter: 50% to 100% of calculated delay
            delay = delay * (0.5 + 0.5 * random.random())
        
        return delay


class ErrorClassifier:
    """Classify errors for appropriate handling strategies"""
    
    # Error type mappings based on exception types and patterns
    ERROR_MAPPINGS = {
        # Transient errors - worth retrying
        'ConnectionError': ErrorType.TRANSIENT,
        'TimeoutError': ErrorType.TRANSIENT,
        'KafkaTimeoutError': ErrorType.TRANSIENT,
        'CommitFailedError': ErrorType.TRANSIENT,
        'RebalanceInProgressError': ErrorType.TRANSIENT,
        
        # Structured exception mappings
        'BrokerConnectionError': ErrorType.TRANSIENT,
        'BrokerAPIError': ErrorType.TRANSIENT,
        'MarketDataError': ErrorType.TRANSIENT,
        'MarketDataConnectionError': ErrorType.TRANSIENT,
        'StaleDataError': ErrorType.TRANSIENT,
        'StrategyExecutionError': ErrorType.TRANSIENT,
        'DatabaseError': ErrorType.INFRASTRUCTURE,
        'RedisError': ErrorType.INFRASTRUCTURE,
        'StreamingError': ErrorType.INFRASTRUCTURE,
        'PortfolioStateError': ErrorType.INFRASTRUCTURE,
        'OrderTimeoutError': ErrorType.TRANSIENT,
        
        # Poison messages - never retry, send to DLQ immediately
        'ValidationError': ErrorType.POISON,
        'ValueError': ErrorType.POISON,
        'KeyError': ErrorType.POISON,
        'JSONDecodeError': ErrorType.POISON,
        'TypeError': ErrorType.POISON,
        'UnicodeDecodeError': ErrorType.POISON,
        'MessageDeserializationError': ErrorType.POISON,
        'ConfigurationError': ErrorType.POISON,
        'InstrumentNotFoundError': ErrorType.POISON,
        'StrategyConfigurationError': ErrorType.POISON,
        
        # Permanent errors that shouldn't be retried
        'RiskValidationError': ErrorType.POISON,
        'PositionLimitError': ErrorType.POISON,
        'InsufficientFundsError': ErrorType.POISON,
        'OrderRejectionError': ErrorType.POISON,
        'AuthorizationError': ErrorType.POISON,
        
        # Infrastructure errors - retry with caution
        'SQLAlchemyError': ErrorType.INFRASTRUCTURE,
        'RedisConnectionError': ErrorType.INFRASTRUCTURE,
        'DatabaseConnectionError': ErrorType.INFRASTRUCTURE,
        'InfrastructureError': ErrorType.INFRASTRUCTURE,
        
        # Authentication errors - special handling
        'AuthenticationError': ErrorType.AUTHENTICATION,
        'TokenExpiredError': ErrorType.AUTHENTICATION,
        'UnauthorizedError': ErrorType.AUTHENTICATION,
        
        # Rate limiting - backoff and retry
        'RateLimitError': ErrorType.RATE_LIMIT,
        'TooManyRequestsError': ErrorType.RATE_LIMIT,
    }
    
    @classmethod
    def classify_error(cls, error: Exception, message_content: str = "") -> ErrorType:
        """
        Classify error based on exception type and content.
        
        Args:
            error: Exception that occurred
            message_content: String representation of message for content analysis
            
        Returns:
            ErrorType classification
        """
        # Handle structured Alpha Panda exceptions first
        if isinstance(error, PermanentError):
            return ErrorType.POISON
        elif isinstance(error, TransientError):
            if isinstance(error, AuthenticationError):
                return ErrorType.AUTHENTICATION
            elif isinstance(error, BrokerError):
                if 'rate limit' in str(error).lower() or 'too many requests' in str(error).lower():
                    return ErrorType.RATE_LIMIT
                return ErrorType.TRANSIENT
            elif isinstance(error, InfrastructureError):
                return ErrorType.INFRASTRUCTURE
            else:
                return ErrorType.TRANSIENT
        
        error_name = type(error).__name__
        
        # Check direct mappings for other exceptions
        if error_name in cls.ERROR_MAPPINGS:
            return cls.ERROR_MAPPINGS[error_name]
        
        # Analyze error message for additional classification
        error_msg = str(error).lower()
        
        # Check for common transient error patterns
        transient_patterns = [
            'connection refused', 'connection reset', 'timeout',
            'temporary failure', 'service unavailable', 'network unreachable'
        ]
        if any(pattern in error_msg for pattern in transient_patterns):
            return ErrorType.TRANSIENT
        
        # Check for poison message patterns
        poison_patterns = [
            'invalid format', 'malformed', 'parse error',
            'schema validation', 'unknown field', 'missing required'
        ]
        if any(pattern in error_msg for pattern in poison_patterns):
            return ErrorType.POISON
        
        # Check for authentication patterns
        auth_patterns = [
            'unauthorized', 'authentication failed', 'invalid token',
            'access denied', 'forbidden', 'credentials'
        ]
        if any(pattern in error_msg for pattern in auth_patterns):
            return ErrorType.AUTHENTICATION
        
        # Default to business logic error for unclassified errors
        return ErrorType.BUSINESS
    
    @classmethod
    def should_retry(cls, error_type: ErrorType) -> bool:
        """Determine if error type should be retried"""
        return error_type in [
            ErrorType.TRANSIENT,
            ErrorType.INFRASTRUCTURE,
            ErrorType.RATE_LIMIT,
            ErrorType.BUSINESS  # Business errors get limited retries
        ]
    
    @classmethod
    def get_retry_config(cls, error_type: ErrorType) -> RetryConfig:
        """Get retry configuration based on error type"""
        configs = {
            ErrorType.TRANSIENT: RetryConfig(max_attempts=5, base_delay=1.0, max_delay=30.0),
            ErrorType.INFRASTRUCTURE: RetryConfig(max_attempts=3, base_delay=2.0, max_delay=60.0),
            ErrorType.RATE_LIMIT: RetryConfig(max_attempts=8, base_delay=5.0, max_delay=300.0),
            ErrorType.BUSINESS: RetryConfig(max_attempts=2, base_delay=1.0, max_delay=10.0),
            ErrorType.AUTHENTICATION: RetryConfig(max_attempts=1, base_delay=60.0, max_delay=60.0),
            ErrorType.POISON: RetryConfig(max_attempts=0, base_delay=0.0, max_delay=0.0),  # No retries
        }
        return configs.get(error_type, RetryConfig(max_attempts=3, base_delay=1.0, max_delay=30.0))


class DLQPublisher:
    """Dead Letter Queue message publisher for failed message handling"""
    
    def __init__(self, producer, service_name: str):
        self.producer = producer
        self.service_name = service_name
        self._dlq_stats = {
            "messages_sent": 0,
            "errors": 0
        }
    
    async def send_to_dlq(
        self, 
        original_message, 
        error: Exception, 
        failure_reason: str, 
        retry_count: int = 0,
        error_type: ErrorType = None
    ) -> bool:
        """
        Send failed message to Dead Letter Queue.
        
        Args:
            original_message: The original message that failed
            error: Exception that caused the failure
            failure_reason: Human-readable reason for failure
            retry_count: Number of retries attempted
            error_type: Classified error type
            
        Returns:
            True if successfully sent to DLQ, False otherwise
        """
        try:
            # Determine DLQ topic
            original_topic = getattr(original_message, 'topic', 'unknown')
            dlq_topic = f"{original_topic}.dlq"
            
            # Extract message data safely
            message_key = getattr(original_message, 'key', b'')
            if hasattr(message_key, 'decode'):
                message_key = message_key.decode('utf-8')
            else:
                message_key = str(message_key)
            
            message_value = getattr(original_message, 'value', {})
            
            # Create comprehensive DLQ event
            dlq_event = {
                "dlq_metadata": {
                    "original_topic": original_topic,
                    "original_partition": getattr(original_message, 'partition', -1),
                    "original_offset": getattr(original_message, 'offset', -1),
                    "original_timestamp": getattr(original_message, 'timestamp', 0),
                    "dlq_timestamp": datetime.now(timezone.utc).isoformat(),
                    "service_name": self.service_name
                },
                "failure_info": {
                    "error_type": error_type.value if error_type else "unknown",
                    "error_class": type(error).__name__,
                    "error_message": str(error),
                    "failure_reason": failure_reason,
                    "retry_count": retry_count,
                    "stack_trace": None  # Could add traceback if needed for debugging
                },
                "original_message": {
                    "key": message_key,
                    "value": message_value,
                    "headers": self._serialize_headers(getattr(original_message, 'headers', {}))
                },
                "replay_metadata": {
                    "can_replay": error_type not in [ErrorType.POISON] if error_type else True,
                    "suggested_delay_minutes": self._get_suggested_replay_delay(error_type),
                    "consumer_group": f"alpha-panda.{self.service_name}",
                    "requires_manual_review": error_type in [ErrorType.POISON, ErrorType.AUTHENTICATION] if error_type else False
                }
            }
            
            # Send to DLQ topic
            await self.producer.send(
                topic=dlq_topic,
                key=message_key,
                value=dlq_event
            )
            
            self._dlq_stats["messages_sent"] += 1
            logger.warning(
                f"Message sent to DLQ: topic={dlq_topic}, reason={failure_reason}, "
                f"error_type={error_type.value if error_type else 'unknown'}, "
                f"retry_count={retry_count}"
            )
            return True
            
        except Exception as dlq_error:
            self._dlq_stats["errors"] += 1
            logger.error(f"Failed to send message to DLQ: {dlq_error}")
            # Critical: If we can't send to DLQ, we must not lose the message
            # In production, this might trigger an alert or write to local storage
            return False
    
    def _get_suggested_replay_delay(self, error_type: Optional[ErrorType]) -> int:
        """Get suggested delay in minutes before replaying from DLQ"""
        delays = {
            ErrorType.TRANSIENT: 5,
            ErrorType.INFRASTRUCTURE: 15,
            ErrorType.RATE_LIMIT: 30,
            ErrorType.BUSINESS: 60,
            ErrorType.AUTHENTICATION: 120,
            ErrorType.POISON: -1,  # Never replay automatically
        }
        return delays.get(error_type, 30) if error_type else 30
    
    def _serialize_headers(self, headers) -> Dict[str, str]:
        """
        CRITICAL FIX: Serialize aiokafka headers to JSON-safe format.
        
        aiokafka headers are (key: str, value: bytes) tuples.
        json.dumps fails on bytes, so we convert to base64.
        """
        if not headers:
            return {}
        
        try:
            # Handle both dict and list of tuples formats
            if isinstance(headers, dict):
                serialized = {}
                for key, value in headers.items():
                    if isinstance(value, bytes):
                        serialized[key] = base64.b64encode(value).decode('utf-8')
                    else:
                        serialized[key] = str(value)
                return serialized
            elif isinstance(headers, (list, tuple)):
                # aiokafka format: [(key, bytes), ...]
                serialized = {}
                for key, value in headers:
                    if isinstance(value, bytes):
                        serialized[key] = base64.b64encode(value).decode('utf-8')
                    else:
                        serialized[key] = str(value)
                return serialized
            else:
                logger.warning(f"Unknown headers format: {type(headers)}")
                return {"serialization_error": str(headers)}
        except Exception as e:
            logger.error(f"Failed to serialize headers: {e}")
            return {"serialization_error": f"Failed to serialize: {e}"}
    
    def get_dlq_stats(self) -> Dict[str, int]:
        """Get DLQ statistics for monitoring"""
        return self._dlq_stats.copy()


class ErrorHandler:
    """Comprehensive error handler with retry logic and DLQ integration"""
    
    def __init__(
        self, 
        service_name: str,
        dlq_publisher: DLQPublisher,
        default_retry_config: Optional[RetryConfig] = None
    ):
        self.service_name = service_name
        self.dlq_publisher = dlq_publisher
        self.default_retry_config = default_retry_config or RetryConfig()
        self.error_classifier = ErrorClassifier()
        self._message_retry_count: Dict[str, int] = {}
        self._error_stats = {
            "total_errors": 0,
            "retried_errors": 0,
            "dlq_sent": 0,
            "successful_retries": 0
        }
    
    async def handle_processing_error(
        self, 
        message,
        error: Exception,
        processing_func: Callable,
        commit_func: Optional[Callable] = None
    ) -> bool:
        """
        Handle processing error with retry logic and DLQ fallback.
        
        Args:
            message: The message that failed to process
            error: Exception that occurred
            processing_func: Function to retry processing with
            commit_func: Optional function to commit offset after success/DLQ
            
        Returns:
            True if handled successfully (including DLQ), False if should be reprocessed
        """
        self._error_stats["total_errors"] += 1
        
        # Classify the error
        message_content = str(getattr(message, 'value', ''))
        error_type = self.error_classifier.classify_error(error, message_content)
        
        # Get message identifier for retry tracking
        message_key = self._get_message_key(message)
        retry_count = self._message_retry_count.get(message_key, 0)
        
        # Create structured error context for logging
        error_context = create_error_context(error, f"{self.service_name}_message_processing", {
            "message_topic": getattr(message, 'topic', 'unknown'),
            "message_partition": getattr(message, 'partition', -1),
            "message_offset": getattr(message, 'offset', -1),
            "retry_count": retry_count,
            "error_type": error_type.value
        })
        
        logger.error(f"Processing error in {self.service_name}", extra=error_context)
        
        # Handle poison messages immediately
        if error_type == ErrorType.POISON:
            await self._send_to_dlq_and_commit(message, error, error_type, retry_count, commit_func)
            return True
        
        # Check if we should retry based on both error type and structured exceptions
        should_retry_type = self.error_classifier.should_retry(error_type)
        should_retry_structured = is_retryable_error(error) if isinstance(error, AlphaPandaException) else True
        
        if not (should_retry_type and should_retry_structured):
            await self._send_to_dlq_and_commit(message, error, error_type, retry_count, commit_func)
            return True
        
        # Get retry configuration for this error type
        retry_config = self.error_classifier.get_retry_config(error_type)
        
        # For structured exceptions, also consider their specific retry limits
        if isinstance(error, TransientError) and hasattr(error, 'max_retries'):
            retry_config.max_attempts = min(retry_config.max_attempts, error.max_retries)
        
        # Check if max retries exceeded
        if retry_count >= retry_config.max_attempts:
            await self._send_to_dlq_and_commit(
                message, error, error_type, retry_count, commit_func, "max_retries_exceeded"
            )
            return True
        
        # Perform retry with backoff
        return await self._retry_processing(
            message, error, error_type, retry_count, retry_config, 
            processing_func, commit_func
        )
    
    async def _retry_processing(
        self,
        message,
        error: Exception,
        error_type: ErrorType,
        retry_count: int,
        retry_config: RetryConfig,
        processing_func: Callable,
        commit_func: Optional[Callable]
    ) -> bool:
        """Perform retry with exponential backoff"""
        message_key = self._get_message_key(message)
        self._message_retry_count[message_key] = retry_count + 1
        self._error_stats["retried_errors"] += 1
        
        # Calculate delay - use structured exception delay if available, otherwise use retry_config
        if isinstance(error, TransientError):
            delay = get_retry_delay(error)
        else:
            delay = retry_config.get_delay(retry_count)
            
        logger.info(
            f"Retrying message processing (attempt {retry_count + 1}/{retry_config.max_attempts}) "
            f"after {delay:.2f}s delay"
        )
        
        await asyncio.sleep(delay)
        
        try:
            # Attempt reprocessing
            await processing_func()
            
            # Success - clean up retry tracking and commit
            del self._message_retry_count[message_key]
            self._error_stats["successful_retries"] += 1
            
            if commit_func:
                await commit_func()
            
            logger.info(f"Retry successful for message after {retry_count + 1} attempts")
            return True
            
        except Exception as retry_error:
            # Retry failed - will be handled in next iteration
            logger.warning(f"Retry {retry_count + 1} failed: {retry_error}")
            return False
    
    async def _send_to_dlq_and_commit(
        self,
        message,
        error: Exception,
        error_type: ErrorType,
        retry_count: int,
        commit_func: Optional[Callable],
        reason: str = "processing_failed"
    ) -> None:
        """Send message to DLQ and commit offset"""
        message_key = self._get_message_key(message)
        
        # Send to DLQ
        dlq_success = await self.dlq_publisher.send_to_dlq(
            message, error, reason, retry_count, error_type
        )
        
        if dlq_success:
            self._error_stats["dlq_sent"] += 1
            
            # Clean up retry tracking
            if message_key in self._message_retry_count:
                del self._message_retry_count[message_key]
            
            # Commit offset to skip this message
            if commit_func:
                await commit_func()
        else:
            # Critical: DLQ failed - this is a serious issue
            logger.critical(f"Failed to send message to DLQ - message may be lost!")
    
    def _get_message_key(self, message) -> str:
        """Generate unique key for message retry tracking"""
        return f"{message.topic}:{message.partition}:{message.offset}"
    
    def get_error_stats(self) -> Dict[str, int]:
        """Get error handling statistics for monitoring"""
        return self._error_stats.copy()
    
    def reset_stats(self) -> None:
        """Reset error statistics"""
        self._error_stats = {
            "total_errors": 0,
            "retried_errors": 0,
            "dlq_sent": 0,
            "successful_retries": 0
        }


# Utility function for graceful degradation in auth failures
async def handle_auth_degradation(service_name: str, error: Exception) -> Dict[str, Any]:
    """
    Handle authentication failures with graceful degradation.
    
    For broker auth failures, services should:
    1. Switch to mock data mode
    2. Alert operations team
    3. Continue operating in degraded state
    
    Args:
        service_name: Name of service experiencing auth failure
        error: Authentication error
        
    Returns:
        Degradation strategy configuration
    """
    logger.critical(f"Authentication failure in {service_name}: {error}")
    
    degradation_config = {
        "mode": "degraded",
        "use_mock_data": True,
        "alert_operations": True,
        "retry_auth_interval": 300,  # 5 minutes
        "max_degraded_time": 3600,   # 1 hour before escalation
        "fallback_strategies": [
            "switch_to_paper_trading",
            "use_cached_data",
            "disable_new_orders"
        ]
    }
    
    return degradation_config