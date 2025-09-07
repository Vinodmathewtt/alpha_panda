# alphaP/app/main.py

import asyncio
import signal
import sys
import logging

from core.logging import configure_logging, get_logger
from core.observability.tracing import init_tracing
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
        # Route main application logs to the application channel for structured routing
        self.logger = get_logger("alpha_panda.main", component="application")

        # Initialize tracing for background services if enabled (safe no-op otherwise)
        try:
            init_tracing(self.settings, service_name="alpha_panda")
        except Exception:
            pass
        
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
                # Graceful shutdown without stack trace
                sys.exit(1)
        except Exception as e:
            # If validation itself fails, still try cleanup
            await self._cleanup_partial_initialization()
            # Exit cleanly rather than surfacing a traceback to CLI
            self.logger.critical("Startup validation crashed unexpectedly", error=str(e))
            sys.exit(1)
        
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

        ml_feat_result = None
        ml_feat_mismatches = 0
        env_str_for_policy = None
        try:
            _env = getattr(self.settings, 'environment', 'development')
            env_str_for_policy = getattr(_env, 'value', None) or str(_env)
        except Exception:
            env_str_for_policy = "development"

        for result in self.health_monitor.results:
            if result.passed:
                self.logger.info(f"✅ Health check PASSED for {result.component}: {result.message}")
            else:
                self.logger.error(f"❌ Health check FAILED for {result.component}: {result.message}")

            # Track ML Feature Compatibility for enhanced messaging
            try:
                if getattr(result, 'component', '') == "ML Feature Compatibility":
                    ml_feat_result = result
                    # Derive mismatches from details if available
                    det = getattr(result, 'details', None) or {}
                    strategies = det.get('strategies', {}) if isinstance(det, dict) else {}
                    ml_feat_mismatches = sum(1 for _sid, info in strategies.items() if isinstance(info, dict) and info.get('status') == 'mismatch')
            except Exception:
                pass

        # One-line startup summary for market-closed scenario
        try:
            mh = next((r for r in self.health_monitor.results if getattr(r, 'component', '') == "Market Hours"), None)
            if mh and isinstance(getattr(mh, 'message', None), str) and ("closed" in mh.message.lower()):
                self.logger.info("Market closed: services will remain idle; monitoring set to idle")
        except Exception:
            pass

        # Additional clarity for ML feature compatibility in dev/test
        try:
            if ml_feat_result is not None and ml_feat_mismatches > 0:
                self.logger.info(
                    "ML feature compatibility: mismatches detected (dev: proceed, prod: block)",
                    mismatches=ml_feat_mismatches
                )
        except Exception:
            pass

        # Write preflight summary JSON for diagnostics
        try:
            import json as _json
            from datetime import datetime as _dt
            logs_dir = self.settings.logs_dir
            # Normalize environment to a plain string (e.g., "development")
            _env = getattr(self.settings, 'environment', 'unknown')
            try:
                env_str = getattr(_env, 'value', None) or str(_env)
            except Exception:
                env_str = str(_env)
            # Build checks with optional status annotation
            checks_list = []
            for i, r in enumerate(self.health_monitor.results):
                check = {
                    "component": r.component,
                    "passed": bool(r.passed),
                    "message": r.message,
                    "duration_ms": float(self.health_monitor.timings_ms[i]) if i < len(self.health_monitor.timings_ms) else None,
                    "details": getattr(r, 'details', None),
                }
                # Annotate ML Feature Compatibility with a warning status in non-production when mismatches exist
                if r.component == "ML Feature Compatibility":
                    try:
                        det = getattr(r, 'details', None) or {}
                        strategies = det.get('strategies', {}) if isinstance(det, dict) else {}
                        _mm = sum(1 for _sid, info in strategies.items() if isinstance(info, dict) and info.get('status') == 'mismatch')
                    except Exception:
                        _mm = 0
                    if env_str == "production" and _mm > 0:
                        check["status"] = "error"
                    elif env_str != "production" and _mm > 0:
                        check["status"] = "warning"
                    else:
                        check["status"] = "ok"
                checks_list.append(check)

            summary = {
                "timestamp": _dt.utcnow().isoformat() + "Z",
                "environment": env_str,
                "overall_healthy": bool(is_healthy),
                "checks": checks_list,
                # Resolve policy without importing Environment enum to avoid NameError
                "policy": "fail_fast" if env_str == "production" else "warn_dev",
            }
            import os as _os
            _os.makedirs(logs_dir, exist_ok=True)
            with open(_os.path.join(logs_dir, 'preflight_summary.json'), 'w', encoding='utf-8') as f:
                _json.dump(summary, f, indent=2)
        except Exception as _e:
            self.logger.warning("Failed to write preflight summary", error=str(_e))

        if not is_healthy:
            # Provide concise next actions based on failed checks
            next_actions = []
            try:
                # Prefer guidance from consolidated infra check
                infra = next((r for r in self.health_monitor.results if r.component == "infrastructure"), None)
                if infra and getattr(infra, "details", None):
                    for step in infra.details.get("remediation", []) or []:  # type: ignore
                        if step and step not in next_actions:
                            next_actions.append(step)
                # Broker topics guidance
                missing_topics = [r for r in self.health_monitor.results if r.component.startswith("broker_topics") and not r.passed]
                if missing_topics:
                    hint = "After Redpanda is up, run 'make bootstrap' to create topics"
                    if hint not in next_actions:
                        next_actions.append(hint)
                # Generic infra hint if DB/Redis/Redpanda failed but no consolidated guidance
                simple_infra_fail = any(
                    (r.component in ("PostgreSQL", "Redis", "Redpanda")) and not r.passed
                    for r in self.health_monitor.results
                )
                if simple_infra_fail and not any("make up" in s for s in next_actions):
                    next_actions.append("Start infra: 'make up' or 'docker compose up -d'")
            except Exception:
                pass

            if next_actions:
                self.logger.info("Next actions to fix startup", steps=next_actions)
            self.logger.critical("System health checks failed. Application will not start.")
            self.logger.critical("Please fix the configuration or infrastructure issues above and restart.")
            # Clean up any resources that may have been initialized during DI container wiring
            await self._cleanup_partial_initialization()
            sys.exit(1) # Exit with a non-zero code to indicate failure

        self.logger.info("✅ All health checks passed. Proceeding with remaining service startup...")

        # --- Resolve effective trading enablement (transition model) ---
        # Defaults: paper=True, zerodha=False; explicit False wins; legacy shim honored for paper
        paper_enabled = self.settings.is_paper_trading_enabled()
        zerodha_enabled = self.settings.is_zerodha_trading_enabled()

        # Log effective configuration and sources
        self.logger.info(
            "Effective trading enablement resolved",
            paper_enabled=paper_enabled,
            zerodha_enabled=zerodha_enabled,
            active_brokers=self.settings.active_brokers,
        )
        # Emit concise per-service enablement summary and transition guidance
        try:
            brokers = list(self.settings.active_brokers)
            paper_started_intent = bool(paper_enabled and ("paper" in brokers))
            zerodha_started_intent = bool(zerodha_enabled and ("zerodha" in brokers))
            self.logger.info(
                "Service enablement summary",
                service="PaperTradingService",
                enabled=bool(paper_enabled),
                active_brokers=[b for b in brokers if b == "paper"],
                started=paper_started_intent,
                reason=None if paper_started_intent else ("TRADING__PAPER__ENABLED=false" if not paper_enabled else "broker not in ACTIVE_BROKERS")
            )
            self.logger.info(
                "Service enablement summary",
                service="ZerodhaTradingService",
                enabled=bool(zerodha_enabled),
                active_brokers=[b for b in brokers if b == "zerodha"],
                started=zerodha_started_intent,
                reason=None if zerodha_started_intent else ("TRADING__ZERODHA__ENABLED=false" if not zerodha_enabled else "broker not in ACTIVE_BROKERS")
            )
            # One-time transition note when ACTIVE_BROKERS includes a disabled broker
            if ("zerodha" in brokers and not zerodha_enabled) or ("paper" in brokers and not paper_enabled):
                self.logger.info(
                    "Transition note: ACTIVE_BROKERS includes a broker with trading disabled; fan-out/validator remain multi-broker"
                )
        except Exception:
            pass
        if (paper_enabled is False) and (zerodha_enabled is False):
            self.logger.warning(
                "All trading services disabled (paper=false, zerodha=false). Auth/feed will run; no orders will be placed."
            )

        # --- START REMAINING SERVICES (auth service already started) ---
        all_services = self.container.lifespan_services()

        # Apply gating: only start trading services when enabled AND broker active
        def _allow(service_obj) -> bool:
            name = type(service_obj).__name__
            if name == "PaperTradingService":
                return paper_enabled and ("paper" in self.settings.active_brokers)
            if name == "ZerodhaTradingService":
                return zerodha_enabled and ("zerodha" in self.settings.active_brokers)
            return True

        # Log explicit skips for transparency
        skipped = []
        for s in all_services:
            if not s:
                continue
            name = type(s).__name__
            if name == "PaperTradingService":
                if not paper_enabled:
                    skipped.append((name, "TRADING__PAPER__ENABLED=false"))
                elif "paper" not in self.settings.active_brokers:
                    skipped.append((name, "broker not in ACTIVE_BROKERS"))
            elif name == "ZerodhaTradingService":
                if not zerodha_enabled:
                    skipped.append((name, "TRADING__ZERODHA__ENABLED=false"))
                elif "zerodha" not in self.settings.active_brokers:
                    skipped.append((name, "broker not in ACTIVE_BROKERS"))
        if skipped:
            for svc, reason in skipped:
                self.logger.info("Skipping trading service", service=svc, reason=reason)

        gated_services = [s for s in all_services if s and _allow(s)]

        # Filter out auth_service since it's already started
        remaining_services = [s for s in gated_services if s is not auth_service]
        # Track started services to avoid stopping never-started ones on shutdown
        self._started_services = []
        for service in remaining_services:
            if not service:
                continue
            await service.start()
            self._started_services.append(service)
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
        # Prefer stopping only services that were actually started
        services = getattr(self, '_started_services', None) or self.container.lifespan_services()
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
