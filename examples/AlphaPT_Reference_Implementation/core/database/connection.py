"""Database connection management."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Optional

import asyncpg
import clickhouse_connect
import redis.asyncio as redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config.settings import Settings
from core.utils.error_handler import (
    ErrorCategory,
    ErrorSeverity,
    create_error_context,
    with_error_handling,
    with_retry,
)
from core.utils.exceptions import ConnectionError, DatabaseError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections for PostgreSQL, ClickHouse, and Redis."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.postgres_engine = None
        self.postgres_session_factory = None
        self.clickhouse_client = None
        self.redis_client = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize all database connections."""
        if self._initialized:
            return

        try:
            await self._initialize_postgres()
            await self._initialize_clickhouse()
            await self._initialize_redis()
            self._initialized = True
            logger.info("Database connections initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database connections: {e}")
            await self.close()
            raise DatabaseError(f"Database initialization failed: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _initialize_postgres(self) -> None:
        """Initialize PostgreSQL connection."""
        try:
            db_config = self.settings.database
            self.postgres_engine = create_async_engine(
                db_config.postgres_async_url,
                pool_size=db_config.postgres_pool_size,
                max_overflow=db_config.postgres_max_overflow,
                pool_timeout=db_config.postgres_pool_timeout,
                pool_pre_ping=db_config.postgres_pool_pre_ping,
                pool_recycle=db_config.postgres_pool_recycle,
                echo=False,  # Disable SQLAlchemy query logging to reduce verbosity
                future=True,
                # Performance optimizations
                connect_args={
                    "command_timeout": 10,
                    "server_settings": {
                        "jit": "off",  # Disable JIT for faster connections
                        "application_name": "alphapt",
                    },
                },
            )

            self.postgres_session_factory = async_sessionmaker(
                self.postgres_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # Test connection
            async with self.postgres_engine.begin() as conn:
                await conn.execute(text("SELECT 1"))

            logger.info("PostgreSQL connection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL: {e}")
            raise ConnectionError(f"PostgreSQL connection failed: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _initialize_clickhouse(self) -> None:
        """Initialize ClickHouse connection."""
        try:
            db_config = self.settings.database
            connection_params = db_config.get_clickhouse_connection_params()
            self.clickhouse_client = clickhouse_connect.get_client(**connection_params)

            # Test connection
            result = self.clickhouse_client.query("SELECT 1")
            if not result.result_rows:
                raise ConnectionError("ClickHouse connection test failed")

            logger.info("ClickHouse connection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize ClickHouse: {e}")
            raise ConnectionError(f"ClickHouse connection failed: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _initialize_redis(self) -> None:
        """Initialize Redis connection."""
        try:
            self.redis_client = redis.from_url(
                self.settings.redis_url,
                db=self.settings.redis_db,
                password=self.settings.redis_password,
                max_connections=self.settings.redis_max_connections,
                decode_responses=True,
            )

            # Test connection
            await self.redis_client.ping()

            logger.info("Redis connection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Redis: {e}")
            raise ConnectionError(f"Redis connection failed: {e}")

    async def close(self) -> None:
        """Close all database connections."""
        try:
            # Flush any pending batch data before closing
            await self._flush_batch_data()
            
            if self.postgres_engine:
                await self.postgres_engine.dispose()
                self.postgres_engine = None
                self.postgres_session_factory = None

            if self.clickhouse_client:
                self.clickhouse_client.close()
                self.clickhouse_client = None

            if self.redis_client:
                await self.redis_client.close()
                self.redis_client = None

            self._initialized = False
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")

    @asynccontextmanager
    async def get_postgres_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get PostgreSQL database session with proper initialization handling."""
        # Ensure initialization is complete before proceeding
        if not self._initialized:
            await self.initialize()

        # Double-check initialization completed successfully
        if not self.postgres_session_factory:
            raise DatabaseError("PostgreSQL not initialized - session factory unavailable")

        if not self.postgres_engine:
            raise DatabaseError("PostgreSQL not initialized - engine unavailable")

        async with self.postgres_session_factory() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
            finally:
                await session.close()

    def get_clickhouse_client(self) -> clickhouse_connect.driver.Client:
        """Get ClickHouse client with initialization check."""
        if not self._initialized:
            raise DatabaseError("Database manager not initialized - call initialize() first")

        if not self.clickhouse_client:
            raise DatabaseError("ClickHouse client not available - initialization may have failed")

        return self.clickhouse_client

    def get_redis_client(self) -> redis.Redis:
        """Get Redis client with initialization check."""
        if not self._initialized:
            raise DatabaseError("Database manager not initialized - call initialize() first")

        if not self.redis_client:
            raise DatabaseError("Redis client not available - initialization may have failed")

        return self.redis_client

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all database connections."""
        health_status = {
            "postgres": {"healthy": False, "error": None},
            "clickhouse": {"healthy": False, "error": None},
            "redis": {"healthy": False, "error": None},
        }

        # Check PostgreSQL
        try:
            if self.postgres_engine:
                async with self.postgres_engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                health_status["postgres"]["healthy"] = True
        except Exception as e:
            health_status["postgres"]["error"] = str(e)

        # Check ClickHouse
        try:
            if self.clickhouse_client:
                result = self.clickhouse_client.query("SELECT 1")
                if result.result_rows:
                    health_status["clickhouse"]["healthy"] = True
        except Exception as e:
            health_status["clickhouse"]["error"] = str(e)

        # Check Redis
        try:
            if self.redis_client:
                await self.redis_client.ping()
                health_status["redis"]["healthy"] = True
        except Exception as e:
            health_status["redis"]["error"] = str(e)

        return health_status
    
    async def get_database_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive database health summary with aggregation.
        
        Returns:
            Aggregated health status for all database components
        """
        try:
            health_data = await self.health_check()
            
            # Determine overall status
            component_statuses = []
            for component, status in health_data.items():
                component_statuses.append(status.get('healthy', False))
            
            # Overall status logic
            if all(component_statuses):
                overall_status = 'healthy'
                status_message = 'All database components are healthy'
            elif any(component_statuses):
                overall_status = 'degraded'
                status_message = 'Some database components are unhealthy'
            else:
                overall_status = 'unhealthy'
                status_message = 'All database components are unhealthy'
            
            # Count healthy vs total
            healthy_count = sum(component_statuses)
            total_count = len(component_statuses)
            
            return {
                'overall_status': overall_status,
                'status_message': status_message,
                'healthy_components': healthy_count,
                'total_components': total_count,
                'health_percentage': (healthy_count / total_count * 100) if total_count > 0 else 0,
                'components': health_data,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'critical_components': ['postgres'],  # Define critical components
                'optional_components': ['redis']  # Define optional components
            }
            
        except Exception as e:
            logger.error(f"Failed to get database health summary: {e}")
            return {
                'overall_status': 'error',
                'status_message': f'Health check failed: {e}',
                'healthy_components': 0,
                'total_components': 0,
                'health_percentage': 0,
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

    async def execute_query(self, query: str, parameters: tuple = None) -> Any:
        """Execute query with standardized interface for migration compatibility.
        
        Args:
            query: SQL query to execute
            parameters: Optional query parameters
            
        Returns:
            Query result
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Route to appropriate database based on query type
            query_upper = query.strip().upper()
            
            if any(keyword in query_upper for keyword in ['CREATE TABLE', 'INSERT INTO market_ticks', 'CREATE MATERIALIZED VIEW']):
                # ClickHouse operations
                if not self.clickhouse_client:
                    raise DatabaseError("ClickHouse client not available")
                
                if parameters:
                    # Handle parameterized queries for ClickHouse
                    formatted_query = query
                    for param in parameters:
                        formatted_query = formatted_query.replace('%s', f"'{param}'", 1)
                    query = formatted_query
                
                if query_upper.startswith(('CREATE', 'DROP', 'ALTER', 'INSERT')):
                    return self.clickhouse_client.command(query)
                else:
                    result = self.clickhouse_client.query(query)
                    return result.result_rows
            
            else:
                # PostgreSQL operations
                async with self.get_postgres_session() as session:
                    if parameters:
                        result = await session.execute(text(query), parameters)
                    else:
                        result = await session.execute(text(query))
                    
                    await session.commit()
                    
                    # Return appropriate result based on query type
                    if query_upper.startswith('SELECT'):
                        return result.fetchall()
                    else:
                        return result.rowcount
                        
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            raise DatabaseError(f"Query execution failed: {e}")
    
    async def _flush_batch_data(self) -> None:
        """Flush any pending batch data.
        
        This method ensures compatibility with cleanup operations.
        Actual batch flushing is handled by specific managers.
        """
        try:
            # This is a compatibility method for the interface
            # Actual batch data flushing is handled by specialized managers
            # like ClickHouseManager and StorageManager
            logger.debug("Database manager batch data flush completed")
            
        except Exception as e:
            logger.error(f"Error flushing batch data: {e}")

    async def create_tables(self) -> None:
        """Create database tables."""
        if not self._initialized:
            await self.initialize()

        try:
            # Create PostgreSQL tables
            from core.database.models import Base

            async with self.postgres_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Create ClickHouse tables
            await self._create_clickhouse_tables()

            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise DatabaseError(f"Table creation failed: {e}")

    async def _create_clickhouse_tables(self) -> None:
        """Create ClickHouse tables and materialized views."""
        clickhouse_schemas = [
            # Market ticks table with optimized compression - matches migration 001 schema
            """
            CREATE TABLE IF NOT EXISTS market_ticks (
                -- Core identification
                timestamp DateTime64(3) CODEC(Delta, LZ4),
                instrument_token UInt32 CODEC(DoubleDelta, LZ4),
                exchange String CODEC(ZSTD(1)),
                tradingsymbol String CODEC(ZSTD(1)),
                
                -- Price data
                last_price Float64 CODEC(DoubleDelta, LZ4),
                last_quantity UInt32 CODEC(DoubleDelta, LZ4),
                average_price Float64 CODEC(DoubleDelta, LZ4),
                volume_traded UInt64 CODEC(DoubleDelta, LZ4),
                
                -- Market sentiment
                buy_quantity UInt64 CODEC(DoubleDelta, LZ4),
                sell_quantity UInt64 CODEC(DoubleDelta, LZ4),
                
                -- OHLC data
                open Float64 CODEC(DoubleDelta, LZ4),
                high Float64 CODEC(DoubleDelta, LZ4),
                low Float64 CODEC(DoubleDelta, LZ4),
                close Float64 CODEC(DoubleDelta, LZ4),
                
                -- Price changes
                net_change Float64 CODEC(DoubleDelta, LZ4),
                percentage_change Float64 CODEC(DoubleDelta, LZ4),
                
                -- Open Interest (F&O)
                oi UInt64 CODEC(DoubleDelta, LZ4),
                oi_day_high UInt64 CODEC(DoubleDelta, LZ4),
                oi_day_low UInt64 CODEC(DoubleDelta, LZ4),
                
                -- Market depth (5 levels each side)
                depth_buy Array(Tuple(price Float64, quantity UInt32, orders UInt16)) CODEC(ZSTD(1)),
                depth_sell Array(Tuple(price Float64, quantity UInt32, orders UInt16)) CODEC(ZSTD(1)),
                
                -- Metadata
                mode String CODEC(ZSTD(1)),
                tradable Bool CODEC(ZSTD(1)),
                exchange_timestamp DateTime64(3) CODEC(Delta, LZ4),
                
                -- Data quality indicators
                data_quality_score Float32 DEFAULT 1.0 CODEC(ZSTD(1)),
                validation_flags UInt32 DEFAULT 0 CODEC(ZSTD(1))
                
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (instrument_token, timestamp)
            SETTINGS 
                index_granularity = 8192,
                compress_marks = 1,
                compress_primary_key = 1,
                enable_mixed_granularity_parts = 1
            """,
            # Trading signals table
            """
            CREATE TABLE IF NOT EXISTS strategy_signals (
                timestamp DateTime64(3),
                strategy_name String,
                instrument_token UInt32,
                signal_type Enum('BUY', 'SELL', 'HOLD'),
                signal_strength Float64,
                features Map(String, Float64),
                confidence Float64,
                metadata String
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (strategy_name, instrument_token, timestamp)
            """,
            # Materialized view for 1-minute features with compression
            """
            CREATE MATERIALIZED VIEW IF NOT EXISTS ml_features_1m
            ENGINE = AggregatingMergeTree()
            PARTITION BY toYYYYMM(minute)
            ORDER BY (instrument_token, minute)
            SETTINGS index_granularity = 8192, compress_marks = 1
            AS SELECT
                instrument_token,
                toStartOfMinute(timestamp) as minute,
                avgState(last_price) as avg_price_state,
                maxState(high) as max_high_state,
                minState(low) as min_low_state,
                sumState(volume_traded) as total_volume_state,
                argMaxState(last_price, timestamp) as close_price_state,
                countState() as tick_count_state
            FROM market_ticks
            GROUP BY instrument_token, minute
            """,
            # Performance optimization indexes
            """
            CREATE TABLE IF NOT EXISTS market_ticks_buffer AS market_ticks
            ENGINE = Buffer(alphapt, market_ticks, 16, 10, 100, 10000, 1000000, 10000000, 100000000)
            """,
            # OHLC materialized view for faster queries
            """
            CREATE MATERIALIZED VIEW IF NOT EXISTS ohlc_1m
            ENGINE = ReplacingMergeTree()
            PARTITION BY toYYYYMM(minute)
            ORDER BY (instrument_token, minute)
            AS SELECT
                instrument_token,
                toStartOfMinute(timestamp) as minute,
                argMin(last_price, timestamp) as open,
                max(high) as high,
                min(low) as low,
                argMax(last_price, timestamp) as close,
                sum(volume_traded) as volume,
                count() as tick_count
            FROM market_ticks
            GROUP BY instrument_token, minute
            """,
        ]

        for schema in clickhouse_schemas:
            try:
                self.clickhouse_client.command(schema)
            except Exception as e:
                logger.warning(f"ClickHouse schema creation warning: {e}")


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_database_manager(settings: Optional[Settings] = None) -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager
    if _db_manager is None:
        if settings is None:
            from core.config.settings import settings as default_settings

            settings = default_settings
        _db_manager = DatabaseManager(settings)
    return _db_manager


async def initialize_database(settings: Optional[Settings] = None) -> DatabaseManager:
    """Initialize the database manager."""
    db_manager = get_database_manager(settings)
    await db_manager.initialize()
    return db_manager


async def close_database() -> None:
    """Close the database manager."""
    global _db_manager
    if _db_manager:
        await _db_manager.close()
        _db_manager = None
