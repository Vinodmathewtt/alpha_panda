"""Centralized error handling for API routers."""

from datetime import datetime
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from core.logging.logger import get_logger

logger = get_logger(__name__)


class APIError(Exception):
    """Base API error class."""
    def __init__(self, message: str, status_code: int = 500, details: dict = None):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class TradingError(APIError):
    """Trading-specific errors."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, 400, details)


class AuthenticationError(APIError):
    """Authentication errors."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, 401)


class AuthorizationError(APIError):
    """Authorization errors."""
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, 403)


class ValidationError(APIError):
    """Input validation errors."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, 422, details)


class ResourceNotFoundError(APIError):
    """Resource not found errors."""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, 404)


class ServiceUnavailableError(APIError):
    """Service unavailable errors."""
    def __init__(self, message: str = "Service temporarily unavailable"):
        super().__init__(message, 503)


async def api_exception_handler(request: Request, exc: APIError):
    """Handle custom API exceptions."""
    logger.error(f"API Error: {exc.message}", extra={
        "status_code": exc.status_code,
        "details": exc.details,
        "path": request.url.path,
        "method": request.method,
        "client_ip": request.client.host if request.client else "unknown"
    })
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "details": exc.details,
            "path": request.url.path,
            "timestamp": datetime.now().isoformat()
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions with consistent format."""
    logger.warning(f"HTTP Exception: {exc.detail}", extra={
        "status_code": exc.status_code,
        "path": request.url.path,
        "method": request.method,
        "client_ip": request.client.host if request.client else "unknown"
    })
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "details": {},
            "path": request.url.path,
            "timestamp": datetime.now().isoformat()
        }
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {str(exc)}", extra={
        "path": request.url.path,
        "method": request.method,
        "client_ip": request.client.host if request.client else "unknown",
        "exception_type": type(exc).__name__
    }, exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "details": {"exception_type": type(exc).__name__},
            "path": request.url.path,
            "timestamp": datetime.now().isoformat()
        }
    )


def create_error_response(message: str, status_code: int = 500, details: dict = None):
    """Create standardized error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": message,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        }
    )


def validate_required_fields(data: dict, required_fields: list) -> None:
    """Validate that required fields are present in request data."""
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    
    if missing_fields:
        raise ValidationError(
            f"Missing required fields: {', '.join(missing_fields)}",
            {"missing_fields": missing_fields}
        )


def validate_positive_number(value: any, field_name: str) -> None:
    """Validate that a value is a positive number."""
    try:
        num_value = float(value)
        if num_value <= 0:
            raise ValidationError(f"{field_name} must be a positive number")
    except (ValueError, TypeError):
        raise ValidationError(f"{field_name} must be a valid number")


def validate_instrument_token(token: any) -> int:
    """Validate and convert instrument token."""
    try:
        token_int = int(token)
        if token_int <= 0:
            raise ValidationError("Instrument token must be a positive integer")
        return token_int
    except (ValueError, TypeError):
        raise ValidationError("Invalid instrument token format")