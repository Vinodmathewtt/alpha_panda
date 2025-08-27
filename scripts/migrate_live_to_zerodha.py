"""
Migration script to rename 'live' to 'zerodha' in database schema
"""
import asyncio
from sqlalchemy import text
from core.database.connection import DatabaseManager
from core.config.settings import Settings


async def migrate_terminology():
    """Migrate live_trading_enabled to zerodha_trading_enabled"""
    settings = Settings()
    db_manager = DatabaseManager(settings.database.postgres_url)
    await db_manager.init()
    
    async with db_manager.get_session() as session:
        # Add new column
        await session.execute(text("""
            ALTER TABLE strategy_configurations 
            ADD COLUMN IF NOT EXISTS zerodha_trading_enabled BOOLEAN DEFAULT FALSE NOT NULL;
        """))
        
        # Copy data from old column
        await session.execute(text("""
            UPDATE strategy_configurations 
            SET zerodha_trading_enabled = live_trading_enabled;
        """))
        
        # Remove old column (do this carefully in production)
        # await session.execute(text("ALTER TABLE strategy_configurations DROP COLUMN live_trading_enabled;"))
        
        await session.commit()
    
    print("✅ Migration completed: live -> zerodha")


if __name__ == "__main__":
    asyncio.run(migrate_terminology())