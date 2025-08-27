"""
Base service class for standardized service lifecycle management.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict
from enum import Enum
from core.monitoring.service_health import ServiceHealthMonitor, HealthStatus


class ServiceStatus(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class BaseService(ABC):
    """Base class for all Alpha Panda services"""
    
    def __init__(self, service_name: str, redis_client=None):
        self.service_name = service_name
        self.logger = logging.getLogger(f"alpha_panda.{service_name}")
        self.status = ServiceStatus.STOPPED
        self._startup_time = None
        self._shutdown_event = asyncio.Event()
        
        # Add health monitoring
        self.health_monitor = ServiceHealthMonitor(service_name, redis_client)
    
    async def start(self) -> None:
        """Start the service with standardized lifecycle"""
        if self.status != ServiceStatus.STOPPED:
            self.logger.warning(f"Service {self.service_name} already started or starting")
            return
        
        self.status = ServiceStatus.STARTING
        self.logger.info(f"Starting {self.service_name}...")
        
        try:
            await self._pre_start()
            await self._start_implementation()
            await self._post_start()
            
            self.status = ServiceStatus.RUNNING
            self._startup_time = asyncio.get_event_loop().time()
            self.logger.info(f"✅ {self.service_name} started successfully")
            
            # Record successful startup
            await self.health_monitor.record_metric(
                "startup",
                True,
                HealthStatus.HEALTHY,
                "Service started successfully"
            )
            
        except Exception as e:
            self.status = ServiceStatus.ERROR
            self.logger.error(f"❌ Failed to start {self.service_name}: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop the service with standardized lifecycle"""
        if self.status in [ServiceStatus.STOPPED, ServiceStatus.STOPPING]:
            return
        
        self.status = ServiceStatus.STOPPING
        self.logger.info(f"Stopping {self.service_name}...")
        
        try:
            self._shutdown_event.set()
            await self._pre_stop()
            await self._stop_implementation()
            await self._post_stop()
            
            self.status = ServiceStatus.STOPPED
            self.logger.info(f"✅ {self.service_name} stopped successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Error stopping {self.service_name}: {e}")
            self.status = ServiceStatus.ERROR
            # Don't raise during shutdown - just log
    
    @abstractmethod
    async def _start_implementation(self) -> None:
        """Service-specific start implementation"""
        pass
    
    @abstractmethod
    async def _stop_implementation(self) -> None:
        """Service-specific stop implementation"""
        pass
    
    async def _pre_start(self) -> None:
        """Pre-start hook - override if needed"""
        pass
    
    async def _post_start(self) -> None:
        """Post-start hook - override if needed"""
        pass
    
    async def _pre_stop(self) -> None:
        """Pre-stop hook - override if needed"""
        pass
    
    async def _post_stop(self) -> None:
        """Post-stop hook - override if needed"""
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status information"""
        uptime = None
        if self._startup_time and self.status == ServiceStatus.RUNNING:
            uptime = asyncio.get_event_loop().time() - self._startup_time
        
        return {
            "service_name": self.service_name,
            "status": self.status.value,
            "uptime_seconds": uptime
        }
    
    def is_running(self) -> bool:
        """Check if service is running"""
        return self.status == ServiceStatus.RUNNING
    
    async def _monitor_health(self):
        """Background health monitoring task"""
        while not self._shutdown_event.is_set():
            try:
                # Record uptime metric
                if self._startup_time:
                    uptime = asyncio.get_event_loop().time() - self._startup_time
                    await self.health_monitor.record_metric(
                        "uptime_seconds",
                        uptime,
                        HealthStatus.HEALTHY
                    )
                
                # Service-specific health checks
                await self._perform_health_checks()
                
                # Wait before next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                await self.health_monitor.record_metric(
                    "health_check_error",
                    str(e),
                    HealthStatus.UNHEALTHY,
                    f"Health check failed: {e}"
                )
    
    async def _perform_health_checks(self):
        """Service-specific health checks - override in subclasses"""
        pass
    
    async def get_health(self) -> Dict[str, Any]:
        """Get current health status"""
        return await self.health_monitor.get_current_health()