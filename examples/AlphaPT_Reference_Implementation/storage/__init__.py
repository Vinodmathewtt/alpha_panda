"""Data layer module for AlphaPT.

This module handles all data operations including:
- Market data ingestion and storage
- ClickHouse analytics and ML features  
- Redis caching for hot data
- Data quality monitoring and validation
"""

from .clickhouse_schemas import ClickHouseSchemas
from .clickhouse_manager import ClickHouseManager
from .redis_cache_manager import RedisCacheManager
from .data_quality_monitor import DataQualityMonitor
from .storage_manager import MarketDataStorageManager

# Global instance for API access
# This will be initialized by the application
storage_manager: MarketDataStorageManager = None

__all__ = [
    "ClickHouseSchemas",
    "ClickHouseManager",
    "RedisCacheManager", 
    "DataQualityMonitor",
    "MarketDataStorageManager",
    "storage_manager",
]