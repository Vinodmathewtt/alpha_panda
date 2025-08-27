# Strategy Runner Service - Main orchestrator service
from typing import Dict, Any, List
from sqlalchemy import select
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.schemas.events import EventType
from core.schemas.topics import TopicNames, ConsumerGroups, TopicMap
from core.config.settings import RedpandaSettings, Settings
from core.database.connection import DatabaseManager
from core.database.models import StrategyConfiguration
from core.logging import get_trading_logger_safe, get_performance_logger_safe, get_error_logger_safe
from core.market_hours.market_hours_checker import MarketHoursChecker
from .factory import StrategyFactory
from .runner import StrategyRunner


class StrategyRunnerService:
    """Main orchestrator service for running trading strategies"""
    
    def __init__(self, config: RedpandaSettings, settings: Settings, db_manager: DatabaseManager, redis_client=None, market_hours_checker: MarketHoursChecker = None):
        self.settings = settings
        self.db_manager = db_manager
        self.logger = get_trading_logger_safe("strategy_runner")
        self.perf_logger = get_performance_logger_safe("strategy_runner_performance")
        self.error_logger = get_error_logger_safe("strategy_runner_errors")
        
        # Market hours checker for market status awareness - use injected or create new
        self.market_hours_checker = market_hours_checker or MarketHoursChecker()
        
        # Pipeline monitoring metrics
        self.signals_generated = 0
        self.strategies_processed = 0
        self.last_signal_time = None
        # Store active brokers for signal generation
        self.active_brokers = settings.active_brokers
        self.strategy_runners: Dict[str, StrategyRunner] = {}
        self.strategy_instruments: Dict[str, List[int]] = {}  # strategy_id -> instrument_tokens
        
        # Build streaming service - CLEANED: Remove wrapper pattern
        self.orchestrator = (StreamServiceBuilder("strategy_runner", config, settings)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                topics=[TopicNames.MARKET_TICKS],  # Shared market data
                group_id=f"{settings.redpanda.group_id_prefix}.strategy_runner.ticks",
                handler_func=self._handle_market_tick  # Direct topic-aware handler
            )
            .build()
        )
    
    async def _get_producer(self):
        """Safely get producer with error handling"""
        if not self.orchestrator.producers:
            raise RuntimeError(f"No producers available for {self.__class__.__name__}")
        
        if len(self.orchestrator.producers) == 0:
            raise RuntimeError(f"Producers list is empty for {self.__class__.__name__}")
        
        return self.orchestrator.producers[0]
        
    async def start(self):
        """Start the strategy runner service"""
        await self.orchestrator.start()
        
        # Load strategies from database
        await self._load_strategies()
        
        self.logger.info(f"🏭 Strategy runner started with active brokers: {self.settings.active_brokers}",
                        strategies_loaded=len(self.strategy_runners))
        
    async def _load_strategies(self):
        """Load active strategies from database, fallback to YAML if empty"""
        strategies_loaded = 0
        
        # Try loading from database first
        async with self.db_manager.get_session() as session:
            # Query active strategies
            stmt = select(StrategyConfiguration).where(
                StrategyConfiguration.is_active == True
            )
            result = await session.execute(stmt)
            strategy_configs = result.scalars().all()
            
            for config in strategy_configs:
                try:
                    # Create strategy instance with broker awareness
                    strategy = StrategyFactory.create_strategy(
                        strategy_id=config.id,
                        strategy_type=config.strategy_type,
                        parameters=config.parameters,
                        brokers=["paper", "zerodha"] if config.zerodha_trading_enabled else ["paper"],
                        instrument_tokens=config.instruments
                    )
                    
                    # Create runner for this strategy
                    runner = StrategyRunner(strategy)
                    self.strategy_runners[config.id] = runner
                    
                    # Store instrument mapping for filtering
                    self.strategy_instruments[config.id] = config.instruments
                    
                    self.logger.info(
                        "Loaded strategy",
                        strategy_id=config.id,
                        strategy_type=config.strategy_type,
                        instruments=config.instruments
                    )
                    
                except Exception as e:
                    self.logger.error(
                        "Failed to load strategy",
                        strategy_id=config.id,
                        error=str(e)
                    )
            
            strategies_loaded = len(self.strategy_runners)
        
        # Fallback to YAML configuration if no database strategies loaded
        if strategies_loaded == 0:
            self.logger.info("No strategies found in database, loading from YAML configurations")
            try:
                yaml_strategies = StrategyFactory.create_strategies_from_yaml()
                for strategy in yaml_strategies:
                    runner = StrategyRunner(strategy)
                    self.strategy_runners[strategy.strategy_id] = runner
                    
                    # Store instrument mapping for filtering
                    self.strategy_instruments[strategy.strategy_id] = strategy.instrument_tokens
                    
                    self.logger.info(
                        "Loaded strategy from YAML",
                        strategy_id=strategy.strategy_id,
                        brokers=strategy.brokers,
                        instruments=strategy.instrument_tokens
                    )
                    strategies_loaded += 1
                    
            except Exception as e:
                self.logger.error("Failed to load strategies from YAML", error=str(e))
        
        self.logger.info(f"Total strategies loaded: {strategies_loaded}")
    
    async def stop(self):
        """Stop the strategy runner service"""
        await self.orchestrator.stop()
        self.logger.info("Strategy runner service stopped")
    
    async def _handle_market_tick(self, message: Dict[str, Any], topic: str) -> None:
        """Process market tick and generate signals for all active brokers."""
        if message.get('type') != EventType.MARKET_TICK:
            return
        
        if not self.market_hours_checker.is_market_open():
            self.logger.debug("Ignoring market tick - market is closed")
            return
            
        tick_data = message.get("data", {})
        instrument_token = tick_data.get("instrument_token")
        
        if not instrument_token:
            return
        
        # Find strategies interested in this instrument
        interested_strategies = []
        for strategy_id, runner in self.strategy_runners.items():
            strategy_instruments = self.strategy_instruments.get(strategy_id, [])
            if instrument_token in strategy_instruments:
                interested_strategies.append((strategy_id, runner))
        
        # Process tick through each interested strategy
        for strategy_id, runner in interested_strategies:
            try:
                # Get strategy configuration for broker routing
                strategy_config = await self._get_strategy_config(strategy_id)
                
                # FIXED: Call process_market_data without producer_callback, get returned signals
                signals = await runner.process_market_data(tick_data)
                
                if signals:
                    # Generate signals for each active broker that this strategy should run on
                    for broker in self.active_brokers:
                        if self._should_process_strategy_for_broker(strategy_config, broker):
                            # Emit each signal to the appropriate broker topic
                            for signal in signals:
                                await self._emit_signal(signal, broker, strategy_id)
                                
            except Exception as e:
                self.error_logger.error("Error executing strategy",
                                      strategy_id=strategy_id,
                                      instrument_token=instrument_token,
                                      error=str(e))
    
    def _should_process_strategy_for_broker(self, strategy_config: Dict, broker: str) -> bool:
        """Determine if strategy should generate signals for specific broker."""
        if broker == "paper":
            return True  # Always generate paper signals
        elif broker == "zerodha":
            return strategy_config.get('zerodha_trading_enabled', False)
        return False
    
    async def _get_strategy_config(self, strategy_id: str) -> Dict:
        """Get strategy configuration from database or default."""
        # Simplified - can be enhanced to query database
        return {"zerodha_trading_enabled": True}  # Default config
    
    async def _emit_signal(self, signal, broker: str, strategy_id: str):
        """Emit trading signal to appropriate broker topic with validation"""
        
        try:
            # Validate broker configuration
            if broker not in self.active_brokers:
                self.error_logger.error(f"Broker {broker} not in active brokers: {self.active_brokers}")
                raise ValueError(f"Invalid broker: {broker}")
            
            # Get and validate topic
            topic_map = TopicMap(broker)
            topic = topic_map.signals_raw()
            
            # Validate topic matches broker
            from core.schemas.topic_validator import TopicValidator
            if not TopicValidator.validate_broker_topic_pair(topic, broker):
                raise ValueError(f"Topic {topic} does not match broker {broker}")
            
            self.logger.debug(f"Emitting signal to validated topic: {topic} for broker: {broker}")
            
            # Get producer safely and emit signal
            producer = await self._get_producer()
            key = f"{strategy_id}:{signal.instrument_token}"
            
            await producer.send(
                topic=topic,
                key=key,
                data=signal.dict(),
                event_type=EventType.TRADING_SIGNAL
            )
            
            self.logger.info("Signal generated", 
                            broker=broker,
                            strategy_id=strategy_id,
                            signal_type=signal.signal_type,
                            topic=topic)
                            
        except Exception as e:
            self.error_logger.error(f"Failed to emit signal: {e}")
            raise