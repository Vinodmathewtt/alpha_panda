"""Health monitoring and checking for Alpha Panda services."""

# Legacy health check classes (for backward compatibility)
import asyncio
from typing import List, Any, Dict
from pydantic import BaseModel
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from sqlalchemy import text

from core.database.connection import DatabaseManager
from core.config.settings import Settings
from aiokafka.admin import AIOKafkaAdminClient
import redis.asyncio as redis

# Import enhanced health checker
from .health_checker import (
    ServiceHealthChecker,
    HealthCheck as EnhancedHealthCheck,
    HealthResult,
    HealthStatus
)

class HealthCheckResult(BaseModel):
    """Standardized result for a health check."""
    component: str
    passed: bool
    message: str
    details: Optional[Dict[str, Any]] = None

class HealthCheck(ABC):
    """Abstract base class for a single health check."""
    @abstractmethod
    async def check(self) -> HealthCheckResult:
        ...

class DatabaseHealthCheck(HealthCheck):
    """Checks the PostgreSQL database connection."""
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    async def check(self) -> HealthCheckResult:
        try:
            async with self.db_manager.get_session() as session:
                await session.execute(text("SELECT 1"))
            return HealthCheckResult(component="PostgreSQL", passed=True, message="Connection successful.")
        except Exception as e:
            return HealthCheckResult(component="PostgreSQL", passed=False, message=f"Connection failed: {e}")

class RedisHealthCheck(HealthCheck):
    """Checks the Redis connection."""
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client

    async def check(self) -> HealthCheckResult:
        try:
            await self.redis_client.ping()
            return HealthCheckResult(component="Redis", passed=True, message="Connection successful.")
        except Exception as e:
            return HealthCheckResult(component="Redis", passed=False, message=f"Connection failed: {e}")

class RedpandaHealthCheck(HealthCheck):
    """Checks the Redpanda/Kafka connection."""
    def __init__(self, settings: Settings):
        self.settings = settings

    async def check(self) -> HealthCheckResult:
        admin_client = None
        try:
            admin_client = AIOKafkaAdminClient(
                bootstrap_servers=self.settings.redpanda.bootstrap_servers
            )
            await admin_client.start()
            await admin_client.describe_cluster()
            return HealthCheckResult(component="Redpanda", passed=True, message="Connection successful.")
        except Exception as e:
            return HealthCheckResult(component="Redpanda", passed=False, message=f"Connection failed: {e}")
        finally:
            if admin_client:
                await admin_client.close()

class ZerodhaAuthenticationCheck(HealthCheck):
    """Checks that Zerodha authentication is active and valid."""
    def __init__(self, auth_service):
        self.auth_service = auth_service

    async def check(self) -> HealthCheckResult:
        if not self.auth_service:
            return HealthCheckResult(
                component="Zerodha Authentication",
                passed=False,
                message="Auth service not available - system cannot operate without Zerodha authentication."
            )
        
        try:
            # Check if authenticated
            is_authenticated = self.auth_service.is_authenticated()
            
            if not is_authenticated:
                return HealthCheckResult(
                    component="Zerodha Authentication",
                    passed=False,
                    message="Zerodha authentication is not active. System requires valid Zerodha session before startup."
                )
            
            # Validate session by trying to get user profile
            user_profile = await self.auth_service.get_current_user_profile()
            
            if not user_profile:
                return HealthCheckResult(
                    component="Zerodha Authentication",
                    passed=False,
                    message="Zerodha session is invalid - cannot retrieve user profile. Please re-authenticate."
                )
            
            return HealthCheckResult(
                component="Zerodha Authentication", 
                passed=True, 
                message=f"Zerodha authentication is active and valid for user: {getattr(user_profile, 'user_id', 'unknown')}"
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="Zerodha Authentication",
                passed=False,
                message=f"Zerodha authentication check failed: {str(e)}"
            )


class SystemHealthMonitor:
    """Orchestrator for running all system health checks."""
    def __init__(self, checks: List[HealthCheck]):
        self.checks = checks
        self.is_healthy = False
        self.results: List[HealthCheckResult] = []
        self.timings_ms: List[float] = []

    async def run_checks(self) -> bool:
        """Runs all registered health checks concurrently and records durations."""
        import time
        async def _timed(check: HealthCheck):
            start = time.perf_counter()
            res = await check.check()
            dur = (time.perf_counter() - start) * 1000.0
            return res, dur

        timed_results = await asyncio.gather(*(_timed(c) for c in self.checks))
        self.results = [r for r, _ in timed_results]
        self.timings_ms = [d for _, d in timed_results]
        self.is_healthy = all(result.passed for result in self.results)
        return self.is_healthy


# Export both legacy and new health check classes
__all__ = [
    # Legacy classes
    "HealthCheck",
    "HealthCheckResult", 
    "DatabaseHealthCheck",
    "RedisHealthCheck",
    "RedpandaHealthCheck",
    "ZerodhaAuthenticationCheck",
    "SystemHealthMonitor",
    # Enhanced health checker
    "ServiceHealthChecker",
    "EnhancedHealthCheck",
    "HealthResult",
    "HealthStatus"
]
