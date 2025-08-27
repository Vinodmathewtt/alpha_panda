"""
AlphaPT Application Class

Main application orchestrator that manages the lifecycle of all components.
This is the core application class that can be imported and used by main.py
or other entry points.
"""

import asyncio
import signal
from typing import Dict, Any, Optional
from pathlib import Path

# Global application state type
AppState = Dict[str, Any]


class AlphaPTApplication:
    """
    AlphaPT application manager with enhanced lifecycle management.
    
    This class orchestrates the initialization, startup, running, and cleanup
    of all application components including database, event bus, trading engines,
    strategy manager, risk manager, and monitoring systems.
    """
    
    def __init__(self):
        self.running = False
        self.shutdown_requested = False
        self.logger: Optional[Any] = None
        
        # Application state containing all initialized components
        self.app_state: AppState = {
            "settings": None,
            "db_manager": None,
            "event_bus": None,
            "stream_manager": None,
            "subscriber_manager": None,
            "publisher_service": None, # NEW: Explicit publisher service
            "auth_manager": None,
            "metrics_collector": None,
            "business_metrics": None,
            "health_checker": None,
            "storage_manager": None,
            "mock_feed_manager": None,
            "zerodha_feed_manager": None,
            "strategy_manager": None,
            "risk_manager": None,
            "paper_trading_engine": None,
            "zerodha_trading_engine": None,
            "api_server": None,
            "shutdown_event": None,
        }
        
        # Initialize logging and settings
        self._setup_logging()
        
    def _safe_log_error(self, message: str, error: Exception = None) -> None:
        """Safe error logging that handles both structured and standard formats."""
        if error:
            try:
                self.logger.error(message, error=error)
            except TypeError:
                self.logger.error(f"{message}: {error}")
        else:
            self.logger.error(message)
            
    def _safe_log_warning(self, message: str, error: Exception = None) -> None:
        """Safe warning logging that handles both structured and standard formats."""
        if error:
            try:
                self.logger.warning(message, error=error)
            except TypeError:
                self.logger.warning(f"{message}: {error}")
        else:
            self.logger.warning(message)
        
    def _setup_logging(self):
        """Setup logging and load settings with proper error handling"""
        try:
            from core.logging.logger import configure_logging, get_logger
            from core.config.settings import get_settings
            
            # Load settings for logging configuration
            settings = get_settings()
            if not settings:
                raise ValueError("Failed to load application settings - settings object is None")
            
            self.app_state["settings"] = settings
            
            # Configure logging
            configure_logging(settings)
            self.logger = get_logger(__name__, "application")
            
        except (ImportError, ValueError) as e:
            # Fallback to basic logging with proper error handling
            import logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            self.logger = logging.getLogger(__name__)
            self.logger.warning(f"Using fallback logging due to error: {e}")
            
            # Create minimal settings for fallback mode
            if not self.app_state.get("settings"):
                try:
                    from core.config.settings import Settings
                    self.app_state["settings"] = Settings()
                    self.logger.info("Created fallback settings configuration")
                except Exception as settings_error:
                    self.logger.error(f"Failed to create fallback settings: {settings_error}")
                    # Create absolute minimal settings to prevent NoneType errors
                    from types import SimpleNamespace
                    fallback_settings = SimpleNamespace()
                    fallback_settings.environment = SimpleNamespace()
                    fallback_settings.environment.value = "development"
                    fallback_settings.mock_market_feed = True
                    fallback_settings.api = SimpleNamespace()
                    fallback_settings.api.enable_api_server = False
                    fallback_settings.api.host = "localhost"
                    fallback_settings.api.port = 8000
                    # Add missing attributes
                    fallback_settings.app_version = "0.1.0"
                    fallback_settings.app_name = "AlphaPT"
                    self.app_state["settings"] = fallback_settings
            
    def display_startup_banner(self):
        """Display startup banner with configuration and safe attribute access"""
        settings = self.app_state.get("settings")
        
        if not settings:
            print("=" * 60)
            print("🚀 AlphaPT - Algorithmic Trading Platform")
            print("=" * 60)
            print("⚠️  WARNING: Running in emergency mode - settings not loaded")
            print("=" * 60)
            return
        
        print("=" * 60)
        print("🚀 AlphaPT - Algorithmic Trading Platform")
        print("=" * 60)
        
        # Safe attribute access with fallbacks
        try:
            environment_value = getattr(settings.environment, 'value', 'unknown') if hasattr(settings, 'environment') else 'unknown'
            print(f"📊 Environment: {environment_value}")
        except Exception:
            print("📊 Environment: unknown")
            
        try:
            mock_feed = getattr(settings, 'mock_market_feed', True)
            print(f"🎭 Mock Market Feed: {'Enabled' if mock_feed else 'Disabled'}")
        except Exception:
            print("🎭 Mock Market Feed: Enabled (default)")
            
        try:
            api_enabled = getattr(settings.api, 'enable_api_server', False) if hasattr(settings, 'api') else False
            print(f"🌐 API Server: {'Enabled' if api_enabled else 'Disabled'}")
            
            if api_enabled:
                api_host = getattr(settings.api, 'host', 'localhost') if hasattr(settings, 'api') else 'localhost'
                api_port = getattr(settings.api, 'port', 8000) if hasattr(settings, 'api') else 8000
                print(f"🔗 API Documentation: http://{api_host}:{api_port}/docs")
        except Exception:
            print("🌐 API Server: Disabled (default)")
            
        print(f"🎯 Performance Target: 1000+ ticks/second")
        print("=" * 60)
        
    async def initialize(self) -> bool:
        """
        Initializes all application components, creating instances but not starting them.
        Returns: True if initialization successful, False otherwise.
        """
        try:
            settings = self.app_state["settings"]
            # Handle structured vs standard logging
            app_version = getattr(settings, 'app_version', 'unknown')
            environment_value = getattr(settings.environment, 'value', 'unknown') if hasattr(settings, 'environment') else 'unknown'
            
            try:
                # Try structured logging first
                self.logger.info("Starting AlphaPT application initialization", 
                               version=app_version, 
                               environment=environment_value)
            except TypeError:
                # Fall back to standard logging
                self.logger.info(f"Starting AlphaPT application initialization - version: {app_version}, environment: {environment_value}")

            # Initialize core infrastructure
            if not await self._init_database(): return False
            if not await self._init_event_bus(): return False
            if not await self._init_auth_manager(): return False
            if not await self._init_monitoring(): return False

            # Initialize data and business logic layers
            if not await self._init_storage_manager(): return False
            if not await self._init_market_feed(): return False
            if not await self._init_strategy_manager(): return False
            if not await self._init_risk_manager(): return False
            if not await self._init_trading_engines(): return False

            if settings.api.enable_api_server:
                if not await self._init_api_server(): return False

            self.app_state["shutdown_event"] = asyncio.Event()
            loop = asyncio.get_event_loop()
            loop.set_exception_handler(self._global_exception_handler)

            self.logger.info("✅ AlphaPT application initialization completed successfully")
            return True
        except Exception as e:
            self._safe_log_error("Failed to initialize application", e)
            await self.cleanup()
            return False
            
    async def start(self) -> bool:
        """
        Starts all the initialized application services in the correct order.
        Returns: True if startup successful, False otherwise.
        """
        try:
            self.logger.info("🚀 Starting AlphaPT services...")

            # NEW: Wait for the event bus to be fully ready before starting other services
            event_bus = self.app_state["event_bus"]
            if event_bus:
                self.logger.info("Waiting for event bus to become fully ready...")
                await event_bus.wait_for_ready(timeout=60.0)
                self.logger.info("✅ Event bus is fully ready.")

            # Start services that depend on the event bus
            if self.app_state["storage_manager"]: await self.app_state["storage_manager"].start()
            if self.app_state["health_checker"]: await self.app_state["health_checker"].start()
            if self.app_state["risk_manager"]: await self.app_state["risk_manager"].start()

            # Start the strategy manager, which will now publish subscription events
            if self.app_state["strategy_manager"]: await self.app_state["strategy_manager"].start()

            # Start market feeds and trading engines
            if self.app_state["mock_feed_manager"]: await self.app_state["mock_feed_manager"].start_data_streaming()
            if self.app_state["zerodha_feed_manager"]: pass # Zerodha feed starts on its own
            if self.app_state["paper_trading_engine"]: await self.app_state["paper_trading_engine"].start()
            if self.app_state["zerodha_trading_engine"]: await self.app_state["zerodha_trading_engine"].start()

            self.running = True
            self.logger.info("✅ AlphaPT started successfully")
            self.logger.info("📊 System is now processing market data and executing strategies")
            self.logger.info("🛑 Press Ctrl+C to stop the application gracefully")
            return True
        except Exception as e:
            self._safe_log_error("❌ Application startup failed", e)
            return False
            
    async def run(self):
        """Run the main application loop"""
        # Setup signal handlers
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating shutdown...")
            self.shutdown_requested = True
            if self.app_state.get("shutdown_event"):
                self.app_state["shutdown_event"].set()
                
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        settings = self.app_state["settings"]
        
        # Check if API server should be started
        if settings.api.enable_api_server:
            self.logger.info("🌐 Starting API server...")
            await self._run_with_api_server()
        else:
            self.logger.info("🔄 AlphaPT main loop started (Ctrl+C to stop)")
            
            try:
                # Wait for shutdown signal
                await self.app_state["shutdown_event"].wait()
                self.logger.info("Shutdown signal received, stopping application...")
                
            except KeyboardInterrupt:
                self.logger.info("Keyboard interrupt received")
                self.shutdown_requested = True
                
    async def stop(self):
        """Stop the application gracefully"""
        try:
            self.logger.info("🛑 Stopping AlphaPT...")
            await self.cleanup()
            self.running = False
            self.logger.info("✅ AlphaPT stopped gracefully")
            
        except Exception as e:
            self._safe_log_error("⚠️ Shutdown error", e)
            
    async def cleanup(self):
        """Cleanup all application components in the correct reverse order."""
        self.logger.info("🧹 Starting application cleanup...")

        # MODIFIED: Refined cleanup order and logic

        # 1. Stop components that produce events first
        stoppable_services = [
            self.app_state.get("strategy_manager"),
            self.app_state.get("risk_manager"),
            self.app_state.get("paper_trading_engine"),
            self.app_state.get("zerodha_trading_engine"),
            self.app_state.get("health_checker"),
            self.app_state.get("storage_manager"),
        ]

        cleanup_tasks = []
        for service in stoppable_services:
            if service and hasattr(service, 'stop'):
                cleanup_tasks.append(service.stop())

        # 2. Stop market data feeds
        if self.app_state.get("zerodha_feed_manager"):
            cleanup_tasks.append(self.app_state["zerodha_feed_manager"].cleanup())
        if self.app_state.get("mock_feed_manager"):
            cleanup_tasks.append(self.app_state["mock_feed_manager"].cleanup())

        # 3. Stop monitoring and authentication
        if self.app_state.get("metrics_collector"):
            cleanup_tasks.append(self.app_state["metrics_collector"].stop())
        if self.app_state.get("auth_manager"):
            cleanup_tasks.append(self.app_state["auth_manager"].stop())

        # Execute cleanup tasks concurrently
        if cleanup_tasks:
            results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"Cleanup task failed: {result}", exc_info=result)

        # 4. Stop the event system (subscribers first, then the connection)
        if self.app_state.get("subscriber_manager"):
            await self.app_state["subscriber_manager"].stop()
            self.logger.info("Subscriber manager stopped")

        if self.app_state.get("event_bus"):
            await self.app_state["event_bus"].disconnect()

        # 5. Close database connections last
        if self.app_state.get("db_manager"):
            from core.database.connection import close_database
            await close_database()

        self.logger.info("✅ Application cleanup completed")

    
    def _global_exception_handler(self, loop, context):
        """
        Global exception handler for unhandled exceptions in background tasks.
        Triggers graceful shutdown if critical component fails.
        """
        exception = context.get('exception')
        if exception:
            self.logger.error(
                "Unhandled exception in background task - triggering graceful shutdown",
                error=exception,
                context=context
            )
        else:
            self.logger.error(
                "Unhandled error in background task - triggering graceful shutdown",
                context=context
            )
        
        # Trigger graceful shutdown
        if self.app_state.get("shutdown_event") and not self.shutdown_requested:
            self.shutdown_requested = True
            self.app_state["shutdown_event"].set()
        
    async def health_check(self) -> Dict[str, Any]:
        """
        Get application health status.
        
        Returns:
            Dict containing health status information
        """
        try:
            health_checker = self.app_state.get("health_checker")
            if health_checker:
                return await health_checker.get_overall_health()
            else:
                return {"status": "unhealthy", "message": "Health checker not initialized"}
        except Exception as e:
            return {"status": "unhealthy", "message": f"Health check failed: {str(e)}"}
            
    # Private initialization methods
    
    async def _init_database(self) -> bool:
        """Initialize database connections and tables"""
        try:
            self.logger.info("🗄️ Initializing database connections...")
            
            from core.database.connection import initialize_database
            
            settings = self.app_state["settings"]
            db_manager = await initialize_database(settings)
            self.app_state["db_manager"] = db_manager
            
            # Create database tables
            await db_manager.create_tables()
            self.logger.info("✅ Database initialization completed")
            return True
            
        except Exception as e:
            self._safe_log_error("❌ Database initialization failed", e)
            return False
            
    async def _init_event_bus(self) -> bool:
        """Initialize NATS JetStream event bus using new refactored system"""
        try:
            self.logger.info("📡 Initializing event bus...")
            
            from core.events import get_event_bus_core, create_stream_manager, create_subscriber_manager, get_event_publisher
            
            settings = self.app_state["settings"]
            event_bus_core = get_event_bus_core(settings)
            await event_bus_core.connect()

            stream_manager = create_stream_manager(settings, event_bus_core)
            await stream_manager.ensure_streams()

            subscriber_manager = create_subscriber_manager(settings, event_bus_core)
            await subscriber_manager.start() # Subscribers can start listening early

            publisher_service = get_event_publisher(settings)

            self.app_state["event_bus"] = event_bus_core
            self.app_state["stream_manager"] = stream_manager
            self.app_state["subscriber_manager"] = subscriber_manager
            self.app_state["publisher_service"] = publisher_service

            self.logger.info("✅ Event bus core connected and streams ensured")
            return True
        except Exception as e:
            self._safe_log_error("❌ Event bus initialization failed", e)
            return False
            
    async def _init_auth_manager(self) -> bool:
        """Initialize authentication manager"""
        try:
            self.logger.info("🔐 Initializing authentication manager...")
            
            from core.auth.auth_manager import AuthManager
            
            settings = self.app_state["settings"]
            db_manager = self.app_state["db_manager"]
            
            auth_manager = AuthManager(settings, db_manager)
            auth_success = await auth_manager.initialize()
            self.app_state["auth_manager"] = auth_manager
            
            if auth_success:
                # Display user profile details like reference implementation
                try:
                    if auth_manager.is_authenticated():
                        user_profile = await auth_manager.get_profile()
                        if user_profile:
                            # Display authentication info in a clean format
                            print("")
                            print("=" * 60)
                            print("🔐 AUTHENTICATION STATUS")
                            print("=" * 60)
                            print(f"✅ Authentication completed successfully")
                            print(f"📋 Logged in as: {user_profile.user_shortname or user_profile.user_name or 'Unknown'}")
                            print(f"🆔 User ID: {user_profile.user_id}")
                            print(f"🏢 Broker: {user_profile.broker or 'Unknown'}")
                            
                            # Display session information
                            session_info = auth_manager.get_session_info()
                            if session_info:
                                login_method = session_info.get('login_method', 'unknown').upper()
                                expires_at = session_info.get('expires_at')
                                time_to_expiry = session_info.get('time_to_expiry')
                                print(f"🔐 Login Method: {login_method}")
                                if expires_at:
                                    print(f"⏰ Session Expires: {expires_at}")
                                if time_to_expiry and time_to_expiry > 0:
                                    hours = int(time_to_expiry // 3600)
                                    minutes = int((time_to_expiry % 3600) // 60)
                                    print(f"⏳ Time to Expiry: {hours}h {minutes}m")
                            print("=" * 60)
                            print("")
                            
                            self.logger.info("✅ Authentication manager initialization completed")
                        else:
                            self.logger.info("✅ Authentication manager initialized (session data available)")
                    else:
                        self.logger.info("✅ Authentication manager initialized (unauthenticated mode)")
                except Exception as e:
                    self.logger.debug(f"Could not retrieve user profile details: {e}")
                    self.logger.info("✅ Authentication manager initialization completed")
            
            return True
            
        except Exception as e:
            self._safe_log_error("❌ Authentication manager initialization failed", e)
            return False
            
    async def _init_monitoring(self) -> bool:
        """Initialize monitoring components"""
        try:
            self.logger.info("📊 Initializing monitoring system...")
            
            from monitoring.metrics_collector import MetricsCollector
            from monitoring.health_checker import HealthChecker
            from monitoring.business_metrics import initialize_business_metrics
            
            settings = self.app_state["settings"]
            db_manager = self.app_state["db_manager"]
            event_bus = self.app_state["event_bus"]
            
            # Initialize metrics collector
            metrics_collector_instance = MetricsCollector(settings)
            await metrics_collector_instance.start()
            self.app_state["metrics_collector"] = metrics_collector_instance
            
            # Initialize business metrics
            business_metrics_instance = initialize_business_metrics()
            self.app_state["business_metrics"] = business_metrics_instance
            
            # Initialize health checker
            health_checker_instance = HealthChecker(settings, db_manager, event_bus)
            self.app_state["health_checker"] = health_checker_instance # Start is called in app.start()
            
            # Set global instances for API access
            import monitoring
            monitoring.metrics_collector = metrics_collector_instance
            monitoring.health_checker = health_checker_instance
            
            self.logger.info("✅ Monitoring system initialization completed")
            return True
            
        except Exception as e:
            self._safe_log_error("❌ Monitoring system initialization failed", e)
            return False
            
    async def _init_storage_manager(self) -> bool:
        """Initialize market data storage manager"""
        try:
            self.logger.info("🗄️ Initializing market data storage manager...")
            
            from storage.storage_manager import MarketDataStorageManager
            
            settings = self.app_state["settings"]
            event_bus = self.app_state["event_bus"]
            
            storage_manager = MarketDataStorageManager(settings, event_bus)
            self.app_state["storage_manager"] = storage_manager # Start is called in app.start()
            
            self.logger.info("✅ Market data storage manager initialized")
            return True
            
        except Exception as e:
            self._safe_log_error("❌ Storage manager initialization failed", e)
            return False
            
    async def _init_market_feed(self) -> bool:
        """Initialize market feed manager (mock or zerodha)"""
        try:
            settings = self.app_state["settings"]
            event_bus = self.app_state["event_bus"]
            
            if settings.mock_market_feed:
                self.logger.info("🎭 Initializing mock market feed manager...")
                
                from mock_market_feed.mock_feed_manager import MockFeedManager
                
                mock_feed_manager = MockFeedManager(settings, self.app_state["publisher_service"])
                await mock_feed_manager.initialize()
                await mock_feed_manager.subscribe_instruments(settings.market_data.default_instrument_tokens)
                self.app_state["mock_feed_manager"] = mock_feed_manager
                
                default_tokens = settings.market_data.default_instrument_tokens
                self.logger.info(f"✅ Mock market feed initialized with {len(default_tokens)} instruments")
            else:
                self.logger.info("🔌 Initializing Zerodha market feed...")
                
                # Ensure authentication for Zerodha feed
                auth_manager = self.app_state.get("auth_manager")
                if not auth_manager:
                    self.logger.error("❌ Auth manager not initialized, cannot proceed with Zerodha market feed")
                    return False
                if not await auth_manager.ensure_authenticated():
                    self.logger.error("❌ Zerodha authentication failed - cannot initialize market feed")
                    return False
                
                from zerodha_market_feed.zerodha_feed_manager import ZerodhaMarketFeedManager
                
                zerodha_feed_manager = ZerodhaMarketFeedManager(settings, self.app_state["publisher_service"])
                zerodha_feed_manager.set_auth_manager(auth_manager)
                await zerodha_feed_manager.initialize()
                self.app_state["zerodha_feed_manager"] = zerodha_feed_manager
                
                self.logger.info("✅ Zerodha market feed initialized")
            
            return True
            
        except Exception as e:
            self._safe_log_error("❌ Market feed initialization failed", e)
            return False
            
    async def _init_strategy_manager(self) -> bool:
        """Initialize strategy manager"""
        try:
            self.logger.info("🧠 Initializing strategy manager...")
            
            from strategy_manager.strategy_manager import StrategyManager
            
            settings = self.app_state.get("settings")
            event_bus = self.app_state.get("event_bus")
            
            if not settings or not event_bus:
                self.logger.error("❌ Required components (settings, event_bus) not initialized for strategy manager")
                return False
            
            strategy_manager = StrategyManager(settings, self.app_state["publisher_service"])
            await strategy_manager.initialize() # This now only loads configs
            self.app_state["strategy_manager"] = strategy_manager
            
            self.logger.info("✅ Strategy manager initialized")
            return True
            
        except Exception as e:
            self._safe_log_error("❌ Strategy manager initialization failed", e)
            return False
            
    async def _init_risk_manager(self) -> bool:
        """Initialize risk manager"""
        try:
            self.logger.info("🛡️ Initializing risk manager...")
            
            from risk_manager.risk_manager import RiskManager
            
            settings = self.app_state.get("settings")
            event_bus = self.app_state.get("event_bus")
            
            if not settings or not event_bus:
                self.logger.error("❌ Required components (settings, event_bus) not initialized for risk manager")
                return False
            
            risk_manager = RiskManager(settings, event_bus)
            self.app_state["risk_manager"] = risk_manager # Start is called in app.start()
            
            self.logger.info("✅ Risk manager initialized")
            return True
            
        except Exception as e:
            self._safe_log_error("❌ Risk manager initialization failed", e)
            return False
            
    async def _init_trading_engines(self) -> bool:
        """Initialize trading engines (paper and/or zerodha)"""
        try:
            self.logger.info("💰 Initializing trading engines...")
            
            settings = self.app_state.get("settings")
            event_bus = self.app_state.get("event_bus")
            
            if not settings or not event_bus:
                self.logger.error("❌ Required components (settings, event_bus) not initialized for trading engines")
                return False
            
            engines_initialized = 0
            
            # Initialize paper trading engine if enabled
            if settings.paper_trading_enabled:
                try:
                    from paper_trade.engine import PaperTradingEngine
                    from decimal import Decimal
                    
                    # Get risk manager from app state if available
                    risk_manager = self.app_state.get("risk_manager")
                    
                    paper_engine = PaperTradingEngine(
                        risk_manager=risk_manager,
                        event_bus=event_bus
                    )
                    self.app_state["paper_trading_engine"] = paper_engine
                    engines_initialized += 1
                    self.logger.info("✅ Paper trading engine initialized")
                except Exception as e:
                    self._safe_log_warning("⚠️ Paper trading engine disabled", e)
            else:
                self.logger.info("📄 Paper trading engine disabled by configuration")
            
            # Initialize Zerodha trading engine if enabled and authenticated
            try:
                if settings.zerodha_trading_enabled:  # Use explicit setting
                    from zerodha_trade.engine import ZerodhaTradeEngine
                    
                    zerodha_engine = ZerodhaTradeEngine(settings, event_bus)
                    self.app_state["zerodha_trading_engine"] = zerodha_engine
                    engines_initialized += 1
                    self.logger.info("✅ Zerodha trading engine initialized")
            except Exception as e:
                self._safe_log_warning("⚠️ Zerodha trading engine disabled", e)
            
            if engines_initialized == 0:
                self.logger.warning("⚠️ No trading engines enabled - running in observation mode")
            
            return True
            
        except Exception as e:
            self._safe_log_error("❌ Trading engines initialization failed", e)
            return False
            
    async def _init_api_server(self) -> bool:
        """Initialize API server if enabled"""
        try:
            self.logger.info("🌐 Initializing API server...")
            
            # Store API server flag for later use
            self.app_state["api_server"] = True
            
            return True
            
        except Exception as e:
            self._safe_log_error("❌ API server initialization failed", e)
            return False
            
    async def _run_with_api_server(self):
        """Run application with API server"""
        settings = self.app_state["settings"]
        
        # Import and run API server
        from api.server import run_server
        
        await run_server(
            host=settings.api.host,
            port=settings.api.port,
            reload=settings.api.reload,
            log_level=settings.log_level.value.lower(),
        )