"""Central strategy manager for AlphaPT strategy framework."""

import asyncio
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

from .base_strategy import BaseStrategy
from .strategy_factory import StrategyFactory, strategy_factory
from .signal_types import TradingSignal
from .strategy_health_monitor import StrategyHealthMonitor, initialize_strategy_health_monitor
from .config.config_loader import strategy_config_loader
from core.config.settings import Settings
from core.events import EventBusCore, get_event_publisher, subscriber
from core.events.event_types import MarketDataEvent, TradingEvent
from core.logging import get_trading_logger


# Global strategy manager instance for decorator handlers
_strategy_manager_instance: Optional['StrategyManager'] = None


@subscriber.on_event("market.tick.*", durable_name="strategy-manager-ticks")
async def handle_market_tick_strategy(event: MarketDataEvent) -> None:
    """Handle market tick events for strategy processing.
    
    This decorator-based handler routes market data events to the strategy manager.
    """
    global _strategy_manager_instance
    if _strategy_manager_instance:
        await _strategy_manager_instance._handle_market_data_event(event)


@subscriber.on_event("trading.signal.*", durable_name="strategy-manager-signals")
async def handle_trading_signal_strategy(event: TradingEvent) -> None:
    """Handle trading signal events from strategies."""
    global _strategy_manager_instance
    if _strategy_manager_instance:
        await _strategy_manager_instance._handle_trading_signal_event(event)


