#!/usr/bin/env python3
"""
Create portfolio and trading event tables for persistent paper trading state.
This script adds the new database tables required for portfolio persistence.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.database.models import Base, PortfolioSnapshot, TradingEvent
from core.logging import get_logger

logger = get_logger("create_portfolio_tables")


async def create_portfolio_tables():
    """Create portfolio and trading event tables"""
    settings = Settings()
    db_manager = DatabaseManager(settings.database.postgres_url)
    
    try:
        await db_manager.init()
        
        # Create tables using SQLAlchemy metadata
        async with db_manager._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("✅ Portfolio tables created successfully")
        
        # Log the new tables created
        logger.info("📊 New tables created:")
        logger.info("  - portfolio_snapshots: For persistent portfolio state storage")
        logger.info("  - trading_events: For complete audit trail of trading activities")
        
    except Exception as e:
        logger.error(f"❌ Failed to create portfolio tables: {e}")
        raise
    finally:
        await db_manager.shutdown()


async def main():
    """Main entry point"""
    logger.info("🚀 Creating portfolio and trading event tables...")
    
    try:
        await create_portfolio_tables()
        logger.info("✅ Portfolio tables setup completed")
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())