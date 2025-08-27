"""Zerodha market feed manager for real-time market data from KiteConnect."""

import asyncio
import logging
import time
import csv
import os
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta, timezone
import json
from collections import deque
from pathlib import Path

from core.auth.auth_manager import AuthManager
from core.utils.exceptions import MarketDataError
from core.config.settings import get_settings
from core.logging.logger import get_logger
from .config import ZerodhaFeedConfig

logger = get_logger(__name__)


def _safe_publish_event(event_type: str, data: Dict[str, Any], manager_instance=None) -> None:
    """
    Thread-safe event publishing using event loop handoff.
    This ensures thread-safe communication from WebSocket thread to async event loop.
    """
    try:
        from core.events.event_bus import Event, EventPriority
        from datetime import datetime
        
        # Create event object
        event = Event(
            event_type=event_type,
            data=data,
            timestamp=datetime.now(timezone.utc),
            priority=EventPriority.NORMAL,
            persist=False  # Don't persist tick data
        )
        
        # Thread-safe handoff to event loop
        priority_value = 5 - event.priority.value  # Invert for PriorityQueue
        
        # Use the event loop reference for thread-safe handoff
        loop_to_use = None
        
        # Try manager's event loop first (if provided)
        if manager_instance and hasattr(manager_instance, '_event_loop') and manager_instance._event_loop:
            loop_to_use = manager_instance._event_loop
        # Try event bus loop reference  
        elif manager_instance and hasattr(manager_instance, 'event_bus') and hasattr(manager_instance.event_bus, '_loop') and manager_instance.event_bus._loop:
            loop_to_use = manager_instance.event_bus._loop
        # Fallback: try to get current loop (this may fail in thread context)
        else:
            try:
                import asyncio
                loop_to_use = asyncio.get_running_loop()
            except RuntimeError:
                logger.debug(f"No event loop available for thread-safe publishing of {event_type}")
                return
        
        # Execute thread-safe handoff
        if loop_to_use and manager_instance and hasattr(manager_instance, 'event_bus'):
            loop_to_use.call_soon_threadsafe(
                manager_instance.event_bus.event_queue.put_nowait, 
                (priority_value, event)
            )
        else:
            logger.debug(f"No event loop available for thread-safe publishing of {event_type}")
            return
        
        logger.debug(f"Event {event_type} added to queue thread-safely")
    
    except Exception as e:
        # Never let event publishing errors crash tick processing (industry standard)
        logger.debug(f"Could not publish event {event_type}: {e} (non-critical, continuing)")


