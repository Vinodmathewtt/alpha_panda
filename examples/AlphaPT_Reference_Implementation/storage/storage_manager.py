"""High-performance market data storage manager.

This module coordinates the storage of market data across multiple databases:
- ClickHouse for high-frequency tick data and analytics
- Redis for hot data caching
- Event-driven data pipeline with batching and buffering
"""

import asyncio
import logging
import gzip
import lz4.frame
import time
import uuid
import traceback
from typing import List, Dict, Any, Optional, Set, Callable
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
import threading

from core.config.settings import Settings
from core.events import EventBusCore, get_event_publisher, subscriber
from core.events.event_types import EventFactory, EventType, MarketDataEvent
from core.logging import get_database_logger
from core.utils.exceptions import DatabaseError

from .clickhouse_manager import ClickHouseManager
from .redis_cache_manager import RedisCacheManager
from .data_quality_monitor import DataQualityMonitor


@dataclass
class StorageMetrics:
    """Storage performance metrics."""
    ticks_received: int = 0
    ticks_stored: int = 0
    ticks_failed: int = 0
    batches_processed: int = 0
    avg_batch_size: float = 0.0
    avg_storage_latency_ms: float = 0.0
    buffer_size: int = 0
    last_flush_time: Optional[datetime] = None
    compression_ratio: float = 0.0
    compressed_bytes: int = 0
    uncompressed_bytes: int = 0
    processing_rate_per_sec: float = 0.0


# Global storage manager instance for decorator handlers
_storage_manager_instance: Optional['MarketDataStorageManager'] = None


@subscriber.on_event("market.tick.*", durable_name="storage-ticks")
async def handle_market_tick_storage(event: MarketDataEvent) -> None:
    """Handle market tick events for storage processing.
    
    This decorator-based handler routes market data events to the storage manager.
    """
    global _storage_manager_instance
    if _storage_manager_instance:
        event_data = {
            'instrument_token': event.instrument_token,
            'last_price': float(event.last_price),
            'ohlc': event.ohlc,
            'volume': event.volume,
            'timestamp': event.timestamp,
            'correlation_id': event.correlation_id,
            'exchange': event.exchange,
            'tradingsymbol': event.tradingsymbol
        }
        await _storage_manager_instance._handle_market_tick_event(event_data)


@subscriber.on_event("market.depth.*", durable_name="storage-depth")
async def handle_market_depth_storage(event: MarketDataEvent) -> None:
    """Handle market depth events for storage processing."""
    global _storage_manager_instance
    if _storage_manager_instance:
        # Handle depth data if available
        if hasattr(event, 'depth') and event.depth:
            event_data = {
                'instrument_token': event.instrument_token,
                'depth': event.depth,
                'timestamp': event.timestamp,
                'correlation_id': event.correlation_id,
                'exchange': event.exchange,
                'tradingsymbol': event.tradingsymbol
            }
            await _storage_manager_instance._handle_market_tick_event(event_data)


