"""API middleware for authentication, rate limiting, and request logging."""

import time
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import Request, Response, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse

from core.auth.auth_manager import AuthManager
from core.logging.logger import get_logger
from core.config.settings import settings

logger = get_logger(__name__)

# Rate limiting storage (in production, use Redis)
rate_limit_storage: Dict[str, Dict[str, Any]] = defaultdict(dict)

# Security scheme
security = HTTPBearer()


class RateLimitExceeded(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=429,
            detail="Rate limit exceeded. Too many requests."
        )


async def request_logging_middleware(request: Request, call_next):
    """Log all API requests."""
    start_time = time.time()
    
    # Log request
    logger.info(f"API Request: {request.method} {request.url.path}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    process_time = time.time() - start_time
    logger.info(
        f"API Response: {request.method} {request.url.path} "
        f"- Status: {response.status_code} - Time: {process_time:.3f}s"
    )
    
    # Add timing header
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    client_ip = request.client.host
    endpoint = f"{request.method}:{request.url.path}"
    
    # Get rate limit configuration
    max_requests = getattr(settings.api, 'rate_limit_requests', 100)
    window_seconds = getattr(settings.api, 'rate_limit_window', 60)
    
    current_time = time.time()
    window_start = current_time - window_seconds
    
    # Get or create rate limit data for this client
    client_data = rate_limit_storage[client_ip]
    endpoint_data = client_data.setdefault(endpoint, {
        'requests': [],
        'blocked_until': 0
    })
    
    # Check if client is currently blocked
    if current_time < endpoint_data['blocked_until']:
        raise RateLimitExceeded()
    
    # Clean old requests
    endpoint_data['requests'] = [
        req_time for req_time in endpoint_data['requests']
        if req_time > window_start
    ]
    
    # Check rate limit
    if len(endpoint_data['requests']) >= max_requests:
        # Block client for the remaining window time
        endpoint_data['blocked_until'] = current_time + window_seconds
        logger.warning(f"Rate limit exceeded for {client_ip} on {endpoint}")
        raise RateLimitExceeded()
    
    # Record this request
    endpoint_data['requests'].append(current_time)
    
    # Process request
    response = await call_next(request)
    
    # Add rate limit headers
    remaining = max_requests - len(endpoint_data['requests'])
    reset_time = window_start + window_seconds
    response.headers["X-RateLimit-Limit"] = str(max_requests)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(reset_time))
    
    return response


async def auth_middleware(request: Request, call_next):
    """Authentication middleware for protected endpoints."""
    # Skip auth for health checks and docs
    if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
        return await call_next(request)
    
    # Skip auth for public endpoints
    if request.url.path.startswith("/api/v1/health"):
        return await call_next(request)
    
    # Check for API key or JWT token
    api_key = request.headers.get("X-API-Key")
    auth_header = request.headers.get("Authorization")
    
    if api_key:
        # Validate API key
        if not await validate_api_key(api_key):
            raise HTTPException(status_code=401, detail="Invalid API key")
    elif auth_header and auth_header.startswith("Bearer "):
        # Validate JWT token
        token = auth_header[7:]  # Remove "Bearer " prefix
        if not await validate_jwt_token(token, request):
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    else:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    return await call_next(request)


async def validate_api_key(api_key: str) -> bool:
    """Validate API key."""
    try:
        # In production, validate against database or cache
        valid_keys = getattr(settings.api, 'api_keys', [])
        return api_key in valid_keys
    except Exception as e:
        logger.error(f"API key validation error: {e}")
        return False


async def validate_jwt_token(token: str, request: Request = None) -> bool:
    """Validate JWT token."""
    try:
        # Get auth manager from app state
        if request and hasattr(request.app.state, 'auth_manager'):
            auth_manager = request.app.state.auth_manager
            return await auth_manager.validate_token(token)
        else:
            logger.warning("Auth manager not available in app state")
            return False
    except Exception as e:
        logger.error(f"JWT token validation error: {e}")
        return False


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """Get current authenticated user."""
    try:
        token = credentials.credentials
        
        # For now, return a basic user info structure
        # This should be properly implemented when auth manager is available
        
        logger.warning("Auth manager integration needed for user info retrieval")
        raise HTTPException(status_code=401, detail="Authentication service needs configuration")
    except Exception as e:
        logger.error(f"Get current user error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


async def require_trading_permission(user: Dict[str, Any] = Depends(get_current_user)):
    """Require trading permission for user."""
    if not user.get("permissions", {}).get("trading", False):
        raise HTTPException(
            status_code=403,
            detail="Trading permission required"
        )
    return user


async def require_admin_permission(user: Dict[str, Any] = Depends(get_current_user)):
    """Require admin permission for user."""
    if not user.get("permissions", {}).get("admin", False):
        raise HTTPException(
            status_code=403,
            detail="Admin permission required"
        )
    return user


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add basic security headers to responses."""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Only add security headers in production
        if settings.environment.value == "production":
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            # Don't add HSTS for development flexibility
        
        return response