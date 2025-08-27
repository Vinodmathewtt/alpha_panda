"""ClickHouse connection and data management.

This module provides high-performance ClickHouse operations for:
- Connection management with pooling
- Market data ingestion at scale
- Real-time analytics queries
- Schema management and migrations
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Union, AsyncGenerator
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

import clickhouse_connect
from clickhouse_connect.driver import Client
from clickhouse_connect.driver.exceptions import ClickHouseError, DatabaseError

from core.config.settings import Settings
from core.utils.exceptions import DatabaseError as AlphaPTDatabaseError
from core.logging.logger import get_logger
from .clickhouse_schemas import ClickHouseSchemas, TableDefinition


class ClickHouseManager:
    """ClickHouse connection and data management."""
    
    def __init__(self, settings: Settings):
        """Initialize ClickHouse manager.
        
        Args:
            settings: Application settings with ClickHouse configuration
        """
        self.settings = settings
        self.logger = get_logger("clickhouse_manager")
        self._client: Optional[Client] = None
        self._connection_pool_size = 10
        self._is_connected = False
        
        # Performance settings
        self.batch_size = settings.market_data_batch_size
        self.flush_interval = settings.market_data_flush_interval
        self._batch_buffer = []
        self._last_flush = datetime.now(timezone.utc)
        
        # Schema management
        self.schemas = ClickHouseSchemas()
    
    async def connect(self) -> bool:
        """Connect to ClickHouse database.
        
        Returns:
            True if connection successful, False otherwise
        """
        if self._is_connected:
            return True
        
        try:
            self.logger.info("Connecting to ClickHouse database...")
            
            # Get connection parameters
            params = self.settings.database.get_clickhouse_connection_params()
            
            # Create client connection
            self._client = clickhouse_connect.get_client(
                host=params["host"],
                port=params["port"],
                username=params["username"],
                password=params["password"],
                database=params["database"],
                connect_timeout=params["connect_timeout"],
                send_receive_timeout=params["send_receive_timeout"],
                compression=params["compression"],
                # Additional performance settings moved to settings dict
                settings={
                    'max_execution_time': 300,
                    'max_memory_usage': 10000000000,  # 10GB
                    'max_result_rows': 1000000
                }
            )
            
            # Test connection
            await self._test_connection()
            
            # Apply database settings
            await self._apply_database_settings()
            
            self._is_connected = True
            self.logger.info("✅ ClickHouse connection established")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to ClickHouse: {e}")
            self._is_connected = False
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from ClickHouse database."""
        try:
            if self._client:
                # Flush any remaining data
                await self._flush_batch_data()
                
                self._client.close()
                self._client = None
                self._is_connected = False
                
            self.logger.info("ClickHouse connection closed")
            
        except Exception as e:
            self.logger.error(f"Error closing ClickHouse connection: {e}")
    
    async def _test_connection(self) -> None:
        """Test ClickHouse connection."""
        if not self._client:
            raise AlphaPTDatabaseError("ClickHouse client not initialized")
        
        try:
            result = self._client.command("SELECT 1")
            if result != 1:
                raise AlphaPTDatabaseError("ClickHouse connection test failed")
                
        except ClickHouseError as e:
            raise AlphaPTDatabaseError(f"ClickHouse connection test failed: {e}")
    
    async def _apply_database_settings(self) -> None:
        """Apply performance-optimized database settings."""
        if not self._client:
            return
        
        try:
            settings = self.schemas.get_database_settings()
            for setting in settings:
                self._client.command(setting)
                
            self.logger.debug("Applied ClickHouse database settings")
            
        except Exception as e:
            self.logger.warning(f"Failed to apply some database settings: {e}")
    
    async def initialize_schema(self) -> bool:
        """Initialize ClickHouse database schema using migrations.
        
        Returns:
            True if schema initialization successful
        """
        if not self._is_connected:
            await self.connect()
        
        try:
            self.logger.info("Initializing ClickHouse schema using migrations...")
            
            # Import migration manager (lazy import to avoid circular dependency)
            from storage.migration_manager import MigrationManager
            
            # Run migrations
            migration_manager = MigrationManager(self.settings, self)
            if not await migration_manager.run_migrations():
                self.logger.error("Failed to run database migrations")
                return False
            
            # Legacy fallback: Create tables directly if no migrations found
            # This ensures backward compatibility
            migration_status = await migration_manager.get_migration_status()
            if migration_status.get("total_available", 0) == 0:
                self.logger.info("No migration files found, using legacy schema creation...")
                return await self._initialize_schema_legacy()
            
            # Create indexes after migrations
            indexes = self.schemas.get_indexes()
            for index_sql in indexes:
                try:
                    self._client.command(index_sql)
                except ClickHouseError as e:
                    if "already exists" not in str(e):
                        self.logger.warning(f"Index creation failed: {e}")
            
            self.logger.info("✅ ClickHouse schema initialization completed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Schema initialization failed: {e}")
            return False
    
    async def _initialize_schema_legacy(self) -> bool:
        """Legacy schema initialization using Python-defined schemas."""
        try:
            # Create all tables
            table_definitions = self.schemas.get_all_table_definitions()
            
            for table_def in table_definitions:
                try:
                    self._client.command(table_def.create_sql)
                    self.logger.debug(f"Created table/view: {table_def.name}")
                    
                except ClickHouseError as e:
                    if "already exists" not in str(e):
                        self.logger.error(f"Failed to create {table_def.name}: {e}")
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Legacy schema initialization failed: {e}")
            return False
    
    async def insert_market_tick(self, tick_data: Dict[str, Any]) -> bool:
        """Insert single market tick data.
        
        Args:
            tick_data: Market tick data dictionary
            
        Returns:
            True if insertion successful
        """
        return await self.insert_market_ticks([tick_data])
    
    async def insert_market_ticks(self, ticks_data: List[Dict[str, Any]]) -> bool:
        """Insert multiple market ticks data with batching.
        
        Args:
            ticks_data: List of market tick data dictionaries
            
        Returns:
            True if insertion successful
        """
        if not self._is_connected:
            self.logger.warning("ClickHouse not connected, cannot insert data")
            return False
        
        try:
            # Prepare data for insertion
            prepared_data = []
            for tick in ticks_data:
                prepared_tick = self._prepare_tick_for_insertion(tick)
                if prepared_tick:
                    prepared_data.append(prepared_tick)
            
            if not prepared_data:
                return True
            
            # Insert data
            self._client.insert(
                table="market_ticks",
                data=prepared_data,
                column_names=[
                    'timestamp', 'instrument_token', 'exchange', 'tradingsymbol',
                    'last_price', 'last_quantity', 'average_price', 'volume_traded',
                    'buy_quantity', 'sell_quantity', 'open', 'high', 'low', 'close',
                    'net_change', 'percentage_change', 'oi', 'oi_day_high', 'oi_day_low',
                    'depth_buy', 'depth_sell', 'mode', 'tradable', 'exchange_timestamp'
                ]
            )
            
            self.logger.debug(f"Inserted {len(prepared_data)} market ticks")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to insert market ticks: {e}")
            return False
    
    def _prepare_tick_for_insertion(self, tick_data: Dict[str, Any]) -> Optional[List[Any]]:
        """Prepare tick data for ClickHouse insertion.
        
        Args:
            tick_data: Raw tick data dictionary
            
        Returns:
            Prepared data row or None if invalid
        """
        try:
            # Extract depth data
            depth_buy = []
            depth_sell = []
            
            if 'depth' in tick_data and tick_data['depth']:
                depth = tick_data['depth']
                
                # Convert buy depth
                for level in depth.get('buy', [])[:5]:  # Top 5 levels
                    if isinstance(level, dict):
                        depth_buy.append((
                            float(level.get('price', 0)),
                            int(level.get('quantity', 0)),
                            int(level.get('orders', 1))
                        ))
                
                # Convert sell depth
                for level in depth.get('sell', [])[:5]:  # Top 5 levels
                    if isinstance(level, dict):
                        depth_sell.append((
                            float(level.get('price', 0)),
                            int(level.get('quantity', 0)),
                            int(level.get('orders', 1))
                        ))
            
            # Extract OHLC data
            ohlc = tick_data.get('ohlc', {})
            
            return [
                datetime.fromisoformat(tick_data.get('timestamp', datetime.now(timezone.utc).isoformat())),
                int(tick_data.get('instrument_token', 0)),
                str(tick_data.get('exchange', 'NSE')),
                str(tick_data.get('tradingsymbol', '')),
                float(tick_data.get('last_price', 0)),
                int(tick_data.get('last_quantity', 0)),
                float(tick_data.get('average_price', 0)),
                int(tick_data.get('volume', 0)),
                int(tick_data.get('buy_quantity', 0)),
                int(tick_data.get('sell_quantity', 0)),
                float(ohlc.get('open', 0)),
                float(ohlc.get('high', 0)),
                float(ohlc.get('low', 0)),
                float(ohlc.get('close', 0)),
                float(tick_data.get('net_change', 0)),
                float(tick_data.get('percentage_change', 0)),
                int(tick_data.get('oi', 0)),
                int(tick_data.get('oi_day_high', 0)),
                int(tick_data.get('oi_day_low', 0)),
                depth_buy,
                depth_sell,
                str(tick_data.get('mode', 'full')),
                bool(tick_data.get('tradable', True)),
                datetime.fromisoformat(tick_data.get('timestamp', datetime.now(timezone.utc).isoformat())),
            ]
            
        except Exception as e:
            self.logger.error(f"Failed to prepare tick data: {e}")
            return None
    
    async def insert_strategy_signal(self, signal_data: Dict[str, Any]) -> bool:
        """Insert strategy signal data.
        
        Args:
            signal_data: Strategy signal data dictionary
            
        Returns:
            True if insertion successful
        """
        if not self._is_connected:
            return False
        
        try:
            prepared_data = [[
                datetime.fromisoformat(signal_data.get('timestamp', datetime.now(timezone.utc).isoformat())),
                str(signal_data.get('strategy_name', '')),
                str(signal_data.get('strategy_type', 'traditional')),
                int(signal_data.get('instrument_token', 0)),
                str(signal_data.get('exchange', 'NSE')),
                str(signal_data.get('tradingsymbol', '')),
                str(signal_data.get('signal_type', 'HOLD')),
                float(signal_data.get('signal_strength', 0)),
                float(signal_data.get('confidence', 0)),
                float(signal_data.get('signal_price', 0)),
                float(signal_data.get('market_price', 0)),
                float(signal_data.get('price_deviation', 0)),
                signal_data.get('ml_features', {}),
                signal_data.get('technical_features', {}),
                float(signal_data.get('risk_score', 0)),
                float(signal_data.get('volatility_estimate', 0)),
                str(signal_data.get('signal_id', '')),
                str(signal_data.get('parent_signal_id', '')),
                str(signal_data.get('metadata', '')),
                int(signal_data.get('processing_latency_ms', 0)),
            ]]
            
            self._client.insert(
                table="strategy_signals",
                data=prepared_data
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to insert strategy signal: {e}")
            return False
    
    async def query_market_data(
        self, 
        instrument_tokens: List[int],
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Query market data with flexible parameters.
        
        Args:
            instrument_tokens: List of instrument tokens to query
            start_time: Start time for data
            end_time: End time for data (defaults to now)
            limit: Maximum number of records
            
        Returns:
            List of market data records
        """
        if not self._is_connected:
            return []
        
        try:
            end_time = end_time or datetime.now(timezone.utc)
            
            tokens_str = ','.join(map(str, instrument_tokens))
            
            query = f"""
            SELECT *
            FROM market_ticks
            WHERE instrument_token IN ({tokens_str})
              AND timestamp >= '{start_time.isoformat()}'
              AND timestamp <= '{end_time.isoformat()}'
            ORDER BY timestamp DESC
            LIMIT {limit}
            """
            
            result = self._client.query(query)
            return result.result_rows
            
        except Exception as e:
            self.logger.error(f"Failed to query market data: {e}")
            return []
    
    async def get_latest_ohlc(
        self, 
        instrument_tokens: List[int],
        timeframe: str = '1m',
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get latest OHLC data for instruments.
        
        Args:
            instrument_tokens: List of instrument tokens
            timeframe: OHLC timeframe (1m, 5m, 1h, 1d)
            limit: Maximum records per instrument
            
        Returns:
            List of OHLC records
        """
        if not self._is_connected:
            return []
        
        try:
            tokens_str = ','.join(map(str, instrument_tokens))
            
            # For now, only 1m is supported via materialized view
            if timeframe == '1m':
                query = f"""
                SELECT *
                FROM ohlc_1m
                WHERE instrument_token IN ({tokens_str})
                ORDER BY minute DESC, instrument_token
                LIMIT {limit}
                """
            else:
                # Aggregate on-demand for other timeframes
                interval = self._get_clickhouse_interval(timeframe)
                query = f"""
                SELECT
                    toStartOfInterval(minute, INTERVAL {interval}) as period,
                    instrument_token,
                    any(exchange) as exchange,
                    any(tradingsymbol) as tradingsymbol,
                    argMin(open, minute) as open,
                    max(high) as high,
                    min(low) as low,
                    argMax(close, minute) as close,
                    sum(volume) as volume,
                    sum(trades_count) as trades_count
                FROM ohlc_1m
                WHERE instrument_token IN ({tokens_str})
                  AND minute >= now() - INTERVAL 1 DAY
                GROUP BY period, instrument_token
                ORDER BY period DESC, instrument_token
                LIMIT {limit}
                """
            
            result = self._client.query(query)
            return result.result_rows
            
        except Exception as e:
            self.logger.error(f"Failed to query OHLC data: {e}")
            return []
    
    def _get_clickhouse_interval(self, timeframe: str) -> str:
        """Convert timeframe to ClickHouse interval."""
        mapping = {
            '1m': '1 MINUTE',
            '5m': '5 MINUTE',
            '15m': '15 MINUTE',
            '1h': '1 HOUR',
            '4h': '4 HOUR',
            '1d': '1 DAY'
        }
        return mapping.get(timeframe, '1 MINUTE')
    
    async def store_market_data_batch(self, batch_data: List[Dict[str, Any]]) -> int:
        """Store batch of market data and return success count.
        
        Args:
            batch_data: List of market data records to store
            
        Returns:
            Number of successfully stored records
        """
        if not batch_data:
            return 0
        
        try:
            success = await self.insert_market_ticks(batch_data)
            return len(batch_data) if success else 0
            
        except Exception as e:
            self.logger.error(f"Failed to store market data batch: {e}")
            return 0
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """Get ClickHouse database statistics.
        
        Returns:
            Database statistics dictionary
        """
        if not self._is_connected:
            return {}
        
        try:
            # Table sizes
            tables_query = """
            SELECT
                table,
                formatReadableSize(sum(bytes)) as size,
                sum(rows) as rows
            FROM system.parts
            WHERE database = currentDatabase()
            GROUP BY table
            ORDER BY sum(bytes) DESC
            """
            
            tables_result = self._client.query(tables_query)
            
            # Query statistics
            queries_query = """
            SELECT
                type,
                count() as count,
                avg(query_duration_ms) as avg_duration_ms,
                max(query_duration_ms) as max_duration_ms
            FROM system.query_log
            WHERE event_time >= now() - INTERVAL 1 HOUR
            GROUP BY type
            """
            
            try:
                queries_result = self._client.query(queries_query)
            except:
                queries_result = None  # system.query_log might not be available
            
            return {
                "tables": tables_result.result_rows,
                "queries": queries_result.result_rows if queries_result else [],
                "connection_status": "connected",
                "database": self.settings.database.clickhouse_database,
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get database stats: {e}")
            return {"error": str(e)}
    
    @asynccontextmanager
    async def transaction(self):
        """Async context manager for database transactions."""
        if not self._is_connected:
            await self.connect()
        
        try:
            yield self
        except Exception as e:
            self.logger.error(f"Transaction failed: {e}")
            raise
    
    async def execute_query(self, query: str, parameters: tuple = None) -> Any:
        """Execute a query and return the result.
        
        Args:
            query: SQL query to execute
            parameters: Optional query parameters for parameterized queries
            
        Returns:
            Query result
        """
        if not self._is_connected:
            await self.connect()
        
        try:
            # Handle parameterized queries
            if parameters:
                # For ClickHouse, we need to format the query with parameters
                if '%s' in query:
                    # Replace %s placeholders with actual values
                    formatted_query = query
                    for param in parameters:
                        formatted_query = formatted_query.replace('%s', f"'{param}'", 1)
                    query = formatted_query
            
            if query.strip().upper().startswith(('CREATE', 'DROP', 'ALTER', 'INSERT')):
                return self._client.command(query)
            else:
                result = self._client.query(query)
                return result.result_rows
        except Exception as e:
            self.logger.error(f"Failed to execute query: {e}")
            raise AlphaPTDatabaseError(f"Query execution failed: {e}")
    
    async def _flush_batch_data(self) -> None:
        """Flush any pending batch data."""
        if self._batch_buffer:
            try:
                await self.insert_market_ticks(self._batch_buffer)
                self._batch_buffer.clear()
                self._last_flush = datetime.now(timezone.utc)
            except Exception as e:
                self.logger.error(f"Failed to flush batch data: {e}")

    async def health_check(self) -> Dict[str, Any]:
        """Perform ClickHouse health check.
        
        Returns:
            Health check results
        """
        try:
            if not self._is_connected:
                return {
                    "status": "unhealthy",
                    "message": "Not connected to ClickHouse"
                }
            
            # Test connection
            start_time = datetime.now(timezone.utc)
            result = self._client.command("SELECT 1")
            response_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            if result == 1:
                return {
                    "status": "healthy",
                    "response_time_ms": round(response_time, 2),
                    "database": self.settings.database.clickhouse_database,
                    "host": self.settings.database.clickhouse_host
                }
            else:
                return {
                    "status": "unhealthy",
                    "message": "Unexpected response from ClickHouse"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Health check failed: {e}"
            }