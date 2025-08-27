"""API server configuration."""

from typing import List, Optional

from pydantic import BaseModel, Field


class APIConfig(BaseModel):
    """API server configuration."""

    # Server settings
    host: str = Field(default="0.0.0.0", description="API server host")
    port: int = Field(default=8000, description="API server port")
    reload: bool = Field(default=False, description="Enable auto-reload in development")

    # API settings
    prefix: str = Field(default="/api/v1", description="API URL prefix")
    title: str = Field(default="AlphaPT API", description="API title")
    description: str = Field(default="High-Performance Algorithmic Trading Platform API", description="API description")
    version: str = Field(default="1.0.0", description="API version")

    # Documentation
    docs_url: Optional[str] = Field(default="/docs", description="Swagger UI URL")
    redoc_url: Optional[str] = Field(default="/redoc", description="ReDoc URL")
    openapi_url: Optional[str] = Field(default="/openapi.json", description="OpenAPI schema URL")

    # Security
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000"],
        description="Allowed CORS origins",
    )
    cors_methods: List[str] = Field(default=["GET", "POST", "PUT", "DELETE"], description="Allowed CORS methods")
    cors_headers: List[str] = Field(default=["*"], description="Allowed CORS headers")

    # Rate limiting
    rate_limit_requests: int = Field(default=100, description="Rate limit requests per window")
    rate_limit_window: int = Field(default=60, description="Rate limit window in seconds")

    # API keys for authentication
    api_keys: List[str] = Field(default=[], description="Valid API keys")

    # WebSocket settings
    websocket_heartbeat_interval: int = Field(default=30, description="WebSocket heartbeat interval in seconds")
    websocket_connection_timeout: int = Field(default=60, description="WebSocket connection timeout in seconds")
    websocket_max_connections: int = Field(default=1000, description="Maximum WebSocket connections")

    # Response settings
    response_timeout: int = Field(default=30, description="API response timeout in seconds")
    max_request_size: int = Field(default=10 * 1024 * 1024, description="Maximum request size in bytes (10MB)")

    # Feature flags
    enable_api_server: bool = Field(default=False, description="Enable API server")
    enable_websockets: bool = Field(default=True, description="Enable WebSocket support")
    enable_swagger_ui: bool = Field(default=True, description="Enable Swagger UI in development")

    def get_cors_config(self) -> dict:
        """Get CORS configuration for FastAPI."""
        return {
            "allow_origins": self.cors_origins,
            "allow_methods": self.cors_methods,
            "allow_headers": self.cors_headers,
            "allow_credentials": True,
        }

    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.reload and self.docs_url is None
