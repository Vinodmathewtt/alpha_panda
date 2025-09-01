# alphaP/services/market_feed/service.py

from typing import List, Dict, Any
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.schemas.events import EventType, MarketTick
from core.schemas.topics import TopicNames, PartitioningKeys
from core.config.settings import Settings, RedpandaSettings
from core.logging import get_market_data_logger_safe, get_performance_logger_safe, get_error_logger_safe
from core.monitoring import PipelineMetricsCollector
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector
from services.auth.service import AuthService
from services.instrument_data.instrument_registry_service import InstrumentRegistryService
from services.instrument_data.csv_loader import InstrumentCSVLoader

from .auth import BrokerAuthenticator
from .formatter import TickFormatter
from .models import ConnectionStats, MarketDataMetrics, ReconnectionConfig, TickerSubscription


class MarketFeedService:
    """
    Ingests live market data from Zerodha and publishes it as standardized
    events into the unified log (Redpanda).
    """

    def __init__(
        self,
        config: RedpandaSettings,
        settings: Settings,
        auth_service: AuthService,
        instrument_registry_service: InstrumentRegistryService,
        redis_client=None,
        prometheus_metrics: PrometheusMetricsCollector | None = None,
    ):
        self.settings = settings
        self.auth_service = auth_service
        self.instrument_registry_service = instrument_registry_service
        self.authenticator = BrokerAuthenticator(auth_service, settings)
        self.formatter = TickFormatter()
        self.kws = None
        # FIXED: Initialize _running flag to False
        self._running = False
        self._feed_task = None
        self.logger = get_market_data_logger_safe("market_feed")
        self.perf_logger = get_performance_logger_safe("market_feed_performance")
        self.error_logger = get_error_logger_safe("market_feed_errors")
        
        # Pipeline monitoring metrics
        self.ticks_processed = 0
        self.ticks_received = 0
        self.last_tick_time = None
        # Market feed uses shared namespace since it serves all brokers
        self.metrics_collector = PipelineMetricsCollector(redis_client, settings, "market")
        self.prom_metrics: PrometheusMetricsCollector | None = prometheus_metrics
        
        # Instrument subscription list
        self.instrument_tokens = []
        
        # Structured metrics and state tracking
        self.connection_stats = ConnectionStats()
        self.metrics = MarketDataMetrics()
        
        # Use settings for reconnection configuration
        self.reconnection_config = ReconnectionConfig(
            max_attempts=settings.reconnection.max_attempts,
            base_delay=settings.reconnection.base_delay_seconds,
            max_delay=settings.reconnection.max_delay_seconds,
            backoff_multiplier=settings.reconnection.backoff_multiplier,
            timeout=settings.reconnection.timeout_seconds
        )
        self._reconnection_attempts = 0
        self._start_time = None
        
        # ADDED: Components for reliability
        self._reconnection_lock = asyncio.Lock()
        self._tick_queue = asyncio.Queue(maxsize=10000)  # Bounded queue for backpressure
        self._processor_task = None
        self._failed_sends = 0
        self._failed_metrics = 0
        self._dropped_ticks = 0
        
        # Build streaming service using composition
        self.orchestrator = (StreamServiceBuilder("market_feed", config, settings)
            .with_prometheus(prometheus_metrics)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .build()
        )

    def set_prometheus(self, prom: PrometheusMetricsCollector):
        self.prom_metrics = prom
        
    async def _load_instruments_from_csv(self):
        """
        Load instruments from the CSV file to subscribe to.
        """
        try:
            # Load instruments directly from CSV file
            csv_loader = InstrumentCSVLoader.from_default_path()
            instruments_data = csv_loader.load_instruments()
            
            # Extract instrument tokens
            self.instrument_tokens = [int(item['instrument_token']) for item in instruments_data]
            
            self.logger.info(f"📊 Loaded {len(self.instrument_tokens)} instruments from CSV for subscription")
            
            # Also ensure instruments are loaded into the database via registry service
            try:
                await self.instrument_registry_service.load_instruments_from_csv()
                self.logger.info("✅ Instruments loaded into database successfully")
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to load instruments into database: {e}")
                # Continue with CSV data even if database loading fails
                
        except Exception as e:
            self.error_logger.error(f"❌ CRITICAL: Failed to load instruments from CSV: {e}")
            # FAIL FAST: No fallbacks allowed - system must have proper instrument configuration
            raise RuntimeError(
                f"CRITICAL FAILURE: Cannot load instruments from CSV file. "
                f"This is a mandatory requirement for market feed operation. "
                f"Error: {e}"
            )

    async def start(self):
        """
        Initializes the service, authenticates with the broker via AuthService,
        and starts the WebSocket connection for market data.
        """
        await self.orchestrator.start()
        # Capture the running event loop for threadsafe operations
        self.loop = asyncio.get_running_loop()
        self.logger.info("🚀 Starting Market Feed Service...")
        try:
            # Load instruments from CSV first
            await self._load_instruments_from_csv()
            
            self.kws = await self.authenticator.get_ticker()
            self._assign_callbacks()
            
            # FIXED: Set _running to True before starting the feed task
            self._start_time = datetime.now(timezone.utc)
            self._running = True
            
            # ADDED: Start the tick processor worker
            self._processor_task = asyncio.create_task(self._tick_processor())
            
            self._feed_task = asyncio.create_task(self._run_feed())
            self.logger.info("✅ Market Feed Service started and is connecting to WebSocket.")
            # Prometheus: mark healthy and connection status
            if self.prom_metrics:
                try:
                    self.prom_metrics.set_pipeline_health("market_feed", "shared", True)
                    self.prom_metrics.set_connection_status("zerodha_ws", "zerodha", True)
                except Exception:
                    pass
        except Exception as e:
            self.logger.error(f"❌ FATAL: Market Feed Service could not start: {e}")
            # Ensure _running is False on startup failure
            self._running = False
            raise

    async def stop(self):
        """Gracefully stops the WebSocket connection."""
        # FIXED: Set _running to False at the beginning of stop
        self._running = False
        
        if self._feed_task:
            self._feed_task.cancel()
            try:
                await self._feed_task
            except asyncio.CancelledError:
                pass
        
        # ADDED: Gracefully stop the processor task
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
                
        if self.kws and self.kws.is_connected():
            self.logger.info("🛑 Stopping Market Feed Service WebSocket...")
            self.kws.close(1000, "Service shutting down")
        await self.orchestrator.stop()
        self.logger.info("✅ Market Feed Service stopped.")
        if self.prom_metrics:
            try:
                self.prom_metrics.set_connection_status("zerodha_ws", "zerodha", False)
                self.prom_metrics.set_pipeline_health("market_feed", "shared", False)
            except Exception:
                pass
    
    async def _tick_processor(self):
        """Worker task that consumes ticks from the queue and emits them."""
        self.logger.info("Tick processor worker started.")
        while True:
            try:
                tick = await self._tick_queue.get()

                emit_coro = self._emit_tick(tick)
                metrics_coro = self._update_metrics(tick)

                # Use asyncio.gather for concurrent execution
                await asyncio.gather(emit_coro, metrics_coro)

                self._tick_queue.task_done()
            except asyncio.CancelledError:
                self.logger.info("Tick processor worker stopping.")
                break
            except Exception as e:
                self.error_logger.error(f"Unhandled exception in tick processor: {e}", exc_info=True)

    async def _emit_tick(self, tick: MarketTick):
        try:
            if self.orchestrator.producers and len(self.orchestrator.producers) > 0:
                producer = self.orchestrator.producers[0]
                key = PartitioningKeys.market_tick_key(tick.instrument_token)
                await producer.send(
                    topic=TopicNames.MARKET_TICKS,
                    key=key,
                    data=tick.model_dump(mode='json'),
                    event_type=EventType.MARKET_TICK,
                    broker="shared"  # Market data is shared across all brokers
                )
                if self.prom_metrics:
                    try:
                        self.prom_metrics.record_event_processed("market_feed", "shared", EventType.MARKET_TICK.value)
                        self.prom_metrics.record_market_tick("zerodha")
                    except Exception:
                        pass
        except Exception as e:
            self.error_logger.error(f"Failed to emit tick to Kafka: {e}", extra={"tick": tick.instrument_token})
            self._failed_sends += 1
            raise

    async def _update_metrics(self, tick: MarketTick):
        try:
            await self.metrics_collector.record_market_tick(tick.model_dump(mode='json'))
        except Exception as e:
            self.error_logger.error(f"Failed to update metrics in Redis: {e}", extra={"tick": tick.instrument_token})
            self._failed_metrics += 1
            raise

    async def _attempt_reconnection(self):
        """
        Attempt to reconnect with exponential backoff strategy and concurrency protection.
        """
        # MODIFIED: Guard reconnection logic with a lock
        async with self._reconnection_lock:
            if not self._running:
                return
            
            if self._reconnection_attempts >= self.reconnection_config.max_attempts:
                self.logger.error(f"❌ Maximum reconnection attempts ({self.reconnection_config.max_attempts}) reached. Stopping service.")
                self._running = False
                return
            
            self._reconnection_attempts += 1
            delay = min(
                self.reconnection_config.base_delay * (self.reconnection_config.backoff_multiplier ** (self._reconnection_attempts - 1)),
                self.reconnection_config.max_delay
            )
            
            self.logger.info(f"🔄 Reconnection attempt {self._reconnection_attempts}/{self.reconnection_config.max_attempts} in {delay:.1f} seconds")
            await asyncio.sleep(delay)
            
            try:
                # Close existing connection
                if self.kws and self.kws.is_connected():
                    self.kws.close(1000, "Reconnecting")
                
                # Get new ticker instance
                self.kws = await self.authenticator.get_ticker()
                self._assign_callbacks()
                
                # Start new connection
                self.kws.connect(threaded=True)
                
                # Wait for connection to establish
                connection_timeout = self.reconnection_config.timeout
                start_time = asyncio.get_event_loop().time()
                
                while not self.kws.is_connected() and self._running:
                    if asyncio.get_event_loop().time() - start_time > connection_timeout:
                        raise Exception("Connection timeout")
                    await asyncio.sleep(1)
                
                if self.kws.is_connected():
                    self.logger.info("✅ Reconnection successful")
                    self._reconnection_attempts = 0  # Reset on successful connection
                else:
                    raise Exception("Failed to establish connection")
                    
            except Exception as e:
                self.logger.error(f"❌ Reconnection attempt {self._reconnection_attempts} failed: {e}")
                # Schedule another reconnection attempt
                if self._running:
                    asyncio.create_task(self._attempt_reconnection())

    async def _run_feed(self):
        """Connects the KiteTicker and keeps the task alive."""
        self.kws.connect(threaded=True)
        while self._running and not self.kws.is_connected():
            await asyncio.sleep(1) # Wait for connection

        while self._running:
            await asyncio.sleep(1) # Keep the task running

    def _assign_callbacks(self):
        """Assigns the handler methods to the KiteTicker instance."""
        self.kws.on_ticks = self._on_ticks
        self.kws.on_connect = self._on_connect
        self.kws.on_close = self._on_close
        self.kws.on_error = self._on_error

    def _on_ticks(self, ws, ticks: List[Dict[str, Any]]):
        """
        The main callback for processing incoming market data ticks.
        This method is called from the KiteTicker's background thread.
        Captures COMPLETE PyKiteConnect data including market depth.
        """
        if not self._running:
            return

        # Count received ticks regardless of processing outcome
        try:
            self.ticks_received += len(ticks)
        except Exception:
            pass

        for tick in ticks:
            try:
                # Log data richness for first few ticks (debugging)
                if self.ticks_processed < 5:
                    available_fields = list(tick.keys())
                    has_depth = 'depth' in tick and tick['depth'] is not None
                    has_ohlc = 'ohlc' in tick and tick['ohlc'] is not None
                    has_volume = 'volume_traded' in tick
                    self.logger.debug(f"Tick data richness - Fields: {len(available_fields)}, Depth: {has_depth}, OHLC: {has_ohlc}, Volume: {has_volume}")
                    if has_depth:
                        depth = tick['depth']
                        buy_levels = len(depth.get('buy', []))
                        sell_levels = len(depth.get('sell', []))
                        self.logger.debug(f"Market depth: {buy_levels} buy levels, {sell_levels} sell levels")
                
                # Format complete tick data
                formatted_tick = self.formatter.format_tick(tick)
                market_tick = MarketTick(**formatted_tick)

                # Update tick processing counter
                self.ticks_processed += 1

                # Thread-safe enqueue: KiteTicker callbacks run on a background thread.
                # Use the event loop to safely schedule queue operations.
                try:
                    if hasattr(self, 'loop') and self.loop is not None:
                        self.loop.call_soon_threadsafe(self._tick_queue.put_nowait, market_tick)
                    else:
                        # Fallback (should not happen post-start); best effort enqueue
                        self._tick_queue.put_nowait(market_tick)
                except asyncio.QueueFull:
                    self._dropped_ticks += 1
                    self.logger.warning(
                        f"Tick queue is full. Dropping tick to maintain stability. Total dropped: {self._dropped_ticks}")
                    
            except Exception as e:
                self.logger.error(f"❌ Error processing tick: {tick}, Error: {e}")
                self.error_logger.error(f"Tick processing error", extra={"tick_data": tick, "error": str(e)})

    def _on_connect(self, ws, response):
        """Callback for when the WebSocket connection is established."""
        self.logger.info("✅ WebSocket connected. Subscribing to instruments...")
        
        if not self.instrument_tokens:
            # FAIL FAST: No instruments available - this should never happen if CSV loading worked
            self.error_logger.error("❌ CRITICAL: No instruments available for subscription")
            raise RuntimeError(
                "CRITICAL FAILURE: No instruments available for market data subscription. "
                "This indicates a failure in instrument loading during service initialization."
            )
        
        # Subscribe to instruments
        ws.subscribe(self.instrument_tokens)
        # CRITICAL: Set FULL mode to capture complete data including market depth
        ws.set_mode(ws.MODE_FULL, self.instrument_tokens)
        self.logger.info(f"📊 Subscribed to {len(self.instrument_tokens)} instruments in FULL mode (complete data + 5-level depth)")

    def _on_close(self, ws, code, reason):
        """Callback for when the WebSocket connection is closed."""
        self.logger.warning(f"WebSocket closed. Code: {code}, Reason: {reason}")
        if self._running:
            self.logger.info("Attempting to reconnect...")
            # Schedule reconnection attempt
            if hasattr(self, 'loop'):
                asyncio.run_coroutine_threadsafe(self._attempt_reconnection(), self.loop)
        else:
            self.logger.info("Service is stopping, not attempting reconnection")

    def _on_error(self, ws, code, reason):
        """Callback for WebSocket errors."""
        self.logger.error(f"WebSocket error. Code: {code}, Reason: {reason}")

    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive service metrics."""
        current_queue_size = self._tick_queue.qsize() if hasattr(self, '_tick_queue') else 0
        
        return {
            'ticks_received': self.ticks_received,
            'ticks_processed': self.ticks_processed,
            'ticks_dropped': self._dropped_ticks,
            'send_failures': self._failed_sends,
            'metrics_failures': self._failed_metrics,
            'reconnection_attempts': self._reconnection_attempts,
            'queue_size': current_queue_size,
            'connection_status': 'connected' if (self.kws and self.kws.is_connected()) else 'disconnected',
            'is_running': self._running,
            'processing_rate': self._calculate_processing_rate()
        }

    def _calculate_processing_rate(self) -> float:
        """Calculate ticks per second processing rate."""
        if not self._start_time or self.ticks_processed == 0:
            return 0.0
        
        # Use precise elapsed time since service start
        elapsed = (datetime.now(timezone.utc) - self._start_time).total_seconds()
        return self.ticks_processed / elapsed if elapsed > 0 else 0.0

    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for monitoring systems."""
        metrics = await self.get_metrics()
        
        # Calculate health score
        is_healthy = (
            self._running and
            (self.kws and self.kws.is_connected()) and
            metrics['queue_size'] < 8000 and  # Queue not near full
            metrics['send_failures'] / max(metrics['ticks_processed'], 1) < 0.01  # < 1% failure rate
        )
        
        return {
            'status': 'healthy' if is_healthy else 'unhealthy',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'metrics': metrics,
            'issues': self._identify_health_issues(metrics)
        }

    def _identify_health_issues(self, metrics: Dict[str, Any]) -> List[str]:
        """Identify specific health issues."""
        issues = []
        
        if not self._running:
            issues.append("Service not running")
        if not (self.kws and self.kws.is_connected()):
            issues.append("WebSocket disconnected")
        if metrics['queue_size'] > 8000:
            issues.append("Queue near capacity")
        if metrics['send_failures'] / max(metrics['ticks_processed'], 1) > 0.01:
            issues.append("High failure rate")
        if metrics['ticks_dropped'] > 0:
            issues.append("Dropped ticks detected")
        
        return issues

    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Market feed doesn't handle incoming messages."""
        pass
