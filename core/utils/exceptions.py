# Structured exception hierarchy for Alpha Panda trading system

from typing import Dict, Any, Optional
from datetime import datetime, timezone


class AlphaPandaException(Exception):
    """Base exception for all Alpha Panda specific errors"""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, 
                 correlation_id: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.correlation_id = correlation_id
        self.timestamp = datetime.now(timezone.utc)


class TransientError(AlphaPandaException):
    """Base class for transient errors that should be retried with exponential backoff"""
    
    def __init__(self, message: str, retry_count: int = 0, max_retries: int = 5,
                 details: Optional[Dict[str, Any]] = None, correlation_id: Optional[str] = None):
        super().__init__(message, details, correlation_id)
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.retryable = retry_count < max_retries


class PermanentError(AlphaPandaException):
    """Base class for permanent errors that should go to DLQ immediately"""
    pass


# Authentication and Authorization Errors
class AuthenticationError(TransientError):
    """Authentication failures - may recover with token refresh"""
    
    def __init__(self, message: str, auth_provider: str, **kwargs):
        super().__init__(message, **kwargs)
        self.auth_provider = auth_provider


class AuthorizationError(PermanentError):
    """Authorization failures - user lacks required permissions"""
    pass


# Broker Integration Errors
class BrokerError(TransientError):
    """Base class for broker integration errors"""
    
    def __init__(self, message: str, broker: str, **kwargs):
        super().__init__(message, **kwargs)
        self.broker = broker


class BrokerConnectionError(BrokerError):
    """Broker connection failures - network or service issues"""
    pass


