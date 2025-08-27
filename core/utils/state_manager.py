# Generic Redis-backed state management base class

import json
import redis.asyncio as redis
from typing import Optional, Dict, Any, List, Union
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from core.config.settings import Settings
from core.utils.exceptions import RedisError, InfrastructureError


class BaseStateManager(ABC):
    """
    Base class for Redis-backed state management with namespace support.
    
    Provides common patterns for Redis operations including:
    - Connection management with automatic initialization
    - Namespace-based key generation for broker segregation
    - Consistent error handling with structured exceptions
    - Connection lifecycle management
    """
    
    def __init__(self, settings: Settings, redis_client=None):
        self.settings = settings
        self.redis_client = redis_client
        self.namespace = None
        
    async def initialize(self, namespace: str = None):
        """Initialize Redis client connection with optional namespace"""
        try:
            if not self.redis_client:
                self.redis_client = redis.from_url(self.settings.redis.url, decode_responses=True)
            self.namespace = namespace
        except Exception as e:
            raise RedisError(f"Failed to initialize Redis connection: {e}", operation="initialize")

    def _get_key(self, key_type: str, identifier: str) -> str:
        """
        Generate standardized Redis key with namespace support.
        
        Args:
            key_type: Type of data being stored (e.g., 'portfolio', 'risk', 'position')
            identifier: Unique identifier for the specific item
            
        Returns:
            Namespaced Redis key string
        """
        base_key = f"{self._get_service_prefix()}:{key_type}:{identifier}"
        if self.namespace:
            return f"{self.namespace}:{base_key}"
        return base_key
    
    @abstractmethod
    def _get_service_prefix(self) -> str:
        """Return the service-specific prefix for Redis keys (e.g., 'portfolio', 'risk')"""
        pass

    async def _get_value(self, key: str) -> Optional[str]:
        """Get a single value from Redis with error handling"""
        try:
            if not self.redis_client:
                await self.initialize()
            return await self.redis_client.get(key)
        except Exception as e:
            raise RedisError(f"Failed to get key {key}: {e}", operation="get", key=key)

    async def _set_value(self, key: str, value: Union[str, int, float], ttl: Optional[int] = None):
        """Set a single value in Redis with optional TTL"""
        try:
            if not self.redis_client:
                await self.initialize()
            await self.redis_client.set(key, value)
            if ttl:
                await self.redis_client.expire(key, ttl)
        except Exception as e:
            raise RedisError(f"Failed to set key {key}: {e}", operation="set", key=key)

    async def _increment_value(self, key: str, amount: int = 1, ttl: Optional[int] = None) -> int:
        """Atomically increment a value in Redis with optional TTL"""
        try:
            if not self.redis_client:
                await self.initialize()
            result = await self.redis_client.incr(key, amount)
            if ttl:
                await self.redis_client.expire(key, ttl)
            return result
        except Exception as e:
            raise RedisError(f"Failed to increment key {key}: {e}", operation="incr", key=key)

    async def _get_multiple_values(self, keys: List[str]) -> Dict[str, Optional[str]]:
        """Get multiple values from Redis efficiently"""
        try:
            if not self.redis_client:
                await self.initialize()
            if not keys:
                return {}
            values = await self.redis_client.mget(keys)
            return dict(zip(keys, values))
        except Exception as e:
            raise RedisError(f"Failed to get multiple keys: {e}", operation="mget")

    async def _get_keys_by_pattern(self, pattern: str) -> List[str]:
        """Get keys matching a pattern"""
        try:
            if not self.redis_client:
                await self.initialize()
            return await self.redis_client.keys(pattern)
        except Exception as e:
            raise RedisError(f"Failed to get keys by pattern {pattern}: {e}", operation="keys")

    async def _delete_key(self, key: str) -> bool:
        """Delete a key from Redis"""
        try:
            if not self.redis_client:
                await self.initialize()
            result = await self.redis_client.delete(key)
            return result > 0
        except Exception as e:
            raise RedisError(f"Failed to delete key {key}: {e}", operation="delete", key=key)

    async def _set_json_value(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None):
        """Set a JSON-serialized value in Redis"""
        try:
            json_value = json.dumps(value)
            await self._set_value(key, json_value, ttl)
        except (TypeError, ValueError) as e:
            raise RedisError(f"Failed to serialize JSON for key {key}: {e}", operation="set_json", key=key)

    async def _get_json_value(self, key: str) -> Optional[Dict[str, Any]]:
        """Get and deserialize a JSON value from Redis"""
        try:
            value = await self._get_value(key)
            if value:
                return json.loads(value)
            return None
        except (TypeError, ValueError, json.JSONDecodeError) as e:
            raise RedisError(f"Failed to deserialize JSON for key {key}: {e}", operation="get_json", key=key)

    async def close(self):
        """Close Redis connection"""
        try:
            if self.redis_client:
                await self.redis_client.aclose()
        except Exception as e:
            raise RedisError(f"Failed to close Redis connection: {e}", operation="close")

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on Redis connection"""
        try:
            if not self.redis_client:
                await self.initialize()
            
            # Simple ping test
            await self.redis_client.ping()
            
            return {
                "redis_connected": True,
                "namespace": self.namespace,
                "service_prefix": self._get_service_prefix(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "redis_connected": False,
                "error": str(e),
                "namespace": self.namespace,
                "service_prefix": self._get_service_prefix(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    async def clear_namespace_data(self, confirm_namespace: str):
        """
        Clear all data for the current namespace (dangerous operation).
        
        Args:
            confirm_namespace: Must match current namespace for safety
        """
        if not self.namespace or confirm_namespace != self.namespace:
            raise ValueError(f"Namespace confirmation required. Expected: {self.namespace}")
        
        try:
            pattern = f"{self.namespace}:{self._get_service_prefix()}:*"
            keys = await self._get_keys_by_pattern(pattern)
            if keys:
                await self.redis_client.delete(*keys)
                return len(keys)
            return 0
        except Exception as e:
            raise RedisError(f"Failed to clear namespace data: {e}", operation="clear_namespace")


class KeyValueStateManager(BaseStateManager):
    """
    Simple key-value state manager for storing individual values.
    
    Suitable for:
    - Configuration values
    - Counters and metrics
    - Simple state flags
    """
    
    def __init__(self, service_prefix: str, settings: Settings, redis_client=None):
        super().__init__(settings, redis_client)
        self.service_prefix = service_prefix
    
    def _get_service_prefix(self) -> str:
        return self.service_prefix
    
    async def get_value(self, key: str) -> Optional[str]:
        """Get a string value"""
        redis_key = self._get_key("value", key)
        return await self._get_value(redis_key)
    
    async def set_value(self, key: str, value: Union[str, int, float], ttl: Optional[int] = None):
        """Set a value with optional TTL"""
        redis_key = self._get_key("value", key)
        await self._set_value(redis_key, value, ttl)
    
    async def increment_counter(self, key: str, amount: int = 1, ttl: Optional[int] = None) -> int:
        """Increment a counter"""
        redis_key = self._get_key("counter", key)
        return await self._increment_value(redis_key, amount, ttl)
    
    async def get_counter(self, key: str) -> int:
        """Get counter value"""
        redis_key = self._get_key("counter", key)
        value = await self._get_value(redis_key)
        return int(value) if value else 0


class DocumentStateManager(BaseStateManager):
    """
    Document-based state manager for storing complex JSON objects.
    
    Suitable for:
    - Portfolio states
    - Complex configurations
    - Aggregated data structures
    """
    
    def __init__(self, service_prefix: str, settings: Settings, redis_client=None):
        super().__init__(settings, redis_client)
        self.service_prefix = service_prefix
    
    def _get_service_prefix(self) -> str:
        return self.service_prefix
    
    async def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get a JSON document"""
        redis_key = self._get_key("document", document_id)
        return await self._get_json_value(redis_key)
    
    async def save_document(self, document_id: str, document: Dict[str, Any], ttl: Optional[int] = None):
        """Save a JSON document"""
        redis_key = self._get_key("document", document_id)
        await self._set_json_value(redis_key, document, ttl)
    
    async def update_document_field(self, document_id: str, field_path: str, value: Any):
        """Update a specific field in a document"""
        document = await self.get_document(document_id) or {}
        
        # Support nested field paths like "stats.trades.count"
        keys = field_path.split('.')
        current = document
        for key in keys[:-1]:
            current = current.setdefault(key, {})
        current[keys[-1]] = value
        
        await self.save_document(document_id, document)
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document"""
        redis_key = self._get_key("document", document_id)
        return await self._delete_key(redis_key)


class CollectionStateManager(BaseStateManager):
    """
    Collection-based state manager for storing multiple related items.
    
    Suitable for:
    - Position collections
    - Trade history
    - Time series data
    """
    
    def __init__(self, service_prefix: str, settings: Settings, redis_client=None):
        super().__init__(settings, redis_client)
        self.service_prefix = service_prefix
    
    def _get_service_prefix(self) -> str:
        return self.service_prefix
    
    async def get_collection(self, collection_id: str) -> Dict[str, Any]:
        """Get all items in a collection"""
        pattern = self._get_key("collection", f"{collection_id}:*")
        keys = await self._get_keys_by_pattern(pattern)
        
        if not keys:
            return {}
        
        values = await self._get_multiple_values(keys)
        result = {}
        
        for key, value in values.items():
            if value is not None:
                # Extract item ID from key
                item_id = key.split(":")[-1]
                try:
                    result[item_id] = json.loads(value)
                except json.JSONDecodeError:
                    result[item_id] = value
        
        return result
    
    async def get_collection_item(self, collection_id: str, item_id: str) -> Optional[Any]:
        """Get a specific item from a collection"""
        redis_key = self._get_key("collection", f"{collection_id}:{item_id}")
        value = await self._get_value(redis_key)
        
        if value is None:
            return None
        
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    
    async def set_collection_item(self, collection_id: str, item_id: str, 
                                value: Any, ttl: Optional[int] = None):
        """Set an item in a collection"""
        redis_key = self._get_key("collection", f"{collection_id}:{item_id}")
        
        if isinstance(value, (dict, list)):
            await self._set_json_value(redis_key, value, ttl)
        else:
            await self._set_value(redis_key, value, ttl)
    
    async def remove_collection_item(self, collection_id: str, item_id: str) -> bool:
        """Remove an item from a collection"""
        redis_key = self._get_key("collection", f"{collection_id}:{item_id}")
        return await self._delete_key(redis_key)
    
    async def get_collection_size(self, collection_id: str) -> int:
        """Get the number of items in a collection"""
        pattern = self._get_key("collection", f"{collection_id}:*")
        keys = await self._get_keys_by_pattern(pattern)
        return len(keys)


# Convenience factory functions
def create_kv_state_manager(service_name: str, settings: Settings, redis_client=None) -> KeyValueStateManager:
    """Create a key-value state manager for simple values"""
    return KeyValueStateManager(service_name, settings, redis_client)


def create_document_state_manager(service_name: str, settings: Settings, redis_client=None) -> DocumentStateManager:
    """Create a document state manager for complex JSON objects"""
    return DocumentStateManager(service_name, settings, redis_client)


def create_collection_state_manager(service_name: str, settings: Settings, redis_client=None) -> CollectionStateManager:
    """Create a collection state manager for related items"""
    return CollectionStateManager(service_name, settings, redis_client)