from typing import Dict, Any
from core.config.settings import RedpandaSettings, Settings
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.schemas.topics import TopicMap, TopicNames
from core.schemas.events import EventType, TradingSignal
from core.logging import get_trading_logger_safe, get_performance_logger_safe, get_error_logger_safe
from core.market_hours.market_hours_checker import MarketHoursChecker
from datetime import datetime, timezone
from collections import defaultdict

from .traders.trader_factory import TraderFactory
from .routing.execution_router import ExecutionRouter


class TradingEngineService:
    """Refactored trading engine using composition over inheritance."""
    
    def __init__(
        self, 
        config: RedpandaSettings, 
        settings: Settings, 
        redis_client,
        trader_factory: TraderFactory,
        execution_router: ExecutionRouter,
        market_hours_checker: MarketHoursChecker
    ):
        self.settings = settings
        self.trader_factory = trader_factory
        self.execution_router = execution_router
        self.market_hours_checker = market_hours_checker
        
        # State management
        self.last_prices: Dict[int, float] = {}
        self.pending_signals: Dict[int, list] = defaultdict(list)
        self.warmed_up_instruments: set[int] = set()
        
        # Metrics
        self.processed_count = 0
        self.error_count = 0
        
        # Enhanced logging setup
        self.logger = get_trading_logger_safe("trading_engine")
        self.perf_logger = get_performance_logger_safe("trading_engine_performance")
        self.error_logger = get_error_logger_safe("trading_engine_errors")
        
        # --- REFACTORED: Multi-broker topic subscription ---
        # Generate list of topics for all active brokers
        validated_signal_topics = []
        for broker in settings.active_brokers:
            topic_map = TopicMap(broker)
            validated_signal_topics.append(topic_map.signals_validated())
        
        # Build orchestrator with topic-aware handlers
        self.orchestrator = (StreamServiceBuilder("trading_engine", config, settings)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                topics=validated_signal_topics,  # Multiple broker topics
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.signals",  # Unified group
                handler_func=self._handle_validated_signal  # Now topic-aware
            )
            .add_consumer_handler(
                topics=[TopicNames.MARKET_TICKS],  # Market data is shared
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.ticks",
                handler_func=self._handle_market_tick
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
    
    async def start(self) -> None:
        """Start the service."""
        self.logger.info(f"🏢 Trading Engine starting with active brokers: {self.settings.active_brokers}")
        await self.trader_factory.initialize()
        await self.orchestrator.start()
        self.logger.info(f"🏢 Trading Engine started for brokers: {self.settings.active_brokers}")
    
    async def stop(self) -> None:
        """Stop the service."""
        self.logger.info(f"🏢 Trading Engine stopping for brokers: {self.settings.active_brokers}")
        await self.orchestrator.stop()
        await self.trader_factory.shutdown()
        self.logger.info(f"🏢 Trading Engine stopped for brokers: {self.settings.active_brokers}")
    
    # --- ENHANCED: Topic-aware message handlers ---
    async def _handle_validated_signal(self, message: Dict[str, Any], topic: str) -> None:
        """Handle validated signal with broker context from topic."""
        # Extract broker from topic name (e.g., "paper.signals.validated" -> "paper")
        broker = topic.split('.')[0]
        
        self.logger.info("Processing validated signal", 
                        broker=broker, 
                        topic=topic,
                        strategy_id=message.get('data', {}).get('original_signal', {}).get('strategy_id'))
        
        if message.get('type') != EventType.VALIDATED_SIGNAL:
            return
        
        if not self.market_hours_checker.is_market_open():
            self.logger.debug("Ignoring validated signal - market is closed", broker=broker)
            return
        
        data = message.get('data', {})
        original_signal = data.get('original_signal')
        if not original_signal:
            self.error_logger.error("Validated signal is missing the 'original_signal' data payload.", 
                                  broker=broker)
            return
        
        strategy_id = original_signal.get('strategy_id')
        instrument_token = original_signal.get('instrument_token')
        signal_type = original_signal.get('signal_type')
        quantity = original_signal.get('quantity')
        
        if not strategy_id or not instrument_token:
            self.error_logger.error("Invalid signal: missing strategy_id or instrument_token", 
                                  broker=broker)
            return
        
        # Check if instrument is warmed up with market data
        if instrument_token not in self.warmed_up_instruments:
            # Queue the signal with broker context for later processing
            self.pending_signals[instrument_token].append((data, broker))
            self.logger.info("Signal queued - waiting for market data",
                           strategy_id=strategy_id,
                           instrument_token=instrument_token,
                           signal_type=signal_type,
                           queued_signals=len(self.pending_signals[instrument_token]),
                           broker=broker)
            return
        
        self.logger.info("Processing validated signal for execution",
                        strategy_id=strategy_id,
                        instrument_token=instrument_token,
                        signal_type=signal_type,
                        quantity=quantity,
                        broker=broker)
        
        # Route to appropriate trader based on broker
        signal = TradingSignal(**original_signal)
        await self._execute_on_trader(signal, broker)
        
        self.processed_count += 1
    
    async def _handle_market_tick(self, message: Dict[str, Any], topic: str) -> None:
        """Handle market tick - pure business logic."""
        if message.get('type') != EventType.MARKET_TICK:
            return
        
        data = message.get('data', {})
        instrument_token = data.get('instrument_token')
        last_price = data.get('last_price')
        
        if instrument_token and last_price:
            self.last_prices[instrument_token] = last_price
            
            # Mark instrument as warmed up and process any pending signals
            if instrument_token not in self.warmed_up_instruments:
                self.warmed_up_instruments.add(instrument_token)
                await self._process_pending_signals(instrument_token)
                self.logger.info("Instrument warmed up with market data",
                               instrument_token=instrument_token,
                               pending_signals=len(self.pending_signals.get(instrument_token, [])),
                               broker="shared")
    
    async def _execute_on_trader(self, signal: TradingSignal, namespace: str) -> None:
        """Execute signal on trader - same business logic as before."""
        try:
            trader = self.trader_factory.get_trader(namespace)
            last_price = self.last_prices.get(signal.instrument_token)
            
            result_data = await trader.execute_order(signal, last_price)
            
            # Emit appropriate event based on result
            await self._emit_execution_result(signal, result_data, namespace)
            
        except Exception as e:
            self.error_count += 1
            self.error_logger.error(f"Execution failed on {namespace}", 
                                  strategy_id=signal.strategy_id, 
                                  error=str(e),
                                  broker=namespace)
    
    async def _emit_execution_result(self, signal: TradingSignal, result_data: Dict[str, Any], broker: str):
        """Emit appropriate event to broker-specific topic."""
        try:
            producer = await self._get_producer()
            
            # Dynamically construct broker-specific topic
            topic_map = TopicMap(broker)
            
            if "error_message" in result_data:
                event_type = EventType.ORDER_FAILED
                topic = topic_map.orders_failed()
            elif broker == "paper":
                event_type = EventType.ORDER_FILLED
                topic = topic_map.orders_filled()
            else:  # zerodha or other live trading
                event_type = EventType.ORDER_PLACED
                topic = topic_map.orders_submitted()
            
            key = f"{signal.strategy_id}:{signal.instrument_token}"
            
            await producer.send(
                topic=topic,
                key=key,
                data=result_data,
                event_type=event_type,
            )
            
            self.logger.info("Execution result emitted", 
                            broker=broker, 
                            topic=topic, 
                            event_type=event_type.value)
        except Exception as e:
            self.logger.error(f"Failed to get producer for order event emission: {e}")
            raise
    
    async def _process_pending_signals(self, instrument_token: int):
        """Process all pending signals for an instrument once market data is available"""
        pending = self.pending_signals.get(instrument_token, [])
        if not pending:
            return
        
        self.logger.info("Processing pending signals",
                        instrument_token=instrument_token,
                        pending_count=len(pending))
        
        # Process pending signals with their original broker context
        for signal_data, broker in pending:
            original_signal = signal_data.get('original_signal')
            if not original_signal:
                continue
            
            signal = TradingSignal(**original_signal)
            # Execute on the original broker only
            await self._execute_on_trader(signal, broker)
        
        # Clear processed signals
        del self.pending_signals[instrument_token]
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "service_name": "trading_engine",
            "active_brokers": self.settings.active_brokers,
            "orchestrator_status": self.orchestrator.get_status(),
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "warmed_up_instruments": len(self.warmed_up_instruments),
            "pending_signals": sum(len(signals) for signals in self.pending_signals.values())
        }