"""
Health check system for Alpha Panda services.
Provides comprehensive health monitoring for all components.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union
import psutil

from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.logging import get_monitoring_logger_safe
from core.monitoring.alerting import (
    get_alert_manager, 
    AlertSeverity, 
    AlertCategory,
    send_critical_alert,
    send_auth_failure_alert
)


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


class ServiceHealthChecker:
    """Enhanced health checker for Alpha Panda services."""
    
    def __init__(
        self, 
        settings: Settings, 
        db_manager: Optional[DatabaseManager] = None,
        redis_client=None,
        kafka_producer=None,
        kafka_consumer=None,
        auth_service=None
    ):
        self.settings = settings
        self.db_manager = db_manager
        self.redis_client = redis_client
        self.kafka_producer = kafka_producer
        self.kafka_consumer = kafka_consumer
        self.auth_service = auth_service
        
        self.health_checks: List[HealthCheck] = []
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        self._last_results: Dict[str, HealthResult] = {}
        
        self.logger = get_monitoring_logger_safe("health_checker")
        
        # Alert manager integration
        self.alert_manager = get_alert_manager(settings)
        
        # Register default health checks
        self._register_default_checks()
    
    def _register_default_checks(self) -> None:
        """Register default health checks for Alpha Panda components."""
        
        # CRITICAL: Zerodha Authentication Check (must be first)
        self.health_checks.append(
            HealthCheck(
                name="zerodha_authentication",
                component="authentication",
                check_function=self._check_zerodha_auth_health,
                critical=True,
            )
        )
        
        # Database health checks
        if self.db_manager:
            self.health_checks.append(
                HealthCheck(
                    name="postgres_connection",
                    component="database",
                    check_function=self._check_postgres_health,
                    critical=True,
                )
            )
        
        # Redis health checks
        if self.redis_client:
            self.health_checks.append(
                HealthCheck(
                    name="redis_connection",
                    component="cache",
                    check_function=self._check_redis_health,
                    critical=False,
                )
            )
        
        # Kafka/Redpanda health checks
        if self.kafka_producer or self.kafka_consumer:
            self.health_checks.extend([
                HealthCheck(
                    name="kafka_producer",
                    component="streaming",
                    check_function=self._check_kafka_producer_health,
                    critical=True,
                ),
                HealthCheck(
                    name="kafka_consumer",
                    component="streaming", 
                    check_function=self._check_kafka_consumer_health,
                    critical=True,
                ),
                HealthCheck(
                    name="consumer_lag",
                    component="streaming",
                    check_function=self._check_consumer_lag,
                    critical=False,
                ),
            ])
        
        # System health checks
        self.health_checks.extend([
            HealthCheck(
                name="memory_usage",
                component="system",
                check_function=self._check_memory_usage,
                critical=False,
            ),
            HealthCheck(
                name="disk_space",
                component="system",
                check_function=self._check_disk_space,
                critical=False,
            ),
            HealthCheck(
                name="cpu_usage",
                component="system",
                check_function=self._check_cpu_usage,
                critical=False,
            ),
        ])
        
        # Pipeline flow monitoring
        if self.settings.monitoring.pipeline_flow_monitoring_enabled:
            self.health_checks.extend([
                HealthCheck(
                    name="market_data_flow",
                    component="pipeline",
                    check_function=self._check_market_data_flow,
                    critical=True,
                ),
                HealthCheck(
                    name="signal_generation_flow", 
                    component="pipeline",
                    check_function=self._check_signal_generation_flow,
                    critical=True,
                ),
                HealthCheck(
                    name="order_flow",
                    component="pipeline",
                    check_function=self._check_order_flow,
                    critical=True,
                ),
            ])
    
    async def start(self) -> None:
        """Start health checker."""
        if self._running:
            return

        if self.settings.monitoring.health_check_enabled:
            self._check_task = asyncio.create_task(self._periodic_health_check())

        self._running = True
        self.logger.info("Health checker started", 
                        checks_enabled=len([c for c in self.health_checks if c.enabled]),
                        interval=self.settings.monitoring.health_check_interval)

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
        self.logger.info("Health checker stopped")
    
    async def run_health_check(self, check: HealthCheck) -> HealthResult:
        """Run a single health check."""
        if not check.enabled:
            return HealthResult(
                name=check.name,
                component=check.component,
                status=HealthStatus.UNKNOWN,
                message="Health check disabled"
            )

        start_time = datetime.now(timezone.utc)

        try:
            # Run check with timeout
            if asyncio.iscoroutinefunction(check.check_function):
                result = await asyncio.wait_for(check.check_function(), timeout=check.timeout)
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(check.check_function), timeout=check.timeout
                )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            # Interpret result
            if isinstance(result, bool):
                status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
                message = "Check passed" if result else "Check failed"
                details = None
            elif isinstance(result, dict):
                status_str = result.get("status", "unknown")
                status = HealthStatus(status_str) if status_str in HealthStatus.__members__ else HealthStatus.UNKNOWN
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
            self.logger.error("Health check failed", 
                            check_name=check.name, 
                            component=check.component,
                            error=str(e))
            return HealthResult(
                name=check.name,
                component=check.component,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                timestamp=start_time,
                duration_ms=duration,
                error=str(e),
            )
    
    async def get_overall_health(self) -> Dict[str, Any]:
        """Get overall system health status."""
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
                self.logger.error("Failed to run health check", 
                                check_name=name, error=str(e))
                results[name] = HealthResult(
                    name=name,
                    component="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Failed to execute check: {str(e)}",
                    error=str(e),
                )
        
        # Calculate overall status
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
            "active_brokers": self.settings.active_brokers,
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
        self.logger.info("Periodic health check started")

        while self._running:
            try:
                await asyncio.sleep(self.settings.monitoring.health_check_interval)

                # Run health checks
                health_status = await self.get_overall_health()

                # Log health status
                overall_status = health_status["status"]
                summary = health_status["summary"]

                if overall_status == "healthy":
                    self.logger.debug("Health check completed",
                                    status=overall_status,
                                    brokers=self.settings.active_brokers,
                                    **summary)
                else:
                    self.logger.warning("Health check detected issues",
                                      status=overall_status,
                                      brokers=self.settings.active_brokers,
                                      **summary)
                    
                    # Send alerts for critical issues
                    await self._send_health_alerts(health_status)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Periodic health check error", error=str(e))

        self.logger.info("Periodic health check stopped")
    
    async def _send_health_alerts(self, health_status: Dict[str, Any]):
        """Send alerts for critical health check failures"""
        checks = health_status.get("checks", {})
        overall_status = health_status.get("status", "unknown")
        brokers = health_status.get("active_brokers", [])
        
        # Send critical alert for overall unhealthy status
        if overall_status == "unhealthy":
            await self.alert_manager.send_alert(
                title="System Health Check Failed",
                message=f"Alpha Panda system health check failed for brokers {brokers}",
                severity=AlertSeverity.CRITICAL,
                category=AlertCategory.SYSTEM,
                component="health_checker",
                broker_namespace=",".join(brokers),
                details={
                    "overall_status": overall_status,
                    "active_brokers": brokers,
                    "summary": health_status.get("summary", {}),
                    "timestamp": health_status.get("timestamp")
                }
            )
        
        # Send specific alerts for critical component failures
        for check_name, result in checks.items():
            result_status = result.get("status", "unknown")
            component_name = result.get("component", "unknown")
            
            # Critical component failures
            if result_status == "unhealthy":
                severity = AlertSeverity.CRITICAL
                category = self._get_alert_category_for_component(component_name)
                
                await self.alert_manager.send_alert(
                    title=f"{component_name.title()} Health Check Failed",
                    message=result.get("message", f"{check_name} health check failed"),
                    severity=severity,
                    category=category,
                    component=component_name,
                    broker_namespace=broker,
                    details=result
                )
            
            # Authentication failures get special handling
            elif check_name == "zerodha_authentication" and result_status != "healthy":
                await self.alert_manager.authentication_alert(
                    title="Zerodha Authentication Failure",
                    message=result.get("message", "Zerodha authentication check failed"),
                    component="authentication",
                    broker_namespace=broker,
                    details=result
                )
    
    def _get_alert_category_for_component(self, component: str) -> AlertCategory:
        """Get appropriate alert category for component"""
        category_mapping = {
            "authentication": AlertCategory.AUTHENTICATION,
            "database": AlertCategory.SYSTEM,
            "cache": AlertCategory.SYSTEM,
            "streaming": AlertCategory.PIPELINE,
            "system": AlertCategory.SYSTEM,
            "pipeline": AlertCategory.PIPELINE
        }
        return category_mapping.get(component, AlertCategory.SYSTEM)
    
    # Health check implementations
    async def _check_postgres_health(self) -> Dict[str, Any]:
        """Check PostgreSQL database health."""
        if not self.db_manager:
            return {"status": "unknown", "message": "Database manager not available"}

        try:
            async with self.db_manager.get_session() as session:
                # Simple query to check connection
                result = await session.execute("SELECT 1")
                await result.fetchone()
                
            return {
                "status": "healthy",
                "message": "PostgreSQL connection is healthy",
                "details": {"connection_pool": "active"}
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"PostgreSQL connection failed: {str(e)}"
            }
    
    async def _check_redis_health(self) -> Dict[str, Any]:
        """Check Redis health."""
        if not self.redis_client:
            return {"status": "unknown", "message": "Redis client not available"}

        try:
            # Test Redis ping
            await self.redis_client.ping()
            return {
                "status": "healthy",
                "message": "Redis connection is healthy",
                "details": {"ping": "successful"}
            }
        except Exception as e:
            return {
                "status": "degraded",  # Redis is not critical for core pipeline
                "message": f"Redis connection failed: {str(e)}"
            }
    
    async def _check_kafka_producer_health(self) -> Dict[str, Any]:
        """Check Kafka producer health."""
        if not self.kafka_producer:
            return {"status": "unknown", "message": "Kafka producer not available"}

        try:
            # Check if producer is properly initialized and connected
            if hasattr(self.kafka_producer, '_closed') and self.kafka_producer._closed:
                return {
                    "status": "unhealthy",
                    "message": "Kafka producer is closed"
                }
            
            return {
                "status": "healthy",
                "message": "Kafka producer is healthy",
                "details": {"state": "connected"}
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Kafka producer check failed: {str(e)}"
            }
    
    async def _check_kafka_consumer_health(self) -> Dict[str, Any]:
        """Check Kafka consumer health."""
        if not self.kafka_consumer:
            return {"status": "unknown", "message": "Kafka consumer not available"}

        try:
            # Check consumer status
            if hasattr(self.kafka_consumer, '_closed') and self.kafka_consumer._closed:
                return {
                    "status": "unhealthy",
                    "message": "Kafka consumer is closed"
                }
                
            return {
                "status": "healthy",
                "message": "Kafka consumer is healthy",
                "details": {"state": "connected"}
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Kafka consumer check failed: {str(e)}"
            }
    
    async def _check_consumer_lag(self) -> Dict[str, Any]:
        """Check consumer lag across all partitions."""
        if not self.kafka_consumer:
            return {"status": "unknown", "message": "Kafka consumer not available"}

        try:
            # This is a simplified implementation
            # In production, you'd check actual lag metrics
            max_lag = 0  # Placeholder
            
            if max_lag > self.settings.monitoring.consumer_lag_threshold:
                return {
                    "status": "degraded",
                    "message": f"Consumer lag is high ({max_lag} messages)",
                    "details": {"max_lag": max_lag, "threshold": self.settings.monitoring.consumer_lag_threshold}
                }
            
            return {
                "status": "healthy",
                "message": f"Consumer lag is normal ({max_lag} messages)",
                "details": {"max_lag": max_lag}
            }
        except Exception as e:
            return {
                "status": "unknown",
                "message": f"Consumer lag check failed: {str(e)}"
            }
    
    def _check_memory_usage(self) -> Dict[str, Any]:
        """Check system memory usage."""
        try:
            memory = psutil.virtual_memory()
            memory_percent = memory.percent / 100

            if memory_percent < self.settings.monitoring.memory_alert_threshold:
                status = "healthy"
                message = f"Memory usage is normal ({memory.percent:.1f}%)"
            else:
                status = "degraded"
                message = f"Memory usage is high ({memory.percent:.1f}%)"

            return {
                "status": status,
                "message": message,
                "details": {
                    "used_percent": memory.percent,
                    "used_gb": round(memory.used / (1024**3), 2),
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "threshold_percent": self.settings.monitoring.memory_alert_threshold * 100,
                },
            }
        except Exception as e:
            return {"status": "unknown", "message": f"Memory check failed: {str(e)}"}
    
    def _check_disk_space(self) -> Dict[str, Any]:
        """Check disk space usage."""
        try:
            disk_usage = psutil.disk_usage(self.settings.base_dir)
            used_percent = (disk_usage.used / disk_usage.total)

            if used_percent < self.settings.monitoring.disk_alert_threshold:
                status = "healthy"
                message = f"Disk usage is normal ({used_percent*100:.1f}%)"
            else:
                status = "degraded"
                message = f"Disk usage is high ({used_percent*100:.1f}%)"

            return {
                "status": status,
                "message": message,
                "details": {
                    "used_percent": round(used_percent * 100, 1),
                    "used_gb": round(disk_usage.used / (1024**3), 2),
                    "total_gb": round(disk_usage.total / (1024**3), 2),
                    "free_gb": round(disk_usage.free / (1024**3), 2),
                    "threshold_percent": self.settings.monitoring.disk_alert_threshold * 100,
                },
            }
        except Exception as e:
            return {"status": "unknown", "message": f"Disk space check failed: {str(e)}"}
    
    def _check_cpu_usage(self) -> Dict[str, Any]:
        """Check CPU usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_threshold = self.settings.monitoring.cpu_alert_threshold * 100

            if cpu_percent < cpu_threshold:
                status = "healthy"
                message = f"CPU usage is normal ({cpu_percent:.1f}%)"
            else:
                status = "degraded"
                message = f"CPU usage is high ({cpu_percent:.1f}%)"

            return {
                "status": status,
                "message": message,
                "details": {
                    "cpu_percent": cpu_percent,
                    "threshold_percent": cpu_threshold,
                    "cpu_count": psutil.cpu_count(),
                    "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None,
                },
            }
        except Exception as e:
            return {"status": "unknown", "message": f"CPU check failed: {str(e)}"}
    
    # Pipeline flow health checks
    async def _check_market_data_flow(self) -> Dict[str, Any]:
        """Check if market data is flowing through the pipeline."""
        if not self.redis_client:
            return {
                "status": "unknown",
                "message": "Redis client not available for market data flow check"
            }
        
        try:
            # Check for recent market tick activity in Redis metrics
            market_tick_key = "alpha_panda:metrics:market_ticks:last_processed"
            last_processed = await self.redis_client.get(market_tick_key)
            
            if not last_processed:
                return {
                    "status": "degraded",
                    "message": "No recent market data activity found",
                    "details": {
                        "last_market_tick": None,
                        "check_time": datetime.now(timezone.utc).isoformat()
                    }
                }
            
            # Parse last processed timestamp
            last_tick_time = datetime.fromisoformat(last_processed.decode('utf-8'))
            time_since_last = (datetime.now(timezone.utc) - last_tick_time).total_seconds()
            
            # Market data should be received within the last 30 seconds during market hours
            max_age_seconds = 30
            
            if time_since_last > max_age_seconds:
                return {
                    "status": "degraded",
                    "message": f"Market data is stale ({time_since_last:.1f}s old)",
                    "details": {
                        "last_market_tick": last_tick_time.isoformat(),
                        "age_seconds": time_since_last,
                        "max_age_seconds": max_age_seconds
                    }
                }
            
            # Check tick count in the last minute
            tick_count_key = "alpha_panda:metrics:market_ticks:count_last_minute"
            tick_count = await self.redis_client.get(tick_count_key)
            tick_count = int(tick_count) if tick_count else 0
            
            return {
                "status": "healthy",
                "message": f"Market data flowing normally ({tick_count} ticks/min)",
                "details": {
                    "last_market_tick": last_tick_time.isoformat(),
                    "age_seconds": time_since_last,
                    "ticks_per_minute": tick_count,
                    "flow_rate": "normal" if tick_count > 10 else "low"
                }
            }
            
        except Exception as e:
            return {
                "status": "unknown",
                "message": f"Market data flow check failed: {str(e)}"
            }
    
    async def _check_signal_generation_flow(self) -> Dict[str, Any]:
        """Check if signals are being generated by strategies."""
        if not self.redis_client:
            return {
                "status": "unknown",
                "message": "Redis client not available for signal generation flow check"
            }
        
        try:
            # Check for recent signal generation activity
            signals_key = f"alpha_panda:metrics:{self.settings.broker_namespace}:signals:last_generated"
            last_signal = await self.redis_client.get(signals_key)
            
            # Get signal count in the last 5 minutes
            signal_count_key = f"alpha_panda:metrics:{self.settings.broker_namespace}:signals:count_last_5min"
            signal_count = await self.redis_client.get(signal_count_key)
            signal_count = int(signal_count) if signal_count else 0
            
            if not last_signal:
                # No signals might be normal during low volatility
                return {
                    "status": "healthy",
                    "message": "No recent signals generated (may be normal during low volatility)",
                    "details": {
                        "last_signal_time": None,
                        "signals_last_5min": signal_count,
                        "broker": self.settings.broker_namespace
                    }
                }
            
            last_signal_time = datetime.fromisoformat(last_signal.decode('utf-8'))
            time_since_last = (datetime.now(timezone.utc) - last_signal_time).total_seconds()
            
            # Signals can be infrequent, so allow up to 5 minutes
            max_age_seconds = 300
            
            if time_since_last > max_age_seconds and signal_count == 0:
                return {
                    "status": "degraded",
                    "message": f"No signals generated in {max_age_seconds/60:.1f} minutes",
                    "details": {
                        "last_signal_time": last_signal_time.isoformat(),
                        "age_seconds": time_since_last,
                        "signals_last_5min": signal_count,
                        "broker": self.settings.broker_namespace
                    }
                }
            
            return {
                "status": "healthy",
                "message": f"Signal generation active ({signal_count} signals in 5min)",
                "details": {
                    "last_signal_time": last_signal_time.isoformat(),
                    "age_seconds": time_since_last,
                    "signals_last_5min": signal_count,
                    "broker": self.settings.broker_namespace,
                    "generation_rate": "normal" if signal_count > 0 else "low"
                }
            }
            
        except Exception as e:
            return {
                "status": "unknown",
                "message": f"Signal generation flow check failed: {str(e)}"
            }
    
    async def _check_order_flow(self) -> Dict[str, Any]:
        """Check if orders are being processed."""
        if not self.redis_client:
            return {
                "status": "unknown",
                "message": "Redis client not available for order flow check"
            }
        
        try:
            # Check for recent order activity
            orders_key = f"alpha_panda:metrics:{self.settings.broker_namespace}:orders:last_processed"
            last_order = await self.redis_client.get(orders_key)
            
            # Get order counts for different statuses
            filled_count_key = f"alpha_panda:metrics:{self.settings.broker_namespace}:orders:filled_last_hour"
            failed_count_key = f"alpha_panda:metrics:{self.settings.broker_namespace}:orders:failed_last_hour"
            
            filled_count = await self.redis_client.get(filled_count_key)
            failed_count = await self.redis_client.get(failed_count_key)
            
            filled_count = int(filled_count) if filled_count else 0
            failed_count = int(failed_count) if failed_count else 0
            total_orders = filled_count + failed_count
            
            if not last_order and total_orders == 0:
                return {
                    "status": "healthy",
                    "message": "No recent order activity (normal during low signal periods)",
                    "details": {
                        "last_order_time": None,
                        "orders_last_hour": 0,
                        "success_rate": 0.0,
                        "broker": self.settings.broker_namespace
                    }
                }
            
            last_order_time = None
            age_seconds = 0
            
            if last_order:
                last_order_time = datetime.fromisoformat(last_order.decode('utf-8'))
                age_seconds = (datetime.now(timezone.utc) - last_order_time).total_seconds()
            
            # Calculate success rate
            success_rate = (filled_count / total_orders * 100) if total_orders > 0 else 100.0
            
            # Determine status based on success rate and activity
            if success_rate < 80 and total_orders > 5:
                status = "degraded"
                message = f"Low order success rate ({success_rate:.1f}%)"
            elif failed_count > filled_count and total_orders > 10:
                status = "degraded"
                message = f"More failed than successful orders ({failed_count}F vs {filled_count}S)"
            else:
                status = "healthy"
                message = f"Order processing normal ({total_orders} orders, {success_rate:.1f}% success)"
            
            return {
                "status": status,
                "message": message,
                "details": {
                    "last_order_time": last_order_time.isoformat() if last_order_time else None,
                    "age_seconds": age_seconds,
                    "orders_last_hour": total_orders,
                    "filled_orders": filled_count,
                    "failed_orders": failed_count,
                    "success_rate": success_rate,
                    "broker": self.settings.broker_namespace
                }
            }
            
        except Exception as e:
            return {
                "status": "unknown",
                "message": f"Order flow check failed: {str(e)}"
            }
    
    async def _check_zerodha_auth_health(self) -> Dict[str, Any]:
        """Check Zerodha authentication health - CRITICAL for all operations."""
        if not self.auth_service:
            return {
                "status": "unhealthy", 
                "message": "Auth service not available - system cannot operate without Zerodha authentication"
            }

        try:
            # Check if authenticated
            is_authenticated = self.auth_service.is_authenticated()
            
            if not is_authenticated:
                return {
                    "status": "unhealthy",
                    "message": "Zerodha authentication is not active - system requires valid Zerodha session",
                    "details": {
                        "authentication_required": True,
                        "provider": "zerodha",
                        "action_required": "Please authenticate with Zerodha before starting the application"
                    }
                }
            
            # Try to get user profile to validate session
            user_profile = await self.auth_service.get_current_user_profile()
            
            if not user_profile:
                return {
                    "status": "unhealthy",
                    "message": "Zerodha session is invalid - cannot retrieve user profile",
                    "details": {
                        "authentication_required": True,
                        "provider": "zerodha",
                        "action_required": "Please re-authenticate with Zerodha"
                    }
                }
            
            return {
                "status": "healthy",
                "message": "Zerodha authentication is active and valid",
                "details": {
                    "provider": "zerodha",
                    "user_id": getattr(user_profile, 'user_id', 'unknown'),
                    "authenticated": True
                }
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Zerodha authentication check failed: {str(e)}",
                "details": {
                    "authentication_required": True,
                    "provider": "zerodha",
                    "error": str(e)
                }
            }