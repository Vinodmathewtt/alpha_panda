"""
Database migrations for instrument data tables.
"""

from sqlalchemy.ext.asyncio import AsyncEngine
from core.logging.logger import get_logger

logger = get_logger(__name__)
from ..models.instrument import Base


async def create_instrument_tables(engine: AsyncEngine) -> None:
    """
    Create instrument data tables in the database.
    
    Args:
        engine: Async SQLAlchemy engine
    """
    try:
        async with engine.begin() as conn:
            # Create all tables defined in the models
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Successfully created instrument data tables")
        
    except Exception as e:
        logger.error(f"Failed to create instrument data tables: {e}")
        raise


async def drop_instrument_tables(engine: AsyncEngine) -> None:
    """
    Drop instrument data tables from the database.
    
    Args:
        engine: Async SQLAlchemy engine
    """
    try:
        async with engine.begin() as conn:
            # Drop all tables defined in the models
            await conn.run_sync(Base.metadata.drop_all)
            
        logger.info("Successfully dropped instrument data tables")
        
    except Exception as e:
        logger.error(f"Failed to drop instrument data tables: {e}")
        raise


async def migrate_instrument_database(engine: AsyncEngine, force_recreate: bool = False) -> None:
    """
    Run instrument database migrations.
    
    Args:
        engine: Async SQLAlchemy engine
        force_recreate: If True, drop existing tables and recreate
    """
    try:
        if force_recreate:
            logger.warning("Force recreating instrument tables - all data will be lost!")
            await drop_instrument_tables(engine)
        
        await create_instrument_tables(engine)
        logger.info("Instrument database migration completed successfully")
        
    except Exception as e:
        logger.error(f"Instrument database migration failed: {e}")
        raise