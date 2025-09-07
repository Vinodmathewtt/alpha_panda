# Strategy Runner Service - Main orchestrator service
import asyncio
import time
from typing import Dict, Any, List, Optional
from collections import defaultdict
from sqlalchemy import select
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.schemas.events import EventType
from core.schemas.topics import TopicNames, TopicMap
from core.config.settings import RedpandaSettings, Settings
from core.database.connection import DatabaseManager
from core.database.models import StrategyConfiguration
from core.logging import get_trading_logger_safe, get_performance_logger_safe, get_error_logger_safe, bind_broker_context
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
        ) if redis_client else None
        
        # Market hours checker for market status awareness - use injected or create new
        self.market_hours_checker = market_hours_checker or MarketHoursChecker()
        # Prometheus metrics (shared registry via DI)
        self.prom_metrics: PrometheusMetricsCollector | None = prometheus_metrics
        
        # Pipeline monitoring metrics
        self.signals_generated = 0
        self.strategies_processed = 0
        self.last_signal_time = None
        # Store active brokers for signal generation and prepare broker-bound loggers
        self.active_brokers = settings.active_brokers
        try:
            self._broker_loggers = {b: bind_broker_context(self.logger, b) for b in self.active_brokers}
        except Exception:
            self._broker_loggers = {}
        
        # ✅ COMPOSITION-ONLY ARCHITECTURE - NO LEGACY SUPPORT
        self.strategy_executors: Dict[str, Any] = {}  # Composition strategies ONLY
        self.strategy_instruments: Dict[str, List[int]] = {}  # strategy_id -> instrument_tokens
        
        # 🔥 NEW: ML strategy tracking
        self.ml_strategies_loaded = 0
        self.ml_inference_count = 0
        self.ml_inference_errors = 0
        
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
        # Per-broker start line for dashboard clarity
        try:
            for _b, _bl in (self._broker_loggers or {}).items():
                _bl.info("Strategy Runner active", broker=_b)
        except Exception:
            pass

        # Mark pipeline stage healthy in Prometheus for active brokers
        if self.prom_metrics:
            try:
                for broker in self.active_brokers:
                    self.prom_metrics.set_pipeline_health("strategy_runner", broker, True)
            except Exception as _e:
                # Do not fail startup on metrics errors
                self.logger.warning("Failed to set Prometheus pipeline health", error=str(_e))

        # Lightweight heartbeat for observability (similar to risk manager)
        try:
            import asyncio as _asyncio
            self._heartbeat_task = _asyncio.create_task(self._heartbeat_loop())
        except Exception:
            self._heartbeat_task = None
        
    async def _load_strategies(self):
        """Load active strategies from database with ML model validation"""
        strategies_loaded = 0
        ml_models_loaded = 0
        ml_models_failed = 0
        
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
                        # ML-only broker routing: default to paper; if zerodha enabled, use zerodha only
                        brokers=["zerodha"] if config.zerodha_trading_enabled else ["paper"],
                        instrument_tokens=config.instruments
                    )
                    
                    # 🔥 Optional ML Model Health Validation:
                    # ML validation is optional - strategies can still be registered without ML
                    loaded = True
                    if self._has_ml_capability(strategy_executor):
                        self.ml_strategies_loaded += 1
                        loaded = await self._validate_ml_capability(strategy_executor, config.id)
                        if loaded:
                            ml_models_loaded += 1
                            # Prometheus: record ML model load success
                            if self.prom_metrics:
                                try:
                                    self.prom_metrics.record_ml_model_load_success(config.id)
                                except Exception:
                                    pass
                        else:
                            ml_models_failed += 1
                            # Prometheus: record ML model load failure
                            if self.prom_metrics:
                                try:
                                    self.prom_metrics.record_ml_model_load_failure(config.id)
                                except Exception:
                                    pass
                            self.logger.warning(
                                f"ML model validation failed for {config.id} - continuing with degraded ML capability"
                            )
                            # Continue loading - don't skip non-ML strategies
                    
                    self.strategy_executors[config.id] = strategy_executor
                    self.strategy_instruments[config.id] = config.instruments
                    
                    # Update instrument mapping for O(1) tick routing
                    for instrument_token in config.instruments:
                        self.instrument_to_strategies[instrument_token].append(config.id)
                    
                    strategies_loaded += 1
                    
                    # Enhanced logging for ML vs rule-based strategies
                    strategy_type_info = "ML" if self._has_ml_capability(strategy_executor) else "rule-based"
                    self.logger.info(f"Loaded {strategy_type_info} composition strategy: {config.id}", 
                                   strategy_type=config.strategy_type,
                                   architecture="composition",
                                   has_ml_capability=self._has_ml_capability(strategy_executor))
                    
                except ValueError as e:
                    if "Failed to load ML model" in str(e):
                        ml_models_failed += 1
                        self.logger.error(f"ML model loading error for {config.id}: {e}")
                        # Continue loading other strategies - don't fail entire startup
                        continue
                    else:
                        raise  # Re-raise non-ML errors
                except Exception as e:
                    self.logger.error(
                        "Failed to load strategy",
                        strategy_id=config.id,
                        error=str(e)
                    )
            
            strategies_loaded = len(self.strategy_executors)
        
        # Only use database strategies - no YAML fallback in composition architecture
        
        # 🔥 NEW: Enhanced logging with ML statistics
        traditional_strategies = strategies_loaded - self.ml_strategies_loaded
        self.logger.info("Strategy Loading Summary", 
                        total_strategies=strategies_loaded,
                        traditional_strategies=traditional_strategies,
                        ml_strategies=self.ml_strategies_loaded,
                        ml_models_loaded=ml_models_loaded,
                        ml_models_failed=ml_models_failed)

        # One-time advisory: warn if ML strategies are present but NumPy is unavailable.
        # ML processors have graceful fallbacks, but this helps operators tune envs.
        try:
            import numpy as _np  # noqa: F401
            _has_numpy = True
        except Exception:
            _has_numpy = False
        if self.ml_strategies_loaded > 0 and not _has_numpy:
            self.logger.warning(
                "NumPy not available; ML strategies will use fallback features (reduced performance/precision)"
            )

        # Record per-broker active strategy counts for validator context (no warnings when none configured)
        try:
            if self.metrics_collector:
                per_broker_counts: Dict[str, int] = {b: 0 for b in self.active_brokers}
                for executor in self.strategy_executors.values():
                    for b in getattr(executor.config, 'active_brokers', []):
                        if b in per_broker_counts:
                            per_broker_counts[b] += 1
                for broker, cnt in per_broker_counts.items():
                    await self.metrics_collector.set_strategy_count(broker, cnt)
                self.logger.info("Recorded per-broker active strategy counts", counts=per_broker_counts)
        except Exception as e:
            self.logger.warning("Failed to record strategy counts", error=str(e))
    
    async def stop(self):
        """Stop the strategy runner service"""
        await self.orchestrator.stop()
        self.logger.info("Strategy runner service stopped")
        try:
            for _b, _bl in (self._broker_loggers or {}).items():
                _bl.info("Strategy Runner stopped", broker=_b)
        except Exception:
            pass
        # Mark pipeline stage unhealthy for active brokers
        if self.prom_metrics:
            try:
                for broker in self.active_brokers:
                    self.prom_metrics.set_pipeline_health("strategy_runner", broker, False)
            except Exception:
                pass
        # Stop heartbeat
        try:
            if hasattr(self, "_heartbeat_task") and self._heartbeat_task:
                self._heartbeat_task.cancel()
                import asyncio as _asyncio
                try:
                    await self._heartbeat_task
                except _asyncio.CancelledError:
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

    def _is_ml_strategy(self, executor) -> bool:
        """Backwards-compatible alias for ML-capability check.

        Some spans/metrics annotate strategies as ML vs rules-based. Treat any
        processor that exposes ML methods as ML-capable.
        """
        return self._has_ml_capability(executor)

    def _has_ml_capability(self, executor) -> bool:
        """Check if strategy executor has optional ML capabilities"""
        return (hasattr(executor.processor, 'load_model') or 
                hasattr(executor.processor, 'predict_signal') or
                hasattr(executor.processor, 'extract_features'))
    
    async def _validate_ml_capability(self, executor, strategy_id: str) -> bool:
        """Validate ML capability - returns True if ML works, False if degraded"""
        try:
            if hasattr(executor.processor, 'load_model'):
                # Model loading is handled in factory, check if model exists
                return hasattr(executor.processor, 'model') and executor.processor.model is not None
            return True  # Non-model ML strategies (feature-based) are valid
        except Exception as e:
            self.error_logger.warning(f"ML capability validation failed for {strategy_id}: {e}")
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
            # Even if no interested strategies, record activity for liveness panels
            if self.prom_metrics:
                try:
                    self.prom_metrics.set_last_activity("strategy_runner", "tick", "shared")
                except Exception:
                    pass
            return  # No strategies interested in this instrument

        # Construct MarketTick once per incoming tick; reuse for all strategies
        from core.schemas.events import MarketTick as _MarketTick
        market_tick = _MarketTick(
            instrument_token=tick_data["instrument_token"],
            last_price=tick_data["last_price"],
            timestamp=tick_data["timestamp"],
            symbol=tick_data.get("symbol", "")
        )
        
        # Process tick through each interested strategy using composition architecture only
        for strategy_id in interested_strategy_ids:
            executor = self.strategy_executors.get(strategy_id)
            if executor:
                try:
                    # COMPOSITION: Process using StrategyExecutor under tracing span
                    with tracer.start_as_current_span("strategy.process_tick") as span:
                        try:
                            span.set_attribute("strategy.id", strategy_id)
                            span.set_attribute("instrument_token", instrument_token)
                            span.set_attribute("is_ml_strategy", self._is_ml_strategy(executor))
                            span.set_attribute("strategy.type", executor.processor.get_strategy_name())
                        except Exception:
                            pass

                        # 🔥 NEW: Track ML vs traditional processing with timing
                        is_ml_strategy = self._is_ml_strategy(executor)
                        start_time = time.time()

                        signal_result = executor.process_tick(market_tick)
                        # Count processed strategies
                        self.strategies_processed += 1

                        # Record tick activity for liveness
                        if self.prom_metrics:
                            try:
                                self.prom_metrics.set_last_activity("strategy_runner", "process_tick", "shared")
                            except Exception:
                                pass
                    
                    # 🔥 NEW: Record processing metrics
                    processing_time = (time.time() - start_time)
                    if is_ml_strategy:
                        self.ml_inference_count += 1
                    if self.prom_metrics:
                        try:
                            # Record generic processing latency
                            self.prom_metrics.record_processing_time(
                                service="strategy_runner",
                                event_type="strategy.process",
                                duration_seconds=processing_time,
                            )
                            # Also count ML inference events separately (throughput)
                            if is_ml_strategy:
                                self.prom_metrics.record_event_processed(
                                    service="strategy_runner",
                                    broker="shared",
                                    event_type="ML_INFERENCE",
                                )
                        except Exception:
                            pass
                    
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
                        
                        # Normalize confidence to 0.0–1.0 (accept 0–100 legacy or 0.0–1.0 native)
                        _conf = None
                        try:
                            if signal_result.confidence is not None:
                                _raw_conf = float(signal_result.confidence)
                                _conf_val = (_raw_conf / 100.0) if _raw_conf > 1.0 else _raw_conf
                                _conf = max(0.0, min(1.0, _conf_val))
                        except Exception:
                            _conf = None

                        trading_signal = TradingSignal(
                            strategy_id=strategy_id,
                            instrument_token=tick_data["instrument_token"],
                            signal_type=signal_type,
                            quantity=signal_result.quantity,
                            price=signal_result.price,
                            timestamp=tick_data["timestamp"],
                            confidence=_conf,
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
                            self.last_signal_time = time.time()
                            
                except Exception as e:
                    # 🔥 NEW: ML-aware error handling and classification
                    if self._is_ml_strategy(executor):
                        self.ml_inference_errors += 1
                        
                        # Classify ML-specific errors
                        error_msg = str(e).lower()
                        if any(keyword in error_msg for keyword in ["model", "prediction", "inference", "ml"]):
                            self.error_logger.error(f"ML inference error in strategy {strategy_id}: {e}",
                                                  strategy_type="ML",
                                                  error_category="ML_INFERENCE")
                            if self.prom_metrics:
                                try:
                                    self.prom_metrics.record_error("strategy_runner", "ML_INFERENCE", "shared")
                                except Exception:
                                    pass
                        elif any(keyword in error_msg for keyword in ["feature", "extract", "transform"]):
                            self.error_logger.error(f"ML feature extraction error in strategy {strategy_id}: {e}",
                                                  strategy_type="ML", 
                                                  error_category="ML_FEATURE_EXTRACTION")
                            if self.prom_metrics:
                                try:
                                    self.prom_metrics.record_error("strategy_runner", "ML_FEATURE_EXTRACTION", "shared")
                                except Exception:
                                    pass
                        else:
                            self.error_logger.error(f"ML strategy error in {strategy_id}: {e}",
                                                  strategy_type="ML",
                                                  error_category="ML_GENERAL")
                            if self.prom_metrics:
                                try:
                                    self.prom_metrics.record_error("strategy_runner", "ML_GENERAL", "shared")
                                except Exception:
                                    pass
                    else:
                        # Traditional strategy error handling (unchanged)
                        self.error_logger.error(f"Error processing traditional strategy {strategy_id}: {e}",
                                              strategy_type="traditional",
                                              error_category="STRATEGY_PROCESSING")
                    
                    # Continue processing other strategies - graceful degradation
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
                    # Use proper signal recording method for consistency (pydantic v2)
                    signal_data = signal.model_dump(mode='json')
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
                    # Update last-activity for signal stage (per strategy)
                    try:
                        self.prom_metrics.set_last_activity("strategy_runner", f"signal.{strategy_id}", broker)
                    except Exception:
                        pass
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
    
    def get_service_metrics(self) -> Dict[str, Any]:
        """Enhanced service metrics including ML strategy statistics"""
        # Base metrics (existing)
        base_metrics = {
            "total_strategies": len(self.strategy_executors),
            "signals_generated": self.signals_generated,
            "strategies_processed": self.strategies_processed,
            "last_signal_time": self.last_signal_time,
            "active_brokers": self.active_brokers
        }
        
        # 🔥 NEW: ML-specific metrics
        traditional_strategies = len(self.strategy_executors) - self.ml_strategies_loaded
        ml_error_rate = self.ml_inference_errors / max(self.ml_inference_count, 1)
        
        ml_metrics = {
            "traditional_strategies_loaded": traditional_strategies,
            "ml_strategies_loaded": self.ml_strategies_loaded,
            "ml_inference_count": self.ml_inference_count,
            "ml_inference_errors": self.ml_inference_errors,
            "ml_error_rate": round(ml_error_rate, 4),
            "ml_success_rate": round(1.0 - ml_error_rate, 4)
        }
        
        return {**base_metrics, **ml_metrics}

    async def _heartbeat_loop(self):
        """Periodically update last-activity timestamps for liveness dashboards."""
        import asyncio as _asyncio
        try:
            while True:
                if self.prom_metrics:
                    for broker in self.active_brokers:
                        try:
                            self.prom_metrics.set_last_activity("strategy_runner", "heartbeat", broker)
                        except Exception:
                            pass
                await _asyncio.sleep(15)
        except _asyncio.CancelledError:
            return