class MarketDataStorageManager:
    """High-performance market data storage manager."""
    
    def __init__(self, settings: Settings, event_bus: EventBusCore):
        """Initialize storage manager.
        
        Args:
            settings: Application settings
            event_bus: Event bus for data pipeline
        """
        self.settings = settings
        self.event_bus = event_bus
        self.logger = get_database_logger("storage_manager")
        
        # Database managers
        self.clickhouse_manager = ClickHouseManager(settings)
        self.redis_cache_manager = RedisCacheManager(settings)
        self.quality_monitor = DataQualityMonitor(settings, event_bus)
        
        # Storage configuration
        self.batch_size = settings.market_data_batch_size
        self.flush_interval = settings.market_data_flush_interval
        self.buffer_size = settings.market_data_buffer_size
        
        # Data buffers with threading protection
        self._tick_buffer: deque = deque(maxlen=self.buffer_size)
        self._signal_buffer: deque = deque(maxlen=1000)
        self._tick_buffer_lock = threading.Lock()
        self._signal_buffer_lock = threading.Lock()
        self._last_flush = datetime.now(timezone.utc)
        
        # Performance tracking
        self.metrics = StorageMetrics()
        self._performance_window = deque(maxlen=1000)  # Last 1000 operations
        self._rate_tracker = deque(maxlen=60)  # Track processing rate per second
        
        # Processing state
        self.is_running = False
        self._flush_task: Optional[asyncio.Task] = None
        self._rate_monitoring_task: Optional[asyncio.Task] = None
        self._processing_executor = ThreadPoolExecutor(max_workers=6)  # Increased workers
        
        # Compression settings
        self.compression_enabled = getattr(settings, 'enable_compression', True)
        self.compression_method = getattr(settings, 'compression_method', 'lz4')  # lz4 or gzip
        
        # Event subscriptions
        self._subscribed_subjects: Set[str] = set()
        
        # Memory-mapped buffer for high-frequency writes
        self._memory_mapped_buffer = []
        self._memory_mapped_size = 0
        self._max_memory_mapped_size = 64 * 1024 * 1024  # 64MB
        
    async def start(self) -> bool:
        """Start the storage manager.
        
        Returns:
            True if started successfully
        """
        try:
            self.logger.info("Starting market data storage manager...")
            
            # Connect to ClickHouse
            if not await self.clickhouse_manager.connect():
                raise DatabaseError("Failed to connect to ClickHouse")
            
            # Initialize schema
            if not await self.clickhouse_manager.initialize_schema():
                raise DatabaseError("Failed to initialize ClickHouse schema")
            
            # Connect to Redis cache
            if not await self.redis_cache_manager.connect():
                self.logger.warning("Failed to connect to Redis cache - continuing without caching")
            
            # Start data quality monitoring
            if not await self.quality_monitor.start():
                self.logger.warning("Failed to start data quality monitoring")
            
            # Set global instance for decorator handlers
            global _storage_manager_instance
            _storage_manager_instance = self
            self.logger.info("✅ Storage manager registered for event subscriptions")
            
            # Start background flush task
            self._flush_task = asyncio.create_task(self._flush_loop())
            
            # Start rate monitoring task
            self._rate_monitoring_task = asyncio.create_task(self._rate_monitoring_loop())
            
            self.is_running = True
            self.logger.info("✅ Market data storage manager started with compression enabled")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start storage manager: {e}")
            await self.stop()
            return False
    
    async def stop(self) -> None:
        """Stop the storage manager."""
        try:
            self.logger.info("Stopping market data storage manager...")
            
            self.is_running = False
            
            # Cancel flush task
            if self._flush_task and not self._flush_task.done():
                self._flush_task.cancel()
                try:
                    await self._flush_task
                except asyncio.CancelledError:
                    pass
            
            # Flush remaining data
            await self._flush_all_buffers()
            
            # Clear global instance
            global _storage_manager_instance
            _storage_manager_instance = None
            self.logger.info("Storage manager unregistered from event subscriptions")
            
            # Stop quality monitoring
            await self.quality_monitor.stop()
            
            # Disconnect from databases  
            await self.clickhouse_manager.disconnect()
            await self.redis_cache_manager.disconnect()
            
            # Shutdown thread pool
            self._processing_executor.shutdown(wait=True)
            
            self.logger.info("✅ Market data storage manager stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping storage manager: {e}")
    
    
    async def _handle_market_tick_event(self, event_data: Dict[str, Any]) -> None:
        """Enhanced market tick event handler with comprehensive correlation tracking.
        
        Args:
            event_data: Market tick event data
        """
        # Extract or generate correlation ID for tracking
        correlation_id = event_data.get('correlation_id', f"storage_{int(time.perf_counter_ns())}_{uuid.uuid4().hex[:8]}")
        processing_start_ns = time.perf_counter_ns()
        
        # Pre-processing logging
        self.logger.debug("Market tick event processing started", extra={
            'correlation_id': correlation_id,
            'event_type': 'storage_processing_start',
            'component': 'storage_manager',
            'event_size': len(str(event_data)),
            'buffer_size_before': len(self._tick_buffer)
        })
        
        try:
            # Extract tick data with validation
            tick_data = event_data.get('data', {})
            if not tick_data:
                self.logger.warning("Empty tick data received", extra={
                    'correlation_id': correlation_id,
                    'event_type': 'empty_tick_data',
                    'event_data_keys': list(event_data.keys())
                })
                return
            
            instrument_token = tick_data.get('instrument_token')
            if not instrument_token:
                self.logger.warning("Missing instrument token in tick data", extra={
                    'correlation_id': correlation_id,
                    'event_type': 'missing_instrument_token',
                    'tick_data_keys': list(tick_data.keys())
                })
                return
            
            # Cache latest tick data in Redis with correlation tracking
            cache_start_ns = time.perf_counter_ns()
            if instrument_token:
                try:
                    # Add correlation ID to cache metadata
                    cache_metadata = {
                        'correlation_id': correlation_id,
                        'cached_at': datetime.now(timezone.utc).isoformat(),
                        'processing_component': 'storage_manager'
                    }
                    tick_data_with_metadata = {**tick_data, '_cache_metadata': cache_metadata}
                    
                    asyncio.create_task(
                        self.redis_cache_manager.cache_tick_data(instrument_token, tick_data_with_metadata)
                    )
                    
                    cache_time_us = (time.perf_counter_ns() - cache_start_ns) / 1000
                    
                    self.logger.debug("Tick data cached successfully", extra={
                        'correlation_id': correlation_id,
                        'event_type': 'cache_operation_success',
                        'instrument_token': instrument_token,
                        'cache_time_us': cache_time_us
                    })
                    
                except Exception as cache_error:
                    cache_time_us = (time.perf_counter_ns() - cache_start_ns) / 1000
                    self.logger.error("Cache operation failed", extra={
                        'correlation_id': correlation_id,
                        'event_type': 'cache_operation_failed',
                        'error': str(cache_error),
                        'error_type': type(cache_error).__name__,
                        'cache_time_us': cache_time_us,
                        'instrument_token': instrument_token
                    })
            
            # Compress tick data with monitoring
            compression_start_ns = time.perf_counter_ns()
            processed_data = await self._process_and_compress_tick_data_comprehensive(tick_data, correlation_id)
            compression_time_us = (time.perf_counter_ns() - compression_start_ns) / 1000
            
            # Calculate sizes for metrics
            original_size = len(json.dumps(tick_data).encode('utf-8'))
            compressed_size = len(processed_data) if isinstance(processed_data, bytes) else len(json.dumps(processed_data).encode('utf-8'))
            compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
            
            # Add to buffer with thread safety and enhanced metadata
            buffer_start_ns = time.perf_counter_ns()
            with self._tick_buffer_lock:
                self._tick_buffer.append({
                    'correlation_id': correlation_id,
                    'timestamp': event_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                    'data': processed_data,
                    'received_at': datetime.now(timezone.utc),
                    'original_size': original_size,
                    'compressed_size': compressed_size,
                    'compression_ratio': compression_ratio,
                    'instrument_token': instrument_token,
                    'processing_time_us': compression_time_us
                })
                buffer_size = len(self._tick_buffer)
            buffer_time_us = (time.perf_counter_ns() - buffer_start_ns) / 1000
            
            # Update metrics with enhanced tracking
            self.metrics.ticks_received += 1
            self.metrics.buffer_size = buffer_size
            self.metrics.uncompressed_bytes += original_size
            self.metrics.compressed_bytes += compressed_size
            
            # Track for rate calculation
            self._rate_tracker.append(datetime.now(timezone.utc))
            
            # Calculate total processing time
            total_processing_time_ns = time.perf_counter_ns() - processing_start_ns
            total_processing_time_us = total_processing_time_ns / 1000
            
            # Log successful processing
            self.logger.info("Market tick processed successfully", extra={
                'correlation_id': correlation_id,
                'event_type': 'storage_processing_success',
                'instrument_token': instrument_token,
                'total_processing_time_us': total_processing_time_us,
                'compression_time_us': compression_time_us,
                'buffer_time_us': buffer_time_us,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'compression_ratio': compression_ratio,
                'buffer_size_after': buffer_size,
                'tick_price': tick_data.get('last_price', 'unknown'),
                'tick_volume': tick_data.get('last_traded_quantity', 'unknown')
            })
            
            # Performance threshold alerts
            if total_processing_time_us > 5000:  # Alert if processing takes more than 5ms
                self.logger.warning("Slow storage processing detected", extra={
                    'correlation_id': correlation_id,
                    'event_type': 'performance_warning',
                    'processing_time_us': total_processing_time_us,
                    'threshold_us': 5000,
                    'instrument_token': instrument_token
                })
            
            # Check if immediate flush is needed
            if buffer_size >= self.batch_size:
                flush_correlation_id = f"flush_{correlation_id}"
                asyncio.create_task(self._flush_tick_buffer_comprehensive(flush_correlation_id))
            
        except Exception as e:
            # Comprehensive error handling
            total_error_time_ns = time.perf_counter_ns() - processing_start_ns
            
            self.logger.error("Market tick processing failed", extra={
                'correlation_id': correlation_id,
                'event_type': 'storage_processing_error',
                'error': str(e),
                'error_type': type(e).__name__,
                'error_time_us': total_error_time_ns / 1000,
                'stack_trace': traceback.format_exc(),
                'event_data_preview': str(event_data)[:200] if event_data else 'None',
                'buffer_size': len(self._tick_buffer)
            })
            
            self.metrics.ticks_failed += 1
    
    async def _handle_signal_event(self, event_data: Dict[str, Any]) -> None:
        """Handle strategy signal event.
        
        Args:
            event_data: Strategy signal event data
        """
        try:
            # Add to signal buffer
            self._signal_buffer.append({
                'timestamp': event_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                'data': event_data,
                'received_at': datetime.now(timezone.utc)
            })
            
            # Flush if buffer is full
            if len(self._signal_buffer) >= 50:  # Smaller batch size for signals
                asyncio.create_task(self._flush_signal_buffer())
            
        except Exception as e:
            self.logger.error(f"Error handling signal event: {e}")
    
    async def _flush_loop(self) -> None:
        """Background task for periodic data flushing."""
        self.logger.info("Started storage flush loop")
        
        try:
            while self.is_running:
                current_time = datetime.now(timezone.utc)
                time_since_flush = (current_time - self._last_flush).total_seconds()
                
                # Flush if interval exceeded or buffer is getting full
                if (time_since_flush >= self.flush_interval or 
                    len(self._tick_buffer) >= self.batch_size * 0.8):
                    
                    await self._flush_all_buffers()
                
                # Sleep for a short interval
                await asyncio.sleep(0.1)
                
        except asyncio.CancelledError:
            self.logger.info("Storage flush loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in flush loop: {e}")
    
    async def _rate_monitoring_loop(self) -> None:
        """Monitor processing rate and update metrics."""
        try:
            while self.is_running:
                current_time = datetime.now(timezone.utc)
                
                # Clean old entries (older than 60 seconds)
                cutoff_time = current_time - timedelta(seconds=60)
                while self._rate_tracker and self._rate_tracker[0] < cutoff_time:
                    self._rate_tracker.popleft()
                
                # Calculate processing rate
                if self._rate_tracker:
                    self.metrics.processing_rate_per_sec = len(self._rate_tracker)
                
                await asyncio.sleep(5)  # Update every 5 seconds
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Error in rate monitoring loop: {e}")
    
    async def _process_and_compress_tick_data(self, tick_data: Dict[str, Any]) -> Any:
        """Process and optionally compress tick data."""
        if not self.compression_enabled:
            return tick_data
        
        try:
            # Serialize to JSON
            json_data = json.dumps(tick_data, separators=(',', ':')).encode('utf-8')
            original_size = len(json_data)
            
            # Compress based on method
            if self.compression_method == 'lz4':
                compressed_data = lz4.frame.compress(json_data)
            elif self.compression_method == 'gzip':
                compressed_data = gzip.compress(json_data)
            else:
                return tick_data  # No compression
            
            compressed_size = len(compressed_data)
            
            # Update compression metrics
            self.metrics.uncompressed_bytes += original_size
            self.metrics.compressed_bytes += compressed_size
            
            if self.metrics.uncompressed_bytes > 0:
                self.metrics.compression_ratio = self.metrics.compressed_bytes / self.metrics.uncompressed_bytes
            
            # Return compressed data with metadata
            return {
                'compressed': True,
                'method': self.compression_method,
                'data': compressed_data,
                'original_size': original_size,
                'compressed_size': compressed_size
            }
            
        except Exception as e:
            self.logger.error(f"Error compressing tick data: {e}")
            return tick_data
    
    async def _decompress_tick_data(self, compressed_item: Dict[str, Any]) -> Dict[str, Any]:
        """Decompress tick data."""
        if not isinstance(compressed_item, dict) or not compressed_item.get('compressed'):
            return compressed_item
        
        try:
            compressed_data = compressed_item['data']
            method = compressed_item['method']
            
            # Decompress based on method
            if method == 'lz4':
                decompressed_data = lz4.frame.decompress(compressed_data)
            elif method == 'gzip':
                decompressed_data = gzip.decompress(compressed_data)
            else:
                return compressed_item
            
            # Parse JSON
            return json.loads(decompressed_data.decode('utf-8'))
            
        except Exception as e:
            self.logger.error(f"Error decompressing tick data: {e}")
            return compressed_item
    
    async def _flush_all_buffers(self) -> None:
        """Flush all data buffers."""
        tasks = []
        
        if self._tick_buffer:
            tasks.append(self._flush_tick_buffer())
        
        if self._signal_buffer:
            tasks.append(self._flush_signal_buffer())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            self._last_flush = datetime.now(timezone.utc)
            self.metrics.last_flush_time = self._last_flush
    
    async def _flush_tick_buffer(self) -> None:
        """Flush market tick buffer to ClickHouse."""
        if not self._tick_buffer:
            return
        
        try:
            # Extract batch of ticks with thread safety
            batch_data = []
            with self._tick_buffer_lock:
                batch_size = min(len(self._tick_buffer), self.batch_size)
                for _ in range(batch_size):
                    if self._tick_buffer:
                        batch_data.append(self._tick_buffer.popleft())
            
            if not batch_data:
                return
            
            # Prepare tick data for insertion (decompress if needed)
            tick_records = []
            total_original_size = 0
            total_compressed_size = 0
            
            for item in batch_data:
                # Decompress if compressed
                if isinstance(item['data'], dict) and item['data'].get('compressed'):
                    decompressed_data = await self._decompress_tick_data(item['data'])
                    tick_records.append(decompressed_data)
                else:
                    tick_records.append(item['data'])
                
                # Track compression metrics
                total_original_size += item.get('original_size', 0)
                total_compressed_size += item.get('compressed_size', 0)
            
            # Measure storage latency
            start_time = datetime.now(timezone.utc)
            
            # Insert into ClickHouse
            success = await self.clickhouse_manager.insert_market_ticks(tick_records)
            
            # Update performance metrics
            end_time = datetime.now(timezone.utc)
            latency_ms = (end_time - start_time).total_seconds() * 1000
            
            if success:
                self.metrics.ticks_stored += len(tick_records)
                self.metrics.batches_processed += 1
                self._update_performance_metrics(len(tick_records), latency_ms)
                
                self.logger.debug(f"Stored batch of {len(tick_records)} ticks in {latency_ms:.2f}ms")
            else:
                self.metrics.ticks_failed += len(tick_records)
                self.logger.error(f"Failed to store batch of {len(tick_records)} ticks")
            
            self.metrics.buffer_size = len(self._tick_buffer)
            
        except Exception as e:
            self.logger.error(f"Error flushing tick buffer: {e}")
            self.metrics.ticks_failed += batch_size
    
    async def _flush_signal_buffer(self) -> None:
        """Flush strategy signal buffer to ClickHouse."""
        if not self._signal_buffer:
            return
        
        try:
            # Extract all signals
            signals_to_flush = list(self._signal_buffer)
            self._signal_buffer.clear()
            
            # Insert signals one by one (smaller volume)
            success_count = 0
            for signal_item in signals_to_flush:
                signal_data = signal_item['data']
                success = await self.clickhouse_manager.insert_strategy_signal(signal_data)
                if success:
                    success_count += 1
            
            self.logger.debug(f"Stored {success_count}/{len(signals_to_flush)} strategy signals")
            
        except Exception as e:
            self.logger.error(f"Error flushing signal buffer: {e}")
    
    def _update_performance_metrics(self, batch_size: int, latency_ms: float) -> None:
        """Update rolling performance metrics.
        
        Args:
            batch_size: Size of the processed batch
            latency_ms: Processing latency in milliseconds
        """
        self._performance_window.append({
            'batch_size': batch_size,
            'latency_ms': latency_ms,
            'timestamp': datetime.now(timezone.utc)
        })
        
        # Calculate rolling averages
        if self._performance_window:
            recent_batches = list(self._performance_window)
            
            self.metrics.avg_batch_size = sum(p['batch_size'] for p in recent_batches) / len(recent_batches)
            self.metrics.avg_storage_latency_ms = sum(p['latency_ms'] for p in recent_batches) / len(recent_batches)
    
    async def _process_and_compress_tick_data_comprehensive(self, tick_data: Dict[str, Any], correlation_id: str) -> Any:
        """Process and compress tick data with comprehensive monitoring.
        
        Args:
            tick_data: Raw tick data
            correlation_id: Correlation ID for tracking
            
        Returns:
            Processed and optionally compressed data
        """
        try:
            if not self.compression_enabled:
                return tick_data
            
            # Convert to JSON string
            json_data = json.dumps(tick_data, separators=(',', ':'), ensure_ascii=False)
            json_bytes = json_data.encode('utf-8')
            
            # Apply compression
            if self.compression_method == 'lz4':
                compressed_data = lz4.frame.compress(json_bytes)
            elif self.compression_method == 'gzip':
                compressed_data = gzip.compress(json_bytes)
            else:
                compressed_data = json_bytes
            
            # Calculate compression ratio
            original_size = len(json_bytes)
            compressed_size = len(compressed_data)
            compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
            
            self.logger.debug("Data compression completed", extra={
                'correlation_id': correlation_id,
                'event_type': 'compression_completed',
                'compression_method': self.compression_method,
                'original_size': original_size,
                'compressed_size': compressed_size,
                'compression_ratio': compression_ratio
            })
            
            return compressed_data
            
        except Exception as e:
            self.logger.error("Data compression failed", extra={
                'correlation_id': correlation_id,
                'event_type': 'compression_failed',
                'error': str(e),
                'error_type': type(e).__name__,
                'compression_method': self.compression_method
            })
            # Return uncompressed data on compression failure
            return tick_data
    
    async def _flush_tick_buffer_comprehensive(self, correlation_id: str) -> None:
        """Flush tick buffer with comprehensive correlation tracking.
        
        Args:
            correlation_id: Correlation ID for tracking this flush operation
        """
        flush_start_ns = time.perf_counter_ns()
        
        self.logger.debug("Buffer flush started", extra={
            'correlation_id': correlation_id,
            'event_type': 'buffer_flush_start',
            'buffer_size': len(self._tick_buffer),
            'flush_type': 'tick_buffer'
        })
        
        try:
            # Extract data from buffer with thread safety
            with self._tick_buffer_lock:
                if not self._tick_buffer:
                    return
                
                ticks_to_flush = list(self._tick_buffer)
                self._tick_buffer.clear()
                buffer_size = len(ticks_to_flush)
            
            if not ticks_to_flush:
                return
            
            # Store to ClickHouse with tracking
            clickhouse_start_ns = time.perf_counter_ns()
            success_count = await self.clickhouse_manager.store_market_data_batch(
                [tick['data'] for tick in ticks_to_flush]
            )
            clickhouse_time_us = (time.perf_counter_ns() - clickhouse_start_ns) / 1000
            
            # Calculate flush metrics
            total_flush_time_ns = time.perf_counter_ns() - flush_start_ns
            total_flush_time_us = total_flush_time_ns / 1000
            
            # Update metrics
            self.metrics.ticks_stored += success_count
            self.metrics.batches_processed += 1
            self.metrics.last_flush_time = datetime.now(timezone.utc)
            self._last_flush = datetime.now(timezone.utc)
            
            # Calculate compression statistics
            total_original_size = sum(tick.get('original_size', 0) for tick in ticks_to_flush)
            total_compressed_size = sum(tick.get('compressed_size', 0) for tick in ticks_to_flush)
            overall_compression_ratio = (1 - total_compressed_size / total_original_size) * 100 if total_original_size > 0 else 0
            
            # Update performance metrics
            self._update_performance_metrics(buffer_size, total_flush_time_us / 1000)  # Convert to ms
            
            # Log successful flush
            self.logger.info("Buffer flush completed successfully", extra={
                'correlation_id': correlation_id,
                'event_type': 'buffer_flush_success',
                'ticks_flushed': buffer_size,
                'ticks_stored': success_count,
                'total_flush_time_us': total_flush_time_us,
                'clickhouse_time_us': clickhouse_time_us,
                'total_original_size': total_original_size,
                'total_compressed_size': total_compressed_size,
                'compression_ratio': overall_compression_ratio,
                'success_rate': (success_count / buffer_size * 100) if buffer_size > 0 else 0
            })
            
            # Performance threshold alerts
            if total_flush_time_us > 10000:  # Alert if flush takes more than 10ms
                self.logger.warning("Slow buffer flush detected", extra={
                    'correlation_id': correlation_id,
                    'event_type': 'flush_performance_warning',
                    'flush_time_us': total_flush_time_us,
                    'threshold_us': 10000,
                    'buffer_size': buffer_size
                })
            
        except Exception as e:
            # Comprehensive error handling
            total_error_time_ns = time.perf_counter_ns() - flush_start_ns
            
            self.logger.error("Buffer flush failed", extra={
                'correlation_id': correlation_id,
                'event_type': 'buffer_flush_error',
                'error': str(e),
                'error_type': type(e).__name__,
                'error_time_us': total_error_time_ns / 1000,
                'stack_trace': traceback.format_exc(),
                'buffer_size': len(self._tick_buffer)
            })

    async def store_tick_data(self, tick_data: Dict[str, Any]) -> bool:
        """Directly store tick data (bypasses event system).
        
        Args:
            tick_data: Market tick data dictionary
            
        Returns:
            True if storage initiated successfully
        """
        try:
            # Add to buffer for batched processing
            self._tick_buffer.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'data': tick_data,
                'received_at': datetime.now(timezone.utc)
            })
            
            self.metrics.ticks_received += 1
            self.metrics.buffer_size = len(self._tick_buffer)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing tick data: {e}")
            return False
    
    async def query_recent_ticks(
        self, 
        instrument_tokens: List[int],
        minutes: int = 5,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Query recent market tick data (cache first, then database).
        
        Args:
            instrument_tokens: List of instrument tokens
            minutes: Number of minutes to look back
            limit: Maximum number of records
            
        Returns:
            List of recent tick records
        """
        try:
            # For recent data (< 5 minutes), try cache first
            if minutes <= 5:
                cached_data = await self.redis_cache_manager.get_multiple_ticks(instrument_tokens)
                if cached_data:
                    # Convert to list format
                    tick_list = []
                    for token, tick_data in cached_data.items():
                        tick_data['instrument_token'] = token
                        tick_list.append(tick_data)
                    return tick_list[:limit]
            
            # Fallback to database
            start_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            return await self.clickhouse_manager.query_market_data(
                instrument_tokens, start_time, limit=limit
            )
            
        except Exception as e:
            self.logger.error(f"Error querying recent ticks: {e}")
            # Fallback to database only
            start_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            return await self.clickhouse_manager.query_market_data(
                instrument_tokens, start_time, limit=limit
            )
    
    async def get_ohlc_data(
        self,
        instrument_tokens: List[int],
        timeframe: str = '1m',
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get OHLC data for instruments.
        
        Args:
            instrument_tokens: List of instrument tokens
            timeframe: OHLC timeframe (1m, 5m, 1h, 1d)
            limit: Maximum records per instrument
            
        Returns:
            List of OHLC records
        """
        return await self.clickhouse_manager.get_latest_ohlc(
            instrument_tokens, timeframe, limit
        )
    
    def get_storage_metrics(self) -> Dict[str, Any]:
        """Get storage performance metrics.
        
        Returns:
            Storage metrics dictionary
        """
        return {
            'ticks_received': self.metrics.ticks_received,
            'ticks_stored': self.metrics.ticks_stored,
            'ticks_failed': self.metrics.ticks_failed,
            'success_rate': (
                self.metrics.ticks_stored / max(self.metrics.ticks_received, 1) * 100
            ),
            'batches_processed': self.metrics.batches_processed,
            'avg_batch_size': round(self.metrics.avg_batch_size, 2),
            'avg_storage_latency_ms': round(self.metrics.avg_storage_latency_ms, 2),
            'current_buffer_size': self.metrics.buffer_size,
            'max_buffer_size': self.buffer_size,
            'buffer_utilization': (self.metrics.buffer_size / self.buffer_size * 100),
            'last_flush_time': self.metrics.last_flush_time.isoformat() if self.metrics.last_flush_time else None,
            'is_running': self.is_running,
        }
    
    async def get_database_health(self) -> Dict[str, Any]:
        """Get comprehensive database and cache health information with aggregation.
        
        Returns:
            Aggregated database health dictionary with detailed component status
        """
        correlation_id = f"health_check_{uuid.uuid4().hex[:8]}"
        health_check_start_ns = time.perf_counter_ns()
        
        self.logger.debug("Database health check started", extra={
            'correlation_id': correlation_id,
            'event_type': 'health_check_start',
            'component': 'storage_manager'
        })
        
        try:
            # Get health from all components in parallel for performance
            tasks = [
                self.clickhouse_manager.health_check(),
                self.clickhouse_manager.get_database_stats(),
                self.redis_cache_manager.health_check(),
                self.redis_cache_manager.get_cache_info(),
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            clickhouse_health, clickhouse_stats, redis_health, redis_info = results
            
            # Get quality report (synchronous)
            try:
                quality_report = self.quality_monitor.get_quality_report()
            except Exception as e:
                quality_report = {'error': str(e)}
            
            # Get storage metrics
            storage_metrics = self.get_storage_metrics()
            
            # Determine component health status
            components = {
                'clickhouse': {
                    'healthy': isinstance(clickhouse_health, dict) and clickhouse_health.get('status') == 'healthy',
                    'health': clickhouse_health if not isinstance(clickhouse_health, Exception) else {'error': str(clickhouse_health)},
                    'stats': clickhouse_stats if not isinstance(clickhouse_stats, Exception) else {'error': str(clickhouse_stats)},
                    'critical': True  # ClickHouse is critical for data storage
                },
                'redis_cache': {
                    'healthy': isinstance(redis_health, dict) and redis_health.get('status') == 'healthy',
                    'health': redis_health if not isinstance(redis_health, Exception) else {'error': str(redis_health)},
                    'info': redis_info if not isinstance(redis_info, Exception) else {'error': str(redis_info)},
                    'critical': False  # Redis is optional for caching
                },
                'data_quality': {
                    'healthy': 'error' not in quality_report,
                    'report': quality_report,
                    'critical': False  # Quality monitoring is optional
                },
                'storage_pipeline': {
                    'healthy': self.is_running and storage_metrics['success_rate'] > 90,
                    'metrics': storage_metrics,
                    'critical': True  # Storage pipeline is critical
                }
            }
            
            # Calculate overall health
            critical_components = [name for name, comp in components.items() if comp['critical']]
            critical_healthy = [comp['healthy'] for name, comp in components.items() if comp['critical']]
            all_healthy = [comp['healthy'] for comp in components.values()]
            
            # Overall status logic
            if all(critical_healthy):
                if all(all_healthy):
                    overall_status = 'healthy'
                    status_message = 'All storage components are healthy'
                else:
                    overall_status = 'degraded'
                    status_message = 'Critical components healthy, some optional components degraded'
            else:
                overall_status = 'unhealthy'
                status_message = 'One or more critical storage components are unhealthy'
            
            # Performance metrics
            health_check_time_ms = (time.perf_counter_ns() - health_check_start_ns) / 1_000_000
            
            result = {
                'overall_status': overall_status,
                'status_message': status_message,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'health_check_duration_ms': health_check_time_ms,
                'summary': {
                    'total_components': len(components),
                    'healthy_components': sum(1 for comp in components.values() if comp['healthy']),
                    'critical_components': len(critical_components),
                    'critical_healthy': sum(critical_healthy),
                    'health_percentage': (sum(1 for comp in components.values() if comp['healthy']) / len(components) * 100)
                },
                'components': components,
                'correlation_id': correlation_id
            }
            
            self.logger.info("Database health check completed", extra={
                'correlation_id': correlation_id,
                'event_type': 'health_check_complete',
                'overall_status': overall_status,
                'health_check_duration_ms': health_check_time_ms,
                'healthy_components': result['summary']['healthy_components'],
                'total_components': result['summary']['total_components']
            })
            
            return result
            
        except Exception as e:
            health_check_time_ms = (time.perf_counter_ns() - health_check_start_ns) / 1_000_000
            
            self.logger.error("Database health check failed", extra={
                'correlation_id': correlation_id,
                'event_type': 'health_check_error',
                'error': str(e),
                'error_type': type(e).__name__,
                'health_check_duration_ms': health_check_time_ms
            })
            
            return {
                'overall_status': 'error',
                'status_message': f'Health check failed: {e}',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'health_check_duration_ms': health_check_time_ms,
                'error': str(e),
                'correlation_id': correlation_id
            }
    
    async def force_flush(self) -> Dict[str, Any]:
        """Force flush all buffers immediately.
        
        Returns:
            Flush operation results
        """
        try:
            start_time = datetime.now(timezone.utc)
            
            tick_count = len(self._tick_buffer)
            signal_count = len(self._signal_buffer)
            
            await self._flush_all_buffers()
            
            end_time = datetime.now(timezone.utc)
            duration_ms = (end_time - start_time).total_seconds() * 1000
            
            return {
                'success': True,
                'ticks_flushed': tick_count,
                'signals_flushed': signal_count,
                'duration_ms': round(duration_ms, 2),
                'timestamp': end_time.isoformat(),
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }