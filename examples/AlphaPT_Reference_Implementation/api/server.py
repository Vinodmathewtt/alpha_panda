"""FastAPI server implementation for AlphaPT REST API."""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from core.config.settings import settings
from core.logging import get_api_logger
from monitoring import health_checker, metrics_collector
from .routes import register_routes
from .websocket import WebSocketManager
from .middleware import (
    auth_middleware,
    rate_limit_middleware,
    request_logging_middleware
)
from .error_handlers import (
    APIError,
    api_exception_handler,
    http_exception_handler,
    general_exception_handler
)

logger = get_api_logger("api_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    logger.info("🚀 Starting AlphaPT API server...")
    
    # Initialize components
    try:
        # Initialize WebSocket manager
        app.state.websocket_manager = WebSocketManager()
        await app.state.websocket_manager.initialize()
        
        # Start health monitoring
        await health_checker.start()
        
        # Start metrics collection
        await metrics_collector.start()
        
        logger.info("✅ AlphaPT API server started successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to start API server: {e}")
        raise
    
    finally:
        # Cleanup
        logger.info("🔄 Shutting down AlphaPT API server...")
        
        # Stop WebSocket manager
        if hasattr(app.state, 'websocket_manager'):
            await app.state.websocket_manager.stop()
        
        # Stop monitoring
        await health_checker.stop()
        await metrics_collector.stop()
        
        logger.info("✅ AlphaPT API server shutdown complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    
    app = FastAPI(
        title="AlphaPT API",
        description="High-Performance Algorithmic Trading Platform API",
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan
    )
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Add custom middleware
    app.middleware("http")(request_logging_middleware)
    app.middleware("http")(rate_limit_middleware)
    app.middleware("http")(auth_middleware)
    
    # Register routes
    register_routes(app)
    
    # Register WebSocket routes
    from .websocket_routes import create_websocket_routes
    for route in create_websocket_routes():
        app.router.routes.append(route)
    
    # Add centralized exception handlers
    app.add_exception_handler(APIError, api_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Basic health check endpoint."""
        try:
            health_status = await health_checker.get_health_status()
            status_code = 200 if health_status["overall_status"] == "healthy" else 503
            
            return JSONResponse(
                status_code=status_code,
                content=health_status
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "overall_status": "unhealthy",
                    "error": str(e)
                }
            )
    
    return app


async def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
    log_level: str = "info"
):
    """Run the FastAPI server with uvicorn."""
    try:
        logger.info(f"Starting AlphaPT API server on {host}:{port}")
        
        config = uvicorn.Config(
            app="api.server:create_app",
            factory=True,
            host=host,
            port=port,
            reload=reload,
            log_level=log_level,
            access_log=True,
            server_header=False,
            date_header=False
        )
        
        server = uvicorn.Server(config)
        await server.serve()
        
    except Exception as e:
        logger.error(f"Failed to run API server: {e}")
        raise


def main():
    """Main entry point for running the API server."""
    import asyncio
    
    # Get configuration from settings
    host = getattr(settings.api, 'host', '0.0.0.0')
    port = getattr(settings.api, 'port', 8000)
    reload = settings.debug
    log_level = "debug" if settings.debug else "info"
    
    asyncio.run(run_server(
        host=host,
        port=port,
        reload=reload,
        log_level=log_level
    ))


if __name__ == "__main__":
    main()