class ZerodhaMarketFeedManager:
    """Manages real-time market data from Zerodha KiteConnect with batch processing."""
    
    def __init__(self, settings=None, event_bus=None, config: Optional[ZerodhaFeedConfig] = None):
        self.settings = settings
        self.event_bus = event_bus
        self.auth_manager = None
        self.storage_manager = None
        self.config = config or ZerodhaFeedConfig()
        
        # WebSocket ticker
        self.ticker = None
        self.subscribed_tokens = set()
        
        # Event loop reference for thread-safe operations
        self._event_loop = None
        
        # Data streaming
        self.streaming = False
        self.tick_count = 0
        self.last_tick_time = None
        
        # Optimized batch processing with memory management
        self.tick_buffer = deque()
        self.depth_buffer = deque()
        self.batch_size = self.config.batch_size
        self.batch_timeout = self.config.batch_timeout
        self.max_buffer_size = self.config.max_buffer_size
        self.last_batch_time = datetime.now(timezone.utc)
        self._batch_task = None
        
        # Memory management
        self._memory_pressure_detected = False
        self._dropped_ticks_count = 0
        
        # Instrument mapping
        self.instruments = {}  # symbol -> instrument data
        self.token_to_symbol = {}  # token -> symbol
        
        # Data callbacks
        self.tick_callbacks = []
        
        # Enhanced statistics with performance metrics
        self.stats = {
            'ticks_received': 0,
            'ticks_processed': 0,
            'ticks_batched': 0,
            'ticks_dropped': 0,
            'depth_entries_stored': 0,
            'batch_operations': 0,
            'connection_status': 'disconnected',
            'subscribed_instruments': 0,
            'last_tick_time': None,
            'mode': 'zerodha',
            'memory_pressure': False,
            'buffer_overflow_count': 0,
            'avg_processing_latency_ms': 0.0
        }
        
        logger.info("ZerodhaMarketFeedManager initialized")
    
    def set_auth_manager(self, auth_manager):
        """Set the auth manager reference."""
        self.auth_manager = auth_manager
        logger.info("Auth manager reference set for Zerodha feed manager")
    
    def set_storage_manager(self, storage_manager):
        """Set the storage manager reference."""
        self.storage_manager = storage_manager
        logger.info("Storage manager reference set for Zerodha feed manager")
    
    def set_event_loop(self, loop):
        """Set the event loop reference for thread-safe operations."""
        self._event_loop = loop
        logger.info("Event loop reference set for thread-safe operations")
    
    async def initialize(self) -> bool:
        """Initialize the market data manager."""
        try:
            logger.info("Initializing Zerodha market feed manager...")
            
            # Check if we're in mock mode
            if self.settings and self.settings.mock_market_feed:
                logger.info("🎭 Mock mode - skipping Zerodha initialization")
                return True
            
            # Check authentication for real Zerodha mode
            if not self.auth_manager or not self.auth_manager.is_authenticated():
                logger.error("Authentication required for Zerodha market feed")
                return False
            
            logger.info("✅ Authentication verified for Zerodha market feed")
            
            # Load instruments from Zerodha
            await self._load_instruments()
            
            # Setup WebSocket ticker
            self._setup_ticker()
            
            logger.info("✅ Zerodha market feed manager initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Zerodha market feed manager: {e}")
            return False
    
    async def _load_instruments(self):
        """Load instruments from local CSV file."""
        try:
            logger.info("Loading instruments from CSV file...")
            
            # Get CSV file path
            csv_path = Path(__file__).parent / "instruments.csv"
            if not csv_path.exists():
                raise Exception(f"Instruments CSV file not found: {csv_path}")
            
            # Read instruments from CSV
            instruments_loaded = 0
            with open(csv_path, 'r', encoding='utf-8') as file:
                # Skip comment lines and find the data
                lines = file.readlines()
                data_lines = []
                
                for line in lines:
                    line = line.strip()
                    # Skip empty lines and comment lines
                    if line and not line.startswith('#'):
                        data_lines.append(line)
                
                # Use explicit field names since we know the format
                fieldnames = ['instrument_token', 'tradingsymbol', 'name', 'exchange']
                csv_reader = csv.DictReader(data_lines, fieldnames=fieldnames)
                
                for row in csv_reader:
                    try:
                        # Parse instrument data
                        instrument_token = int(row['instrument_token'])
                        tradingsymbol = row['tradingsymbol'].strip()
                        name = row['name'].strip()
                        exchange = row['exchange'].strip()
                        
                        # Create instrument data structure compatible with KiteConnect
                        instrument_data = {
                            'instrument_token': instrument_token,
                            'exchange_token': instrument_token // 256,  # Standard Zerodha formula
                            'tradingsymbol': tradingsymbol,
                            'name': name,
                            'exchange': exchange,
                            'segment': exchange,
                            'instrument_type': 'EQ' if exchange == 'NSE' else 'INDEX',
                            'lot_size': 1,
                            'tick_size': 0.05,
                            'expiry': None,
                            'strike': 0,
                            'option_type': None
                        }
                        
                        # Store instrument data
                        self.instruments[tradingsymbol] = instrument_data
                        self.token_to_symbol[instrument_token] = tradingsymbol
                        instruments_loaded += 1
                        
                        logger.debug(f"Loaded instrument: {tradingsymbol} ({instrument_token})")
                        
                    except (ValueError, KeyError) as e:
                        logger.warning(f"Skipping invalid instrument row: {row} - {e}")
                        continue
            
            logger.info(f"✅ Loaded {instruments_loaded} instruments from CSV file")
            
            if instruments_loaded == 0:
                raise Exception("No valid instruments loaded from CSV file")
            
        except Exception as e:
            logger.error(f"Failed to load instruments from CSV: {e}")
            raise MarketDataError(f"Failed to load instruments from CSV: {e}")
    
    def _setup_ticker(self):
        """Set up WebSocket ticker."""
        try:
            # Skip ticker setup for mock mode
            if self.settings and self.settings.mock_market_feed:
                logger.info("🎭 Mock mode - skipping ticker setup")
                self.ticker = None
                return
            
            # Get kite client from auth manager
            if not self.auth_manager:
                logger.warning("Cannot setup ticker: Auth manager not available")
                self.ticker = None
                return
                
            kite = self.auth_manager.get_kite_client()
            if not kite:
                logger.warning("Cannot setup ticker: KiteConnect client not available")
                self.ticker = None
                return
            
            # Import KiteTicker
            try:
                from kiteconnect import KiteTicker
                self.ticker = KiteTicker(kite.api_key, kite.access_token)
            except ImportError:
                logger.error("KiteTicker not available - install kiteconnect package")
                self.ticker = None
                return
            
            # Set up event handlers
            self.ticker.on_ticks = self._on_ticks
            self.ticker.on_connect = self._on_connect
            self.ticker.on_close = self._on_close
            self.ticker.on_error = self._on_error
            self.ticker.on_reconnect = self._on_reconnect
            self.ticker.on_noreconnect = self._on_noreconnect
            
            logger.info("WebSocket ticker configured successfully")
            
        except Exception as e:
            logger.error(f"Failed to setup ticker: {e}")
            logger.warning("Ticker setup failed - market data streaming will not be available")
            self.ticker = None
    
    def refresh_ticker_setup(self):
        """Refresh ticker setup after authentication."""
        try:
            logger.info("Refreshing ticker setup after authentication...")
            self._setup_ticker()
            if self.ticker:
                logger.info("✅ Ticker setup refreshed successfully")
                return True
            else:
                logger.warning("⚠️ Ticker still not configured after refresh")
                return False
        except Exception as e:
            logger.error(f"Failed to refresh ticker setup: {e}")
            return False
    
    async def start_data_streaming(self) -> bool:
        """Start real-time data streaming."""
        
        # Check if we're in mock mode first
        if self.settings and self.settings.mock_market_feed:
            logger.info("🎭 Mock mode - skipping Zerodha data streaming")
            logger.info("ℹ️ Market data will come from mock feed instead")
            return True
        
        # Check authentication for real mode
        if not self.auth_manager or not self.auth_manager.is_authenticated():
            logger.error("Authentication required for market data streaming")
            return False
        
        if not self.ticker:
            logger.error("Ticker not configured")
            return False
        
        try:
            logger.info("Starting Zerodha market data streaming...")
            
            # Get all instrument tokens from loaded CSV instruments
            instrument_tokens = list(self.token_to_symbol.keys())
            
            if not instrument_tokens:
                logger.warning("No instruments available for subscription")
                return False
            
            # Validate instrument count
            if len(instrument_tokens) > self.config.max_instruments_per_request:
                logger.warning(f"Too many instruments ({len(instrument_tokens)}), limiting to {self.config.max_instruments_per_request}")
                instrument_tokens = instrument_tokens[:self.config.max_instruments_per_request]
            
            # Start streaming
            self.streaming = True
            self.stats['connection_status'] = 'connecting'
            
            # Start batch processing task for efficient database writes
            if self.config.enable_tick_storage:
                self._batch_task = asyncio.create_task(self._batch_processor())
                logger.info(f"✅ Batch processor started (batch_size={self.batch_size}, timeout={self.batch_timeout}s)")
            
            # Connect ticker
            if hasattr(self.ticker, 'connect'):
                self.ticker.connect(threaded=True)
                
                # Wait a moment for connection to establish
                import time
                await asyncio.sleep(2)  # Give WebSocket time to connect
                
                # Check if connection was successful
                connection_attempts = 0
                max_attempts = 10
                while connection_attempts < max_attempts:
                    if self.is_connected():
                        break
                    await asyncio.sleep(0.5)
                    connection_attempts += 1
                
                if self.is_connected():
                    logger.info("✅ Zerodha WebSocket connected successfully")
                else:
                    logger.warning(f"⚠️ WebSocket connection status unclear after {max_attempts * 0.5} seconds")
                    
            else:
                logger.error("Ticker does not have connect method")
                return False
            
            logger.info(f"✅ Zerodha market data streaming started for {len(instrument_tokens)} instruments")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            return False
    
    async def subscribe_instruments(self, instrument_tokens: List[int]) -> bool:
        """Subscribe to instruments for data streaming."""
        try:
            if not self.ticker or not self.streaming:
                logger.error("Cannot subscribe - ticker not active")
                return False
            
            # Subscribe to instruments
            self.ticker.subscribe(instrument_tokens)
            
            # Set mode based on configuration
            mode_map = {
                "ltp": self.ticker.MODE_LTP,
                "quote": self.ticker.MODE_QUOTE,
                "full": self.ticker.MODE_FULL
            }
            mode = mode_map.get(self.config.default_mode, self.ticker.MODE_QUOTE)
            self.ticker.set_mode(mode, instrument_tokens)
            
            self.subscribed_tokens.update(instrument_tokens)
            self.stats['subscribed_instruments'] = len(self.subscribed_tokens)
            
            logger.info(f"Subscribed to {len(instrument_tokens)} instruments in {self.config.default_mode} mode")
            return True
            
        except Exception as e:
            logger.error(f"Failed to subscribe to instruments: {e}")
            return False
    
    async def unsubscribe_instruments(self, instrument_tokens: List[int]) -> bool:
        """Unsubscribe from instruments."""
        try:
            if not self.ticker:
                logger.error("Cannot unsubscribe - ticker not available")
                return False
            
            self.ticker.unsubscribe(instrument_tokens)
            self.subscribed_tokens.difference_update(instrument_tokens)
            self.stats['subscribed_instruments'] = len(self.subscribed_tokens)
            
            logger.info(f"Unsubscribed from {len(instrument_tokens)} instruments")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from instruments: {e}")
            return False
    
    async def stop(self):
        """Stop data streaming and flush remaining batches."""
        if self.ticker and self.streaming:
            try:
                logger.info("Stopping Zerodha market data streaming...")
                self.streaming = False
                
                # Stop batch processor and flush remaining data
                if self._batch_task:
                    self._batch_task.cancel()
                    try:
                        await self._batch_task
                    except asyncio.CancelledError:
                        pass
                    
                    # Flush remaining batches
                    await self._flush_remaining_batches()
                    logger.info("✅ Remaining batches flushed to database")
                
                self.ticker.close()
                self.stats['connection_status'] = 'disconnected'
                logger.info("✅ Zerodha market data streaming stopped")
                
            except Exception as e:
                logger.error(f"Error stopping ticker: {e}")
    
    async def cleanup(self):
        """Cleanup resources and stop the feed manager."""
        await self.stop()
    
    def _on_connect(self, ws, response):
        """Handle WebSocket connection."""
        logger.info("Zerodha market data WebSocket connected")
        
        # Get instrument tokens from loaded CSV instruments
        tokens = list(self.token_to_symbol.keys())
        
        if tokens:
            # Limit tokens based on configuration
            if len(tokens) > self.config.max_instruments_per_request:
                tokens = tokens[:self.config.max_instruments_per_request]
                
            ws.subscribe(tokens)
            
            # Set mode based on configuration
            mode_map = {
                "ltp": ws.MODE_LTP,
                "quote": ws.MODE_QUOTE,
                "full": ws.MODE_FULL
            }
            mode = mode_map.get(self.config.default_mode, ws.MODE_QUOTE)
            ws.set_mode(mode, tokens)
            
            self.subscribed_tokens.update(tokens)
            self.stats['subscribed_instruments'] = len(tokens)
            
            logger.info(f"Subscribed to {len(tokens)} instruments in {self.config.default_mode} mode")
        else:
            logger.warning("No instruments available for subscription")
        
        # Publish connection event
        _safe_publish_event('connection_status', {
            'connection_type': 'zerodha_market_feed', 
            'status': 'connected'
        }, self)
    
    def _on_ticks(self, ws, ticks):
        """Handle incoming market ticks with optimized processing."""
        try:
            self.tick_count += len(ticks)
            self.last_tick_time = datetime.now(timezone.utc)
            self.stats['ticks_received'] += len(ticks)
            self.stats['last_tick_time'] = self.last_tick_time.isoformat()
            
            # Process each tick
            for tick in ticks:
                start_time = time.time()
                
                # Thread-safe event publishing for downstream consumers
                _safe_publish_event('market_data_received', tick, self)
                
                # Direct batch preparation for database storage
                if self.config.enable_tick_storage:
                    self._prepare_tick_for_batch_sync(tick)
                
                # Execute synchronous callbacks
                self._execute_callbacks_sync(tick)
                
                # Record performance timing
                self._add_performance_timing('tick_processing', start_time)
            
        except Exception as e:
            logger.error(f"Error processing ticks: {e}")
    
    def _execute_callbacks_sync(self, tick: Dict[str, Any]):
        """Execute synchronous callbacks only."""
        try:
            # Execute only synchronous callbacks to avoid blocking
            for callback in self.tick_callbacks:
                try:
                    if not asyncio.iscoroutinefunction(callback):
                        callback(tick)
                except Exception as e:
                    logger.error(f"Error in sync tick callback: {e}")
            
            # Update statistics
            self.stats['ticks_processed'] += 1
            
        except Exception as e:
            logger.error(f"Error executing sync callbacks: {e}")
    
    def _prepare_tick_for_batch_sync(self, tick: Dict[str, Any]):
        """Prepare tick for batch processing."""
        try:
            current_time = datetime.now(timezone.utc)
            ohlc_data = tick.get('ohlc', {})
            depth_data = tick.get('depth', {})
            
            # Extract best bid/ask from market depth
            bid_price = bid_qty = ask_price = ask_qty = 0.0
            if depth_data:
                buy_orders = depth_data.get('buy', [])
                sell_orders = depth_data.get('sell', [])
                if buy_orders:
                    bid_price = buy_orders[0].get('price', 0.0)
                    bid_qty = buy_orders[0].get('quantity', 0)
                if sell_orders:
                    ask_price = sell_orders[0].get('price', 0.0)
                    ask_qty = sell_orders[0].get('quantity', 0)
            
            # Create comprehensive tick data for storage including full market depth
            tick_data = {
                'timestamp': tick.get('exchange_timestamp', current_time),
                'instrument_token': tick.get('instrument_token'),
                'last_price': float(tick.get('last_price', 0.0)),
                'last_traded_quantity': int(tick.get('last_traded_quantity', 0)),
                'average_traded_price': float(tick.get('average_traded_price', 0.0)),
                'volume_traded': int(tick.get('volume_traded', 0)),
                'total_buy_quantity': int(tick.get('total_buy_quantity', 0)),
                'total_sell_quantity': int(tick.get('total_sell_quantity', 0)),
                'oi': int(tick.get('oi', 0)),
                'oi_day_high': int(tick.get('oi_day_high', 0)),
                'oi_day_low': int(tick.get('oi_day_low', 0)),
                'change': float(tick.get('change', 0.0)),
                'change_percent': float(tick.get('change_percent', 0.0)),
                'open': float(ohlc_data.get('open', 0.0)) if ohlc_data else 0.0,
                'high': float(ohlc_data.get('high', 0.0)) if ohlc_data else 0.0,
                'low': float(ohlc_data.get('low', 0.0)) if ohlc_data else 0.0,
                'close': float(ohlc_data.get('close', 0.0)) if ohlc_data else 0.0,
                'last_trade_time': tick.get('last_trade_time'),
                'exchange_timestamp': tick.get('exchange_timestamp'),
                'bid': float(bid_price),
                'ask': float(ask_price),
                'bid_quantity': int(bid_qty),
                'ask_quantity': int(ask_qty),
                # Add full market depth data for ML strategies
                'market_depth': self._extract_full_market_depth(depth_data) if depth_data else None,
                'tradingsymbol': self.token_to_symbol.get(tick.get('instrument_token'), 'UNKNOWN')
            }
            
            # Check memory pressure
            if self._check_memory_pressure():
                self._handle_memory_pressure()
                return
            
            # Add to buffer for async batch processing
            self.tick_buffer.append(tick_data)
            
            # Prepare market depth data if enabled
            if depth_data and self.config.enable_depth_storage:
                self._prepare_depth_for_batch_sync(tick, current_time)
            
        except Exception as e:
            logger.error(f"Error preparing tick for batch processing: {e}")
    
    def _prepare_depth_for_batch_sync(self, tick: Dict[str, Any], current_time: datetime):
        """Prepare market depth data for batch processing."""
        try:
            depth = tick.get('depth', {})
            if not depth:
                return
            
            instrument_token = tick.get('instrument_token')
            
            # Process buy orders (5 levels)
            buy_orders = depth.get('buy', [])
            for level, order in enumerate(buy_orders[:5]):
                depth_data = {
                    'timestamp': tick.get('exchange_timestamp', current_time),
                    'instrument_token': instrument_token,
                    'level': level,
                    'side': 'buy',
                    'price': float(order.get('price', 0.0)),
                    'quantity': int(order.get('quantity', 0)),
                    'orders': int(order.get('orders', 0)),
                }
                self.depth_buffer.append(depth_data)
            
            # Process sell orders (5 levels)
            sell_orders = depth.get('sell', [])
            for level, order in enumerate(sell_orders[:5]):
                depth_data = {
                    'timestamp': tick.get('exchange_timestamp', current_time),
                    'instrument_token': instrument_token,
                    'level': level,
                    'side': 'sell',
                    'price': float(order.get('price', 0.0)),
                    'quantity': int(order.get('quantity', 0)),
                    'orders': int(order.get('orders', 0)),
                }
                self.depth_buffer.append(depth_data)
                
        except Exception as e:
            logger.error(f"Error preparing depth for batch: {e}")
    
    def _extract_full_market_depth(self, depth_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract full 5-level market depth data for ML strategies."""
        try:
            market_depth = {
                'buy': [],
                'sell': []
            }
            
            # Extract buy orders (5 levels)
            buy_orders = depth_data.get('buy', [])
            for i, order in enumerate(buy_orders[:5]):
                market_depth['buy'].append({
                    'level': i,
                    'price': float(order.get('price', 0.0)),
                    'quantity': int(order.get('quantity', 0)),
                    'orders': int(order.get('orders', 0))
                })
            
            # Extract sell orders (5 levels)
            sell_orders = depth_data.get('sell', [])
            for i, order in enumerate(sell_orders[:5]):
                market_depth['sell'].append({
                    'level': i,
                    'price': float(order.get('price', 0.0)),
                    'quantity': int(order.get('quantity', 0)),
                    'orders': int(order.get('orders', 0))
                })
            
            return market_depth
            
        except Exception as e:
            logger.error(f"Error extracting market depth: {e}")
            return None
    
    
    async def _batch_processor(self):
        """Background task to process tick and depth batches."""
        logger.info("🔄 Batch processor started")
        
        while self.streaming:
            try:
                # Check if we should process a batch
                now = datetime.now(timezone.utc)
                time_elapsed = (now - self.last_batch_time).total_seconds()
                
                should_process = (
                    len(self.tick_buffer) >= self.batch_size or
                    len(self.depth_buffer) >= self.batch_size or
                    (time_elapsed >= self.batch_timeout and (self.tick_buffer or self.depth_buffer))
                )
                
                if should_process:
                    await self._process_batches()
                    self.last_batch_time = now
                
                # Sleep briefly to avoid busy waiting
                await asyncio.sleep(0.1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in batch processor: {e}")
                await asyncio.sleep(1)
    
    async def _process_batches(self):
        """Process accumulated tick and depth data in batches."""
        if not (self.tick_buffer or self.depth_buffer):
            return
        
        try:
            # Process tick batches
            if self.tick_buffer:
                batch_size = min(len(self.tick_buffer), self.batch_size)
                tick_batch = []
                for _ in range(batch_size):
                    if self.tick_buffer:
                        tick_data = self.tick_buffer.popleft()
                        tick_batch.append(tick_data)
                
                # Store tick batch to ClickHouse
                if tick_batch and self.storage_manager:
                    success = await self.storage_manager.store_market_ticks(tick_batch)
                    if success:
                        self.stats['ticks_batched'] += len(tick_batch)
                        logger.debug(f"✅ Stored {len(tick_batch)} ticks to ClickHouse")
                    else:
                        logger.warning(f"⚠️ Failed to store {len(tick_batch)} ticks to ClickHouse")
            
            # Process depth batches
            if self.depth_buffer:
                batch_size = min(len(self.depth_buffer), self.batch_size)
                depth_batch = []
                for _ in range(batch_size):
                    if self.depth_buffer:
                        depth_data = self.depth_buffer.popleft()
                        depth_batch.append(depth_data)
                
                # Store depth batch to ClickHouse
                if depth_batch and self.storage_manager:
                    success = await self.storage_manager.store_market_depth(depth_batch)
                    if success:
                        self.stats['depth_entries_stored'] += len(depth_batch)
                        logger.debug(f"✅ Stored {len(depth_batch)} depth entries to ClickHouse")
                    else:
                        logger.warning(f"⚠️ Failed to store {len(depth_batch)} depth entries to ClickHouse")
            
            self.stats['batch_operations'] += 1
            
        except Exception as e:
            logger.error(f"Failed to process batch: {e}")
    
    async def _flush_remaining_batches(self):
        """Flush any remaining data in buffers before shutdown."""
        if not (self.tick_buffer or self.depth_buffer):
            return
        
        logger.info(f"🔄 Flushing {len(self.tick_buffer)} ticks and {len(self.depth_buffer)} depth entries...")
        
        while self.tick_buffer or self.depth_buffer:
            await self._process_batches()
            await asyncio.sleep(0.01)
    
    def _check_memory_pressure(self) -> bool:
        """Check if system is under memory pressure."""
        try:
            total_buffer_size = len(self.tick_buffer) + len(self.depth_buffer)
            
            if total_buffer_size > self.max_buffer_size:
                self._memory_pressure_detected = True
                self.stats['memory_pressure'] = True
                return True
            
            # Reset if pressure subsided
            if total_buffer_size < self.max_buffer_size * 0.5:
                self._memory_pressure_detected = False
                self.stats['memory_pressure'] = False
            
            return self._memory_pressure_detected
            
        except Exception as e:
            logger.error(f"Error checking memory pressure: {e}")
            return False
    
    def _handle_memory_pressure(self):
        """Handle memory pressure by dropping oldest ticks."""
        try:
            dropped = 0
            
            # Drop from tick_buffer  
            if len(self.tick_buffer) > self.batch_size:
                excess = len(self.tick_buffer) - self.batch_size
                for _ in range(excess):
                    self.tick_buffer.popleft()
                dropped += excess
            
            # Drop from buffers
            while len(self.tick_buffer) > self.max_buffer_size // 2:
                self.tick_buffer.popleft()
                dropped += 1
            
            while len(self.depth_buffer) > self.max_buffer_size // 2:
                self.depth_buffer.popleft()
                dropped += 1
            
            self._dropped_ticks_count += dropped
            self.stats['ticks_dropped'] += dropped
            self.stats['buffer_overflow_count'] += 1
            
            if dropped > 0:
                logger.warning(f"Memory pressure: dropped {dropped} old ticks/depth entries")
            
        except Exception as e:
            logger.error(f"Error handling memory pressure: {e}")
    
    def _add_performance_timing(self, operation: str, start_time: float):
        """Add performance timing for monitoring."""
        try:
            latency_ms = (time.time() - start_time) * 1000
            
            # Update rolling average
            current_avg = self.stats.get('avg_processing_latency_ms', 0.0)
            self.stats['avg_processing_latency_ms'] = (current_avg * 0.9) + (latency_ms * 0.1)
            
            # Log slow operations
            if latency_ms > self.config.slow_operation_threshold_ms:
                logger.debug(f"Slow {operation}: {latency_ms:.2f}ms")
                
        except Exception as e:
            logger.debug(f"Error recording performance timing: {e}")
    
    def _on_close(self, ws, code, reason):
        """Handle WebSocket close."""
        logger.warning(f"Zerodha market data WebSocket closed: {code} - {reason}")
        self.stats['connection_status'] = 'disconnected'
        
        # Publish disconnection event
        _safe_publish_event('connection_status', {
            'connection_type': 'zerodha_market_feed', 
            'status': 'disconnected', 
            'reason': reason
        }, self)
    
    def _on_error(self, ws, code, reason):
        """Handle WebSocket error."""
        logger.error(f"Zerodha market data WebSocket error: {code} - {reason}")
        
        # Publish error event
        _safe_publish_event('system_error', {
            'component': 'zerodha_market_feed',
            'error_type': 'websocket_error',
            'message': f"Code: {code}, Reason: {reason}"
        }, self)
    
    def _on_reconnect(self, ws, attempts_count):
        """Handle WebSocket reconnection."""
        logger.info(f"Zerodha market data WebSocket reconnecting (attempt {attempts_count})")
        
        # Publish reconnection event
        _safe_publish_event('connection_status', {
            'connection_type': 'zerodha_market_feed', 
            'status': 'reconnecting', 
            'attempt': attempts_count
        }, self)
    
    def _on_noreconnect(self, ws):
        """Handle WebSocket no reconnect."""
        logger.error("Zerodha market data WebSocket failed to reconnect")
        self.stats['connection_status'] = 'failed'
        
        # Publish failure event
        _safe_publish_event('connection_status', {
            'connection_type': 'zerodha_market_feed', 
            'status': 'failed'
        }, self)
    
    def add_tick_callback(self, callback: Callable):
        """Add a callback for tick data."""
        self.tick_callbacks.append(callback)
        logger.debug(f"Added tick callback: {callback}")
    
    def remove_tick_callback(self, callback: Callable):
        """Remove a tick callback."""
        if callback in self.tick_callbacks:
            self.tick_callbacks.remove(callback)
            logger.debug(f"Removed tick callback: {callback}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get feed statistics."""
        stats = self.stats.copy()
        
        # Add buffer status
        stats['buffer_status'] = {
            'tick_buffer_size': len(self.tick_buffer),
            'depth_buffer_size': len(self.depth_buffer),
            'batch_size_config': self.batch_size,
            'batch_timeout_config': self.batch_timeout,
        }
        
        # Add batch processing efficiency metrics
        if stats['batch_operations'] > 0:
            stats['avg_ticks_per_batch'] = stats['ticks_batched'] / stats['batch_operations']
            stats['avg_depth_per_batch'] = stats['depth_entries_stored'] / stats['batch_operations']
        
        # Add connection details
        stats['is_connected'] = self.is_connected()
        stats['detailed_connection_status'] = self.connection_status()
        
        return stats
    
    def is_connected(self) -> bool:
        """Check if WebSocket ticker is connected."""
        try:
            if not self.ticker:
                return False
            
            # Check if ticker has is_connected method
            if hasattr(self.ticker, 'is_connected'):
                return self.ticker.is_connected()
            
            # Fallback: check connection status in stats
            return self.stats.get('connection_status') == 'connected'
            
        except Exception as e:
            logger.error(f"Error checking connection status: {e}")
            return False
    
    def connection_status(self) -> str:
        """Get detailed connection status."""
        try:
            if not self.ticker:
                return 'no_ticker'
            
            if hasattr(self.ticker, 'is_connected'):
                if self.ticker.is_connected():
                    return 'connected'
                else:
                    return 'disconnected'
            
            # Fallback to stats
            return self.stats.get('connection_status', 'unknown')
            
        except Exception as e:
            logger.error(f"Error getting connection status: {e}")
            return 'error'


# Global instance
zerodha_market_feed_manager = ZerodhaMarketFeedManager()