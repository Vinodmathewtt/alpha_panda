# alphaP/app/main.py

import asyncio
import signal
import sys
import logging

from core.logging import configure_logging, get_logger
from app.containers import AppContainer
from core.health import SystemHealthMonitor
from core.config.validator import validate_startup_configuration
from core.streaming.lifecycle_manager import shutdown_all_streaming_components

class ApplicationOrchestrator:
    """Main application orchestrator with pre-flight health checks."""

    def __init__(self):
        self.container = AppContainer()
        self._shutdown_event = asyncio.Event()
        
        # Provide the shutdown event to the container
        self.container.shutdown_event.override(self._shutdown_event)
        
        # Wire the container to the modules that need DI
        self.container.wire(modules=[__name__, "core.health", "api.dependencies"])

        self.settings = self.container.settings()
        configure_logging(self.settings)
        self.logger = get_logger("alpha_panda.main")
        
        # --- ENHANCED: Multi-broker startup logging ---
        self.logger.info(f"🏢 Alpha Panda initializing with active brokers: {self.settings.active_brokers}")
        
        # Validate broker configuration
        self._validate_broker_configuration()

        self.health_monitor: SystemHealthMonitor = self.container.system_health_monitor()
    
    def _validate_broker_configuration(self):
        """Validate that all active brokers are properly configured."""
        for broker in self.settings.active_brokers:
            if broker == "zerodha":
                if not self.settings.zerodha.api_key or not self.settings.zerodha.api_secret:
                    self.logger.warning(f"Zerodha broker active but credentials not configured")
            
            self.logger.info(f"✅ Broker '{broker}' configuration validated")

    async def startup(self):
        """Initialize application with proper startup sequence."""
        self.logger.info("🚀 Initializing application with comprehensive validation...")

        # PRODUCTION SAFETY: Fail fast on default secrets in production
        if hasattr(self.settings, 'environment') and self.settings.environment == "production":
            if hasattr(self.settings, 'auth') and hasattr(self.settings.auth, 'secret_key'):
                if self.settings.auth.secret_key == "your-secret-key-change-in-production":
                    self.logger.critical("FATAL: Default secret_key is being used in a production environment. Shutting down.")
                    sys.exit(1)

        # CRITICAL ADDITION: Validate configuration before proceeding
        try:
            config_valid = await validate_startup_configuration(self.settings)
            if not config_valid:
                self.logger.error("❌ Configuration validation failed - cannot proceed with startup")
                # Clean up any resources created during container wiring
                await self._cleanup_partial_initialization()
                raise RuntimeError("Configuration validation failed - check logs for details")
        except Exception as e:
            # If validation itself fails, still try cleanup
            await self._cleanup_partial_initialization()
            raise
        
        self.logger.info("✅ Configuration validation passed")

        # --- CRITICAL FIX: Initialize database and auth service BEFORE health checks ---
        # This fixes the authentication startup order issue
        
        # Step 1: Initialize database and wait for readiness
        db_manager = self.container.db_manager()
        await db_manager.init()
        
        # ENHANCED: Wait for database to be fully ready
        await db_manager.wait_for_ready(timeout=30)
        self.logger.info("✅ Database initialized and verified ready")

        # Step 2: Start auth service to establish/load session
        auth_service = self.container.auth_service()
        await auth_service.start()
        self.logger.info("✅ Authentication service started")

        # Step 3: Now run health checks (auth service can properly check session)
        self.logger.info("🚀 Conducting system pre-flight health checks...")
        is_healthy = await self.health_monitor.run_checks()

        for result in self.health_monitor.results:
            if result.passed:
                self.logger.info(f"✅ Health check PASSED for {result.component}: {result.message}")
            else:
                self.logger.error(f"❌ Health check FAILED for {result.component}: {result.message}")

        if not is_healthy:
            self.logger.critical("System health checks failed. Application will not start.")
            self.logger.critical("Please fix the configuration or infrastructure issues above and restart.")
            # Clean up any resources that may have been initialized during DI container wiring
            await self._cleanup_partial_initialization()
            sys.exit(1) # Exit with a non-zero code to indicate failure

        self.logger.info("✅ All health checks passed. Proceeding with remaining service startup...")

        # --- START REMAINING SERVICES (auth service already started) ---
        all_services = self.container.lifespan_services()
        # Filter out auth_service since it's already started
        remaining_services = [s for s in all_services if s is not auth_service]
        await asyncio.gather(*(service.start() for service in remaining_services if service))
        self.logger.info("✅ All services started successfully.")
    
    async def _cleanup_partial_initialization(self):
        """Clean up resources that may have been initialized during container wiring."""
        self.logger.info("🧹 Cleaning up partially initialized resources...")
        
        cleanup_tasks = []
        
        try:
            # Try to get services that might have been partially initialized
            services = []
            try:
                services = self.container.lifespan_services()
            except Exception:
                pass  # Container might not be fully initialized
            
            # Stop any services that were created (in reverse order)
            for service in reversed(services):
                if service and hasattr(service, 'stop'):
                    cleanup_tasks.append(self._safe_service_stop(service, type(service).__name__))
            
            # Clean up database manager if it was initialized
            try:
                db_manager = self.container.db_manager()
                if db_manager and hasattr(db_manager, 'shutdown'):
                    cleanup_tasks.append(self._safe_db_shutdown(db_manager))
            except Exception:
                pass  # DB manager might not be initialized
            
            # Wait for all cleanup tasks with timeout
            if cleanup_tasks:
                try:
                    await asyncio.wait_for(asyncio.gather(*cleanup_tasks, return_exceptions=True), timeout=10.0)
                except asyncio.TimeoutError:
                    self.logger.warning("⚠️ Cleanup timeout - some resources may not be fully cleaned up")
                
        except Exception as e:
            self.logger.warning(f"Error during partial initialization cleanup: {e}")
        
        self.logger.info("✅ Partial cleanup completed")
    
    async def _safe_service_stop(self, service, service_name: str):
        """Safely stop a service with proper error handling."""
        try:
            await service.stop()
            self.logger.info(f"✅ Stopped {service_name} during cleanup")
        except Exception as e:
            self.logger.warning(f"⚠️ Error stopping {service_name} during cleanup: {e}")
    
    async def _safe_db_shutdown(self, db_manager):
        """Safely shutdown database manager with proper error handling."""
        try:
            await db_manager.shutdown()
            self.logger.info("✅ Database manager shutdown during cleanup")
        except Exception as e:
            self.logger.warning(f"⚠️ Error shutting down database during cleanup: {e}")

    async def shutdown(self):
        """Gracefully shutdown application."""
        self.logger.info("🛑 Shutting down Alpha Panda application...")

        services = self.container.lifespan_services()
        try:
            await asyncio.gather(*(service.stop() for service in reversed(services) if service))
        except asyncio.CancelledError:
            self.logger.warning("Shutdown process was cancelled. Attempting to force stop services.")
            for service in reversed(services):
                if service and hasattr(service, 'stop'):
                    try:
                        await service.stop()
                    except Exception as e:
                        self.logger.warning(f"Error during forced service shutdown: {e}")
        except Exception as e:
            self.logger.error(f"Error during service shutdown: {e}")
        finally:
            try:
                # Shutdown streaming components first to prevent unclosed producer warnings
                await shutdown_all_streaming_components(timeout=5.0)
                
                db_manager = self.container.db_manager()
                await db_manager.shutdown()
                self.logger.info("✅ Alpha Panda application shutdown complete.")
            except Exception as e:
                self.logger.error(f"Error during database shutdown: {e}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        try:
            self.logger.info(f"Received shutdown signal: {signal.strsignal(signum)}")
            self._shutdown_event.set()
        except Exception as e:
            # Fallback to stderr if logging fails during shutdown
            print(f"Error in signal handler: {e}", file=sys.stderr)
            self._shutdown_event.set()  # Still try to trigger shutdown

    async def run(self):
        """Run the application until shutdown."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            await self.startup()
            self.logger.info("Application is now running. Press Ctrl+C to exit.")
            await self._shutdown_event.wait()
        finally:
            await self.shutdown()

async def main():
    """Application entry point"""
    app = ApplicationOrchestrator()
    await app.run()

if __name__ == "__main__":
    asyncio.run(main())