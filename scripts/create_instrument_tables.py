#!/usr/bin/env python3
"""
Script to create instrument data tables in the database.
"""

import asyncio
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from services.instrument_data.instrument import Instrument, InstrumentRegistry


async def create_instrument_tables():
    """Create instrument data tables in the database."""
    print("🔧 Creating instrument data tables...")
    
    # Initialize settings and database
    settings = Settings()
    db_manager = DatabaseManager(settings.database.postgres_url)
    
    try:
        # Initialize database and create tables
        await db_manager.init()
        print("✅ Instrument data tables created successfully!")
        
    except Exception as e:
        print(f"❌ Failed to create instrument tables: {e}")
        raise
    finally:
        await db_manager.shutdown()


if __name__ == "__main__":
    asyncio.run(create_instrument_tables())