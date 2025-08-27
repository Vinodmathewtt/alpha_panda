"""Event system specific exceptions."""

from core.utils.exceptions import EventError


class EventParsingError(EventError):
    """Raised when event parsing fails."""
    
    def __init__(self, message: str, event_data: str = None, original_error: Exception = None):
        super().__init__(message)
        self.event_data = event_data
        self.original_error = original_error


class EventValidationError(EventError):
    """Raised when event validation fails."""
    
    def __init__(self, message: str, validation_errors: list = None):
        super().__init__(message)
        self.validation_errors = validation_errors or []


class EventSerializationError(EventError):
    """Raised when event serialization fails."""
    pass


class EventDeserializationError(EventError):
    """Raised when event deserialization fails."""
    
    def __init__(self, message: str, json_data: str = None, field_errors: dict = None):
        super().__init__(message)
        self.json_data = json_data
        self.field_errors = field_errors or {}


class CircuitBreakerOpenError(EventError):
    """Raised when circuit breaker is open."""
    
    def __init__(self, message: str = "Circuit breaker is open"):
        super().__init__(message)


class EventTimeoutError(EventError):
    """Raised when event processing times out."""
    
    def __init__(self, message: str, timeout_seconds: float = None):
        super().__init__(message)
        self.timeout_seconds = timeout_seconds


class EventPublishError(EventError):
    """Raised when event publishing fails."""
    
    def __init__(self, message: str, event_id: str = None, subject: str = None):
        super().__init__(message)
        self.event_id = event_id
        self.subject = subject


class EventSubscriptionError(EventError):
    """Raised when event subscription fails."""
    
    def __init__(self, message: str, subject_pattern: str = None, handler_name: str = None):
        super().__init__(message)
        self.subject_pattern = subject_pattern
        self.handler_name = handler_name


class EventRegistrationError(EventError):
    """Raised when event type registration fails."""
    
    def __init__(self, message: str, event_type: str = None):
        super().__init__(message)
        self.event_type = event_type