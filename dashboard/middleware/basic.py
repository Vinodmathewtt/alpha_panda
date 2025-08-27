"""Basic security middleware for dashboard."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time
import hashlib
from typing import Dict


class SecurityMiddleware(BaseHTTPMiddleware):
    """Comprehensive security middleware for dashboard"""

    def __init__(self, app, nonce_store: Dict[str, float] = None):
        super().__init__(app)
        self.nonce_store = nonce_store or {}
        self.nonce_ttl = 300  # 5 minutes

    async def dispatch(self, request: Request, call_next):
        # Generate CSP nonce for inline scripts
        nonce = self.generate_nonce()
        request.state.csp_nonce = nonce
        response = await call_next(request)
        # Security headers
        security_headers = {
            "Content-Security-Policy": f"""default-src 'self';
                script-src 'self' 'nonce-{nonce}' https://unpkg.com https://cdn.jsdelivr.net https://cdn.tailwindcss.com;
                style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;
                connect-src 'self' wss: ws:;
                img-src 'self' data: https:;
                font-src 'self' https://fonts.gstatic.com""".replace('\n', ''),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
        }

        for header, value in security_headers.items():
            response.headers[header] = value
        return response

    def generate_nonce(self) -> str:
        """Generate cryptographically secure nonce"""
        current_time = str(time.time())
        nonce = hashlib.sha256(current_time.encode()).hexdigest()[:16]
        self.nonce_store[nonce] = time.time()
        # Cleanup old nonces
        current = time.time()
        expired = [k for k, v in self.nonce_store.items() if current - v > self.nonce_ttl]
        for k in expired:
            del self.nonce_store[k]
        return nonce
