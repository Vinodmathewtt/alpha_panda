"""Redis cache manager for hot market data and application caching.

This module provides high-performance Redis caching for:
- Latest market tick data
- Real-time instrument prices  
- OHLC data
- Strategy signals
- Application state caching
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Union, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError, ConnectionError

from core.config.settings import Settings
from core.logging.logger import get_logger
from core.utils.exceptions import CacheError


@dataclass
class CacheStats:
    """Redis cache statistics."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    errors: int = 0
    hit_rate: float = 0.0
    
    def calculate_hit_rate(self):
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        self.hit_rate = (self.hits / total * 100) if total > 0 else 0.0


class RedisCacheManager:
    """Redis cache manager for high-performance data caching."""
    
    def __init__(self, settings: Settings):
        """Initialize Redis cache manager.
        
        Args:
            settings: Application settings with Redis configuration
        """
        self.settings = settings
        self.logger = get_logger("redis_cache_manager")
        
        # Redis connection
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[redis.Redis] = None
        self._is_connected = False
        
        # Cache configuration
        self.default_ttl = 60  # Default TTL in seconds
        self.key_prefixes = {
            'tick': 'tick:',
            'ohlc': 'ohlc:',
            'signal': 'signal:',
            'instrument': 'instrument:',
            'strategy': 'strategy:',
            'health': 'health:',
        }
        
        # Performance tracking
        self.stats = CacheStats()
        
        # Cache warming
        self._warm_cache_on_startup = True
        
    async def connect(self) -> bool:
        """Connect to Redis server.
        
        Returns:
            True if connection successful
        """
        if self._is_connected:
            return True
        
        try:
            self.logger.info("Connecting to Redis cache server...")
            
            # Create connection pool
            self._pool = ConnectionPool.from_url(
                self.settings.redis_url,
                password=self.settings.redis_password,
                max_connections=self.settings.redis_max_connections,
                retry_on_timeout=True,
                retry_on_error=[ConnectionError],
                health_check_interval=30,
                decode_responses=False,  # We'll handle encoding manually
            )
            
            # Create Redis client
            self._redis = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._test_connection()
            
            # Warm cache if configured
            if self._warm_cache_on_startup:
                await self._warm_cache()
            
            self._is_connected = True
            self.logger.info("✅ Redis cache connection established")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to connect to Redis: {e}")
            await self.disconnect()
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from Redis server."""
        try:
            if self._redis:
                await self._redis.close()
                self._redis = None
            
            if self._pool:
                await self._pool.disconnect()
                self._pool = None
            
            self._is_connected = False
            self.logger.info("Redis connection closed")
            
        except Exception as e:
            self.logger.error(f"Error closing Redis connection: {e}")
    
    async def _test_connection(self) -> None:
        """Test Redis connection."""
        if not self._redis:
            raise CacheError("Redis client not initialized")
        
        try:
            pong = await self._redis.ping()
            if not pong:
                raise CacheError("Redis ping failed")
                
        except RedisError as e:
            raise CacheError(f"Redis connection test failed: {e}")
    
    async def _warm_cache(self) -> None:
        """Warm cache with frequently accessed data."""
        try:
            self.logger.info("Warming Redis cache...")
            
            # Set cache warming marker
            await self._redis.setex("cache:warmed", 3600, "true")
            
            self.logger.debug("Cache warming completed")
            
        except Exception as e:
            self.logger.warning(f"Cache warming failed: {e}")
    
    # Tick data caching
    async def cache_tick_data(
        self, 
        instrument_token: int, 
        tick_data: Dict[str, Any], 
        ttl: Optional[int] = None
    ) -> bool:
        """Cache latest tick data for instrument.
        
        Args:
            instrument_token: Instrument token
            tick_data: Tick data dictionary
            ttl: Time to live in seconds
            
        Returns:
            True if caching successful
        """
        try:
            key = f"{self.key_prefixes['tick']}{instrument_token}"
            ttl = ttl or self.default_ttl
            
            # Serialize tick data
            serialized_data = json.dumps(tick_data, default=str)
            
            # Cache with TTL
            await self._redis.setex(key, ttl, serialized_data)
            
            # Also store in sorted set for time-based queries
            score = datetime.utcnow().timestamp()
            await self._redis.zadd(f"{key}:history", {serialized_data: score})
            
            # Keep only recent history (last 100 ticks)
            await self._redis.zremrangebyrank(f"{key}:history", 0, -101)
            
            self.stats.sets += 1
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cache tick data: {e}")
            self.stats.errors += 1
            return False
    
    async def get_latest_tick(self, instrument_token: int) -> Optional[Dict[str, Any]]:
        """Get latest tick data for instrument.
        
        Args:
            instrument_token: Instrument token
            
        Returns:
            Latest tick data or None if not found
        """
        try:
            key = f"{self.key_prefixes['tick']}{instrument_token}"
            
            cached_data = await self._redis.get(key)
            
            if cached_data:
                self.stats.hits += 1
                return json.loads(cached_data.decode('utf-8'))
            else:
                self.stats.misses += 1
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get tick data: {e}")
            self.stats.errors += 1
            return None
    
    async def get_tick_history(
        self, 
        instrument_token: int, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent tick history for instrument.
        
        Args:
            instrument_token: Instrument token
            limit: Maximum number of ticks to return
            
        Returns:
            List of recent tick data
        """
        try:
            key = f"{self.key_prefixes['tick']}{instrument_token}:history"
            
            # Get recent ticks (highest scores first)
            tick_data = await self._redis.zrevrange(key, 0, limit-1)
            
            ticks = []
            for tick_json in tick_data:
                try:
                    tick = json.loads(tick_json.decode('utf-8'))
                    ticks.append(tick)
                except json.JSONDecodeError:
                    continue
            
            if ticks:
                self.stats.hits += 1
            else:
                self.stats.misses += 1
                
            return ticks
            
        except Exception as e:
            self.logger.error(f"Failed to get tick history: {e}")
            self.stats.errors += 1
            return []
    
    # OHLC data caching
    async def cache_ohlc_data(
        self, 
        instrument_token: int, 
        timeframe: str,
        ohlc_data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Cache OHLC data for instrument and timeframe.
        
        Args:
            instrument_token: Instrument token
            timeframe: Timeframe (1m, 5m, 1h, etc.)
            ohlc_data: OHLC data dictionary
            ttl: Time to live in seconds
            
        Returns:
            True if caching successful
        """
        try:
            key = f"{self.key_prefixes['ohlc']}{instrument_token}:{timeframe}"
            ttl = ttl or 300  # 5 minutes for OHLC
            
            serialized_data = json.dumps(ohlc_data, default=str)
            await self._redis.setex(key, ttl, serialized_data)
            
            self.stats.sets += 1
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cache OHLC data: {e}")
            self.stats.errors += 1
            return False
    
    async def get_ohlc_data(
        self, 
        instrument_token: int, 
        timeframe: str
    ) -> Optional[Dict[str, Any]]:
        """Get cached OHLC data.
        
        Args:
            instrument_token: Instrument token
            timeframe: Timeframe
            
        Returns:
            OHLC data or None if not found
        """
        try:
            key = f"{self.key_prefixes['ohlc']}{instrument_token}:{timeframe}"
            
            cached_data = await self._redis.get(key)
            
            if cached_data:
                self.stats.hits += 1
                return json.loads(cached_data.decode('utf-8'))
            else:
                self.stats.misses += 1
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get OHLC data: {e}")
            self.stats.errors += 1
            return None
    
    # Instrument data caching
    async def cache_instrument_data(
        self, 
        instrument_token: int, 
        instrument_info: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Cache instrument information.
        
        Args:
            instrument_token: Instrument token
            instrument_info: Instrument information dictionary
            ttl: Time to live in seconds
            
        Returns:
            True if caching successful
        """
        try:
            key = f"{self.key_prefixes['instrument']}{instrument_token}"
            ttl = ttl or 3600  # 1 hour for instrument info
            
            serialized_data = json.dumps(instrument_info, default=str)
            await self._redis.setex(key, ttl, serialized_data)
            
            self.stats.sets += 1
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cache instrument data: {e}")
            self.stats.errors += 1
            return False
    
    async def get_instrument_data(self, instrument_token: int) -> Optional[Dict[str, Any]]:
        """Get cached instrument information.
        
        Args:
            instrument_token: Instrument token
            
        Returns:
            Instrument information or None if not found
        """
        try:
            key = f"{self.key_prefixes['instrument']}{instrument_token}"
            
            cached_data = await self._redis.get(key)
            
            if cached_data:
                self.stats.hits += 1
                return json.loads(cached_data.decode('utf-8'))
            else:
                self.stats.misses += 1
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get instrument data: {e}")
            self.stats.errors += 1
            return None
    
    # Strategy signal caching
    async def cache_strategy_signal(
        self, 
        strategy_name: str,
        instrument_token: int,
        signal_data: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Cache strategy signal.
        
        Args:
            strategy_name: Strategy name
            instrument_token: Instrument token
            signal_data: Signal data dictionary
            ttl: Time to live in seconds
            
        Returns:
            True if caching successful
        """
        try:
            key = f"{self.key_prefixes['signal']}{strategy_name}:{instrument_token}"
            ttl = ttl or 300  # 5 minutes for signals
            
            serialized_data = json.dumps(signal_data, default=str)
            await self._redis.setex(key, ttl, serialized_data)
            
            self.stats.sets += 1
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cache strategy signal: {e}")
            self.stats.errors += 1
            return False
    
    async def get_strategy_signal(
        self, 
        strategy_name: str, 
        instrument_token: int
    ) -> Optional[Dict[str, Any]]:
        """Get cached strategy signal.
        
        Args:
            strategy_name: Strategy name
            instrument_token: Instrument token
            
        Returns:
            Signal data or None if not found
        """
        try:
            key = f"{self.key_prefixes['signal']}{strategy_name}:{instrument_token}"
            
            cached_data = await self._redis.get(key)
            
            if cached_data:
                self.stats.hits += 1
                return json.loads(cached_data.decode('utf-8'))
            else:
                self.stats.misses += 1
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get strategy signal: {e}")
            self.stats.errors += 1
            return None
    
    # Bulk operations
    async def cache_multiple_ticks(
        self, 
        tick_data_map: Dict[int, Dict[str, Any]], 
        ttl: Optional[int] = None
    ) -> int:
        """Cache multiple tick data entries.
        
        Args:
            tick_data_map: Map of instrument_token -> tick_data
            ttl: Time to live in seconds
            
        Returns:
            Number of successfully cached entries
        """
        if not tick_data_map:
            return 0
        
        try:
            ttl = ttl or self.default_ttl
            pipeline = self._redis.pipeline()
            
            for instrument_token, tick_data in tick_data_map.items():
                key = f"{self.key_prefixes['tick']}{instrument_token}"
                serialized_data = json.dumps(tick_data, default=str)
                pipeline.setex(key, ttl, serialized_data)
            
            results = await pipeline.execute()
            success_count = sum(1 for r in results if r)
            
            self.stats.sets += success_count
            return success_count
            
        except Exception as e:
            self.logger.error(f"Failed to cache multiple ticks: {e}")
            self.stats.errors += 1
            return 0
    
    async def get_multiple_ticks(
        self, 
        instrument_tokens: List[int]
    ) -> Dict[int, Dict[str, Any]]:
        """Get multiple tick data entries.
        
        Args:
            instrument_tokens: List of instrument tokens
            
        Returns:
            Map of instrument_token -> tick_data for found entries
        """
        if not instrument_tokens:
            return {}
        
        try:
            pipeline = self._redis.pipeline()
            
            keys = []
            for token in instrument_tokens:
                key = f"{self.key_prefixes['tick']}{token}"
                keys.append(key)
                pipeline.get(key)
            
            results = await pipeline.execute()
            
            tick_data_map = {}
            hits = 0
            misses = 0
            
            for i, (token, cached_data) in enumerate(zip(instrument_tokens, results)):
                if cached_data:
                    try:
                        tick_data = json.loads(cached_data.decode('utf-8'))
                        tick_data_map[token] = tick_data
                        hits += 1
                    except json.JSONDecodeError:
                        misses += 1
                else:
                    misses += 1
            
            self.stats.hits += hits
            self.stats.misses += misses
            
            return tick_data_map
            
        except Exception as e:
            self.logger.error(f"Failed to get multiple ticks: {e}")
            self.stats.errors += 1
            return {}
    
    # Cache management
    async def delete_keys_by_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern.
        
        Args:
            pattern: Redis key pattern (with wildcards)
            
        Returns:
            Number of keys deleted
        """
        try:
            keys = await self._redis.keys(pattern)
            if keys:
                deleted = await self._redis.delete(*keys)
                self.stats.deletes += deleted
                return deleted
            return 0
            
        except Exception as e:
            self.logger.error(f"Failed to delete keys by pattern: {e}")
            self.stats.errors += 1
            return 0
    
    async def clear_instrument_cache(self, instrument_token: int) -> bool:
        """Clear all cached data for instrument.
        
        Args:
            instrument_token: Instrument token
            
        Returns:
            True if clearing successful
        """
        try:
            pattern = f"*{instrument_token}*"
            deleted = await self.delete_keys_by_pattern(pattern)
            self.logger.debug(f"Cleared {deleted} cache entries for instrument {instrument_token}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to clear instrument cache: {e}")
            return False
    
    async def get_cache_info(self) -> Dict[str, Any]:
        """Get Redis cache information and statistics.
        
        Returns:
            Cache information dictionary
        """
        try:
            info = await self._redis.info()
            
            # Calculate hit rate
            self.stats.calculate_hit_rate()
            
            return {
                'connection_status': 'connected' if self._is_connected else 'disconnected',
                'redis_info': {
                    'redis_version': info.get('redis_version', 'unknown'),
                    'used_memory': info.get('used_memory_human', 'unknown'),
                    'connected_clients': info.get('connected_clients', 0),
                    'total_commands_processed': info.get('total_commands_processed', 0),
                    'keyspace_hits': info.get('keyspace_hits', 0),
                    'keyspace_misses': info.get('keyspace_misses', 0),
                },
                'cache_stats': asdict(self.stats),
                'key_counts': await self._get_key_counts(),
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get cache info: {e}")
            return {
                'connection_status': 'error',
                'error': str(e),
                'cache_stats': asdict(self.stats),
            }
    
    async def _get_key_counts(self) -> Dict[str, int]:
        """Get count of keys by prefix."""
        try:
            key_counts = {}
            
            for name, prefix in self.key_prefixes.items():
                keys = await self._redis.keys(f"{prefix}*")
                key_counts[name] = len(keys)
            
            return key_counts
            
        except Exception as e:
            self.logger.error(f"Failed to get key counts: {e}")
            return {}
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform Redis health check.
        
        Returns:
            Health check results
        """
        try:
            if not self._is_connected:
                return {
                    "status": "unhealthy",
                    "message": "Not connected to Redis"
                }
            
            start_time = datetime.utcnow()
            pong = await self._redis.ping()
            response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if pong:
                return {
                    "status": "healthy",
                    "response_time_ms": round(response_time, 2),
                    "cache_stats": asdict(self.stats),
                }
            else:
                return {
                    "status": "unhealthy",
                    "message": "Redis ping failed"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Health check failed: {e}"
            }