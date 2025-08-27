"""Performance metrics middleware for dashboard."""

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import time
from collections import defaultdict
from typing import Dict, DefaultDict


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket rate limiting for dashboard endpoints"""

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_second = requests_per_minute / 60
        self.buckets: DefaultDict[str, Dict] = defaultdict(lambda: {
            'tokens': self.requests_per_minute,
            'last_update': time.time()
        })

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        user_id = getattr(request.state, 'user_id', None)
        key = f"{client_ip}:{user_id}" if user_id else client_ip

        if not self.allow_request(key):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later."
            )

        return await call_next(request)

    def allow_request(self, key: str) -> bool:
        """Token bucket algorithm implementation"""
        bucket = self.buckets[key]
        now = time.time()
        elapsed = now - bucket['last_update']

        # Add tokens based on elapsed time
        bucket['tokens'] = min(
            self.requests_per_minute,
            bucket['tokens'] + elapsed * self.requests_per_second
        )
        bucket['last_update'] = now

        if bucket['tokens'] >= 1:
            bucket['tokens'] -= 1
            return True
        return False


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Performance monitoring middleware"""

    def __init__(self, app):
        super().__init__(app)
        self.metrics = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        # Track request time
        duration = time.time() - start_time
        endpoint = f"{request.method} {request.url.path}"
        self.metrics[f"{endpoint}_response_time"].append(duration)

        # Add performance header
        response.headers["X-Response-Time"] = f"{duration:.3f}s"

        # Alert if response time > 2 seconds
        if duration > 2.0:
            # In a real implementation, this would send an alert
            print(f"ALERT: Slow response on {endpoint}: {duration:.3f}s")

        return response
