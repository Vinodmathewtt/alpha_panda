"""Redis performance optimization and caching manager."""

import asyncio
import logging
import json
import time
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from datetime import datetime, timedelta

import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from core.config.settings import Settings
from core.utils.exceptions import DatabaseError

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Cache performance statistics."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    errors: int = 0
    total_operations: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total_gets = self.hits + self.misses
        return (self.hits / total_gets * 100) if total_gets > 0 else 0.0


class RedisPerformanceManager:
    """Redis performance optimization and caching manager."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.redis_client: Optional[redis.Redis] = None
        self.connection_pool: Optional[ConnectionPool] = None
        self._stats = CacheStats()
        self._initialized = False
        
        # Cache configuration
        self.cache_config = {
            # Market data caching (hot data)
            "market_ticks": {
                "ttl": 300,  # 5 minutes
                "prefix": "tick:",
                "compression": True,
            },
            "market_depth": {
                "ttl": 60,  # 1 minute
                "prefix": "depth:",
                "compression": True,
            },
            "ohlc_data": {
                "ttl": 3600,  # 1 hour
                "prefix": "ohlc:",
                "compression": False,
            },
            # Strategy data
            "strategy_signals": {
                "ttl": 1800,  # 30 minutes
                "prefix": "signal:",
                "compression": False,
            },
            "risk_metrics": {
                "ttl": 300,  # 5 minutes
                "prefix": "risk:",
                "compression": False,
            },
            # Session and auth data
            "user_sessions": {
                "ttl": 86400,  # 24 hours
                "prefix": "session:",
                "compression": False,
            },
            "auth_tokens": {
                "ttl": 3600,  # 1 hour
                "prefix": "auth:",
                "compression": False,
            },
        }
    
    async def initialize(self) -> None:
        """Initialize Redis connection with optimized settings."""
        if self._initialized:
            return
        
        try:
            # Create optimized connection pool
            self.connection_pool = ConnectionPool(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                db=self.settings.redis_db,
                password=self.settings.redis_password,
                max_connections=50,  # Increased for high throughput
                retry_on_timeout=True,
                retry_on_error=[redis.ConnectionError, redis.TimeoutError],
                health_check_interval=30,
                socket_connect_timeout=5,
                socket_timeout=5,
                socket_keepalive=True,
                socket_keepalive_options={},
                decode_responses=False,  # Better performance with bytes
            )
            
            self.redis_client = redis.Redis(
                connection_pool=self.connection_pool,
                decode_responses=False,
            )
            
            # Test connection
            await self.redis_client.ping()
            
            # Configure Redis for optimal performance
            await self._configure_redis_performance()
            
            self._initialized = True
            logger.info("Redis performance manager initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis performance manager: {e}")
            await self.close()
            raise DatabaseError(f"Redis initialization failed: {e}")
    
    async def _configure_redis_performance(self) -> None:
        """Configure Redis for optimal performance."""
        try:
            # Set optimal configuration
            config_commands = [
                # Memory optimization
                ("CONFIG", "SET", "maxmemory-policy", "allkeys-lru"),
                ("CONFIG", "SET", "hash-max-ziplist-entries", "512"),
                ("CONFIG", "SET", "hash-max-ziplist-value", "64"),
                ("CONFIG", "SET", "list-max-ziplist-size", "-2"),
                ("CONFIG", "SET", "set-max-intset-entries", "512"),
                ("CONFIG", "SET", "zset-max-ziplist-entries", "128"),
                ("CONFIG", "SET", "zset-max-ziplist-value", "64"),
                
                # Performance optimization
                ("CONFIG", "SET", "tcp-keepalive", "60"),
                ("CONFIG", "SET", "timeout", "300"),
                ("CONFIG", "SET", "tcp-backlog", "511"),
                
                # Persistence optimization (for high throughput)
                ("CONFIG", "SET", "save", ""),  # Disable RDB snapshots
                ("CONFIG", "SET", "appendonly", "yes"),
                ("CONFIG", "SET", "appendfsync", "everysec"),
            ]
            
            for cmd in config_commands:
                try:
                    await self.redis_client.execute_command(*cmd)
                except Exception as e:
                    logger.warning(f"Redis config command failed {cmd}: {e}")
            
            logger.info("Redis performance configuration applied")
            
        except Exception as e:
            logger.error(f"Error configuring Redis performance: {e}")
    
    async def close(self) -> None:
        """Close Redis connections."""
        try:
            if self.redis_client:
                await self.redis_client.close()
                self.redis_client = None
            
            if self.connection_pool:
                await self.connection_pool.disconnect()
                self.connection_pool = None
            
            self._initialized = False
            logger.info("Redis performance manager closed")
            
        except Exception as e:
            logger.error(f"Error closing Redis connections: {e}")
    
    async def set_cached_data(
        self, 
        cache_type: str, 
        key: str, 
        data: Any, 
        custom_ttl: Optional[int] = None
    ) -> bool:
        """Set data in cache with optimization."""
        if not self._initialized:
            await self.initialize()
        
        try:
            config = self.cache_config.get(cache_type, {})
            full_key = f"{config.get('prefix', '')}{key}"
            ttl = custom_ttl or config.get('ttl', 3600)
            
            # Serialize data
            if isinstance(data, (dict, list)):
                serialized_data = json.dumps(data, default=str).encode('utf-8')
            elif isinstance(data, str):
                serialized_data = data.encode('utf-8')
            else:
                serialized_data = str(data).encode('utf-8')
            
            # Compress if configured
            if config.get('compression', False):
                import gzip
                serialized_data = gzip.compress(serialized_data)
            
            # Set with TTL
            await self.redis_client.setex(full_key, ttl, serialized_data)
            
            self._stats.sets += 1
            self._stats.total_operations += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Error setting cache data {cache_type}:{key}: {e}")
            self._stats.errors += 1
            self._stats.total_operations += 1
            return False
    
    async def get_cached_data(self, cache_type: str, key: str) -> Optional[Any]:
        """Get data from cache with optimization."""
        if not self._initialized:
            await self.initialize()
        
        try:
            config = self.cache_config.get(cache_type, {})
            full_key = f"{config.get('prefix', '')}{key}"
            
            # Get data
            data = await self.redis_client.get(full_key)
            
            if data is None:
                self._stats.misses += 1
                self._stats.total_operations += 1
                return None
            
            # Decompress if needed
            if config.get('compression', False):
                import gzip
                data = gzip.decompress(data)
            
            # Deserialize
            try:
                result = json.loads(data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                result = data.decode('utf-8')
            
            self._stats.hits += 1
            self._stats.total_operations += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting cache data {cache_type}:{key}: {e}")
            self._stats.errors += 1
            self._stats.total_operations += 1
            return None
    
    async def delete_cached_data(self, cache_type: str, key: str) -> bool:
        """Delete data from cache."""
        if not self._initialized:
            await self.initialize()
        
        try:
            config = self.cache_config.get(cache_type, {})
            full_key = f"{config.get('prefix', '')}{key}"
            
            result = await self.redis_client.delete(full_key)
            
            self._stats.deletes += 1
            self._stats.total_operations += 1
            
            return result > 0
            
        except Exception as e:
            logger.error(f"Error deleting cache data {cache_type}:{key}: {e}")
            self._stats.errors += 1
            self._stats.total_operations += 1
            return False
    
    async def set_multiple(self, cache_type: str, data_dict: Dict[str, Any]) -> int:
        """Set multiple cache entries efficiently."""
        if not self._initialized:
            await self.initialize()
        
        try:
            config = self.cache_config.get(cache_type, {})
            prefix = config.get('prefix', '')
            ttl = config.get('ttl', 3600)
            
            # Prepare pipeline
            pipe = self.redis_client.pipeline()
            
            for key, value in data_dict.items():
                full_key = f"{prefix}{key}"
                
                # Serialize data
                if isinstance(value, (dict, list)):
                    serialized_data = json.dumps(value, default=str).encode('utf-8')
                elif isinstance(value, str):
                    serialized_data = value.encode('utf-8')
                else:
                    serialized_data = str(value).encode('utf-8')
                
                # Compress if configured
                if config.get('compression', False):
                    import gzip
                    serialized_data = gzip.compress(serialized_data)
                
                pipe.setex(full_key, ttl, serialized_data)
            
            # Execute pipeline
            results = await pipe.execute()
            
            success_count = sum(1 for r in results if r)
            self._stats.sets += success_count
            self._stats.total_operations += len(data_dict)
            
            return success_count
            
        except Exception as e:
            logger.error(f"Error setting multiple cache entries {cache_type}: {e}")
            self._stats.errors += len(data_dict)
            self._stats.total_operations += len(data_dict)
            return 0
    
    async def get_multiple(self, cache_type: str, keys: List[str]) -> Dict[str, Any]:
        """Get multiple cache entries efficiently."""
        if not self._initialized:
            await self.initialize()
        
        try:
            config = self.cache_config.get(cache_type, {})
            prefix = config.get('prefix', '')
            
            # Prepare full keys
            full_keys = [f"{prefix}{key}" for key in keys]
            
            # Get multiple values
            values = await self.redis_client.mget(full_keys)
            
            result = {}
            for i, (key, value) in enumerate(zip(keys, values)):
                if value is not None:
                    # Decompress if needed
                    if config.get('compression', False):
                        import gzip
                        value = gzip.decompress(value)
                    
                    # Deserialize
                    try:
                        result[key] = json.loads(value.decode('utf-8'))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        result[key] = value.decode('utf-8')
                    
                    self._stats.hits += 1
                else:
                    self._stats.misses += 1
            
            self._stats.total_operations += len(keys)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting multiple cache entries {cache_type}: {e}")
            self._stats.errors += len(keys)
            self._stats.total_operations += len(keys)
            return {}
    
    async def clear_cache_pattern(self, pattern: str) -> int:
        """Clear cache entries matching pattern."""
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get keys matching pattern
            keys = []
            async for key in self.redis_client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                count = await self.redis_client.delete(*keys)
                self._stats.deletes += count
                self._stats.total_operations += len(keys)
                return count
            
            return 0
            
        except Exception as e:
            logger.error(f"Error clearing cache pattern {pattern}: {e}")
            self._stats.errors += 1
            self._stats.total_operations += 1
            return 0
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        try:
            # Redis info
            redis_info = await self.redis_client.info() if self.redis_client else {}
            
            # Memory usage
            memory_stats = {
                "used_memory": redis_info.get("used_memory", 0),
                "used_memory_human": redis_info.get("used_memory_human", "0B"),
                "used_memory_peak": redis_info.get("used_memory_peak", 0),
                "used_memory_peak_human": redis_info.get("used_memory_peak_human", "0B"),
            }
            
            # Performance stats
            perf_stats = {
                "keyspace_hits": redis_info.get("keyspace_hits", 0),
                "keyspace_misses": redis_info.get("keyspace_misses", 0),
                "instantaneous_ops_per_sec": redis_info.get("instantaneous_ops_per_sec", 0),
                "connected_clients": redis_info.get("connected_clients", 0),
            }
            
            # Calculate Redis hit rate
            redis_hits = perf_stats["keyspace_hits"]
            redis_misses = perf_stats["keyspace_misses"]
            redis_hit_rate = (redis_hits / (redis_hits + redis_misses) * 100) if (redis_hits + redis_misses) > 0 else 0
            
            return {
                "application_stats": {
                    "hits": self._stats.hits,
                    "misses": self._stats.misses,
                    "sets": self._stats.sets,
                    "deletes": self._stats.deletes,
                    "errors": self._stats.errors,
                    "total_operations": self._stats.total_operations,
                    "hit_rate": self._stats.hit_rate,
                },
                "redis_stats": perf_stats,
                "redis_hit_rate": redis_hit_rate,
                "memory_stats": memory_stats,
                "connection_pool": {
                    "created_connections": self.connection_pool.created_connections if self.connection_pool else 0,
                    "available_connections": len(self.connection_pool._available_connections) if self.connection_pool else 0,
                    "in_use_connections": len(self.connection_pool._in_use_connections) if self.connection_pool else 0,
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}
    
    async def optimize_memory(self) -> Dict[str, Any]:
        """Optimize Redis memory usage."""
        if not self._initialized:
            return {"error": "Not initialized"}
        
        try:
            results = {}
            
            # Clear expired keys
            expired_cleared = await self.redis_client.execute_command("MEMORY", "PURGE")
            results["expired_keys_cleared"] = expired_cleared
            
            # Get memory usage before
            info_before = await self.redis_client.info("memory")
            memory_before = info_before.get("used_memory", 0)
            
            # Defragment memory (if supported)
            try:
                await self.redis_client.execute_command("MEMORY", "DEFRAG")
                results["memory_defragmented"] = True
            except Exception:
                results["memory_defragmented"] = False
            
            # Get memory usage after
            info_after = await self.redis_client.info("memory")
            memory_after = info_after.get("used_memory", 0)
            
            results["memory_saved"] = memory_before - memory_after
            results["memory_before"] = memory_before
            results["memory_after"] = memory_after
            
            return results
            
        except Exception as e:
            logger.error(f"Error optimizing Redis memory: {e}")
            return {"error": str(e)}
    
    def reset_stats(self) -> None:
        """Reset performance statistics."""
        self._stats = CacheStats()
        logger.info("Redis performance stats reset")


# Global Redis performance manager instance
_redis_performance_manager: Optional[RedisPerformanceManager] = None


def get_redis_performance_manager(settings: Optional[Settings] = None) -> RedisPerformanceManager:
    """Get the global Redis performance manager instance."""
    global _redis_performance_manager
    if _redis_performance_manager is None:
        if settings is None:
            from core.config.settings import settings as default_settings
            settings = default_settings
        _redis_performance_manager = RedisPerformanceManager(settings)
    return _redis_performance_manager


async def initialize_redis_performance_manager(settings: Optional[Settings] = None) -> RedisPerformanceManager:
    """Initialize the Redis performance manager."""
    manager = get_redis_performance_manager(settings)
    await manager.initialize()
    return manager


async def close_redis_performance_manager() -> None:
    """Close the Redis performance manager."""
    global _redis_performance_manager
    if _redis_performance_manager:
        await _redis_performance_manager.close()
        _redis_performance_manager = None