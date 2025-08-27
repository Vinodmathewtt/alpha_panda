from typing import Dict, Any, Optional, List
import asyncio
from datetime import datetime
from core.logging.logger import get_logger
from core.database.connection import get_database_manager
from core.config.settings import settings

from instrument_data.config.settings import get_instrument_data_config, InstrumentDataConfig
from instrument_data.cache.redis_registry import InstrumentRedisRegistry
from instrument_data.scheduler.download_scheduler import DownloadScheduler
from instrument_data.utils.target_tokens import TargetTokenManager
from instrument_data.services.instrument_registry_service import get_instrument_registry_service

logger = get_logger(__name__)


class EnhancedInstrumentDataManager:
    """Enhanced orchestrator for instrument data management with smart features."""
    
    def __init__(self):
        self.config: InstrumentDataConfig = get_instrument_data_config()
        self.scheduler: Optional[DownloadScheduler] = None
        self.redis_registry: Optional[InstrumentRedisRegistry] = None
        self.target_manager: Optional[TargetTokenManager] = None
        self.base_service: Optional[Any] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize all components based on configuration and mock mode."""
        try:
            logger.info("Initializing enhanced instrument data manager")
            
            # Always initialize base service
            self.base_service = await get_instrument_registry_service()
            
            # Initialize target token manager
            self.target_manager = TargetTokenManager(self.config.target_tokens_file)
            
            # Initialize Redis components only if not in mock mode and Redis is enabled
            if not settings.mock_market_feed and self.config.enable_redis_caching:
                await self._initialize_redis_components()
            else:
                logger.info("Skipping Redis components - mock mode or Redis disabled")
            
            # Initialize scheduler only if smart scheduling is enabled and not in mock mode
            if not settings.mock_market_feed and self.config.enable_smart_scheduling:
                await self._initialize_scheduler()
            else:
                logger.info("Skipping scheduler - mock mode or smart scheduling disabled")
            
            self._initialized = True
            logger.info("Enhanced instrument data manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize enhanced instrument data manager: {e}")
            raise
    
    async def _initialize_redis_components(self) -> None:
        """Initialize Redis-based components."""
        try:
            # Get Redis client from existing AlphaPT infrastructure
            db_manager = get_database_manager()
            if not db_manager or not hasattr(db_manager, 'redis'):
                logger.warning("Redis not available from database manager")
                return
            
            redis_client = db_manager.redis
            
            # Initialize Redis registry
            self.redis_registry = InstrumentRedisRegistry(redis_client, self.config)
            
            logger.info("Redis components initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis components: {e}")
            # Don't raise - fall back to database-only mode
    
    async def _initialize_scheduler(self) -> None:
        """Initialize download scheduler."""
        try:
            # Get Redis client for scheduler tracking
            db_manager = get_database_manager()
            if not db_manager or not hasattr(db_manager, 'redis'):
                logger.warning("Redis not available for scheduler")
                return
            
            redis_client = db_manager.redis
            self.scheduler = DownloadScheduler(redis_client, self.config)
            
            logger.info("Download scheduler initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize scheduler: {e}")
            # Don't raise - continue without smart scheduling
    
    async def perform_smart_refresh(self, force: bool = False) -> Dict[str, Any]:
        """Intelligent data refresh with scheduling awareness."""
        try:
            if not self._initialized:
                await self.initialize()
            
            # In mock mode, just use base service
            if settings.mock_market_feed:
                logger.info("Mock mode: Using base service refresh")
                return await self.base_service.refresh_from_default_csv()
            
            # Check if smart scheduling is available
            if not self.scheduler:
                logger.info("No scheduler available - performing direct refresh")
                return await self._perform_direct_refresh(force)
            
            # Check scheduling logic
            if not force:
                should_download = await self.scheduler.should_download_today()
                if not should_download:
                    status = await self.scheduler.get_download_status()
                    return {
                        "status": "skipped",
                        "reason": "Not scheduled for today",
                        "download_status": status,
                        "timestamp": datetime.utcnow().isoformat()
                    }
            
            # Perform refresh
            refresh_result = await self._perform_direct_refresh(force)
            
            # Mark download completed if successful
            if refresh_result.get("status") == "success" and self.scheduler:
                instruments_count = refresh_result.get("total_processed", 0)
                await self.scheduler.mark_download_completed(instruments_count)
            
            return refresh_result
            
        except Exception as e:
            logger.error(f"Failed to perform smart refresh: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def _perform_direct_refresh(self, force: bool = False) -> Dict[str, Any]:
        """Perform direct refresh using base service."""
        try:
            # Load from CSV using base service
            refresh_result = await self.base_service.refresh_from_default_csv()
            
            # Rebuild Redis cache if available
            if self.redis_registry:
                await self._rebuild_redis_cache()
                refresh_result["redis_cache_rebuilt"] = True
            
            return refresh_result
            
        except Exception as e:
            logger.error(f"Failed to perform direct refresh: {e}")
            raise
    
    async def _rebuild_redis_cache(self) -> Dict[str, Any]:
        """Rebuild Redis cache from database."""
        try:
            if not self.redis_registry or not self.target_manager:
                return {"error": "Redis registry or target manager not available"}
            
            # Load target tokens
            target_tokens = await self.target_manager.load_target_tokens()
            if not target_tokens:
                logger.warning("No target tokens found - building cache for all instruments")
            
            # Get instruments from database
            # For now, we'll get a reasonable number of instruments
            # In production, this could be optimized to load in batches
            instruments = []
            try:
                # Get sample instruments to build cache
                # This is a simplified approach - could be enhanced to load all instruments in batches
                for token in target_tokens[:100]:  # Limit for performance
                    instrument_dict = await self.base_service.get_instrument_by_token(token)
                    if instrument_dict:
                        instruments.append(instrument_dict)
                
                if not instruments and target_tokens:
                    # Fallback: try to get some instruments by exchange
                    instruments = await self.base_service.get_instruments_by_exchange("NSE", 50)
            
            except Exception as e:
                logger.warning(f"Error loading instruments for cache: {e}")
                return {"error": f"Failed to load instruments: {e}"}
            
            if not instruments:
                return {"error": "No instruments available to build cache"}
            
            # Build Redis registry
            cached_count = await self.redis_registry.build_registry_from_instruments(
                instruments, target_tokens
            )
            
            return {
                "status": "success",
                "cached_instruments": cached_count,
                "target_tokens": len(target_tokens),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to rebuild Redis cache: {e}")
            return {"error": str(e)}
    
    async def rebuild_redis_cache(self) -> Dict[str, Any]:
        """Public method to rebuild Redis cache."""
        return await self._rebuild_redis_cache()
    
    async def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get detailed system status across all components."""
        try:
            status = {
                "timestamp": datetime.utcnow().isoformat(),
                "mock_mode": settings.mock_market_feed,
                "initialized": self._initialized,
                "config": self.config.dict()
            }
            
            # Base service status
            if self.base_service:
                try:
                    base_stats = await self.base_service.get_statistics()
                    status["database"] = base_stats
                except Exception as e:
                    status["database"] = {"error": str(e)}
            
            # Redis registry status
            if self.redis_registry:
                try:
                    registry_metadata = await self.redis_registry.get_registry_metadata()
                    registry_validation = await self.redis_registry.validate_registry()
                    status["redis_registry"] = {
                        "metadata": registry_metadata,
                        "validation": registry_validation
                    }
                except Exception as e:
                    status["redis_registry"] = {"error": str(e)}
            else:
                status["redis_registry"] = {"available": False}
            
            # Scheduler status
            if self.scheduler:
                try:
                    download_status = await self.scheduler.get_download_status()
                    status["scheduler"] = download_status
                except Exception as e:
                    status["scheduler"] = {"error": str(e)}
            else:
                status["scheduler"] = {"available": False}
            
            # Target tokens status
            if self.target_manager:
                try:
                    tokens_validation = await self.target_manager.validate_tokens_file()
                    target_count = await self.target_manager.get_target_count()
                    status["target_tokens"] = {
                        "validation": tokens_validation,
                        "count": target_count
                    }
                except Exception as e:
                    status["target_tokens"] = {"error": str(e)}
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get comprehensive status: {e}")
            return {
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def validate_system_health(self) -> Dict[str, Any]:
        """Comprehensive health check across all components."""
        try:
            health_checks = {
                "timestamp": datetime.utcnow().isoformat(),
                "overall_health": "unknown",
                "components": {}
            }
            
            issues = []
            warnings = []
            
            # Check base service
            try:
                stats = await self.base_service.get_statistics()
                if stats.get("total_instruments", 0) > 0:
                    health_checks["components"]["database"] = "healthy"
                else:
                    health_checks["components"]["database"] = "warning"
                    warnings.append("No instruments in database")
            except Exception as e:
                health_checks["components"]["database"] = "error"
                issues.append(f"Database error: {e}")
            
            # Check Redis registry (if available)
            if self.redis_registry:
                try:
                    validation = await self.redis_registry.validate_registry()
                    if validation.get("valid", False):
                        health_checks["components"]["redis_registry"] = "healthy"
                    else:
                        health_checks["components"]["redis_registry"] = "warning"
                        warnings.extend(validation.get("issues", []))
                except Exception as e:
                    health_checks["components"]["redis_registry"] = "error"
                    issues.append(f"Redis registry error: {e}")
            
            # Check scheduler (if available)
            if self.scheduler:
                try:
                    download_status = await self.scheduler.get_download_status()
                    health_checks["components"]["scheduler"] = "healthy"
                except Exception as e:
                    health_checks["components"]["scheduler"] = "error"
                    issues.append(f"Scheduler error: {e}")
            
            # Check target tokens
            if self.target_manager:
                try:
                    validation = await self.target_manager.validate_tokens_file()
                    if validation.get("valid", False):
                        health_checks["components"]["target_tokens"] = "healthy"
                    else:
                        health_checks["components"]["target_tokens"] = "warning"
                        warnings.extend(validation.get("issues", []))
                except Exception as e:
                    health_checks["components"]["target_tokens"] = "error"
                    issues.append(f"Target tokens error: {e}")
            
            # Determine overall health
            if issues:
                health_checks["overall_health"] = "error"
            elif warnings:
                health_checks["overall_health"] = "warning"
            else:
                health_checks["overall_health"] = "healthy"
            
            health_checks["issues"] = issues
            health_checks["warnings"] = warnings
            
            return health_checks
            
        except Exception as e:
            logger.error(f"Failed to validate system health: {e}")
            return {
                "overall_health": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    async def force_download_fresh_data(self) -> Dict[str, Any]:
        """Force fresh download bypassing schedule."""
        logger.info("Forcing fresh data download")
        return await self.perform_smart_refresh(force=True)
    
    # Proxy methods to base service for backward compatibility
    async def get_instrument_by_token(self, token: int) -> Optional[Dict[str, Any]]:
        """Get instrument by token with Redis cache fallback."""
        if self.redis_registry:
            try:
                # Try Redis first
                instrument = await self.redis_registry.get_instrument_by_token(token)
                if instrument:
                    return instrument
            except Exception as e:
                logger.warning(f"Redis lookup failed, falling back to database: {e}")
        
        # Fallback to database
        return await self.base_service.get_instrument_by_token(token)
    
    async def search_instruments(self, search_term: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search instruments with Redis cache fallback."""
        if self.redis_registry:
            try:
                # Try Redis first
                results = await self.redis_registry.search_instruments(search_term, limit)
                if results:
                    return results
            except Exception as e:
                logger.warning(f"Redis search failed, falling back to database: {e}")
        
        # Fallback to database
        return await self.base_service.search_instruments(search_term, limit)
    
    async def get_registry_tokens(self) -> List[int]:
        """Get registry tokens."""
        return await self.base_service.get_registry_tokens()


# Global enhanced manager instance
_enhanced_manager: Optional[EnhancedInstrumentDataManager] = None


async def get_enhanced_instrument_data_manager() -> EnhancedInstrumentDataManager:
    """Get the global enhanced instrument data manager instance."""
    global _enhanced_manager
    
    if _enhanced_manager is None:
        _enhanced_manager = EnhancedInstrumentDataManager()
        await _enhanced_manager.initialize()
    
    return _enhanced_manager


async def cleanup_enhanced_manager() -> None:
    """Clean up the global enhanced manager."""
    global _enhanced_manager
    
    if _enhanced_manager:
        # Cleanup base service
        if _enhanced_manager.base_service:
            await _enhanced_manager.base_service.cleanup()
        
        _enhanced_manager = None