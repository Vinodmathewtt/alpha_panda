"""
Correlation ID middleware for FastAPI requests.
Automatically generates and propagates correlation IDs for request tracing.
"""

import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.logging.correlation import (
    CorrelationIdManager,
    create_correlation_context
)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware to handle correlation ID lifecycle for HTTP requests"""
    
    CORRELATION_ID_HEADER = "X-Correlation-ID"
    
    def __init__(self, app, header_name: str = None):
        """
        Initialize correlation middleware.
        
        Args:
            app: FastAPI application instance
            header_name: Optional custom header name for correlation ID
        """
        super().__init__(app)
        self.header_name = header_name or self.CORRELATION_ID_HEADER
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with correlation ID handling.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain
            
        Returns:
            HTTP response with correlation ID header
        """
        # Extract correlation ID from request headers or generate new one
        correlation_id = request.headers.get(self.header_name)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Set correlation ID in context
        CorrelationIdManager.set_correlation_id(correlation_id)
        
        # Create correlation context with request information
        create_correlation_context(
            service="alpha_panda_api",
            operation=f"{request.method} {request.url.path}",
            user_id=getattr(request.state, 'user_id', None),
            client_ip=request.client.host if request.client else "unknown",
            method=request.method,
            path=str(request.url.path),
            query_params=str(request.query_params) if request.query_params else None
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Add correlation ID to response headers
            response.headers[self.header_name] = correlation_id
            
            return response
            
        except Exception as e:
            # Even if request fails, we should return correlation ID
            from fastapi.responses import JSONResponse
            response = JSONResponse(
                status_code=500,
                content={"error": "Internal server error", "correlation_id": correlation_id}
            )
            response.headers[self.header_name] = correlation_id
            raise
        
        finally:
            # Clean up correlation context after request
            CorrelationIdManager.clear_correlation()