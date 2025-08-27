from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging

logger = logging.getLogger(__name__)

class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Enhanced authentication middleware with session management"""
    
    def __init__(self, app, auth_service, excluded_paths=None):
        super().__init__(app)
        self.auth_service = auth_service
        self._validated = False
        self.excluded_paths = excluded_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/api/v1/auth/status",
            "/api/v1/system/info"
        ]
    
    async def _validate_auth_service(self):
        """Validate auth service is ready"""
        if self._validated:
            return
        
        try:
            # Test auth service functionality
            if hasattr(self.auth_service, 'get_status'):
                status = await self.auth_service.get_status()
                if not status:
                    raise RuntimeError("Auth service not ready")
            
            self._validated = True
            logger.info("✅ Auth service validation passed for middleware")
        except Exception as e:
            logger.error(f"❌ Auth service validation failed: {e}")
            raise RuntimeError(f"Auth middleware cannot initialize: {e}")
    
    async def dispatch(self, request: Request, call_next):
        # Validate auth service on first request
        if not self._validated:
            await self._validate_auth_service()
        
        # Skip authentication for excluded paths
        if any(request.url.path.startswith(path) for path in self.excluded_paths):
            return await call_next(request)
        
        # Check if monitoring endpoints should require auth
        if request.url.path.startswith("/api/v1/monitoring"):
            # Allow monitoring access without auth in development
            if hasattr(self.auth_service, 'settings') and getattr(self.auth_service.settings, 'environment', 'development') == 'development':
                return await call_next(request)
        
        # Require authentication for protected endpoints
        if not self.auth_service.is_authenticated():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        return await call_next(request)