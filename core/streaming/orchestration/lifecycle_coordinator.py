import asyncio
import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime, timezone
from ..orchestration.service_orchestrator import ServiceOrchestrator

logger = logging.getLogger(__name__)


class LifecycleCoordinator:
    """Coordinates lifecycle management across multiple service orchestrators."""
    
    def __init__(self):
        self._orchestrators: Dict[str, ServiceOrchestrator] = {}
        self._shutdown_handlers: List[Callable[[], asyncio.Future]] = []
        self._startup_hooks: List[Callable[[], asyncio.Future]] = []
        self._running = False
        self._start_time: Optional[datetime] = None
    
    def register_orchestrator(self, orchestrator: ServiceOrchestrator) -> None:
        """Register a service orchestrator."""
        service_name = orchestrator.service_name
        if service_name in self._orchestrators:
            logger.warning(f"Orchestrator {service_name} already registered, replacing")
        
        self._orchestrators[service_name] = orchestrator
        logger.info(f"Registered orchestrator for {service_name}")
    
    def add_startup_hook(self, hook: Callable[[], asyncio.Future]) -> None:
        """Add a startup hook to be called during startup."""
        self._startup_hooks.append(hook)
    
    def add_shutdown_handler(self, handler: Callable[[], asyncio.Future]) -> None:
        """Add a shutdown handler to be called during shutdown."""
        self._shutdown_handlers.append(handler)
    
    async def start_all(self, start_order: Optional[List[str]] = None) -> None:
        """Start all registered orchestrators."""
        if self._running:
            logger.warning("Lifecycle coordinator already running")
            return
        
        logger.info("Starting lifecycle coordinator")
        self._start_time = datetime.now(timezone.utc)
        
        # Execute startup hooks
        if self._startup_hooks:
            logger.info(f"Executing {len(self._startup_hooks)} startup hooks")
            for hook in self._startup_hooks:
                try:
                    await hook()
                except Exception as e:
                    logger.error(f"Startup hook failed: {e}")
                    raise
        
        # Determine start order
        if start_order:
            # Use specified order
            orchestrator_names = [name for name in start_order if name in self._orchestrators]
            # Add any remaining orchestrators
            orchestrator_names.extend([
                name for name in self._orchestrators.keys() 
                if name not in orchestrator_names
            ])
        else:
            # Default order (alphabetical)
            orchestrator_names = sorted(self._orchestrators.keys())
        
        # Start orchestrators in order
        for service_name in orchestrator_names:
            orchestrator = self._orchestrators[service_name]
            logger.info(f"Starting orchestrator: {service_name}")
            try:
                await orchestrator.start()
                logger.info(f"Successfully started: {service_name}")
            except Exception as e:
                logger.error(f"Failed to start {service_name}: {e}")
                # Stop any already started orchestrators
                await self._emergency_shutdown()
                raise
        
        self._running = True
        logger.info("All orchestrators started successfully")
    
    async def stop_all(self, stop_order: Optional[List[str]] = None) -> None:
        """Stop all orchestrators gracefully."""
        if not self._running:
            logger.warning("Lifecycle coordinator not running")
            return
        
        logger.info("Stopping lifecycle coordinator")
        
        # Determine stop order (reverse of start order by default)
        if stop_order:
            orchestrator_names = [name for name in stop_order if name in self._orchestrators]
            # Add any remaining orchestrators
            orchestrator_names.extend([
                name for name in self._orchestrators.keys() 
                if name not in orchestrator_names
            ])
        else:
            # Reverse alphabetical order
            orchestrator_names = sorted(self._orchestrators.keys(), reverse=True)
        
        # Stop orchestrators in order
        for service_name in orchestrator_names:
            orchestrator = self._orchestrators[service_name]
            logger.info(f"Stopping orchestrator: {service_name}")
            try:
                await orchestrator.stop()
                logger.info(f"Successfully stopped: {service_name}")
            except Exception as e:
                logger.error(f"Error stopping {service_name}: {e}")
                # Continue stopping other services
        
        # Execute shutdown handlers
        if self._shutdown_handlers:
            logger.info(f"Executing {len(self._shutdown_handlers)} shutdown handlers")
            for handler in self._shutdown_handlers:
                try:
                    await handler()
                except Exception as e:
                    logger.error(f"Shutdown handler failed: {e}")
                    # Continue with other handlers
        
        self._running = False
        if self._start_time:
            uptime = datetime.now(timezone.utc) - self._start_time
            logger.info(f"Lifecycle coordinator stopped (uptime: {uptime})")
    
    async def _emergency_shutdown(self) -> None:
        """Emergency shutdown for startup failure recovery."""
        logger.error("Performing emergency shutdown due to startup failure")
        
        # Stop all running orchestrators
        stop_tasks = []
        for orchestrator in self._orchestrators.values():
            if orchestrator.is_running():
                stop_tasks.append(orchestrator.stop())
        
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        
        self._running = False
    
    def get_status(self) -> Dict[str, any]:
        """Get comprehensive status of all orchestrators."""
        uptime = None
        if self._start_time:
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        
        orchestrator_status = {}
        for name, orchestrator in self._orchestrators.items():
            orchestrator_status[name] = orchestrator.get_status()
        
        return {
            "coordinator_running": self._running,
            "uptime_seconds": uptime,
            "registered_orchestrators": len(self._orchestrators),
            "startup_hooks": len(self._startup_hooks),
            "shutdown_handlers": len(self._shutdown_handlers),
            "orchestrators": orchestrator_status
        }
    
    def is_running(self) -> bool:
        """Check if coordinator is running."""
        return self._running
    
    async def restart_orchestrator(self, service_name: str) -> bool:
        """Restart a specific orchestrator."""
        if service_name not in self._orchestrators:
            logger.error(f"Orchestrator {service_name} not registered")
            return False
        
        orchestrator = self._orchestrators[service_name]
        
        try:
            logger.info(f"Restarting orchestrator: {service_name}")
            await orchestrator.stop()
            await orchestrator.start()
            logger.info(f"Successfully restarted: {service_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to restart {service_name}: {e}")
            return False