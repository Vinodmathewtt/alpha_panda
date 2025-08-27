import redis.asyncio as redis
from typing import Dict, List, Optional, Any
import json
from datetime import datetime, timedelta
from core.logging.logger import get_logger
from instrument_data.config.settings import InstrumentDataConfig

logger = get_logger(__name__)


class InstrumentRedisRegistry:
    """High-performance Redis-based instrument registry for fast lookups."""
    
    def __init__(self, redis_client: redis.Redis, config: InstrumentDataConfig):
        self.redis = redis_client
        self.config = config
        self.key_prefix = config.redis_key_prefix
        self.expiry_seconds = config.redis_expiry_days * 24 * 3600
    
    async def build_registry_from_instruments(self, instruments: List[Dict], target_tokens: List[int]) -> int:
        """Build Redis registry from filtered instruments with pipelining for performance."""
        if not instruments:
            logger.warning("No instruments provided to build registry")
            return 0
        
        # Filter instruments to target tokens only for performance
        filtered_instruments = []
        if target_tokens:
            target_set = set(target_tokens)
            filtered_instruments = [
                inst for inst in instruments 
                if inst.get('instrument_token') in target_set
            ]
        else:
            filtered_instruments = instruments
        
        if not filtered_instruments:
            logger.warning("No instruments match target tokens")
            return 0
        
        logger.info(f"Building Redis registry for {len(filtered_instruments)} instruments")
        
        # Use pipeline for bulk operations
        pipe = self.redis.pipeline()
        
        # Clear existing registry
        await self._clear_registry_keys(pipe)
        
        # Build registry with optimized structure
        for instrument in filtered_instruments:
            await self._add_instrument_to_pipeline(pipe, instrument)
        
        # Set registry metadata
        metadata = {
            "build_time": datetime.utcnow().isoformat(),
            "total_instruments": len(filtered_instruments),
            "target_tokens_count": len(target_tokens) if target_tokens else 0,
            "source": "database"
        }
        pipe.hset(f"{self.key_prefix}:metadata", mapping=metadata)
        pipe.expire(f"{self.key_prefix}:metadata", self.expiry_seconds)
        
        # Execute all operations
        await pipe.execute()
        
        logger.info(f"Successfully built Redis registry with {len(filtered_instruments)} instruments")
        return len(filtered_instruments)
    
    async def _clear_registry_keys(self, pipe):
        """Clear existing registry keys efficiently."""
        # Get all keys with our prefix
        pattern = f"{self.key_prefix}:*"
        keys = await self.redis.keys(pattern)
        
        if keys:
            pipe.delete(*keys)
    
    async def _add_instrument_to_pipeline(self, pipe, instrument: Dict):
        """Add instrument to Redis pipeline with optimized structure."""
        token = instrument.get('instrument_token')
        if not token:
            return
        
        # Store complete instrument data by token
        token_key = f"{self.key_prefix}:token:{token}"
        pipe.hset(token_key, mapping=self._serialize_instrument(instrument))
        pipe.expire(token_key, self.expiry_seconds)
        
        # Store exchange:symbol lookup
        exchange = instrument.get('exchange', '')
        symbol = instrument.get('tradingsymbol', '')
        if exchange and symbol:
            symbol_key = f"{self.key_prefix}:symbol:{exchange}:{symbol}"
            pipe.set(symbol_key, str(token), ex=self.expiry_seconds)
        
        # Add to searchable index
        name = instrument.get('name', '').upper()
        symbol_upper = symbol.upper()
        
        # Add to search sets for fast lookup
        if name:
            pipe.sadd(f"{self.key_prefix}:search:name:{name[:3]}", token)
            pipe.expire(f"{self.key_prefix}:search:name:{name[:3]}", self.expiry_seconds)
        
        if symbol_upper:
            pipe.sadd(f"{self.key_prefix}:search:symbol:{symbol_upper[:3]}", token)
            pipe.expire(f"{self.key_prefix}:search:symbol:{symbol_upper[:3]}", self.expiry_seconds)
        
        # Add to all tokens set
        pipe.sadd(f"{self.key_prefix}:all_tokens", token)
        pipe.expire(f"{self.key_prefix}:all_tokens", self.expiry_seconds)
    
    def _serialize_instrument(self, instrument: Dict) -> Dict[str, str]:
        """Serialize instrument data for Redis storage."""
        # Convert all values to strings for Redis
        serialized = {}
        for key, value in instrument.items():
            if value is None:
                serialized[key] = ""
            elif isinstance(value, (dict, list)):
                serialized[key] = json.dumps(value)
            else:
                serialized[key] = str(value)
        return serialized
    
    def _deserialize_instrument(self, data: Dict[str, str]) -> Dict[str, Any]:
        """Deserialize instrument data from Redis."""
        if not data:
            return {}
        
        deserialized = {}
        for key, value in data.items():
            if not value:
                deserialized[key] = None
            elif key in ['instrument_token', 'exchange_token', 'lot_size']:
                # Convert numeric fields back to int
                try:
                    deserialized[key] = int(value)
                except (ValueError, TypeError):
                    deserialized[key] = value
            elif key in ['last_price', 'strike', 'tick_size']:
                # Convert price fields back to float
                try:
                    deserialized[key] = float(value)
                except (ValueError, TypeError):
                    deserialized[key] = value
            else:
                deserialized[key] = value
        
        return deserialized
    
    async def get_instrument_by_token(self, token: int) -> Optional[Dict]:
        """Fast Redis lookup by token."""
        key = f"{self.key_prefix}:token:{token}"
        data = await self.redis.hgetall(key)
        
        if not data:
            return None
        
        return self._deserialize_instrument(data)
    
    async def get_instrument_by_symbol(self, exchange: str, symbol: str) -> Optional[Dict]:
        """Fast Redis lookup by exchange:symbol."""
        symbol_key = f"{self.key_prefix}:symbol:{exchange}:{symbol}"
        token_str = await self.redis.get(symbol_key)
        
        if not token_str:
            return None
        
        try:
            token = int(token_str)
            return await self.get_instrument_by_token(token)
        except (ValueError, TypeError):
            return None
    
    async def search_instruments(self, search_term: str, limit: int = 20) -> List[Dict]:
        """Search instruments in registry."""
        if not search_term or len(search_term) < 2:
            return []
        
        search_upper = search_term.upper()
        prefix = search_upper[:3]
        
        # Search in both name and symbol indices
        name_key = f"{self.key_prefix}:search:name:{prefix}"
        symbol_key = f"{self.key_prefix}:search:symbol:{prefix}"
        
        # Get tokens from both search indices
        name_tokens = await self.redis.smembers(name_key)
        symbol_tokens = await self.redis.smembers(symbol_key)
        
        # Combine and deduplicate
        all_tokens = set()
        all_tokens.update(int(t) for t in name_tokens if t.isdigit())
        all_tokens.update(int(t) for t in symbol_tokens if t.isdigit())
        
        # Limit results
        limited_tokens = list(all_tokens)[:limit]
        
        # Fetch instrument details
        results = []
        for token in limited_tokens:
            instrument = await self.get_instrument_by_token(token)
            if instrument:
                # Filter results that actually match the search term
                name = instrument.get('name', '').upper()
                symbol = instrument.get('tradingsymbol', '').upper()
                
                if search_upper in name or search_upper in symbol:
                    results.append(instrument)
        
        return results[:limit]
    
    async def get_all_registered_tokens(self) -> List[int]:
        """Get all tokens in registry."""
        key = f"{self.key_prefix}:all_tokens"
        tokens = await self.redis.smembers(key)
        
        return [int(token) for token in tokens if token.isdigit()]
    
    async def is_token_registered(self, token: int) -> bool:
        """Check if token is registered."""
        key = f"{self.key_prefix}:token:{token}"
        return await self.redis.exists(key) > 0
    
    async def clear_registry(self) -> None:
        """Clear entire registry."""
        pattern = f"{self.key_prefix}:*"
        keys = await self.redis.keys(pattern)
        
        if keys:
            await self.redis.delete(*keys)
            logger.info(f"Cleared {len(keys)} registry keys")
    
    async def get_registry_size(self) -> int:
        """Get registry size."""
        key = f"{self.key_prefix}:all_tokens"
        return await self.redis.scard(key)
    
    async def validate_registry(self) -> Dict[str, Any]:
        """Validate registry integrity."""
        issues = []
        
        # Check if registry exists
        metadata_key = f"{self.key_prefix}:metadata"
        if not await self.redis.exists(metadata_key):
            issues.append("Registry metadata not found")
        
        # Check token count consistency
        size = await self.get_registry_size()
        if size == 0:
            issues.append("Registry is empty")
        
        # Sample check - validate a few random tokens
        tokens = await self.get_all_registered_tokens()
        if tokens:
            sample_size = min(5, len(tokens))
            sample_tokens = tokens[:sample_size]
            
            for token in sample_tokens:
                instrument = await self.get_instrument_by_token(token)
                if not instrument:
                    issues.append(f"Token {token} not found in registry")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "size": size,
            "sample_tokens_checked": len(sample_tokens) if tokens else 0
        }
    
    async def get_registry_metadata(self) -> Dict[str, Any]:
        """Get registry metadata and statistics."""
        metadata_key = f"{self.key_prefix}:metadata"
        metadata = await self.redis.hgetall(metadata_key)
        
        if not metadata:
            return {"error": "Registry metadata not found"}
        
        # Add current statistics
        size = await self.get_registry_size()
        
        return {
            "build_time": metadata.get("build_time"),
            "total_instruments": int(metadata.get("total_instruments", 0)),
            "target_tokens_count": int(metadata.get("target_tokens_count", 0)),
            "source": metadata.get("source"),
            "current_size": size,
            "redis_expiry_days": self.config.redis_expiry_days
        }