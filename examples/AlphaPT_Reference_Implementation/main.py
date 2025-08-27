#!/usr/bin/env python3
"""
AlphaPT - Main Application Entry Point

A production-ready algorithmic trading system with event-driven architecture,
featuring comprehensive monitoring and multi-database support.

This is the main entry point for containerization and cloud deployment.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import the application class from the app module
from app.application import AlphaPTApplication


async def main_async():
    """Async main function"""
    app = AlphaPTApplication()
    
    # Display startup banner
    app.display_startup_banner()
    
    try:
        # Initialize
        if not await app.initialize():
            print("❌ Application initialization failed")
            sys.exit(1)
            
        # Start
        if not await app.start():
            print("❌ Application startup failed")
            sys.exit(1)
            
        # Run
        await app.run()
        
    except KeyboardInterrupt:
        print("\n⚠️ Application interrupted by user")
    except Exception as e:
        print(f"❌ Application error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await app.stop()


def main():
    """Main entry point"""
    try:
        # Check Python version
        if sys.version_info < (3, 11):
            print("ERROR: Python 3.11 or higher is required")
            sys.exit(1)
            
        # Activate virtual environment reminder
        if not os.environ.get('VIRTUAL_ENV'):
            print("⚠️ WARNING: Virtual environment not detected")
            print("💡 Please run: source venv/bin/activate")
            
        # Run the application
        asyncio.run(main_async())
        
    except KeyboardInterrupt:
        print("\n👋 Application stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Application failed: {e}")
        sys.exit(1)
    finally:
        print("\n👋 AlphaPT shutdown complete")


if __name__ == "__main__":
    main()