class StrategyManager:
    """Central orchestrator for all trading strategies in AlphaPT.
    
    The StrategyManager handles:
    - Strategy lifecycle management (start, stop, reload)
    - Market data routing to strategies
    - Signal collection and routing
    - Performance monitoring and health checks
    - Configuration management
    - Integration with risk management and trading engines
    """
    
    def __init__(self, settings: Settings, event_bus: EventBusCore):
        """Initialize strategy manager.
        
        Args:
            settings: Application settings
            event_bus: Event bus for communication
        """
        self.settings = settings
        self.event_bus = event_bus
        self.logger = get_trading_logger("strategy_manager")
        
        # Strategy management
        self.strategies: Dict[str, BaseStrategy] = {}
        self.active_strategies: Set[str] = set()
        self.failed_strategies: Set[str] = set()
        self.strategy_configs: Dict[str, Dict[str, Any]] = {}
        
        # Signal management (persistent via NATS JetStream)
        self.signal_stream = "TRADING_SIGNALS"
        self.signal_count = 0
        self.signals_routed = 0
        
        # Performance tracking
        self.start_time = datetime.now(timezone.utc)
        self.market_data_processed = 0
        self.total_errors = 0
        self.last_market_data_time: Optional[datetime] = None
        
        # Instrument tracking
        self.subscribed_instruments: Set[int] = set()
        self.instrument_strategy_map: Dict[int, Set[str]] = {}
        
        # Event handlers
        self.is_initialized = False
        self.is_running = False
        
        # Health monitoring
        self.health_monitor: Optional[StrategyHealthMonitor] = None
        
        self.logger.info("Strategy manager initialized")
    
    async def initialize(self):
        """Initialize the strategy manager by loading configurations and creating strategy instances.
        This method does NOT start the strategies or subscribe to market data.
        """
        try:
            self.logger.info("Initializing strategy manager...")
            
            # Discover and register available strategies
            await self._discover_strategies()
            
            # Load strategy configurations
            await self._load_strategy_configurations()
            
            # Create and initialize strategy instances
            await self._create_strategy_instances()
            
            # Setup event subscriptions (decorator-based, no publishing)
            await self._setup_event_subscriptions()
            
            # Initialize health monitoring (no publishing)
            await self._initialize_health_monitoring()
            
            self.is_initialized = True
            self.logger.info(f"Strategy manager initialized with {len(self.strategies)} strategies")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize strategy manager: {e}")
            raise
    
    async def start(self):
        """Start all initialized strategies and subscribe to required market data.
        This method should be called after the event bus is fully ready.
        """
        if not self.is_initialized:
            self.logger.error("Strategy manager not initialized. Call initialize() first.")
            return
        
        try:
            self.logger.info("Starting strategy manager...")
            
            # Subscribe to required instruments (this is where event publishing happens)
            await self._subscribe_to_instruments()
            
            # Publish strategy registration events for health monitoring
            await self._publish_strategy_registrations()
            
            # Start all configured strategies
            await self._start_all_strategies()
            
            # Start health monitoring
            if self.health_monitor:
                await self.health_monitor.start()
            
            # Set global instance for decorator handlers
            global _strategy_manager_instance
            _strategy_manager_instance = self
            self.logger.info("✅ Strategy manager registered for event subscriptions")
            
            self.is_running = True
            self.logger.info(f"Strategy manager started with {len(self.active_strategies)} active strategies")
            
        except Exception as e:
            self.logger.error(f"Failed to start strategy manager: {e}")
            raise
    
    async def stop(self):
        """Stop the strategy manager and all strategies."""
        try:
            self.logger.info("Stopping strategy manager...")
            
            self.is_running = False
            
            # Stop health monitoring
            if self.health_monitor:
                await self.health_monitor.stop()
            
            # Stop all active strategies
            await self._stop_all_strategies()
            
            # Clear global instance
            global _strategy_manager_instance
            _strategy_manager_instance = None
            self.logger.info("Strategy manager unregistered from event subscriptions")
            
            self.logger.info("Strategy manager stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping strategy manager: {e}")
    
    async def _discover_strategies(self):
        """Discover available strategy implementations."""
        # Look for strategies in the strategies directory
        strategies_dir = Path(__file__).parent / "strategies"
        if strategies_dir.exists():
            discovered = strategy_factory.discover_strategies(strategies_dir)
            self.logger.info(f"Discovered {discovered} strategy types")
        else:
            self.logger.warning(f"Strategies directory not found: {strategies_dir}")
        
        # Register built-in example strategies
        await self._register_builtin_strategies()
    
    async def _register_builtin_strategies(self):
        """Register built-in example strategies."""
        try:
            # Import and register built-in strategies
            from .strategies.simple_momentum_strategy import SimpleMomentumStrategy
            from .strategies.mean_reversion_strategy import MeanReversionStrategy
            from .strategies.simple_price_threshold_strategy import SimplePriceThresholdStrategy
            from .strategies.volume_spike_strategy import VolumeSpikeStrategy
            from .strategies.random_signal_strategy import RandomSignalStrategy
            
            strategy_factory.register_strategy(
                "simple_momentum", 
                SimpleMomentumStrategy,
                {"description": "Simple momentum strategy based on price trends", "type": "momentum"}
            )
            
            strategy_factory.register_strategy(
                "mean_reversion",
                MeanReversionStrategy, 
                {"description": "Mean reversion strategy using moving averages", "type": "mean_reversion"}
            )
            
            # Register new testing strategies
            strategy_factory.register_strategy(
                "price_threshold",
                SimplePriceThresholdStrategy,
                {"description": "Price threshold strategy for testing signal generation", "type": "testing", "testing_focused": True}
            )
            
            strategy_factory.register_strategy(
                "volume_spike",
                VolumeSpikeStrategy,
                {"description": "Volume spike strategy for testing signal generation", "type": "testing", "testing_focused": True}
            )
            
            strategy_factory.register_strategy(
                "random_signal",
                RandomSignalStrategy,
                {"description": "Random signal strategy for framework testing", "type": "testing", "testing_focused": True}
            )
            
            self.logger.info("Registered built-in strategies including testing strategies")
            
        except ImportError as e:
            self.logger.info(f"Built-in strategies not available: {e}")
    
    async def _load_strategy_configurations(self):
        """Load strategy configurations from external YAML files."""
        try:
            # Load configurations using the config loader
            enabled_strategies = strategy_config_loader.get_enabled_strategies()
            
            if not enabled_strategies:
                self.logger.warning("No enabled strategies found in configuration")
                # Load default fallback configurations
                await self._load_default_configs()
                return
            
            # Convert external config format to internal format
            for strategy_name, config in enabled_strategies.items():
                # Map external config to internal format
                internal_config = self._map_external_to_internal_config(config)
                self.strategy_configs[strategy_name] = internal_config
                self.logger.info(f"Loaded configuration for strategy: {strategy_name}")
            
            self.logger.info(f"Successfully loaded {len(self.strategy_configs)} strategy configurations from external files")
            
        except Exception as e:
            self.logger.error(f"Failed to load external strategy configurations: {e}")
            # Fallback to default configurations
            await self._load_default_configs()
    
    def _map_external_to_internal_config(self, external_config: Dict[str, Any]) -> Dict[str, Any]:
        """Map external YAML config format to internal strategy config format."""
        return {
            "strategy_type": external_config.get("strategy_type", "unknown"),
            "instruments": external_config.get("instruments", []),
            "parameters": external_config.get("parameters", {}),
            "routing": {
                "paper_trade": external_config.get("routing", {}).get("paper_trade", True),
                "live_trade": external_config.get("routing", {}).get("zerodha_trade", False)
            },
            "risk": external_config.get("risk_limits", {}),
            "monitoring": external_config.get("monitoring", {}),
            "enabled": True  # Only enabled strategies are loaded
        }
    
    async def _load_default_configs(self):
        """Load default fallback configurations when external configs fail."""
        self.logger.info("Loading default fallback strategy configurations")
        default_configs = {
            "momentum_strategy": {
                "strategy_type": "momentum",
                "instruments": [738561, 2714625, 81153],  # RELIANCE, ICICIBANK, TCS
                "parameters": {
                    "lookback_period": 20,
                    "momentum_threshold": 0.02,
                    "position_size_pct": 0.1
                },
                "routing": {
                    "paper_trade": True,
                    "live_trade": False
                },
                "risk": {
                    "max_position_per_stock": 500,
                    "max_daily_loss": 5000
                },
                "enabled": True
            },
            "mean_reversion_strategy": {
                "strategy_type": "mean_reversion",
                "instruments": [1346049, 2939649, 140033],  # ADANIPORTS, NTPC, BHARTIARTL
                "parameters": {
                    "lookback_period": 50,
                    "deviation_threshold": 2.0,
                    "position_size_pct": 0.05
                },
                "routing": {
                    "paper_trade": True,
                    "live_trade": False
                },
                "risk": {
                    "max_position_per_stock": 250,
                    "max_daily_loss": 3000
                },
                "enabled": True
            }
        }
        
        for name, config in default_configs.items():
            self.strategy_configs[name] = config
            self.logger.info(f"Loaded default configuration for strategy: {name}")
        
        self.logger.info(f"Loaded {len(self.strategy_configs)} strategy configurations")
    
    async def _create_strategy_instances(self):
        """Create strategy instances from configurations."""
        for strategy_name, config in self.strategy_configs.items():
            try:
                strategy_type = config.get("strategy_type")
                if not strategy_type:
                    self.logger.error(f"No strategy_type specified for {strategy_name}")
                    continue
                
                # Create strategy instance
                strategy = strategy_factory.create_strategy(strategy_name, strategy_type, config)
                self.strategies[strategy_name] = strategy
                
                # Map instruments to strategies
                for instrument_token in strategy.get_instruments():
                    if instrument_token not in self.instrument_strategy_map:
                        self.instrument_strategy_map[instrument_token] = set()
                    self.instrument_strategy_map[instrument_token].add(strategy_name)
                    self.subscribed_instruments.add(instrument_token)
                
                self.logger.info(f"Created strategy instance: {strategy_name} ({strategy_type})")
                
            except Exception as e:
                self.logger.error(f"Failed to create strategy {strategy_name}: {e}")
                self.failed_strategies.add(strategy_name)
    
    async def _setup_event_subscriptions(self):
        """Setup event subscriptions for market data and signals."""
        # Event subscriptions are now handled by decorator-based handlers
        # @subscriber.on_event decorators at module level handle all subscriptions
        # No manual subscription needed here
        self.logger.info("Event subscriptions configured via decorator handlers")
    
    async def _publish_event(self, subject: str, event, ignore_failures: bool = False):
        """Helper method to publish events using the new event publisher service."""
        from core.events import get_event_publisher
        try:
            event_publisher = get_event_publisher(self.settings)
            await event_publisher.publish(subject, event, ignore_failures=ignore_failures)
        except Exception as e:
            if not ignore_failures:
                self.logger.error(f"Failed to publish event to {subject}: {e}")
            else:
                self.logger.debug(f"Ignoring publish failure during shutdown to {subject}: {e}")
            # Don't raise exception to avoid breaking main functionality
    
    
    async def _subscribe_to_instruments(self):
        """Subscribe to market data for all required instruments."""
        if self.subscribed_instruments:
            # Publish instrument subscription request using the new event publisher
            from core.events.event_types import MarketDataEvent, EventType
            from core.events import get_event_publisher
            import uuid
            
            event = MarketDataEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.MARKET_STATUS_CHANGED,
                timestamp=datetime.now(timezone.utc),
                source="strategy_manager",
                data={
                    "instruments": list(self.subscribed_instruments),
                    "subscriber": "strategy_manager"
                }
            )
            
            # Use the event publisher service helper
            await self._publish_event("market.instrument.subscribe", event)
            
            self.logger.info(f"Subscribed to {len(self.subscribed_instruments)} instruments")
    
    async def _publish_strategy_registrations(self):
        """Publish strategy registration events for health monitoring."""
        try:
            # Register all strategies for health monitoring
            from core.events.event_types import SystemEvent, EventType
            import uuid
            for strategy_name in self.strategies.keys():
                event = SystemEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=EventType.SYSTEM_STARTED,
                    timestamp=datetime.now(timezone.utc),
                    source="strategy_manager",
                    details={
                        "strategy_name": strategy_name,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
                await self._publish_event("strategy.registered", event)
            
            self.logger.info(f"Published registration events for {len(self.strategies)} strategies")
        except Exception as e:
            self.logger.error(f"Failed to publish strategy registration events: {e}")
            # Don't fail startup if registration events fail
    
    async def _initialize_health_monitoring(self):
        """Initialize strategy health monitoring without publishing events."""
        try:
            self.health_monitor = await initialize_strategy_health_monitor(self.settings, self.event_bus)
            
            # Note: Strategy registration events will be published during start() phase
            # to avoid race conditions with event system initialization
            
            self.logger.info("Strategy health monitoring initialized")
        except Exception as e:
            self.logger.error(f"Failed to initialize health monitoring: {e}")
            # Don't fail initialization if health monitoring fails
            self.health_monitor = None
    
    async def _start_all_strategies(self):
        """Start all configured strategies."""
        for strategy_name, strategy in self.strategies.items():
            if strategy_name not in self.failed_strategies:
                try:
                    success = await strategy.start()
                    if success:
                        self.active_strategies.add(strategy_name)
                        # Publish strategy started event for health monitoring
                        from core.events.event_types import SystemEvent, EventType
                        import uuid
                        event = SystemEvent(
                            event_id=str(uuid.uuid4()),
                            event_type=EventType.STRATEGY_STARTED,
                            timestamp=datetime.now(timezone.utc),
                            source="strategy_manager",
                            details={
                                "strategy_name": strategy_name,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )
                        await self._publish_event("strategy.started", event)
                        self.logger.info(f"Started strategy: {strategy_name}")
                    else:
                        self.failed_strategies.add(strategy_name)
                        # Publish strategy error event
                        from core.events.event_types import SystemEvent, EventType
                        import uuid
                        event = SystemEvent(
                            event_id=str(uuid.uuid4()),
                            event_type=EventType.STRATEGY_ERROR,
                            timestamp=datetime.now(timezone.utc),
                            source="strategy_manager",
                            details={
                                "strategy_name": strategy_name,
                                "error": "Failed to start strategy",
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                        )
                        await self._publish_event("strategy.error", event)
                        self.logger.error(f"Failed to start strategy: {strategy_name}")
                        
                except Exception as e:
                    self.logger.error(f"Error starting strategy {strategy_name}: {e}")
                    self.failed_strategies.add(strategy_name)
                    # Publish strategy error event
                    from core.events.event_types import SystemEvent, EventType
                    import uuid
                    event = SystemEvent(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.STRATEGY_ERROR,
                        timestamp=datetime.now(timezone.utc),
                        source="strategy_manager",
                        details={
                            "strategy_name": strategy_name,
                            "error": str(e),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
                    await self._publish_event("strategy.error", event)
        
        self.logger.info(f"Started {len(self.active_strategies)} strategies, "
                        f"{len(self.failed_strategies)} failed")
    
    async def _stop_all_strategies(self):
        """Stop all active strategies."""
        for strategy_name in list(self.active_strategies):
            try:
                strategy = self.strategies[strategy_name]
                await strategy.stop()
                self.active_strategies.remove(strategy_name)
                # Publish strategy stopped event
                from core.events.event_types import SystemEvent, EventType
                import uuid
                event = SystemEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=EventType.STRATEGY_STOPPED,
                    timestamp=datetime.now(timezone.utc),
                    source="strategy_manager",
                    details={
                        "strategy_name": strategy_name,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
                await self._publish_event("strategy.stopped", event, ignore_failures=True)
                self.logger.info(f"Stopped strategy: {strategy_name}")
                
            except Exception as e:
                self.logger.error(f"Error stopping strategy {strategy_name}: {e}")
                # Publish strategy error event
                from core.events.event_types import SystemEvent, EventType
                import uuid
                event = SystemEvent(
                    event_id=str(uuid.uuid4()),
                    event_type=EventType.STRATEGY_ERROR,
                    timestamp=datetime.now(timezone.utc),
                    source="strategy_manager",
                    details={
                        "strategy_name": strategy_name,
                        "error": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                )
                await self._publish_event("strategy.error", event, ignore_failures=True)
    
    async def _handle_market_data(self, event_data: Dict[str, Any]):
        """Handle incoming market data events."""
        try:
            # Extract instrument token from event data
            if "data" in event_data:
                tick_data = event_data["data"]
            else:
                tick_data = event_data
            
            instrument_token = tick_data.get("instrument_token")
            if not instrument_token:
                return
            
            self.market_data_processed += 1
            self.last_market_data_time = datetime.now(timezone.utc)
            
            # Route to relevant strategies
            strategy_names = self.instrument_strategy_map.get(instrument_token, set())
            
            for strategy_name in strategy_names:
                if strategy_name in self.active_strategies:
                    try:
                        strategy = self.strategies[strategy_name]
                        signal = await strategy.process_market_data(tick_data)
                        
                        if signal:
                            await self._handle_strategy_signal(signal)
                            
                    except Exception as e:
                        self.logger.error(f"Error processing market data in strategy {strategy_name}: {e}")
                        self.total_errors += 1
                        
                        # Consider disabling strategy if too many errors
                        await self._handle_strategy_error(strategy_name, e)
        
        except Exception as e:
            self.logger.error(f"Error handling market data event: {e}")
            self.total_errors += 1
    
    async def _handle_strategy_signal(self, signal: TradingSignal):
        """Handle trading signal generated by a strategy."""
        try:
            # Store signal persistently via NATS JetStream
            await self._store_signal_persistently(signal)
            self.signal_count += 1
            
            self.logger.info(f"Signal generated: {signal}")
            
            # NEW ROUTING LOGIC:
            # 1. Paper trading receives ALL signals by default (if paper trading is enabled)
            # 2. Zerodha trading only receives signals from strategies with zerodha_trade=true
            
            # Check if paper trading is enabled via environment
            paper_trading_enabled = self.settings.get('PAPER_TRADING_ENABLED', 'true').lower() == 'true'
            
            if paper_trading_enabled:
                # Route ALL signals to paper trading
                await self._route_to_paper_trading(signal)
                self.logger.debug(f"Signal routed to paper trading: {signal.signal_id}")
            
            # Route to live trading only if strategy specifically enables zerodha_trade
            strategy_config = self.strategy_configs.get(signal.strategy_name, {})
            routing_config = strategy_config.get('routing', {})
            zerodha_trade_enabled = routing_config.get('zerodha_trade', False)
            
            if zerodha_trade_enabled:
                # Check if zerodha trading is globally enabled
                zerodha_trading_enabled = self.settings.get('ZERODHA_TRADING_ENABLED', 'false').lower() == 'true'
                
                if zerodha_trading_enabled:
                    await self._route_to_live_trading(signal)
                    self.logger.info(f"Signal routed to zerodha trading: {signal.signal_id} from strategy {signal.strategy_name}")
                else:
                    self.logger.debug(f"Zerodha trading disabled globally, skipping live routing for signal: {signal.signal_id}")
            else:
                self.logger.debug(f"Strategy {signal.strategy_name} not configured for zerodha trading, skipping live routing")
            
        except Exception as e:
            self.logger.error(f"Error handling strategy signal: {e}")
            self.total_errors += 1
    
    async def _store_signal_persistently(self, signal: TradingSignal):
        """Store signal persistently via NATS JetStream."""
        try:
            # Create signal event for persistent storage
            signal_data = {
                "signal_id": signal.signal_id,
                "strategy_name": signal.strategy_name,
                "instrument_token": signal.instrument_token,
                "tradingsymbol": signal.tradingsymbol,
                "exchange": signal.exchange,
                "signal_type": signal.signal_type.value,
                "quantity": signal.quantity,
                "price": float(signal.price) if signal.price else None,
                "order_type": signal.order_type.value,
                "product": signal.product,
                "validity": signal.validity,
                "timestamp": signal.timestamp.isoformat(),
                "confidence": signal.confidence,
                "metadata": signal.metadata
            }
            
            # Publish to persistent TRADING stream
            await self._publish_event(
                f"trading.signal.{signal.strategy_name}.{signal.instrument_token}",
                signal_data
            )
            
            self.signals_routed += 1
            self.logger.debug(f"Signal stored persistently: {signal.strategy_name} -> {signal.signal_type}")
            
        except Exception as e:
            self.logger.error(f"Failed to store signal persistently: {e}")
            # Don't re-raise to avoid breaking signal processing
    
    async def _route_to_paper_trading(self, signal: TradingSignal):
        """Route signal to paper trading engine.
        
        Paper trading now receives ALL signals by default when enabled,
        regardless of individual strategy configuration.
        """
        try:
            # Convert signal to paper trading format
            paper_signal_data = {
                "strategy_name": signal.strategy_name,
                "instrument_token": signal.instrument_token,
                "tradingsymbol": signal.tradingsymbol,
                "exchange": signal.exchange,
                "transaction_type": signal.signal_type.value,
                "quantity": signal.quantity,
                "price": float(signal.price) if signal.price else None,
                "order_type": signal.order_type.value,
                "product": signal.product,
                "validity": signal.validity,
                "signal_id": signal.signal_id,
                "timestamp": signal.timestamp.isoformat(),
                "routing": "paper"
            }
            
            await self._publish_event("trading.signal.paper", paper_signal_data)
            self.signals_routed += 1
            
            self.logger.info(f"Signal routed to paper trading: {signal.signal_id}")
            
        except Exception as e:
            self.logger.error(f"Error routing signal to paper trading: {e}")
    
    async def _route_to_live_trading(self, signal: TradingSignal):
        """Route signal to live trading engine with risk validation."""
        try:
            # Convert signal to live trading format
            live_signal_data = {
                "strategy_name": signal.strategy_name,
                "instrument_token": signal.instrument_token,
                "tradingsymbol": signal.tradingsymbol,
                "exchange": signal.exchange,
                "transaction_type": signal.signal_type.value,
                "quantity": signal.quantity,
                "price": float(signal.price) if signal.price else None,
                "order_type": signal.order_type.value,
                "product": signal.product,
                "validity": signal.validity,
                "signal_id": signal.signal_id,
                "timestamp": signal.timestamp.isoformat(),
                "routing": "live"
            }
            
            # Route through risk manager first
            from core.events.event_types import TradingEvent
            event = TradingEvent(
                source="strategy_manager",
                data={
                    "signal": live_signal_data,
                    "callback_subject": "trading.signal.validated"
                }
            )
            await self._publish_event("risk.validation.request", event)
            
            self.signals_routed += 1
            self.logger.info(f"Signal sent for risk validation: {signal.signal_id}")
            
        except Exception as e:
            self.logger.error(f"Error routing signal to live trading: {e}")
    
    async def _handle_signal_executed(self, event_data: Dict[str, Any]):
        """Handle signal execution notification."""
        try:
            execution_data = event_data.get("data", event_data)
            strategy_name = execution_data.get("strategy_name")
            signal_id = execution_data.get("signal_id")
            
            if strategy_name in self.strategies:
                strategy = self.strategies[strategy_name]
                
                # Signal lookup would need to be implemented via persistent storage
                # For now, we'll pass the signal_id and let the strategy handle it
                self.logger.info(f"Signal {signal_id} executed for strategy {strategy_name}")
                await strategy.on_signal_executed(None, execution_data)
                self.logger.info(f"Signal execution notified to strategy {strategy_name}")
            
        except Exception as e:
            self.logger.error(f"Error handling signal execution: {e}")
    
    async def _handle_strategy_error(self, strategy_name: str, error: Exception):
        """Handle strategy errors and decide on actions."""
        try:
            strategy = self.strategies.get(strategy_name)
            if strategy:
                await strategy.on_error(error, "market_data_processing")
                
                # Check if strategy should be disabled due to too many errors
                if strategy.error_count >= 5:  # Configurable threshold
                    await self._disable_strategy(strategy_name, f"Too many errors: {strategy.error_count}")
            
        except Exception as e:
            self.logger.error(f"Error handling strategy error for {strategy_name}: {e}")
    
    async def _disable_strategy(self, strategy_name: str, reason: str):
        """Disable a failed strategy."""
        try:
            if strategy_name in self.active_strategies:
                self.active_strategies.remove(strategy_name)
            
            self.failed_strategies.add(strategy_name)
            
            strategy = self.strategies.get(strategy_name)
            if strategy:
                await strategy.stop()
            
            self.logger.warning(f"Strategy disabled: {strategy_name} - {reason}")
            
            # Publish strategy disabled event
            from core.events.event_types import SystemEvent, EventType
            import uuid
            event = SystemEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.STRATEGY_STOPPED,
                timestamp=datetime.now(timezone.utc),
                source="strategy_manager",
                details={
                    "strategy_name": strategy_name,
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
            await self._publish_event("strategy.disabled", event)
            
        except Exception as e:
            self.logger.error(f"Error disabling strategy {strategy_name}: {e}")
    
    # Public API methods
    
    async def start_strategy(self, strategy_name: str) -> bool:
        """Start a specific strategy."""
        if strategy_name not in self.strategies:
            self.logger.error(f"Strategy not found: {strategy_name}")
            return False
        
        if strategy_name in self.active_strategies:
            self.logger.info(f"Strategy already active: {strategy_name}")
            return True
        
        try:
            strategy = self.strategies[strategy_name]
            success = await strategy.start()
            
            if success:
                self.active_strategies.add(strategy_name)
                self.failed_strategies.discard(strategy_name)
                self.logger.info(f"Started strategy: {strategy_name}")
                return True
            else:
                self.failed_strategies.add(strategy_name)
                self.logger.error(f"Failed to start strategy: {strategy_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting strategy {strategy_name}: {e}")
            self.failed_strategies.add(strategy_name)
            return False
    
    async def stop_strategy(self, strategy_name: str) -> bool:
        """Stop a specific strategy."""
        if strategy_name not in self.strategies:
            self.logger.error(f"Strategy not found: {strategy_name}")
            return False
        
        try:
            strategy = self.strategies[strategy_name]
            await strategy.stop()
            self.active_strategies.discard(strategy_name)
            
            self.logger.info(f"Stopped strategy: {strategy_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error stopping strategy {strategy_name}: {e}")
            return False
    
    async def reload_strategy(self, strategy_name: str) -> bool:
        """Reload a strategy configuration and instance."""
        if strategy_name not in self.strategy_configs:
            self.logger.error(f"Strategy configuration not found: {strategy_name}")
            return False
        
        try:
            # Stop existing strategy if active
            if strategy_name in self.active_strategies:
                await self.stop_strategy(strategy_name)
            
            # Reload strategy type if needed
            config = self.strategy_configs[strategy_name]
            strategy_type = config.get("strategy_type")
            strategy_factory.reload_strategy(strategy_type)
            
            # Create new strategy instance
            strategy = strategy_factory.create_strategy(strategy_name, strategy_type, config)
            self.strategies[strategy_name] = strategy
            
            # Start the reloaded strategy
            success = await self.start_strategy(strategy_name)
            
            if success:
                self.logger.info(f"Successfully reloaded strategy: {strategy_name}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error reloading strategy {strategy_name}: {e}")
            return False
    
    def get_strategy_status(self, strategy_name: str) -> Dict[str, Any]:
        """Get status information for a specific strategy."""
        if strategy_name not in self.strategies:
            return {"error": "Strategy not found"}
        
        strategy = self.strategies[strategy_name]
        
        return {
            "strategy_name": strategy_name,
            "is_active": strategy_name in self.active_strategies,
            "is_failed": strategy_name in self.failed_strategies,
            "performance": strategy.get_performance_stats(),
            "config": self.strategy_configs.get(strategy_name, {}),
            "instruments": strategy.get_instruments(),
            "routing": strategy.get_routing_config()
        }
    
    def get_manager_status(self) -> Dict[str, Any]:
        """Get comprehensive strategy manager status."""
        uptime = datetime.now(timezone.utc) - self.start_time
        
        return {
            "is_initialized": self.is_initialized,
            "is_running": self.is_running,
            "uptime_seconds": uptime.total_seconds(),
            "total_strategies": len(self.strategies),
            "active_strategies": len(self.active_strategies),
            "failed_strategies": len(self.failed_strategies),
            "strategy_names": list(self.strategies.keys()),
            "active_strategy_names": list(self.active_strategies),
            "failed_strategy_names": list(self.failed_strategies),
            "subscribed_instruments": len(self.subscribed_instruments),
            "signals_generated": self.signal_count,
            "signals_routed": self.signals_routed,
            "market_data_processed": self.market_data_processed,
            "total_errors": self.total_errors,
            "last_market_data_time": self.last_market_data_time.isoformat() if self.last_market_data_time else None,
            "available_strategy_types": strategy_factory.get_registered_strategies()
        }
    
    def get_all_strategies_performance(self) -> Dict[str, Dict[str, Any]]:
        """Get performance data for all strategies."""
        performance = {}
        
        for strategy_name, strategy in self.strategies.items():
            performance[strategy_name] = strategy.get_performance_stats()
        
        return performance
    
    def get_recent_signals(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent trading signals from persistent storage."""
        # TODO: Implement retrieval from persistent NATS JetStream storage
        # For now, return empty list as signals are stored in event bus
        self.logger.debug(f"Recent signals request (limit: {limit}) - signals now stored persistently")
        return []
    
    # Health monitoring methods
    async def get_strategy_health(self, strategy_name: str) -> Optional[Dict[str, Any]]:
        """Get health metrics for a specific strategy."""
        if not self.health_monitor:
            return {"error": "Health monitoring not available"}
        
        metrics = await self.health_monitor.get_strategy_health(strategy_name)
        if metrics:
            return {
                "strategy_name": metrics.strategy_name,
                "health_level": metrics.health_level.value,
                "health_score": metrics.health_score,
                "is_registered": metrics.is_registered,
                "is_initialized": metrics.is_initialized,
                "is_active": metrics.is_active,
                "market_data_received": metrics.market_data_received,
                "last_market_data_time": metrics.last_market_data_time.isoformat() if metrics.last_market_data_time else None,
                "market_data_lag_seconds": metrics.market_data_lag_seconds,
                "signals_generated": metrics.signals_generated,
                "signals_executed": metrics.signals_executed,
                "execution_success_rate": metrics.execution_success_rate,
                "error_count": metrics.error_count,
                "error_rate": metrics.error_rate,
                "uptime_percentage": metrics.uptime_percentage,
                "issues": [
                    {
                        "type": issue.check_type.value,
                        "severity": issue.severity,
                        "description": issue.description,
                        "timestamp": issue.timestamp.isoformat()
                    }
                    for issue in metrics.issues
                ],
                "last_health_check": metrics.last_health_check.isoformat() if metrics.last_health_check else None
            }
        return {"error": "Strategy not found in health monitoring"}
    
    async def get_all_strategies_health(self) -> Dict[str, Any]:
        """Get health metrics for all strategies."""
        if not self.health_monitor:
            return {"error": "Health monitoring not available"}
        
        metrics = await self.health_monitor.get_all_strategies_health()
        health_data = {}
        
        for strategy_name, strategy_metrics in metrics.items():
            health_data[strategy_name] = {
                "health_level": strategy_metrics.health_level.value,
                "health_score": strategy_metrics.health_score,
                "is_active": strategy_metrics.is_active,
                "market_data_lag_seconds": strategy_metrics.market_data_lag_seconds,
                "execution_success_rate": strategy_metrics.execution_success_rate,
                "error_rate": strategy_metrics.error_rate,
                "issues_count": len(strategy_metrics.issues)
            }
        
        return health_data
    
    async def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary for all strategies."""
        if not self.health_monitor:
            return {"error": "Health monitoring not available"}
        
        return await self.health_monitor.get_health_summary()
    
    async def get_unhealthy_strategies(self) -> List[str]:
        """Get list of strategies with health issues."""
        if not self.health_monitor:
            return []
        
        return await self.health_monitor.get_unhealthy_strategies()
    
    async def _handle_market_data_event(self, event: MarketDataEvent) -> None:
        """Handle market data events and route to active strategies.
        
        Args:
            event: Market data event from new event system
        """
        try:
            # Route market data to all active strategies
            for strategy_name in self.active_strategies:
                strategy = self.strategies.get(strategy_name)
                if strategy and hasattr(strategy, 'on_market_data'):
                    try:
                        await strategy.on_market_data(event)
                    except Exception as e:
                        self.logger.error(f"Error processing market data in strategy {strategy_name}: {e}")
                        await self._handle_strategy_error(strategy_name, e)
            
        except Exception as e:
            self.logger.error(f"Error handling market data event: {e}")
    
    async def _handle_trading_signal_event(self, event: TradingEvent) -> None:
        """Handle trading signal events from strategies.
        
        Args:
            event: Trading signal event from new event system
        """
        try:
            self.logger.info(f"Received trading signal from strategy: {event.source}")
            
            # Update signal tracking
            self.signal_count += 1
            
            # Here you would typically route the signal to:
            # 1. Risk manager for validation
            # 2. Trading engine for execution
            # 3. Performance tracking
            
            # For now, just log the signal details
            if hasattr(event, 'data') and event.data:
                signal_data = event.data
                self.logger.info(f"Signal details: {signal_data}")
                
        except Exception as e:
            self.logger.error(f"Error handling trading signal event: {e}")