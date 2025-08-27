"""Mock Market Feed Manager - Main orchestrator for realistic market data simulation.

This manager provides the same interface as ZerodhaFeedManager but generates
realistic mock data instead of connecting to external APIs. It's designed for
development, testing, and strategy validation without external dependencies.

⚠️ CRITICAL: This module must NEVER be present in production deployment.
             It will be completely removed during production build.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Callable, Any
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager

from core.config.settings import Settings
from core.events import EventBusCore, get_event_publisher
from core.events.event_types import EventFactory, EventType
from core.utils.exceptions import FeedError
from core.logging.logger import get_logger

from .models import MockTickData, InstrumentConfig
from .data_generator import RealisticDataGenerator, HistoricalDataReplay
from .scenarios import ScenarioType, ScenarioScheduler, MarketScenarios


class MockFeedManager:
    """
    Mock Market Feed Manager that replicates Zerodha feed interface.
    
    This class provides identical interface to ZerodhaFeedManager for seamless
    development and testing. It generates realistic market data without requiring
    external API connections or authentication.
    """
    
    def __init__(self, settings: Settings, event_bus: EventBusCore):
        """
        Initialize Mock Feed Manager.
        
        Args:
            settings: Application settings
            event_bus: Event bus for publishing market data events
        """
        self.settings = settings
        self.event_bus = event_bus
        self.event_publisher = get_event_publisher(settings) if event_bus else None
        self.logger = get_logger("mock_feed_manager")
        
        # Feed state
        self.is_running = False
        self.is_connected_state = False
        self.subscribed_instruments: Set[int] = set()
        self.instrument_configs: Dict[int, InstrumentConfig] = {}
        
        # Data generation
        self.data_generator = RealisticDataGenerator(seed=42)  # Deterministic for testing
        self.scenario_scheduler: Optional[ScenarioScheduler] = None
        self.historical_replay: Optional[HistoricalDataReplay] = None
        
        # Streaming control
        self._streaming_task: Optional[asyncio.Task] = None
        self._tick_subscribers: List[Callable] = []
        
        # Comprehensive metrics tracking
        self.detailed_metrics = {
            'generation_performance': {
                'total_ticks_generated': 0,
                'generation_errors': 0,
                'average_generation_time_us': 0.0,
                'peak_generation_time_us': 0.0,
                'ticks_per_second_current': 0.0,
                'generation_success_rate': 100.0
            },
            'subscriber_health': {},
            'publishing_performance': {
                'total_published': 0,
                'publish_errors': 0,
                'average_publish_time_us': 0.0,
                'peak_publish_time_us': 0.0,
                'publish_success_rate': 100.0
            },
            'data_quality': {
                'invalid_ticks_generated': 0,
                'price_anomalies_detected': 0,
                'volume_anomalies_detected': 0,
                'timestamp_errors': 0
            }
        }
        
        # Performance metrics (backward compatibility)
        self.stats = {
            "ticks_generated": 0,
            "events_published": 0,
            "start_time": None,
            "last_tick_time": None,
            "instruments_active": 0,
        }
        
        # Subscriber monitoring
        self.subscriber_failure_counts = {}
        self.subscriber_performance_tracking = {}
        
        # Data quality monitoring
        self.last_prices = {}  # Track for anomaly detection
        self.price_change_thresholds = {}  # Per instrument thresholds
        
        # Mock market configuration - use settings for timing controls
        self.tick_interval = self.settings.get_mock_tick_interval_seconds()  # Use configured interval
        self.market_hours_check_enabled = self.settings.mock_enable_market_hours_check
        self.market_hours = {
            "start": (9, 15),    # 9:15 AM
            "end": (15, 30),     # 3:30 PM
            "lunch_start": (12, 30),  # 12:30 PM
            "lunch_end": (13, 30),    # 1:30 PM
        }
        
        self.logger.info("🎭 Mock Feed Manager initialized - Development mode active")
    
    async def initialize(self) -> bool:
        """
        Initialize mock market feed system.
        
        This replicates the zerodha feed initialization interface but sets up
        mock data generation instead of external API connections.
        
        Returns:
            True if initialization successful
        """
        try:
            self.logger.info("🎭 Initializing mock market feed system...")
            
            # Initialize scenario scheduler with default trading day schedule
            self.scenario_scheduler = ScenarioScheduler()
            
            # Load default instrument configurations
            await self._load_default_instruments()
            
            # Initialize event publishing (EventPublisherService doesn't have is_connected check needed)
            # EventBusCore is already connected during application startup
            
            # Set up market timing
            self._setup_market_timing()
            
            self.stats["start_time"] = datetime.now(timezone.utc)
            
            self.logger.info(
                f"✅ Mock feed system initialized with {len(self.instrument_configs)} instruments"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Mock feed initialization failed: {e}")
            return False
    
    async def start_data_streaming(self) -> bool:
        """
        Start mock market data streaming.
        
        Returns:
            True if streaming started successfully
        """
        if self.is_running:
            self.logger.warning("Mock feed already running")
            return True
        
        try:
            self.logger.info("🚀 Starting mock market data streaming...")
            
            # Start the main streaming task
            self._streaming_task = asyncio.create_task(self._streaming_loop())
            
            self.is_running = True
            self.stats["start_time"] = datetime.now(timezone.utc)
            
            # Publish system event
            await self._publish_system_event("MOCK_FEED_STARTED", "Mock feed streaming started")
            
            self.logger.info("✅ Mock market data streaming started")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start mock streaming: {e}")
            await self.stop_data_streaming()
            return False
    
    async def stop_data_streaming(self) -> bool:
        """
        Stop mock market data streaming.
        
        Returns:
            True if streaming stopped successfully
        """
        if not self.is_running:
            return True
        
        try:
            self.logger.info("⏹️ Stopping mock market data streaming...")
            
            self.is_running = False
            
            # Cancel streaming task
            if self._streaming_task and not self._streaming_task.done():
                self._streaming_task.cancel()
                try:
                    await self._streaming_task
                except asyncio.CancelledError:
                    pass
            
            # Publish system event
            await self._publish_system_event("MOCK_FEED_STOPPED", "Mock feed streaming stopped")
            
            self.logger.info("✅ Mock market data streaming stopped")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error stopping mock streaming: {e}")
            return False
    
    async def subscribe_instruments(self, tokens: List[int]) -> bool:
        """
        Subscribe to instruments for mock data generation.
        
        Args:
            tokens: List of instrument tokens to subscribe
            
        Returns:
            True if subscription successful
        """
        try:
            self.logger.info(f"📊 Subscribing to {len(tokens)} instruments for mock data")
            
            for token in tokens:
                if token not in self.subscribed_instruments:
                    self.subscribed_instruments.add(token)
                    
                    # Initialize instrument if not exists
                    if token not in self.instrument_configs:
                        config = self._create_default_instrument_config(token)
                        self.instrument_configs[token] = config
                    
                    # Initialize data generator for this instrument
                    initial_tick = self.data_generator.initialize_instrument(
                        self.instrument_configs[token],
                        ScenarioType.RANGING  # Start with neutral scenario
                    )
                    
                    self.logger.debug(f"Initialized mock data for instrument {token}")
            
            self.stats["instruments_active"] = len(self.subscribed_instruments)
            
            self.logger.info(f"✅ Successfully subscribed to {len(tokens)} instruments")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to subscribe to instruments: {e}")
            return False
    
    async def unsubscribe_instruments(self, tokens: List[int]) -> bool:
        """
        Unsubscribe from instruments.
        
        Args:
            tokens: List of instrument tokens to unsubscribe
            
        Returns:
            True if unsubscription successful
        """
        try:
            for token in tokens:
                self.subscribed_instruments.discard(token)
            
            self.stats["instruments_active"] = len(self.subscribed_instruments)
            self.logger.info(f"✅ Unsubscribed from {len(tokens)} instruments")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to unsubscribe from instruments: {e}")
            return False
    
    def add_tick_subscriber(self, callback: Callable[[Dict], None]):
        """Add callback for tick data."""
        self._tick_subscribers.append(callback)
    
    def remove_tick_subscriber(self, callback: Callable[[Dict], None]):
        """Remove callback for tick data."""
        if callback in self._tick_subscribers:
            self._tick_subscribers.remove(callback)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get mock feed statistics.
        
        Returns:
            Dictionary of feed statistics
        """
        uptime = None
        if self.stats["start_time"]:
            uptime = (datetime.now(timezone.utc) - self.stats["start_time"]).total_seconds()
        
        ticks_per_second = 0
        if uptime and uptime > 0:
            ticks_per_second = self.stats["ticks_generated"] / uptime
        
        return {
            "feed_type": "mock",
            "is_running": self.is_running,
            "instruments_subscribed": len(self.subscribed_instruments),
            "ticks_generated": self.stats["ticks_generated"],
            "events_published": self.stats["events_published"],
            "uptime_seconds": uptime,
            "ticks_per_second": round(ticks_per_second, 2),
            "last_tick_time": self.stats["last_tick_time"],
            "market_scenario": self._get_current_scenario_info(),
        }
    
    async def _streaming_loop(self):
        """Main streaming loop for generating mock data."""
        self.logger.info("🔄 Mock streaming loop started")
        
        try:
            while self.is_running:
                current_time = datetime.now(timezone.utc)
                
                # Check if market is open (if market hours check is enabled)
                if self.market_hours_check_enabled and not self._is_market_open(current_time):
                    await asyncio.sleep(1.0)
                    continue
                
                # Update scenario based on time
                await self._update_scenarios(current_time)
                
                # Generate ticks for all subscribed instruments
                tasks = []
                for token in self.subscribed_instruments:
                    task = asyncio.create_task(self._generate_and_publish_tick(token))
                    tasks.append(task)
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                # Control tick frequency
                await asyncio.sleep(self.tick_interval)
                
        except asyncio.CancelledError:
            self.logger.info("Mock streaming loop cancelled")
        except Exception as e:
            self.logger.error(f"❌ Error in streaming loop: {e}")
        finally:
            self.logger.info("🔄 Mock streaming loop ended")
    
    async def _generate_and_publish_tick(self, instrument_token: int):
        """Generate and publish tick for specific instrument."""
        try:
            # Generate next tick
            tick = self.data_generator.generate_next_tick(instrument_token)
            if not tick:
                return
            
            # Update statistics
            self.stats["ticks_generated"] += 1
            self.stats["last_tick_time"] = tick.exchange_timestamp
            
            # Notify tick subscribers
            tick_dict = tick.to_zerodha_format()
            for subscriber in self._tick_subscribers:
                try:
                    subscriber(tick_dict)
                except Exception as e:
                    self.logger.error(f"Error in tick subscriber: {e}")
            
            # Publish to event bus
            await self._publish_market_tick_event(tick)
            
        except Exception as e:
            self.logger.error(f"Error generating tick for {instrument_token}: {e}")
    
    async def _publish_market_tick_event(self, tick: MockTickData):
        """Publish market tick event to event bus."""
        try:
            event = EventFactory.create_market_tick_event(
                instrument_token=tick.instrument_token,
                exchange=tick.exchange,
                tick_data=tick.to_dict(),
                source="mock_market_feed"
            )
            
            # Publish to appropriate NATS subject using new event publisher
            if self.event_publisher:
                subject = f"market.tick.{tick.exchange}.{tick.instrument_token}"
                await self.event_publisher.publish(subject, event)
            
            self.stats["events_published"] += 1
            
        except Exception as e:
            self.logger.error(f"Failed to publish market tick event: {e}")
    
    async def _publish_system_event(self, event_type: str, message: str):
        """Publish system event."""
        try:
            event = EventFactory.create_system_event(
                component="mock_market_feed",
                severity="INFO",
                message=message,
                event_type=EventType.SYSTEM_STARTED if "STARTED" in event_type else EventType.SYSTEM_STOPPED,
                source="mock_market_feed"
            )
            
            if self.event_publisher:
                await self.event_publisher.publish("system.mock_feed.status", event)
            
        except Exception as e:
            self.logger.error(f"Failed to publish system event: {e}")
    
    def _is_market_open(self, current_time: datetime) -> bool:
        """Check if mock market should be generating data."""
        # For development, we can run 24/7 or follow market hours
        if self.settings.mock_market_24x7:
            return True
        
        hour = current_time.hour
        minute = current_time.minute
        current_minutes = hour * 60 + minute
        
        start_minutes = self.market_hours["start"][0] * 60 + self.market_hours["start"][1]
        end_minutes = self.market_hours["end"][0] * 60 + self.market_hours["end"][1]
        
        # Check if within market hours
        if start_minutes <= current_minutes <= end_minutes:
            # Check lunch break
            lunch_start = self.market_hours["lunch_start"][0] * 60 + self.market_hours["lunch_start"][1]
            lunch_end = self.market_hours["lunch_end"][0] * 60 + self.market_hours["lunch_end"][1]
            
            if lunch_start <= current_minutes <= lunch_end:
                return False  # Lunch break
            
            return True
        
        return False
    
    async def _update_scenarios(self, current_time: datetime):
        """Update market scenarios based on time."""
        if not self.scenario_scheduler:
            return
        
        minute_of_day = current_time.hour * 60 + current_time.minute
        new_scenario = self.scenario_scheduler.update_minute(minute_of_day)
        
        if new_scenario:
            scenario_type = new_scenario.config.scenario_type
            self.logger.info(f"📈 Switching to market scenario: {scenario_type}")
            
            # Update all instruments to new scenario
            for token in self.subscribed_instruments:
                self.data_generator.update_scenario(token, scenario_type)
    
    def _get_current_scenario_info(self) -> Dict[str, str]:
        """Get current scenario information."""
        if not self.scenario_scheduler:
            return {"scenario": "none", "description": "No scenario active"}
        
        engine = self.scenario_scheduler.get_current_scenario_engine()
        if not engine:
            return {"scenario": "none", "description": "No scenario active"}
        
        return {
            "scenario": engine.config.scenario_type.value,
            "description": engine.config.description,
        }
    
    async def _load_default_instruments(self):
        """Load default instruments for testing."""
        # Popular NSE instruments for testing
        default_instruments = [
            {"token": 408065, "symbol": "RELIANCE", "price": 2500.0},
            {"token": 738561, "symbol": "SBIN", "price": 550.0},
            {"token": 779521, "symbol": "ADANIPORTS", "price": 1200.0},
            {"token": 895745, "symbol": "AXISBANK", "price": 1100.0},
            {"token": 1270529, "symbol": "ICICIBANK", "price": 950.0},
        ]
        
        for inst in default_instruments:
            config = InstrumentConfig(
                instrument_token=inst["token"],
                tradingsymbol=inst["symbol"],
                base_price=inst["price"],
                volatility=0.02,  # 2% daily volatility
                exchange="NSE"
            )
            self.instrument_configs[inst["token"]] = config
        
        self.logger.info(f"Loaded {len(default_instruments)} default instruments")
    
    def _create_default_instrument_config(self, token: int) -> InstrumentConfig:
        """Create default configuration for unknown instrument."""
        return InstrumentConfig(
            instrument_token=token,
            tradingsymbol=f"MOCK{token}",
            base_price=1000.0,
            volatility=0.02,
            exchange="NSE"
        )
    
    def _setup_market_timing(self):
        """Set up market timing configuration."""
        # Add any market timing setup logic here
        pass
    
    async def _validate_tick_quality(self, tick: MockTickData, instrument_token: int, correlation_id: str) -> List[str]:
        """Comprehensive tick data quality validation."""
        quality_issues = []
        
        try:
            # Price validation
            if tick.last_price <= 0:
                quality_issues.append("Invalid price: price must be positive")
            
            # Volume validation
            if tick.last_traded_quantity < 0:
                quality_issues.append("Invalid volume: volume cannot be negative")
            
            # Timestamp validation
            now = datetime.now(timezone.utc)
            tick_time = tick.exchange_timestamp
            if isinstance(tick_time, str):
                tick_time = datetime.fromisoformat(tick_time.replace('Z', '+00:00'))
            
            time_diff = abs((now - tick_time).total_seconds())
            if time_diff > 300:  # 5 minutes tolerance
                quality_issues.append(f"Invalid timestamp: {time_diff}s from current time")
                self.detailed_metrics['data_quality']['timestamp_errors'] += 1
            
            # Price change validation (anomaly detection)
            if instrument_token in self.last_prices:
                last_price = self.last_prices[instrument_token]
                price_change_pct = abs(float(tick.last_price - last_price)) / float(last_price) * 100
                
                # Dynamic threshold based on instrument volatility
                threshold = self.price_change_thresholds.get(instrument_token, 5.0)  # 5% default
                
                if price_change_pct > threshold:
                    quality_issues.append(f"Price anomaly: {price_change_pct:.2f}% change exceeds {threshold}%")
                    self.detailed_metrics['data_quality']['price_anomalies_detected'] += 1
                    
                    self.logger.warning("Price anomaly detected", extra={
                        'instrument_token': instrument_token,
                        'correlation_id': correlation_id,
                        'event_type': 'price_anomaly',
                        'last_price': float(last_price),
                        'current_price': float(tick.last_price),
                        'change_percentage': price_change_pct,
                        'threshold': threshold
                    })
            
            # Update last known price
            self.last_prices[instrument_token] = tick.last_price
            
            # Volume anomaly detection
            if hasattr(tick, 'volume_traded') and tick.volume_traded > 1000000:  # 1M volume threshold
                quality_issues.append("Volume anomaly: unusually high volume detected")
                self.detailed_metrics['data_quality']['volume_anomalies_detected'] += 1
            
            # OHLC consistency validation
            if hasattr(tick, 'ohlc'):
                ohlc = tick.ohlc
                if (ohlc['high'] < ohlc['low'] or 
                    tick.last_price > ohlc['high'] or 
                    tick.last_price < ohlc['low']):
                    quality_issues.append("OHLC inconsistency detected")
            
        except Exception as e:
            quality_issues.append(f"Quality validation error: {str(e)}")
            self.logger.error("Quality validation failed", extra={
                'instrument_token': instrument_token,
                'correlation_id': correlation_id,
                'error': str(e)
            })
        
        return quality_issues
    
    async def _notify_subscribers_comprehensive(self, tick: MockTickData, correlation_id: str) -> List[Dict[str, Any]]:
        """Notify tick subscribers with comprehensive monitoring."""
        notification_results = []
        tick_dict = tick.to_zerodha_format()
        
        for i, subscriber in enumerate(self._tick_subscribers):
            subscriber_id = f"{getattr(subscriber, '__name__', f'subscriber_{i}')}"
            notification_start = time.perf_counter_ns()
            
            try:
                # Execute subscriber callback
                if asyncio.iscoroutinefunction(subscriber):
                    await subscriber(tick_dict)
                else:
                    subscriber(tick_dict)
                
                notification_time_ns = time.perf_counter_ns() - notification_start
                notification_time_us = notification_time_ns / 1000
                
                # Track subscriber performance
                self._track_subscriber_performance(subscriber_id, notification_time_us, True)
                
                notification_results.append({
                    'subscriber_id': subscriber_id,
                    'success': True,
                    'notification_time_us': notification_time_us
                })
                
                self.logger.debug("Subscriber notified successfully", extra={
                    'subscriber_id': subscriber_id,
                    'correlation_id': correlation_id,
                    'event_type': 'subscriber_notification_success',
                    'notification_time_us': notification_time_us,
                    'instrument_token': tick.instrument_token
                })
                
            except Exception as e:
                notification_time_ns = time.perf_counter_ns() - notification_start
                notification_time_us = notification_time_ns / 1000
                
                # Track subscriber failure
                self._track_subscriber_performance(subscriber_id, notification_time_us, False)
                self._record_subscriber_failure(subscriber_id, e)
                
                notification_results.append({
                    'subscriber_id': subscriber_id,
                    'success': False,
                    'error': str(e),
                    'notification_time_us': notification_time_us
                })
                
                self.logger.error("Subscriber notification failed", extra={
                    'subscriber_id': subscriber_id,
                    'correlation_id': correlation_id,
                    'event_type': 'subscriber_notification_error',
                    'error': str(e),
                    'error_type': type(e).__name__,
                    'notification_time_us': notification_time_us,
                    'instrument_token': tick.instrument_token,
                    'failure_count': self.subscriber_failure_counts.get(subscriber_id, 0)
                })
                
                # Check if subscriber should be disabled due to repeated failures
                if self.subscriber_failure_counts.get(subscriber_id, 0) > 10:
                    self.logger.critical("Subscriber has excessive failures - consider disabling", extra={
                        'subscriber_id': subscriber_id,
                        'failure_count': self.subscriber_failure_counts[subscriber_id],
                        'event_type': 'subscriber_excessive_failures'
                    })
        
        return notification_results
    
    def _track_subscriber_performance(self, subscriber_id: str, processing_time_us: float, success: bool) -> None:
        """Track subscriber performance metrics."""
        if subscriber_id not in self.subscriber_performance_tracking:
            self.subscriber_performance_tracking[subscriber_id] = {
                'total_notifications': 0,
                'successful_notifications': 0,
                'failed_notifications': 0,
                'average_processing_time_us': 0.0,
                'peak_processing_time_us': 0.0,
                'success_rate': 100.0
            }
        
        metrics = self.subscriber_performance_tracking[subscriber_id]
        metrics['total_notifications'] += 1
        
        if success:
            metrics['successful_notifications'] += 1
        else:
            metrics['failed_notifications'] += 1
        
        # Update processing time metrics
        if metrics['average_processing_time_us'] == 0:
            metrics['average_processing_time_us'] = processing_time_us
        else:
            # Exponential moving average
            alpha = 0.1
            metrics['average_processing_time_us'] = (
                alpha * processing_time_us + 
                (1 - alpha) * metrics['average_processing_time_us']
            )
        
        if processing_time_us > metrics['peak_processing_time_us']:
            metrics['peak_processing_time_us'] = processing_time_us
        
        # Update success rate
        metrics['success_rate'] = (
            metrics['successful_notifications'] / metrics['total_notifications'] * 100
        )
    
    def _record_subscriber_failure(self, subscriber_id: str, error: Exception) -> None:
        """Record subscriber failure for monitoring."""
        if subscriber_id not in self.subscriber_failure_counts:
            self.subscriber_failure_counts[subscriber_id] = 0
        
        self.subscriber_failure_counts[subscriber_id] += 1
        
        # Store detailed failure information
        if subscriber_id not in self.detailed_metrics['subscriber_health']:
            self.detailed_metrics['subscriber_health'][subscriber_id] = {
                'failure_history': [],
                'last_success_time': None,
                'consecutive_failures': 0
            }
        
        self.detailed_metrics['subscriber_health'][subscriber_id]['failure_history'].append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'error': str(error),
            'error_type': type(error).__name__
        })
        
        self.detailed_metrics['subscriber_health'][subscriber_id]['consecutive_failures'] += 1
        
        # Keep only last 50 failures to prevent memory growth
        failure_history = self.detailed_metrics['subscriber_health'][subscriber_id]['failure_history']
        if len(failure_history) > 50:
            self.detailed_metrics['subscriber_health'][subscriber_id]['failure_history'] = failure_history[-50:]
    
    def _update_generation_performance_metrics(self, generation_time_us: float) -> None:
        """Update tick generation performance metrics."""
        metrics = self.detailed_metrics['generation_performance']
        
        # Update average generation time (exponential moving average)
        if metrics['average_generation_time_us'] == 0:
            metrics['average_generation_time_us'] = generation_time_us
        else:
            alpha = 0.1
            metrics['average_generation_time_us'] = (
                alpha * generation_time_us + 
                (1 - alpha) * metrics['average_generation_time_us']
            )
        
        # Update peak generation time
        if generation_time_us > metrics['peak_generation_time_us']:
            metrics['peak_generation_time_us'] = generation_time_us
    
    def _update_publishing_performance_metrics(self, publish_time_us: float, success: bool) -> None:
        """Update publishing performance metrics."""
        metrics = self.detailed_metrics['publishing_performance']
        
        if success:
            metrics['total_published'] += 1
        else:
            metrics['publish_errors'] += 1
        
        # Update average publish time (exponential moving average)
        if metrics['average_publish_time_us'] == 0:
            metrics['average_publish_time_us'] = publish_time_us
        else:
            alpha = 0.1
            metrics['average_publish_time_us'] = (
                alpha * publish_time_us + 
                (1 - alpha) * metrics['average_publish_time_us']
            )
        
        # Update peak publish time
        if publish_time_us > metrics['peak_publish_time_us']:
            metrics['peak_publish_time_us'] = publish_time_us
        
        # Calculate success rate
        total_attempts = metrics['total_published'] + metrics['publish_errors']
        if total_attempts > 0:
            metrics['publish_success_rate'] = (metrics['total_published'] / total_attempts) * 100
    
    def _update_error_rates(self) -> None:
        """Update error rates for generation performance."""
        gen_metrics = self.detailed_metrics['generation_performance']
        total_attempts = gen_metrics['total_ticks_generated'] + gen_metrics['generation_errors']
        
        if total_attempts > 0:
            gen_metrics['generation_success_rate'] = (
                gen_metrics['total_ticks_generated'] / total_attempts
            ) * 100
    
    def _calculate_generation_success_rate(self) -> float:
        """Calculate current generation success rate."""
        metrics = self.detailed_metrics['generation_performance']
        total = metrics['total_ticks_generated'] + metrics['generation_errors']
        if total == 0:
            return 100.0
        return (metrics['total_ticks_generated'] / total) * 100
    
    def _calculate_publishing_success_rate(self) -> float:
        """Calculate current publishing success rate."""
        metrics = self.detailed_metrics['publishing_performance']
        total = metrics['total_published'] + metrics['publish_errors']
        if total == 0:
            return 100.0
        return (metrics['total_published'] / total) * 100
    
    async def cleanup(self):
        """Cleanup resources."""
        await self.stop_data_streaming()
        self.logger.info("🧹 Mock feed manager cleanup completed")
    
    # Interface compatibility methods (matching ZerodhaFeedManager)
    async def connect(self) -> bool:
        """Interface compatibility - establish connection state."""
        result = await self.initialize()
        if result:
            self.is_connected_state = True
        return result
    
    async def disconnect(self):
        """Interface compatibility - disconnect and cleanup."""
        self.is_connected_state = False
        await self.cleanup()
    
    def is_connected(self) -> bool:
        """Interface compatibility."""
        return self.is_connected_state
    
    @asynccontextmanager
    async def connection(self):
        """Async context manager for connection lifecycle."""
        try:
            await self.connect()
            yield self
        finally:
            await self.disconnect()