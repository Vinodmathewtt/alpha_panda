# Risk Manager Service - Main service
from typing import Dict, Any
from datetime import datetime, timezone
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.schemas.events import EventType, ValidatedSignal, RejectedSignal, TradingSignal
from core.schemas.topics import TopicNames, ConsumerGroups, TopicMap
from core.config.settings import RedpandaSettings, Settings
from core.logging import get_trading_logger_safe, get_performance_logger_safe, get_error_logger_safe
from core.logging.service_logger import get_service_logger
from core.monitoring import PipelineMetricsCollector
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector
from core.observability.tracing import get_tracer
import asyncio
from .rules import RiskRuleEngine
from .state import RiskStateManager


class RiskManagerService:
    """Validates trading signals against risk rules for all active brokers"""
    
    def __init__(self, config: RedpandaSettings, settings: Settings, redis_client=None, prometheus_metrics: PrometheusMetricsCollector = None):
        self.settings = settings
        self.config = config
        
        # Initialize business logic components using standardized logger pattern
        self.loggers = get_service_logger("risk_manager", "core")
        
        # Keep backward compatibility aliases
        self.logger = self.loggers.main
        self.perf_logger = self.loggers.performance
        self.error_logger = self.loggers.error
        self.rule_engine = RiskRuleEngine()
        self.state_manager = RiskStateManager(settings, redis_client)
        
        # Pipeline monitoring metrics
        self.processed_count = 0
        self.last_processed_time = None
        self.error_count = 0
        self.validation_start_time = None
        self.metrics_collector = PipelineMetricsCollector(redis_client, settings)
        self.prom_metrics: PrometheusMetricsCollector | None = prometheus_metrics
        
        
        # --- REFACTORED: Multi-broker topic subscription ---
        # Generate list of raw signal topics for all active brokers
        raw_signal_topics = []
        for broker in settings.active_brokers:
            topic_map = TopicMap(broker)
            raw_signal_topics.append(topic_map.signals_raw())
        
        # Build streaming service using composition with topic-aware handlers
        self.orchestrator = (StreamServiceBuilder("risk_manager", config, settings)
            .with_prometheus(prometheus_metrics)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                topics=raw_signal_topics + [TopicNames.MARKET_TICKS],  # Multi-broker signals + shared ticks
                group_id=f"{settings.redpanda.group_id_prefix}.risk_manager.signals",  # Unified group
                handler_func=self._handle_message  # Direct topic-aware handler
            )
            .build()
        )
        
    async def _get_producer(self):
        """Safely get producer with error handling"""
        if not self.orchestrator.producers:
            raise RuntimeError(f"No producers available for {self.__class__.__name__}")
        return self.orchestrator.producers[0]
        
    async def start(self):
        """Start the risk manager service"""
        # Initialize state manager for all active brokers
        for broker in self.settings.active_brokers:
            await self.state_manager.initialize(broker)
        
        await self.orchestrator.start()
        self.logger.info(f"🛡️ Risk Manager started for brokers: {self.settings.active_brokers}")
        # Per-broker context logs for clarity in multi-broker dashboards
        try:
            for _b in self.settings.active_brokers:
                self.logger.bind(broker=_b).info("Risk Manager started", broker=_b)
        except Exception:
            pass
        if self.prom_metrics:
            try:
                for broker in self.settings.active_brokers:
                    self.prom_metrics.set_pipeline_health("risk_manager", broker, True)
            except Exception:
                pass
        # Start lightweight heartbeat task for observability
        try:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        except Exception:
            self._heartbeat_task = None
    
    async def stop(self):
        """Stop the risk manager service"""
        await self.orchestrator.stop()
        await self.state_manager.close()
        self.logger.info(f"🛡️ Risk Manager stopped for brokers: {self.settings.active_brokers}")
        try:
            for _b in self.settings.active_brokers:
                self.logger.bind(broker=_b).info("Risk Manager stopped", broker=_b)
        except Exception:
            pass
        if self.prom_metrics:
            try:
                for broker in self.settings.active_brokers:
                    self.prom_metrics.set_pipeline_health("risk_manager", broker, False)
            except Exception:
                pass
        # Stop heartbeat
        try:
            if hasattr(self, "_heartbeat_task") and self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
        except Exception:
            pass
    
    def _is_event_type(self, message: Dict[str, Any], et: EventType) -> bool:
        t = message.get('type')
        if isinstance(t, EventType):
            return t == et
        if isinstance(t, str):
            return t == et or t == et.value or t.lower() == et.value
        return False

    async def _handle_message(self, message: Dict[str, Any], topic: str) -> None:
        """Handle incoming messages with broker context from topic."""
        tracer = get_tracer("risk_manager")
        # Extract broker from topic name using robust parsing
        broker = TopicMap.get_broker_from_topic(topic)
        
        # Extract key based on message type
        if self._is_event_type(message, EventType.TRADING_SIGNAL):
            data = message.get('data', {})
            from core.schemas.topics import PartitioningKeys
            try:
                key = PartitioningKeys.trading_signal_key(
                    data.get('strategy_id', ''), data.get('instrument_token', '')
                )
            except Exception:
                key = f"{data.get('strategy_id', '')}:{data.get('instrument_token', '')}"
            with tracer.start_as_current_span("risk.validate_signal") as span:
                try:
                    span.set_attribute("broker", broker)
                    span.set_attribute("key", key)
                except Exception:
                    pass
                await self._handle_trading_signal(key, message, broker)
        elif self._is_event_type(message, EventType.MARKET_TICK):
            await self._handle_market_tick(message)
        else:
            self.error_logger.warning("Unknown message type received",
                                     message_type=message.get('type'), 
                                     broker=broker,
                                     topic=topic,
                                     service="risk_manager")
            self.logger.warning("Unknown message type", message_type=message.get('type'), broker=broker)
    
    async def _handle_trading_signal(self, key: str, message: Dict[str, Any], broker: str):
        """Validate trading signal against risk rules"""
        
        if not self._is_event_type(message, EventType.TRADING_SIGNAL):
            self.logger.warning("Invalid message type for trading signal", message_type=message.get("type"))
            return
            
        signal_data = message.get("data", {})
        signal_id = message.get("id")
        correlation_id = message.get("correlation_id")
        
        # Record processing start
        self.validation_start_time = datetime.now(timezone.utc)
        
        self.logger.info("Processing signal for risk validation", 
                        signal_id=signal_id,
                        correlation_id=correlation_id,
                        strategy_id=signal_data.get("strategy_id"),
                        instrument_token=signal_data.get("instrument_token"),
                        signal_type=signal_data.get("signal_type"),
                        quantity=signal_data.get("quantity"),
                        broker=broker)
        
        try:
            # Get current risk state
            risk_state = await self.state_manager.get_state()
            
            # Evaluate signal against risk rules
            validation_result = self.rule_engine.evaluate_signal(signal_data, risk_state)
        
            if validation_result["passed"]:
                # Signal passed risk checks
                await self._emit_validated_signal(key, signal_data, validation_result, broker)
                
                # Update risk state
                await self._update_risk_state_for_signal(signal_data, broker)
                
            else:
                # Signal failed risk checks
                await self._emit_rejected_signal(key, signal_data, validation_result, broker)
            
            # Record successful processing
            self.processed_count += 1
            self.last_processed_time = datetime.now(timezone.utc)
            
            # Log performance metrics
            if self.validation_start_time:
                duration_ms = (self.last_processed_time - self.validation_start_time).total_seconds() * 1000
                self.perf_logger.info("Signal validation completed",
                                    signal_id=signal_id,
                                    correlation_id=correlation_id,
                                    processing_time_ms=duration_ms,
                                    signals_processed=self.processed_count,
                                    validation_passed=validation_result["passed"],
                                    broker=broker)
                                    
        except Exception as e:
            self.error_count += 1
            self.error_logger.error("Signal validation failed",
                                  signal_id=signal_id,
                                  correlation_id=correlation_id,
                                  strategy_id=signal_data.get("strategy_id"),
                                  error=str(e),
                                  broker=broker)
            if self.prom_metrics:
                try:
                    self.prom_metrics.record_error("risk_manager", type(e).__name__, broker)
                except Exception:
                    pass
            raise
    
    async def _handle_market_tick(self, message: Dict[str, Any]):
        """Update recent prices from market ticks"""
        # Accept both enum and string types robustly
        if not self._is_event_type(message, EventType.MARKET_TICK):
            return
            
        tick_data = message.get("data", {})
        instrument_token = tick_data.get("instrument_token")
        last_price = tick_data.get("last_price")
        
        if instrument_token and last_price:
            await self.state_manager.update_recent_price(
                instrument_token, 
                float(last_price)
            )
    
    async def _emit_validated_signal(self, key: str, signal_data: Dict[str, Any], 
                                   validation_result: Dict[str, Any], broker: str):
        """Emit validated signal"""
        tracer = get_tracer("risk_manager")
        try:
            # Create TradingSignal from data
            original_signal = TradingSignal(**signal_data)
            
            # Create ValidatedSignal
            validated_signal = ValidatedSignal(
                original_signal=original_signal,
                validated_quantity=original_signal.quantity,  # Could be modified by risk rules
                validated_price=original_signal.price,  # Could be modified by risk rules
                risk_checks=validation_result["rule_results"],
                timestamp=datetime.now(timezone.utc)
            )
            
            # Dynamically construct broker-specific validated topic
            topic_map = TopicMap(broker)
            validated_topic = topic_map.signals_validated()
            
            # Emit using generic helper method
            with tracer.start_as_current_span("risk.emit_validated") as span:
                try:
                    span.set_attribute("broker", broker)
                    span.set_attribute("topic", validated_topic)
                except Exception:
                    pass
                await self._emit_signal(key, validated_topic, validated_signal.model_dump(mode='json'), EventType.VALIDATED_SIGNAL, broker)
            
            # Record metrics for pipeline monitoring
            await self.metrics_collector.record_signal_validated(signal_data, passed=True, broker_context=broker)
            if self.prom_metrics:
                try:
                    self.prom_metrics.record_event_processed("risk_manager", broker, EventType.VALIDATED_SIGNAL.value)
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"Failed to get producer for validated signal emission: {e}")
            raise
        
        self.logger.info(
            "Signal validated",
            broker=broker,
            topic=validated_topic,
            strategy_id=signal_data.get("strategy_id"),
            instrument_token=signal_data.get("instrument_token"),
            signal_type=signal_data.get("signal_type"),
            quantity=signal_data.get("quantity")
        )
    
    async def _emit_rejected_signal(self, key: str, signal_data: Dict[str, Any], 
                                  validation_result: Dict[str, Any], broker: str):
        """Emit rejected signal"""
        tracer = get_tracer("risk_manager")
        try:
            # Create TradingSignal from data
            original_signal = TradingSignal(**signal_data)
            
            # Create RejectedSignal
            rejected_signal = RejectedSignal(
                original_signal=original_signal,
                rejection_reason="; ".join(validation_result["rejection_reasons"]),
                risk_checks=validation_result["rule_results"],
                timestamp=datetime.now(timezone.utc)
            )
            
            # Dynamically construct broker-specific rejected topic
            topic_map = TopicMap(broker)
            rejected_topic = topic_map.signals_rejected()
            
            # Emit using generic helper method  
            with tracer.start_as_current_span("risk.emit_rejected") as span:
                try:
                    span.set_attribute("broker", broker)
                    span.set_attribute("topic", rejected_topic)
                except Exception:
                    pass
                await self._emit_signal(key, rejected_topic, rejected_signal.model_dump(mode='json'), EventType.REJECTED_SIGNAL, broker)
            
            # Record metrics for pipeline monitoring
            await self.metrics_collector.record_signal_validated(signal_data, passed=False, broker_context=broker)
            if self.prom_metrics:
                try:
                    self.prom_metrics.record_event_processed("risk_manager", broker, EventType.REJECTED_SIGNAL.value)
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"Failed to get producer for rejected signal emission: {e}")
            raise
        
        self.logger.warning(
            "Signal rejected",
            broker=broker,
            topic=rejected_topic,
            strategy_id=signal_data.get("strategy_id"),
            instrument_token=signal_data.get("instrument_token"),
            signal_type=signal_data.get("signal_type"),
            reasons=validation_result["rejection_reasons"]
        )
    
    async def _update_risk_state_for_signal(self, signal_data: Dict[str, Any], broker: str):
        """Update risk state after signal validation"""
        
        # Update daily trade counter with broker context
        strategy_id = signal_data.get("strategy_id")
        if strategy_id:
            await self.state_manager.increment_daily_trades(strategy_id, broker)
        
        # Note: Position updates will happen when orders are filled,
        # not when signals are generated
    
    async def _emit_signal(self, key: str, topic: str, data: Dict[str, Any], event_type: EventType, broker: str):
        """A generic method to emit signals - reduces code duplication."""
        try:
            producer = await self._get_producer()
            await producer.send(
                topic=topic,
                key=key,
                data=data,
                event_type=event_type,
                broker=broker
            )
        except Exception as e:
            self.logger.error(f"Failed to get producer for signal emission: {e}")
            raise
    
    def get_monitoring_metrics(self) -> Dict[str, Any]:
        """Get comprehensive monitoring metrics for the risk manager"""
        return {
            "processing_metrics": {
                "processed_count": self.processed_count,
                "error_count": self.error_count,
                "last_processed_time": self.last_processed_time.isoformat() if self.last_processed_time else None,
                "current_processing_duration_ms": (
                    (datetime.now(timezone.utc) - self.validation_start_time).total_seconds() * 1000
                    if self.validation_start_time else 0
                )
            },
            "service_info": {
                "active_brokers": self.settings.active_brokers,
                "service_status": "running" if hasattr(self.orchestrator, '_running') else "unknown"
            }
        }

    async def _heartbeat_loop(self):
        """Emit a periodic Prometheus heartbeat timestamp per broker for validator clarity."""
        interval = 30.0
        try:
            while True:
                if self.prom_metrics:
                    for broker in self.settings.active_brokers:
                        try:
                            self.prom_metrics.set_last_activity("risk_manager", "heartbeat", broker)
                        except Exception:
                            pass
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return
