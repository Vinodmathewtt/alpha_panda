"""
Redis-based event deduplication service for exactly-once processing guarantees.

This module provides event deduplication capabilities to prevent duplicate processing
of events across service restarts and consumer rebalancing scenarios.
"""

import redis.asyncio as redis
from typing import Optional, Dict, Any
import json
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)


class EventDeduplicator:
    """Redis-based event deduplication with TTL for memory efficiency"""
    
    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 3600):
        """
        Initialize deduplicator with Redis client and TTL.
        
        Args:
            redis_client: Async Redis client
            ttl_seconds: Time-to-live for deduplication records (default: 1 hour)
        """
        self.redis = redis_client
        self.ttl = ttl_seconds
        self._stats = {
            "total_checks": 0,
            "duplicates_found": 0,
            "marked_processed": 0,
            "errors": 0
        }
    
    async def is_duplicate(self, event_id: str) -> bool:
        """
        Check if event was already processed.
        
        Args:
            event_id: Unique event identifier from EventEnvelope.id
            
        Returns:
            True if event was already processed, False otherwise
        """
        try:
            self._stats["total_checks"] += 1
            key = f"event_processed:{event_id}"
            exists = await self.redis.exists(key)
            
            if exists:
                self._stats["duplicates_found"] += 1
                logger.debug(f"Duplicate event detected: {event_id}")
                return True
            
            return False
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Error checking event deduplication for {event_id}: {e}")
            # Default to not duplicate to avoid blocking processing
            return False
    
    async def mark_processed(self, event_id: str, metadata: Dict[str, Any] = None) -> None:
        """
        Mark event as processed with TTL.
        
        Args:
            event_id: Unique event identifier
            metadata: Optional processing metadata for debugging
        """
        try:
            self._stats["marked_processed"] += 1
            key = f"event_processed:{event_id}"
            value = json.dumps({
                "processed_at": datetime.utcnow().isoformat(),
                "metadata": metadata or {},
                "stats": self._stats.copy()
            })
            
            await self.redis.setex(key, self.ttl, value)
            logger.debug(f"Marked event as processed: {event_id}")
            
        except Exception as e:
            self._stats["errors"] += 1
            logger.error(f"Error marking event as processed {event_id}: {e}")
            # Don't raise - processing should continue even if dedup marking fails
    
    async def get_processing_info(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get processing information for event.
        
        Args:
            event_id: Unique event identifier
            
        Returns:
            Processing metadata if event was processed, None otherwise
        """
        try:
            key = f"event_processed:{event_id}"
            value = await self.redis.get(key)
            return json.loads(value) if value else None
            
        except Exception as e:
            logger.error(f"Error getting processing info for {event_id}: {e}")
            return None
    
    async def cleanup_expired_entries(self) -> int:
        """
        Cleanup expired deduplication entries (Redis handles this automatically with TTL).
        This method is mainly for monitoring purposes.
        
        Returns:
            Number of active deduplication entries
        """
        try:
            pattern = "event_processed:*"
            keys = await self.redis.keys(pattern)
            return len(keys)
            
        except Exception as e:
            logger.error(f"Error during cleanup check: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, int]:
        """Get deduplication statistics for monitoring"""
        return self._stats.copy()
    
    async def reset_stats(self) -> None:
        """Reset statistics counters"""
        self._stats = {
            "total_checks": 0,
            "duplicates_found": 0,
            "marked_processed": 0,
            "errors": 0
        }


class DeduplicationManager:
    """Manager for multiple event deduplicators across services"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self._deduplicators: Dict[str, EventDeduplicator] = {}
    
    def get_deduplicator(self, service_name: str, ttl_seconds: int = 3600) -> EventDeduplicator:
        """
        Get or create deduplicator for a service.
        
        Args:
            service_name: Name of the service (for namespacing)
            ttl_seconds: TTL for deduplication records
            
        Returns:
            EventDeduplicator instance for the service
        """
        if service_name not in self._deduplicators:
            # Create service-specific deduplicator with namespaced keys
            deduplicator = EventDeduplicator(self.redis_client, ttl_seconds)
            # Override key generation to include service namespace
            original_is_duplicate = deduplicator.is_duplicate
            original_mark_processed = deduplicator.mark_processed
            
            async def namespaced_is_duplicate(event_id: str) -> bool:
                namespaced_key = f"{service_name}:event_processed:{event_id}"
                return await self.redis_client.exists(namespaced_key)
            
            async def namespaced_mark_processed(event_id: str, metadata: Dict[str, Any] = None) -> None:
                try:
                    namespaced_key = f"{service_name}:event_processed:{event_id}"
                    value = json.dumps({
                        "service": service_name,
                        "processed_at": datetime.utcnow().isoformat(),
                        "metadata": metadata or {}
                    })
                    await self.redis_client.setex(namespaced_key, ttl_seconds, value)
                except Exception as e:
                    logger.error(f"Error marking event as processed {event_id}: {e}")
            
            deduplicator.is_duplicate = namespaced_is_duplicate
            deduplicator.mark_processed = namespaced_mark_processed
            self._deduplicators[service_name] = deduplicator
        
        return self._deduplicators[service_name]
    
    async def get_global_stats(self) -> Dict[str, Dict[str, int]]:
        """Get statistics across all services"""
        stats = {}
        for service_name, deduplicator in self._deduplicators.items():
            stats[service_name] = deduplicator.get_stats()
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for deduplication system"""
        try:
            # Test Redis connectivity
            await self.redis_client.ping()
            
            # Get active entry counts per service
            service_counts = {}
            for service_name in self._deduplicators.keys():
                pattern = f"{service_name}:event_processed:*"
                keys = await self.redis_client.keys(pattern)
                service_counts[service_name] = len(keys)
            
            return {
                "status": "healthy",
                "redis_connected": True,
                "active_services": list(self._deduplicators.keys()),
                "active_entries_per_service": service_counts,
                "total_active_entries": sum(service_counts.values())
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "redis_connected": False,
                "error": str(e)
            }