from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
import time
import redis.asyncio as redis
from typing import Optional
from core.logging import get_api_logger_safe

class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Production-ready Redis-backed rate limiting middleware"""
    
    def __init__(self, app, redis_client: Optional[redis.Redis] = None, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.redis_client = redis_client
        self.calls = calls
        self.period = period
        self.logger = get_api_logger_safe("rate_limiting")
        
        # Fallback to in-memory if Redis unavailable (development mode)
        self.use_redis = redis_client is not None
        if not self.use_redis:
            from collections import defaultdict, deque
            self.clients = defaultdict(deque)
            self.logger.warning("Redis not available, using in-memory rate limiting (development only)")
    
    async def dispatch(self, request: Request, call_next):
        # Get client IP - handle proxy headers safely
        client_ip = self._get_client_ip(request)
        
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/api/v1/monitoring/health"]:
            return await call_next(request)
        
        try:
            if self.use_redis:
                allowed = await self._check_redis_rate_limit(client_ip)
            else:
                allowed = await self._check_memory_rate_limit(client_ip)
            
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded: {self.calls} requests per {self.period} seconds",
                    headers={"Retry-After": str(self.period)}
                )
            
        except HTTPException:
            raise
        except Exception as e:
            # Fail open - allow request if rate limiting fails
            self.logger.error(f"Rate limiting error: {e}, allowing request")
        
        return await call_next(request)
    
    def _get_client_ip(self, request: Request) -> str:
        """Safely extract client IP, handling proxy headers"""
        # Check for X-Forwarded-For (most common proxy header)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain (original client)
            return forwarded_for.split(",")[0].strip()
        
        # Check for X-Real-IP (Nginx)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Fallback to request client
        return request.client.host if request.client else "unknown"
    
    async def _check_redis_rate_limit(self, client_ip: str) -> bool:
        """Redis-backed sliding window rate limiting"""
        try:
            key = f"rate_limit:{client_ip}"
            now = time.time()
            
            # Use Redis pipeline for atomic operations
            async with self.redis_client.pipeline() as pipe:
                # Remove expired entries
                pipe.zremrangebyscore(key, 0, now - self.period)
                # Add current request
                pipe.zadd(key, {str(now): now})
                # Set expiration
                pipe.expire(key, self.period + 1)  # Slight buffer
                # Count current requests
                pipe.zcard(key)
                
                results = await pipe.execute()
                request_count = results[3]
                
                return request_count <= self.calls
                
        except Exception as e:
            self.logger.error(f"Redis rate limiting error: {e}")
            # Fail open on Redis errors
            return True
    
    async def _check_memory_rate_limit(self, client_ip: str) -> bool:
        """Fallback in-memory rate limiting"""
        now = time.time()
        client_requests = self.clients[client_ip]
        
        # Remove old requests outside the time window
        while client_requests and client_requests[0] <= now - self.period:
            client_requests.popleft()
        
        # Check if client exceeds rate limit
        if len(client_requests) >= self.calls:
            return False
        
        # Record the current request
        client_requests.append(now)
        return True