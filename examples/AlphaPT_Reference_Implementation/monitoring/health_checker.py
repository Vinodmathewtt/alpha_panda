"""System health monitoring for AlphaPT."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.events import EventBusCore
from core.logging import get_monitoring_logger

logger = get_monitoring_logger("health_checker")


class HealthStatus(str, Enum):
    """Health status enumeration."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Health check configuration."""

    name: str
    component: str
    check_function: Callable[[], Any]
    timeout: float = 5.0
    critical: bool = True
    enabled: bool = True


@dataclass
class HealthResult:
    """Health check result."""

    name: str
    component: str
    status: HealthStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "component": self.component,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class HealthChecker:
    """System health checker."""

    def __init__(
        self, settings: Settings, db_manager: Optional[DatabaseManager] = None, event_bus: Optional[EventBusCore] = None
    ):
        self.settings = settings
        self.db_manager = db_manager
        self.event_bus = event_bus

        self.health_checks: List[HealthCheck] = []
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        self._last_results: Dict[str, HealthResult] = {}

        # Register default health checks
        self._register_default_checks()

    def _register_default_checks(self) -> None:
        """Register default health checks."""

        # Database health checks
        if self.db_manager:
            self.health_checks.extend(
                [
                    HealthCheck(
                        name="postgres_connection",
                        component="database",
                        check_function=self._check_postgres_health,
                        critical=True,
                    ),
                    HealthCheck(
                        name="clickhouse_connection",
                        component="database",
                        check_function=self._check_clickhouse_health,
                        critical=True,
                    ),
                    HealthCheck(
                        name="redis_connection",
                        component="database",
                        check_function=self._check_redis_health,
                        critical=False,
                    ),
                ]
            )

        # Event bus health check
        if self.event_bus:
            self.health_checks.append(
                HealthCheck(
                    name="nats_connection", component="event_bus", check_function=self._check_nats_health, critical=True
                )
            )

        # System health checks
        self.health_checks.extend(
            [
                HealthCheck(
                    name="memory_usage", component="system", check_function=self._check_memory_usage, critical=False
                ),
                HealthCheck(
                    name="disk_space", component="system", check_function=self._check_disk_space, critical=False
                ),
            ]
        )

        # Strategy health checks
        self.health_checks.extend(
            [
                HealthCheck(
                    name="strategy_health",
                    component="strategies",
                    check_function=self._check_strategy_health,
                    critical=True,
                ),
            ]
        )

    async def start(self) -> None:
        """Start health checker."""
        if self._running:
            return

        if self.settings.monitoring.health_check_enabled:
            # Start periodic health checks
            self._check_task = asyncio.create_task(self._periodic_health_check())

        self._running = True
        logger.info("Health checker started")

    async def stop(self) -> None:
        """Stop health checker."""
        if not self._running:
            return

        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
            self._check_task = None

        self._running = False
        logger.info("Health checker stopped")

    def add_health_check(self, health_check: HealthCheck) -> None:
        """Add a custom health check."""
        self.health_checks.append(health_check)
        logger.info(f"Added health check: {health_check.name}")

    def remove_health_check(self, name: str) -> bool:
        """Remove a health check by name."""
        for i, check in enumerate(self.health_checks):
            if check.name == name:
                del self.health_checks[i]
                logger.info(f"Removed health check: {name}")
                return True
        return False

    async def run_health_check(self, check: HealthCheck) -> HealthResult:
        """Run a single health check."""
        if not check.enabled:
            return HealthResult(
                name=check.name, component=check.component, status=HealthStatus.UNKNOWN, message="Health check disabled"
            )

        start_time = datetime.now(timezone.utc)

        try:
            # Run check with timeout
            if asyncio.iscoroutinefunction(check.check_function):
                result = await asyncio.wait_for(check.check_function(), timeout=check.timeout)
            else:
                result = await asyncio.wait_for(asyncio.to_thread(check.check_function), timeout=check.timeout)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            # Interpret result
            if isinstance(result, bool):
                status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
                message = "Check passed" if result else "Check failed"
                details = None
            elif isinstance(result, dict):
                status_str = result.get("status", "unknown")
                status = HealthStatus(status_str) if status_str in HealthStatus else HealthStatus.UNKNOWN
                message = result.get("message", "No message provided")
                details = result.get("details")
            else:
                status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
                message = str(result) if result else "Check failed"
                details = None

            return HealthResult(
                name=check.name,
                component=check.component,
                status=status,
                message=message,
                details=details,
                timestamp=start_time,
                duration_ms=duration,
            )

        except asyncio.TimeoutError:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            return HealthResult(
                name=check.name,
                component=check.component,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out after {check.timeout}s",
                timestamp=start_time,
                duration_ms=duration,
                error="timeout",
            )

        except Exception as e:
            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.error(f"Health check {check.name} failed", error=e)
            return HealthResult(
                name=check.name,
                component=check.component,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                timestamp=start_time,
                duration_ms=duration,
                error=str(e),
            )

    async def run_all_health_checks(self) -> Dict[str, HealthResult]:
        """Run all health checks."""
        results = {}

        # Run all checks concurrently
        tasks = []
        for check in self.health_checks:
            if check.enabled:
                task = asyncio.create_task(self.run_health_check(check))
                tasks.append((check.name, task))

        # Wait for all checks to complete
        for name, task in tasks:
            try:
                result = await task
                results[name] = result
                self._last_results[name] = result
            except Exception as e:
                logger.error(f"Failed to run health check {name}", error=e)
                results[name] = HealthResult(
                    name=name,
                    component="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Failed to execute check: {str(e)}",
                    error=str(e),
                )

        return results

    async def get_overall_health(self) -> Dict[str, Any]:
        """Get overall system health status."""
        results = await self.run_all_health_checks()

        # Determine overall status
        critical_failures = []
        non_critical_failures = []
        healthy_count = 0
        degraded_count = 0

        for check in self.health_checks:
            if check.name in results:
                result = results[check.name]

                if result.status == HealthStatus.HEALTHY:
                    healthy_count += 1
                elif result.status == HealthStatus.DEGRADED:
                    degraded_count += 1
                    if check.critical:
                        critical_failures.append(result)
                    else:
                        non_critical_failures.append(result)
                elif result.status == HealthStatus.UNHEALTHY:
                    if check.critical:
                        critical_failures.append(result)
                    else:
                        non_critical_failures.append(result)

        # Calculate overall status
        if critical_failures:
            overall_status = HealthStatus.UNHEALTHY
        elif non_critical_failures or degraded_count > 0:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return {
            "status": overall_status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {name: result.to_dict() for name, result in results.items()},
            "summary": {
                "total_checks": len(self.health_checks),
                "healthy": healthy_count,
                "degraded": degraded_count,
                "unhealthy": len(critical_failures) + len(non_critical_failures),
                "critical_failures": len(critical_failures),
                "non_critical_failures": len(non_critical_failures),
            },
        }

    async def _periodic_health_check(self) -> None:
        """Periodic health check task."""
        logger.info("Periodic health check task started")

        while self._running:
            try:
                await asyncio.sleep(self.settings.monitoring.health_check_interval)

                # Run health checks
                health_status = await self.get_overall_health()

                # Log health status
                overall_status = health_status["status"]
                summary = health_status["summary"]

                if overall_status == "healthy":
                    logger.debug(
                        "Health check completed",
                        status=overall_status,
                        total_checks=summary["total_checks"],
                        healthy=summary["healthy"],
                    )
                else:
                    logger.warning(
                        "Health check detected issues",
                        status=overall_status,
                        total_checks=summary["total_checks"],
                        healthy=summary["healthy"],
                        degraded=summary["degraded"],
                        unhealthy=summary["unhealthy"],
                        critical_failures=summary["critical_failures"],
                    )

                # Publish health event if event bus is available
                if self.event_bus:
                    try:
                        from core.events import get_event_publisher, SystemEvent, EventType
                        from datetime import datetime, timezone
                        import uuid

                        publisher = get_event_publisher(self.event_bus.settings)
                        
                        # Create and publish system health event
                        health_event = SystemEvent(
                            event_id=str(uuid.uuid4()),
                            event_type=EventType.HEALTH_CHECK,
                            timestamp=datetime.now(timezone.utc),
                            source="health_checker",
                            component="health_checker",
                            severity="INFO" if overall_status == "healthy" else "WARNING",
                            message=f"Health check completed with status: {overall_status}",
                            status=overall_status,
                            metrics=summary,
                        )
                        
                        # Publish the event
                        await publisher.publish("health.check", health_event)
                    except Exception as e:
                        logger.warning("Failed to publish health event", error=e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Periodic health check error", error=e)

        logger.info("Periodic health check task stopped")

    # Default health check functions
    async def _check_postgres_health(self) -> Dict[str, Any]:
        """Check PostgreSQL database health."""
        if not self.db_manager:
            return {"status": "unknown", "message": "Database manager not available"}

        try:
            health_status = await self.db_manager.health_check()
            postgres_status = health_status.get("postgres", {})

            if postgres_status.get("healthy"):
                return {"status": "healthy", "message": "PostgreSQL connection is healthy", "details": postgres_status}
            else:
                return {
                    "status": "unhealthy",
                    "message": f"PostgreSQL connection failed: {postgres_status.get('error', 'Unknown error')}",
                    "details": postgres_status,
                }
        except Exception as e:
            return {"status": "unhealthy", "message": f"PostgreSQL health check failed: {str(e)}"}

    async def _check_clickhouse_health(self) -> Dict[str, Any]:
        """Check ClickHouse database health."""
        if not self.db_manager:
            return {"status": "unknown", "message": "Database manager not available"}

        try:
            health_status = await self.db_manager.health_check()
            clickhouse_status = health_status.get("clickhouse", {})

            if clickhouse_status.get("healthy"):
                return {
                    "status": "healthy",
                    "message": "ClickHouse connection is healthy",
                    "details": clickhouse_status,
                }
            else:
                return {
                    "status": "unhealthy",
                    "message": f"ClickHouse connection failed: {clickhouse_status.get('error', 'Unknown error')}",
                    "details": clickhouse_status,
                }
        except Exception as e:
            return {"status": "unhealthy", "message": f"ClickHouse health check failed: {str(e)}"}

    async def _check_redis_health(self) -> Dict[str, Any]:
        """Check Redis health."""
        if not self.db_manager:
            return {"status": "unknown", "message": "Database manager not available"}

        try:
            health_status = await self.db_manager.health_check()
            redis_status = health_status.get("redis", {})

            if redis_status.get("healthy"):
                return {"status": "healthy", "message": "Redis connection is healthy", "details": redis_status}
            else:
                return {
                    "status": "degraded",  # Redis is not critical
                    "message": f"Redis connection failed: {redis_status.get('error', 'Unknown error')}",
                    "details": redis_status,
                }
        except Exception as e:
            return {"status": "degraded", "message": f"Redis health check failed: {str(e)}"}

    async def _check_nats_health(self) -> Dict[str, Any]:
        """Check NATS event bus health."""
        if not self.event_bus:
            return {"status": "unknown", "message": "Event bus not available"}

        try:
            # Use the new EventBusCore's connection status
            if self.event_bus.is_connected:
                connection_details = {
                    "connected": True,
                    "nats_url": self.event_bus.settings.nats_url if hasattr(self.event_bus, 'settings') else "unknown"
                }
                return {"status": "healthy", "message": "NATS connection is healthy", "details": connection_details}
            else:
                return {
                    "status": "unhealthy",
                    "message": "NATS connection is not established",
                    "details": {"connected": False},
                }
        except Exception as e:
            return {"status": "unhealthy", "message": f"NATS health check failed: {str(e)}"}

    def _check_memory_usage(self) -> Dict[str, Any]:
        """Check system memory usage."""
        try:
            import psutil

            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            threshold = self.settings.monitoring.memory_alert_threshold * 100

            if memory_percent < threshold:
                status = "healthy"
                message = f"Memory usage is normal ({memory_percent:.1f}%)"
            else:
                status = "degraded"
                message = f"Memory usage is high ({memory_percent:.1f}%)"

            return {
                "status": status,
                "message": message,
                "details": {
                    "used_percent": memory_percent,
                    "used_gb": memory.used / (1024**3),
                    "total_gb": memory.total / (1024**3),
                    "available_gb": memory.available / (1024**3),
                    "threshold_percent": threshold,
                },
            }
        except Exception as e:
            return {"status": "unknown", "message": f"Memory check failed: {str(e)}"}

    def _check_disk_space(self) -> Dict[str, Any]:
        """Check disk space usage."""
        try:
            import psutil

            # Check disk usage for the application directory
            disk_usage = psutil.disk_usage(str(self.settings.base_dir))
            used_percent = (disk_usage.used / disk_usage.total) * 100

            threshold = self.settings.monitoring.disk_alert_threshold * 100

            if used_percent < threshold:
                status = "healthy"
                message = f"Disk usage is normal ({used_percent:.1f}%)"
            else:
                status = "degraded"
                message = f"Disk usage is high ({used_percent:.1f}%)"

            return {
                "status": status,
                "message": message,
                "details": {
                    "used_percent": used_percent,
                    "used_gb": disk_usage.used / (1024**3),
                    "total_gb": disk_usage.total / (1024**3),
                    "free_gb": disk_usage.free / (1024**3),
                    "threshold_percent": threshold,
                },
            }
        except Exception as e:
            return {"status": "unknown", "message": f"Disk space check failed: {str(e)}"}

    def get_last_results(self) -> Dict[str, HealthResult]:
        """Get last health check results."""
        return self._last_results.copy()

    def is_running(self) -> bool:
        """Check if health checker is running."""
        return self._running

    async def _check_strategy_health(self) -> Dict[str, Any]:
        """Check overall strategy health from strategy manager."""
        try:
            # Try to get strategy health from global strategy manager
            # This would be injected or imported in a real implementation
            from strategy_manager.strategy_health_monitor import (
                get_strategy_health_monitor,
            )

            try:
                # Only attempt to get the monitor if it's already initialized
                # (avoiding the ValueError when settings/event_bus are required)
                monitor = get_strategy_health_monitor()
                summary = await monitor.get_health_summary()

                if summary and "error" not in summary:
                    healthy_percentage = summary.get("overall_health_percentage", 0)
                    total_strategies = summary.get("total_strategies", 0)
                    critical_count = summary.get("critical", 0)
                    failed_count = summary.get("failed", 0)

                    if failed_count > 0:
                        return {
                            "status": "critical",
                            "message": f"{failed_count} strategies failed",
                            "details": summary,
                        }
                    elif critical_count > 0:
                        return {
                            "status": "degraded",
                            "message": f"{critical_count} strategies in critical state",
                            "details": summary,
                        }
                    elif healthy_percentage >= 90:
                        return {
                            "status": "healthy",
                            "message": f"All {total_strategies} strategies healthy ({healthy_percentage:.1f}%)",
                            "details": summary,
                        }
                    else:
                        return {
                            "status": "degraded",
                            "message": f"Strategy health degraded ({healthy_percentage:.1f}%)",
                            "details": summary,
                        }
                else:
                    return {"status": "unknown", "message": "Strategy health monitoring unavailable"}
            except ValueError as e:
                # Strategy health monitor not initialized (requires settings/event_bus)
                return {"status": "unknown", "message": f"Strategy health monitor not initialized: {str(e)}"}
            except Exception as e:
                # Other strategy health monitor errors
                return {"status": "unknown", "message": "Strategy health monitor not available"}

        except Exception as e:
            return {"status": "unknown", "message": f"Strategy health check failed: {str(e)}"}
