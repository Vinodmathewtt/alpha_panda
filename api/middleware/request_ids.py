from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from fastapi import Request
from uuid import uuid4

from core.logging.correlation import CorrelationIdManager


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request_id and ensure correlation_id for every HTTP request.

    - Sets request.state.request_id
    - Ensures a correlation_id exists and binds request_id into correlation_context
    - Adds X-Request-ID and X-Correlation-ID headers to the response
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid4())
        request.state.request_id = request_id

        # Ensure correlation and bind request context
        corr_id = CorrelationIdManager.ensure_correlation_id()
        CorrelationIdManager.set_correlation_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        response = await call_next(request)
        # Expose IDs to clients
        response.headers["X-Request-ID"] = request_id
        if corr_id:
            response.headers["X-Correlation-ID"] = corr_id
        return response

