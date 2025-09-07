from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from core.logging import get_api_logger_safe
from datetime import datetime

logger = get_api_logger_safe("api.middleware.error_handling")

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Global error handling middleware"""
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except HTTPException as e:
            # Let FastAPI handle HTTP exceptions normally
            raise e
        except Exception as e:
            # Log the error
            logger.error(
                "Unhandled API exception",
                path=request.url.path,
                method=request.method,
                error=str(e),
                exc_info=True
            )
            
            # Return a structured error response
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "message": "An unexpected error occurred",
                    "timestamp": datetime.utcnow().isoformat(),
                    "path": request.url.path
                }
            )
