"""
Application lifecycle management utilities
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any

from .application import AlphaPTApplication


@asynccontextmanager
async def lifespan_context():
    """
    Application lifespan context manager for use with FastAPI or other frameworks.
    
    Usage:
        async with lifespan_context() as app_state:
            # Application is running
            pass
        # Application is cleaned up
    """
    app = AlphaPTApplication()
    
    try:
        # Initialize application
        if not await app.initialize():
            raise RuntimeError("Application initialization failed")
            
        # Start application
        if not await app.start():
            raise RuntimeError("Application startup failed")
            
        yield app.app_state
        
    finally:
        await app.cleanup()


async def health_check() -> Dict[str, Any]:
    """
    Standalone health check function that can be used independently.
    
    Returns:
        Dict containing health status information
    """
    try:
        # For a quick health check, we can create a minimal app instance
        # or use existing global state if available
        app = AlphaPTApplication()
        return await app.health_check()
        
    except Exception as e:
        return {
            "status": "unhealthy", 
            "message": f"Health check failed: {str(e)}"
        }