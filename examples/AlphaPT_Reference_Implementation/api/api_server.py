#!/usr/bin/env python3
"""
API Server Entry Point for AlphaPT.

This script starts the API server independently or as part of the main application.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config.settings import get_settings
from core.logging.logger import configure_logging, get_logger
from .server import run_server


async def main():
    """Main entry point for API server."""
    try:
        # Load settings
        settings = get_settings()
        
        # Configure logging
        configure_logging(settings)
        logger = get_logger(__name__)
        
        # Enable API server
        settings.api.enable_api_server = True
        
        logger.info("🌐 Starting AlphaPT API Server...")
        logger.info(f"Host: {settings.api.host}")
        logger.info(f"Port: {settings.api.port}")
        logger.info(f"Environment: {settings.environment}")
        logger.info(f"Debug: {settings.debug}")
        
        # Run API server
        await run_server(
            host=settings.api.host,
            port=settings.api.port,
            reload=settings.api.reload,
            log_level="debug" if settings.debug else "info"
        )
        
    except KeyboardInterrupt:
        print("\n🛑 API server stopped by user")
    except Exception as e:
        print(f"❌ Error starting API server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Set environment variable to enable API
    os.environ["ENABLE_API_SERVER"] = "true"
    
    asyncio.run(main())