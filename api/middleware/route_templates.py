from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from core.logging.correlation import CorrelationIdManager


class RouteTemplateMiddleware(BaseHTTPMiddleware):
    """Capture FastAPI route template and add it to correlation context for logging."""

    async def dispatch(self, request: Request, call_next):
        try:
            route = request.scope.get("route")
            template = getattr(route, "path", None)
            if template:
                CorrelationIdManager.set_correlation_context(route_template=template)
        except Exception:
            pass
        response: Response = await call_next(request)
        return response

