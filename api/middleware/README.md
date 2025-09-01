# API Middleware

## Overview

The API middleware layer provides cross-cutting concerns for the Alpha Panda FastAPI application, including authentication, error handling, rate limiting, and correlation tracking. All middleware follows FastAPI middleware patterns and integrates with the application's dependency injection system.

## Components

### `auth.py`
Authentication middleware for API endpoints:

- **JWT Authentication**: Token validation and user context extraction
- **Dependency Injection**: Integration with auth service dependency injection
- **Request Context**: Automatic user context injection for authenticated endpoints
- **Error Handling**: Proper error responses for authentication failures

### `request_ids.py`
HTTP request ID + correlation middleware:

- **X-Request-ID**: Generates a unique request ID per HTTP request
- **X-Correlation-ID**: Ensures/propagates correlation ID via correlation manager
- **Logging Integration**: Binds `request_id` and `correlation_id` into structured logs and access logs
- **Response Headers**: Adds `X-Request-ID` and `X-Correlation-ID` to responses for client visibility

### `error_handling.py`
Global error handling middleware:

- **Exception Handling**: Catches and formats application exceptions
- **Error Response**: Standardized error response format
- **Logging Integration**: Logs errors with proper context
- **Error Classification**: Different handling for different error types

### `rate_limiting.py`
API rate limiting middleware:

- **Request Rate Limiting**: Limits requests per client/endpoint
- **Redis Integration**: Uses Redis for distributed rate limiting
- **Configurable Limits**: Different rate limits per endpoint
- **Error Responses**: Proper HTTP 429 responses for rate limit exceeded

## Usage

### Middleware Registration
```python
from api.middleware.request_ids import RequestIdMiddleware
from api.middleware.error_handling import ErrorHandlingMiddleware
from api.middleware.auth import AuthenticationMiddleware
from api.middleware.rate_limiting import RateLimitingMiddleware

# Register middleware in FastAPI app (order matters)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(AuthenticationMiddleware)
app.add_middleware(RateLimitingMiddleware)
```

### Authentication Integration
```python
from api.middleware.auth import get_current_user
from fastapi import Depends

@app.get("/protected")
async def protected_endpoint(user: User = Depends(get_current_user)):
    return {"user_id": user.id, "message": "Protected resource"}
```

### Rate Limiting Configuration
```python
from api.middleware.rate_limiting import rate_limit

@app.get("/api/data")
@rate_limit(requests_per_minute=60)
async def get_data():
    return {"data": "response"}
```

## Architecture Patterns

- **Middleware Stack**: Proper ordering and execution of middleware layers
- **Dependency Injection**: Integration with FastAPI's dependency system
- **Context Propagation**: Request context propagation through middleware
- **Error Boundaries**: Clear error handling boundaries at middleware level
- **Configuration**: Configurable middleware behavior through settings

## Configuration

Middleware configuration through settings:

```python
class APISettings(BaseModel):
    auth_enabled: bool = True
    rate_limiting_enabled: bool = True
    correlation_tracking_enabled: bool = True
    max_requests_per_minute: int = 60
    jwt_secret_key: str = "your-secret-key"
```

## Dependencies

- **FastAPI**: Web framework and middleware system
- **Redis**: Rate limiting and session storage
- **JWT**: Token authentication and validation
- **core.logging**: Correlation tracking and structured logging
