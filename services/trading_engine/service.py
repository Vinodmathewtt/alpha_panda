from typing import Dict, Any
from core.config.settings import RedpandaSettings, Settings
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.schemas.topics import TopicMap
from core.schemas.events import EventType, TradingSignal
from core.logging import get_trading_logger_safe, get_performance_logger_safe, get_error_logger_safe
from core.market_hours.market_hours_checker import MarketHoursChecker
from core.monitoring.pipeline_metrics import PipelineMetricsCollector  # CRITICAL FIX: Add metrics integration
from datetime import datetime, timezone
# Removed: from collections import defaultdict (no longer needed)

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
        
        # CRITICAL FIX: Add metrics collection integration
        self.metrics_collector = PipelineMetricsCollector(redis_client, settings, None)  # Multi-broker
        
        # Simplified state management - no warm-up needed
        # Removed: last_prices, pending_signals, warmed_up_instruments
        
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
            # REMOVED: No longer subscribe to market ticks
            # TradingEngine now focuses solely on signal execution
            .build()
        )
    
    async def _get_producer(self):
        """Safely get producer with error handling"""
        if not self.orchestrator.producers:
            raise RuntimeError(f"No producers available for {self.__class__.__name__}")
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
        
        # SIMPLIFIED: Execute immediately using data from unified log
        # No queuing, no waiting for market data
        
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
    
    # REMOVED: No longer handle market ticks
    # TradingEngine is now decoupled from market data
    
    async def _execute_on_trader(self, signal: TradingSignal, namespace: str) -> None:
        """Execute signal on trader - same business logic as before."""
        try:
            trader = self.trader_factory.get_trader(namespace)
            # Use price from signal data (unified log architecture)
            last_price = float(signal.price) if signal.price else None
            
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
                broker=broker  # CRITICAL FIX: Add required broker parameter
            )
            
            # CRITICAL FIX: Record metrics for pipeline monitoring
            if self.metrics_collector:
                try:
                    await self.metrics_collector.record_order_processed(result_data)
                    await self.metrics_collector.set_last_activity_timestamp("orders", broker)
                except Exception as e:
                    self.logger.warning(f"Failed to record order metrics: {e}", broker=broker)
            
            self.logger.info("Execution result emitted", 
                            broker=broker, 
                            topic=topic, 
                            event_type=event_type.value)
        except Exception as e:
            self.logger.error(f"Failed to get producer for order event emission: {e}")
            raise
    
    # REMOVED: No longer need pending signal processing
    # All signals execute immediately using available data
    
    def get_status(self) -> Dict[str, Any]:
        """Get service status."""
        return {
            "service_name": "trading_engine",
            "active_brokers": self.settings.active_brokers,
            "orchestrator_status": self.orchestrator.get_status(),
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            # REMOVED: warm-up and pending signal stats
            # Simplified architecture with immediate execution
        }