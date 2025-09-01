# Strategy Runner Service - Main orchestrator service
import asyncio
from typing import Dict, Any, List
from collections import defaultdict
from sqlalchemy import select
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.schemas.events import EventType
from core.schemas.topics import TopicNames, ConsumerGroups, TopicMap
from core.config.settings import RedpandaSettings, Settings
from core.database.connection import DatabaseManager
from core.database.models import StrategyConfiguration
from core.logging import get_trading_logger_safe, get_performance_logger_safe, get_error_logger_safe
from core.market_hours.market_hours_checker import MarketHoursChecker
from core.monitoring.pipeline_metrics import PipelineMetricsCollector
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector
from core.observability.tracing import get_tracer
from .factory import StrategyFactory
# Legacy runner import removed - composition-only architecture


class StrategyRunnerService:
    """Modern composition-based strategy runner service - NO LEGACY SUPPORT"""
    
    def __init__(self, config: RedpandaSettings, settings: Settings, db_manager: DatabaseManager, redis_client=None, market_hours_checker: MarketHoursChecker = None, prometheus_metrics: PrometheusMetricsCollector = None):
        self.settings = settings
        self.db_manager = db_manager
        self.logger = get_trading_logger_safe("strategy_runner")
        self.perf_logger = get_performance_logger_safe("strategy_runner_performance")
        self.error_logger = get_error_logger_safe("strategy_runner_errors")
        
        # Initialize pipeline metrics collector for observability
        self.metrics_collector = PipelineMetricsCollector(
            redis_client=redis_client,
            settings=settings,
            broker_namespace="strategy_runner"
        ) if redis_client else None
        
        # Market hours checker for market status awareness - use injected or create new
        self.market_hours_checker = market_hours_checker or MarketHoursChecker()
        # Prometheus metrics (shared registry via DI)
        self.prom_metrics: PrometheusMetricsCollector | None = prometheus_metrics
        
        # Pipeline monitoring metrics
        self.signals_generated = 0
        self.strategies_processed = 0
        self.last_signal_time = None
        # Store active brokers for signal generation
        self.active_brokers = settings.active_brokers
        
        # ✅ COMPOSITION-ONLY ARCHITECTURE - NO LEGACY SUPPORT
        self.strategy_executors: Dict[str, Any] = {}  # Composition strategies ONLY
        self.strategy_instruments: Dict[str, List[int]] = {}  # strategy_id -> instrument_tokens
        
        # NEW: Reverse mapping for efficient tick routing (O(1) vs O(n))
        self.instrument_to_strategies: Dict[int, List[str]] = defaultdict(list)
        
        # Build streaming service - CLEANED: Remove wrapper pattern
        self.orchestrator = (StreamServiceBuilder("strategy_runner", config, settings)
            .with_prometheus(prometheus_metrics)
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
        return self.orchestrator.producers[0]
        
    async def start(self):
        """Start the strategy runner service"""
        await self.orchestrator.start()

        # Load strategies from database
        await self._load_strategies()

        self.logger.info(f"🏭 Composition strategy runner started with active brokers: {self.settings.active_brokers}",
                        composition_strategies=len(self.strategy_executors),
                        architecture="composition_only")

        # Mark pipeline stage healthy in Prometheus for active brokers
        if self.prom_metrics:
            try:
                for broker in self.active_brokers:
                    self.prom_metrics.set_pipeline_health("strategy_runner", broker, True)
            except Exception as _e:
                # Do not fail startup on metrics errors
                self.logger.warning("Failed to set Prometheus pipeline health", error=str(_e))
        
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
                    # ✅ COMPOSITION-ONLY ARCHITECTURE - ALL STRATEGIES USE COMPOSITION
                    strategy_executor = StrategyFactory.create_strategy(
                        strategy_id=config.id,
                        strategy_type=config.strategy_type,
                        parameters=config.parameters,
                        brokers=["paper", "zerodha"] if config.zerodha_trading_enabled else ["paper"],
                        instrument_tokens=config.instruments
                    )
                    self.strategy_executors[config.id] = strategy_executor
                    self.strategy_instruments[config.id] = config.instruments
                    
                    # Update instrument mapping for O(1) tick routing
                    for instrument_token in config.instruments:
                        self.instrument_to_strategies[instrument_token].append(config.id)
                    
                    strategies_loaded += 1
                    self.logger.info(f"Loaded composition strategy: {config.id}", 
                                   strategy_type=config.strategy_type,
                                   architecture="composition")
                    
                except Exception as e:
                    self.logger.error(
                        "Failed to load strategy",
                        strategy_id=config.id,
                        error=str(e)
                    )
            
            strategies_loaded = len(self.strategy_executors)
        
        # Only use database strategies - no YAML fallback in composition architecture
        
        self.logger.info(f"Total strategies loaded: {strategies_loaded}")
    
    async def stop(self):
        """Stop the strategy runner service"""
        await self.orchestrator.stop()
        self.logger.info("Strategy runner service stopped")
    
    def _is_event_type(self, message: Dict[str, Any], et: EventType) -> bool:
        t = message.get('type')
        if isinstance(t, EventType):
            return t == et
        if isinstance(t, str):
            return t == et or t == et.value or t.lower() == et.value
        return False

    async def _handle_market_tick(self, message: Dict[str, Any], topic: str) -> None:
        """Process market tick and generate signals for all active brokers."""
        tracer = get_tracer("strategy_runner")
        if not self._is_event_type(message, EventType.MARKET_TICK):
            return
        
        if not self.market_hours_checker.is_market_open():
            self.logger.debug("Ignoring market tick - market is closed")
            return
            
        tick_data = message.get("data", {})
        instrument_token = tick_data.get("instrument_token")
        
        if not instrument_token:
            return
        
        # NEW: Efficiently find interested strategies with O(1) lookup
        interested_strategy_ids = self.instrument_to_strategies.get(instrument_token, [])
        if not interested_strategy_ids:
            return  # No strategies interested in this instrument
        
        # Process tick through each interested strategy using composition architecture only
        for strategy_id in interested_strategy_ids:
            executor = self.strategy_executors.get(strategy_id)
            if executor:
                try:
                    with tracer.start_as_current_span("strategy.process_tick") as span:
                        try:
                            span.set_attribute("strategy.id", strategy_id)
                            span.set_attribute("instrument_token", instrument_token)
                        except Exception:
                            pass
                    # COMPOSITION: Process using StrategyExecutor
                    from core.schemas.events import MarketTick
                    
                    # Convert tick_data to MarketTick format
                    market_tick = MarketTick(
                        instrument_token=tick_data["instrument_token"],
                        last_price=tick_data["last_price"],
                        timestamp=tick_data["timestamp"],
                        symbol=tick_data.get("symbol", "")
                    )
                    
                    signal_result = executor.process_tick(market_tick)
                    
                    if signal_result:
                        # Convert signal result to TradingSignal format
                        from core.schemas.events import TradingSignal, SignalType
                        
                        signal_type_map = {
                            "BUY": SignalType.BUY,
                            "SELL": SignalType.SELL,
                            "HOLD": SignalType.HOLD
                        }
                        
                        signal_type = signal_type_map.get(signal_result.signal_type)
                        
                        # Skip HOLD signals - no action needed
                        if not signal_type or signal_type == SignalType.HOLD:
                            continue
                        
                        trading_signal = TradingSignal(
                            strategy_id=strategy_id,
                            instrument_token=tick_data["instrument_token"],
                            signal_type=signal_type,
                            quantity=signal_result.quantity,
                            price=signal_result.price,
                            timestamp=tick_data["timestamp"],
                            confidence=signal_result.confidence,
                            metadata=signal_result.metadata or {}
                        )
                        
                        # Generate signals for each configured broker
                        emission_tasks = []
                        for broker in executor.config.active_brokers:
                            if broker in self.active_brokers:
                                emission_tasks.append(
                                    self._emit_signal(trading_signal, broker, strategy_id)
                                )
                        
                        # Execute all emission tasks concurrently
                        if emission_tasks:
                            await asyncio.gather(*emission_tasks)
                            self.signals_generated += len(emission_tasks)
                            
                except Exception as e:
                    self.error_logger.error(f"Error processing composition strategy {strategy_id}: {e}")
                continue
    
    
    async def _emit_signal(self, signal, broker: str, strategy_id: str):
        """Emit trading signal to appropriate broker topic with validation"""
        tracer = get_tracer("strategy_runner")
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
            from core.schemas.topics import PartitioningKeys
            key = PartitioningKeys.trading_signal_key(strategy_id, signal.instrument_token)
            
            with tracer.start_as_current_span("strategy.emit_signal") as span:
                try:
                    span.set_attribute("strategy.id", strategy_id)
                    span.set_attribute("broker", broker)
                    span.set_attribute("topic", topic)
                    span.set_attribute("instrument_token", signal.instrument_token)
                except Exception:
                    pass
                await producer.send(
                    topic=topic,
                    key=key,
                    data=signal.model_dump(mode='json'),
                    event_type=EventType.TRADING_SIGNAL,
                    broker=broker
                )

            # Record pipeline metrics for observability
            if self.metrics_collector:
                try:
                    # Use proper signal recording method for consistency
                    signal_data = signal.dict()
                    signal_data.update({"strategy_id": strategy_id, "id": f"{strategy_id}_{signal.instrument_token}"})
                    await self.metrics_collector.record_signal_generated(signal_data, broker_context=broker)
                    
                    # Track strategy-specific metrics
                    await self.metrics_collector.increment_count(
                        f"strategies.{strategy_id}.signals", broker
                    )
                except Exception as metrics_error:
                    # Don't fail signal emission due to metrics errors
                    self.logger.warning("Failed to record metrics", 
                                       error=str(metrics_error))

            # Record Prometheus business and throughput metrics
            if self.prom_metrics:
                try:
                    self.prom_metrics.record_signal_generated(
                        strategy_id=strategy_id,
                        broker=broker,
                        signal_type=signal.signal_type.value,
                    )
                    self.prom_metrics.record_event_processed(
                        service="strategy_runner",
                        broker=broker,
                        event_type=EventType.TRADING_SIGNAL.value,
                    )
                except Exception as _e:
                    self.logger.warning("Failed to record Prometheus metrics", error=str(_e))
            
            self.logger.info("Signal generated", 
                            broker=broker,
                            strategy_id=strategy_id,
                            signal_type=signal.signal_type,
                            topic=topic)
                            
        except Exception as e:
            self.error_logger.error(f"Failed to emit signal: {e}")
            raise
