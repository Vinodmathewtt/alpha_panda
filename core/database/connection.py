# PostgreSQL connection and models
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from contextlib import asynccontextmanager
from typing import AsyncContextManager

logger = logging.getLogger(__name__)

# The base class for all SQLAlchemy models
Base = declarative_base()


class DatabaseManager:
    """Manages the connection to the PostgreSQL database"""

    def __init__(self, db_url: str, environment: str = "development", schema_management: str = "auto"):
        # FIXED: Added connection pool configuration for production
        self._engine = create_async_engine(
            db_url, 
            echo=False,
            pool_pre_ping=True,  # Test connections before use
            pool_size=20,        # Base pool size
            max_overflow=30,     # Additional connections beyond pool_size
            pool_recycle=3600    # Recycle connections after 1 hour
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
        self._environment = environment
        self._schema_management = schema_management
        self.logger = logging.getLogger(__name__)

    async def init(self, environment: str = None, schema_management: str = None):
        """Initialize database with environment-specific approach"""
        # Use instance variables if not provided
        env = environment or self._environment
        schema_mgmt = schema_management or self._schema_management
        
        if env in ["production", "staging"] or schema_mgmt == "migrations_only":
            # Production: Use migrations only
            await self._verify_migrations_current()
            logger.info("Database ready - using migrations for schema management")
        elif schema_mgmt == "create_all":
            # Force create_all mode
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database initialized with create_all (forced mode)")
        else:
            # Development/auto: Use create_all for convenience
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database initialized with create_all (development mode)")
    
    async def _verify_migrations_current(self):
        """Verify that all migrations have been applied"""
        try:
            async with self.get_session() as session:
                try:
                    # Check if alembic_version table exists
                    result = await session.execute(
                        text("SELECT version_num FROM alembic_version")
                    )
                    current_version = result.scalar()
                    
                    if current_version is None:
                        raise Exception(
                            "No migration version found in database. "
                            "Run 'alembic upgrade head' to initialize schema."
                        )
                    
                    logger.info(f"Database schema version: {current_version}")
                    
                except Exception as db_error:
                    if "alembic_version" in str(db_error):
                        raise Exception(
                            "Database schema not initialized. "
                            "Run 'alembic upgrade head' to create schema."
                        )
                    else:
                        raise Exception(f"Migration verification failed: {db_error}")
                        
        except Exception as e:
            logger.error(f"Migration verification failed: {e}")
            raise Exception(f"Production database not ready: {e}")

    async def verify_connection(self) -> bool:
        """Verify database connection is ready"""
        try:
            async with self.get_session() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            self.logger.error(f"Database connection verification failed: {e}")
            return False
    
    async def wait_for_ready(self, timeout: int = 30, check_interval: float = 1.0):
        """Wait for database to be ready with timeout"""
        import asyncio
        
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if await self.verify_connection():
                self.logger.info("✅ Database connection verified")
                return True
            
            self.logger.info("Database not ready, waiting...")
            await asyncio.sleep(check_interval)
        
        raise RuntimeError(f"Database not ready after {timeout} seconds")

    async def shutdown(self):
        """Closes the database connection pool"""
        await self._engine.dispose()
        logger.info("Database connection pool closed.")

    @asynccontextmanager
    async def get_session(self) -> AsyncSession:
        """Provides a new database session context manager WITHOUT auto-commit.
        
        FIXED: Removed auto-commit pattern. Services are now responsible for transaction boundaries.
        This follows the Unit of Work pattern where the service layer manages commits.
        """
        async with self._session_factory() as session:
            try:
                yield session
                # CRITICAL FIX: Removed automatic commit - services handle this
            except Exception:
                await session.rollback()
                raise
    
    def get_postgres_session(self):
        """Alias for get_session for compatibility"""
        return self.get_session()
    
    async def close(self):
        """Alias for shutdown for compatibility"""
        await self.shutdown()