class BrokerAPIError(BrokerError):
    """Broker API errors - rate limits, temporary service issues"""
    
    def __init__(self, message: str, broker: str, api_error_code: Optional[str] = None,
                 api_response: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(message, broker, **kwargs)
        self.api_error_code = api_error_code
        self.api_response = api_response or {}


class InsufficientFundsError(PermanentError):
    """Insufficient funds for trade execution"""
    
    def __init__(self, message: str, required_amount: float, available_amount: float,
                 account_id: str, **kwargs):
        super().__init__(message, **kwargs)
        self.required_amount = required_amount
        self.available_amount = available_amount
        self.account_id = account_id


# Market Data Errors
class MarketDataError(TransientError):
    """Market data feed errors"""
    pass


class MarketDataConnectionError(MarketDataError):
    """Market data connection failures"""
    pass


class StaleDataError(TransientError):
    """Market data is too old for trading decisions"""
    
    def __init__(self, message: str, data_age_seconds: float, max_age_seconds: float,
                 instrument_token: int, **kwargs):
        super().__init__(message, **kwargs)
        self.data_age_seconds = data_age_seconds
        self.max_age_seconds = max_age_seconds
        self.instrument_token = instrument_token


# Risk Management Errors
class RiskValidationError(PermanentError):
    """Risk rule violations - should not be retried"""
    
    def __init__(self, message: str, rule_violations: list, signal_data: Dict[str, Any],
                 **kwargs):
        super().__init__(message, **kwargs)
        self.rule_violations = rule_violations
        self.signal_data = signal_data


class PositionLimitError(RiskValidationError):
    """Position size or exposure limits exceeded"""
    
    def __init__(self, message: str, current_position: float, position_limit: float,
                 instrument_token: int, **kwargs):
        super().__init__(message, [], {}, **kwargs)
        self.current_position = current_position
        self.position_limit = position_limit
        self.instrument_token = instrument_token


# Strategy Execution Errors
class StrategyError(AlphaPandaException):
    """Base class for strategy execution errors"""
    
    def __init__(self, message: str, strategy_id: str, **kwargs):
        super().__init__(message, **kwargs)
        self.strategy_id = strategy_id


class StrategyConfigurationError(PermanentError):
    """Strategy configuration errors - invalid parameters"""
    pass


class StrategyExecutionError(TransientError):
    """Strategy execution errors - may recover on retry"""
    pass


# Infrastructure Errors
class InfrastructureError(TransientError):
    """Base class for infrastructure failures"""
    pass


class DatabaseError(InfrastructureError):
    """Database connection or query failures"""
    
    def __init__(self, message: str, operation: str, table: Optional[str] = None,
                 **kwargs):
        super().__init__(message, **kwargs)
        self.operation = operation
        self.table = table


class RedisError(InfrastructureError):
    """Redis connection or operation failures"""
    
    def __init__(self, message: str, operation: str, key: Optional[str] = None,
                 **kwargs):
        super().__init__(message, **kwargs)
        self.operation = operation
        self.key = key


class StreamingError(InfrastructureError):
    """Event streaming infrastructure errors"""
    
    def __init__(self, message: str, topic: Optional[str] = None, 
                 operation: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.topic = topic
        self.operation = operation


class MessageDeserializationError(PermanentError):
    """Message format or deserialization errors - cannot be retried"""
    
    def __init__(self, message: str, raw_message: str, topic: str, **kwargs):
        super().__init__(message, **kwargs)
        self.raw_message = raw_message
        self.topic = topic


# Configuration Errors
class ConfigurationError(PermanentError):
    """Configuration validation errors"""
    
    def __init__(self, message: str, config_field: str, config_value: Any,
                 **kwargs):
        super().__init__(message, **kwargs)
        self.config_field = config_field
        self.config_value = config_value


# Validation Errors
class ValidationError(PermanentError):
    """Data validation errors"""
    
    def __init__(self, message: str, field: str, value: Any, 
                 expected_type: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value
        self.expected_type = expected_type


# Portfolio Management Errors
class PortfolioError(AlphaPandaException):
    """Base class for portfolio management errors"""
    
    def __init__(self, message: str, portfolio_id: str, **kwargs):
        super().__init__(message, **kwargs)
        self.portfolio_id = portfolio_id


class PortfolioStateError(TransientError):
    """Portfolio state synchronization errors"""
    pass


class InstrumentNotFoundError(PermanentError):
    """Instrument lookup failures"""
    
    def __init__(self, message: str, instrument_token: int, **kwargs):
        super().__init__(message, **kwargs)
        self.instrument_token = instrument_token


# Order Management Errors
class OrderError(AlphaPandaException):
    """Base class for order management errors"""
    
    def __init__(self, message: str, order_id: Optional[str] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.order_id = order_id


class OrderRejectionError(PermanentError):
    """Order rejected by broker - should not be retried"""
    
    def __init__(self, message: str, rejection_reason: str, order_data: Dict[str, Any],
                 **kwargs):
        super().__init__(message, **kwargs)
        self.rejection_reason = rejection_reason
        self.order_data = order_data


class OrderTimeoutError(TransientError):
    """Order processing timeout - may recover on retry"""
    pass


def is_retryable_error(error: Exception) -> bool:
    """
    Determine if an error should be retried
    
    Returns:
        True if error is transient and retryable, False otherwise
    """
    if isinstance(error, TransientError):
        return error.retryable
    return False


def get_retry_delay(error: TransientError, base_delay: float = 1.0) -> float:
    """
    Calculate exponential backoff delay for retrying transient errors
    
    Args:
        error: The transient error to retry
        base_delay: Base delay in seconds
        
    Returns:
        Delay in seconds before retry
    """
    if not isinstance(error, TransientError):
        return 0.0
    
    # Exponential backoff: base_delay * (2 ^ retry_count)
    return base_delay * (2 ** error.retry_count)


def create_error_context(error: Exception, operation: str, 
                        additional_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create structured error context for logging and monitoring
    
    Args:
        error: The exception that occurred
        operation: The operation that failed
        additional_context: Additional context information
        
    Returns:
        Structured error context dictionary
    """
    context = {
        "error_type": type(error).__name__,
        "error_message": str(error),
        "operation": operation,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "retryable": is_retryable_error(error)
    }
    
    # Add specific error attributes if available
    if isinstance(error, AlphaPandaException):
        if error.correlation_id:
            context["correlation_id"] = error.correlation_id
        if error.details:
            context["error_details"] = error.details
            
        # Add specific error type information
        if isinstance(error, TransientError):
            context["retry_count"] = error.retry_count
            context["max_retries"] = error.max_retries
            context["next_retry_delay"] = get_retry_delay(error)
            
        if isinstance(error, BrokerError):
            context["broker"] = error.broker
            
        if isinstance(error, StrategyError):
            context["strategy_id"] = error.strategy_id
            
        if isinstance(error, PortfolioError):
            context["portfolio_id"] = error.portfolio_id
    
    # Merge additional context
    if additional_context:
        context.update(additional_context)
    
    return context