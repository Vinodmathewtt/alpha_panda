# Direct Streaming Clients - Simple aiokafka Wrappers
# 
# ARCHITECTURE NOTE: This module provides direct, lightweight wrappers for basic 
# streaming needs. These are NOT legacy components - they serve a different purpose
# from the enhanced infrastructure components.
#
# USE CASES:
# - Simple message publishing without additional layers
# - Direct Kafka operations with minimal overhead  
# - DI container usage for basic producer needs
# - When you need direct control over Kafka operations
#
# For enhanced features (automatic EventEnvelope wrapping, reliability layers),
# use the infrastructure components via StreamServiceBuilder pattern.
#
# Both approaches are valid and actively maintained for different use cases.

import json
import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timezone
from decimal import Decimal
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient
from aiokafka.errors import KafkaError, KafkaConnectionError
from aiokafka.structs import TopicPartition
from core.schemas.events import EventEnvelope, EventType, generate_uuid7
from core.config.settings import RedpandaSettings
from core.streaming.deduplication import EventDeduplicator
from core.streaming.error_handling import ErrorHandler, DLQPublisher, ErrorClassifier
from core.streaming.correlation import CorrelationContext, CorrelationLogger, trace_metrics
from core.streaming.lifecycle_manager import get_lifecycle_manager, GracefulShutdownMixin
import redis.asyncio as redis
import logging

logger = logging.getLogger(__name__)


def json_serializer(obj):
    """Custom JSON serializer for datetime and Decimal objects"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')


class RedpandaProducer:
    """MANDATORY async producer with idempotence and message keys"""
    
    def __init__(self, config: RedpandaSettings):
        self.config = config
        # MANDATORY: Idempotent producer settings with enhanced reliability
        self._producer = AIOKafkaProducer(
            bootstrap_servers=config.bootstrap_servers,
            client_id=f"{config.client_id}-producer",
            enable_idempotence=True,  # MANDATORY
            acks='all',  # MANDATORY
            request_timeout_ms=30000,  # 30 seconds
            linger_ms=5,
            compression_type='gzip',
            retry_backoff_ms=100,  # Retry backoff (built-in retry mechanism)
            value_serializer=lambda x: json.dumps(x, default=json_serializer).encode('utf-8')
        )
        self._started = False
    
    async def start(self):
        """Start the producer"""
        if not self._started:
            await self._producer.start()
            self._started = True
    
    async def stop(self):
        """Stop the producer with flush"""
        if self._started:
            # MANDATORY: Graceful shutdown with flush
            await self._producer.flush()
            await self._producer.stop()
            self._started = False
    
    async def send(self, topic: str, key: str, value: Dict[str, Any]) -> None:
        """
        Send message with MANDATORY key for ordering
        
        Args:
            topic: Topic name
            key: MANDATORY partition key for ordering
            value: Message payload (will be wrapped in EventEnvelope if not already)
        """
        if not self._started:
            await self.start()
        
        # Ensure message follows EventEnvelope standard
        if 'type' not in value:
            raise ValueError("Message must contain 'type' field or be EventEnvelope")
        
        try:
            await self._producer.send_and_wait(
                topic=topic,
                key=key.encode('utf-8'),  # MANDATORY key
                value=value
            )
        except KafkaError as e:
            # TODO: Add to DLQ in Phase 4
            raise Exception(f"Failed to send message to {topic}: {e}")


class RedpandaConsumer:
    """MANDATORY async consumer with unique group IDs"""
    
    def __init__(self, config: RedpandaSettings, topics: List[str], group_id: str):
        self.config = config
        self.topics = topics
        # MANDATORY: Unique consumer group per service with stability tuning
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=config.bootstrap_servers,
            client_id=f"{config.client_id}-consumer",
            group_id=group_id,  # MANDATORY: Unique per service
            auto_offset_reset='earliest',
            enable_auto_commit=False,  # CRITICAL: Manual commits only
            session_timeout_ms=30000,  # 30 seconds for stability
            heartbeat_interval_ms=10000,  # 10 seconds
            max_poll_records=50,  # Control backpressure
            max_partition_fetch_bytes=1048576,  # 1MB per partition
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        self._started = False
    
    async def start(self):
        """Start the consumer"""
        if not self._started:
            await self._consumer.start()
            self._started = True
    
    async def stop(self):
        """Stop the consumer"""
        if self._started:
            await self._consumer.stop()
            self._started = False
    
    async def commit_offset(self, message=None):
        """Manually commit offset after successful processing"""
        try:
            await self._consumer.commit()
        except Exception as e:
            logger.error(f"Failed to commit offset: {e}")
            raise
    
    async def consume(self, handler: Callable[[str, str, Dict[str, Any], Any], None]) -> None:
        """
        Consume messages and call handler for each
        
        Args:
            handler: Function that takes (topic, key, value, message)
        """
        if not self._started:
            await self.start()
        
        try:
            async for message in self._consumer:
                topic = message.topic
                key = message.key.decode('utf-8') if message.key else None
                value = message.value
                
                # Validate EventEnvelope format
                if not isinstance(value, dict) or 'type' not in value:
                    logger.warning(f"Invalid message format from {topic}: missing 'type' field")
                    # Skip invalid messages and commit to avoid reprocessing
                    await self.commit_offset()
                    continue
                
                try:
                    # Pass the full message for error handling context
                    await handler(topic, key, value, message)
                except Exception as e:
                    # Error handling will be done in StreamProcessor
                    logger.error(f"Handler error for {topic}: {e}")
                    raise
        
        except Exception as e:
            logger.error(f"Consumer error: {e}")
            raise


class StreamProcessor(GracefulShutdownMixin):
    """Base class for stream processing services with deduplication and error handling"""
    
    def __init__(self, name: str, config: RedpandaSettings, 
                 consume_topics: List[str], group_id: str, redis_client=None, settings=None):
        super().__init__()  # Initialize GracefulShutdownMixin
        self.name = name
        self.consume_topics = consume_topics
        self.producer = RedpandaProducer(config)
        self.consumer = RedpandaConsumer(config, consume_topics, group_id)
        self._running = False
        
        # Store settings for multi-broker architecture
        self.settings = settings
        self.active_brokers = getattr(settings, 'active_brokers', ['paper']) if settings else ['paper']
        # Default broker namespace for metrics (can be overridden per operation)
        self.default_broker_namespace = self.active_brokers[0] if self.active_brokers else 'paper'
        
        # Phase 2: Add deduplication and error handling
        if redis_client:
            self.deduplicator = EventDeduplicator(redis_client, ttl_seconds=3600)
        else:
            self.deduplicator = None
            
        # Initialize error handling components
        self.dlq_publisher = DLQPublisher(self.producer, name)
        self.error_handler = ErrorHandler(name, self.dlq_publisher)
        self.error_classifier = ErrorClassifier()
        
        # Enhanced metrics collection
        self._metrics = {
            "messages_processed": 0,
            "messages_published": 0,
            "processing_times": [],
            "error_count": 0,
            "start_time": datetime.now(timezone.utc),
            "last_message_time": None,
            "partition_stats": {},
            "topic_stats": {}
        }
        self._redis_client = redis_client
        
        # Metrics collector integration
        self._last_metrics_push = datetime.now(timezone.utc)
        self._metrics_push_interval = 60  # Push metrics every 60 seconds
        
        # Consumer lag monitoring
        self._admin_client: Optional[AIOKafkaAdminClient] = None
        self._partition_lag_cache = {}
        self._lag_update_interval = 30  # seconds
        self._last_lag_update = 0
        self._config = config
        
        # CRITICAL FIX: Add exponential backoff for consume loop failures
        self._consume_failure_count = 0
        self._max_consume_failures = 10  # Max consecutive failures before giving up
        self._base_backoff_delay = 1.0  # Base delay in seconds
        self._max_backoff_delay = 60.0  # Max delay in seconds
        self._backoff_multiplier = 2.0
    
    async def _initialize_admin_client(self) -> bool:
        """Initialize Kafka admin client for lag monitoring"""
        try:
            self._admin_client = AIOKafkaAdminClient(
                bootstrap_servers=self._config.bootstrap_servers,
                client_id=f"admin_{self.name}",
                security_protocol=getattr(self._config, 'security_protocol', 'PLAINTEXT')
            )
            await self._admin_client.start()
            logger.info(f"Admin client initialized for {self.name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize admin client for lag monitoring: {e}")
            return False

    async def start(self):
        """Start the stream processor"""
        await self.producer.start()
        
        # Only start consumer if there are topics to consume
        if self.consume_topics:
            await self.consumer.start()
            self._running = True
            # Start consumption loop with error handling
            self._consume_task = asyncio.create_task(self._consume_loop())
        else:
            self._running = True
        
        # Initialize admin client for lag monitoring (non-blocking)
        await self._initialize_admin_client()
        
        # Register with lifecycle manager for proper cleanup
        await self.register_for_lifecycle_management(self.name)
    
    async def stop(self):
        """MANDATORY: Stop with producer flush and graceful task completion"""
        self._running = False
        
        # Gracefully stop consumer first to prevent new messages
        if self.consume_topics:
            await self.consumer.stop()
        
        # Wait for current message processing to complete (with timeout)
        if hasattr(self, '_consume_task') and not self._consume_task.done():
            try:
                # Give current message processing time to complete
                await asyncio.wait_for(self._consume_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"{self.name}: Consume task did not complete within 5s, cancelling")
                self._consume_task.cancel()
                try:
                    await self._consume_task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
        
        # MANDATORY: Flush before stopping producer
        await self.producer.stop()
    
    async def _consume_loop(self):
        """Main consumption loop with exponential backoff on failures"""
        while self._running:
            try:
                await self.consumer.consume(self._handle_message_with_error_handling)
                # Reset failure count on successful operation
                self._consume_failure_count = 0
                
            except asyncio.CancelledError:
                logger.info(f"{self.name} consume loop cancelled")
                raise
                
            except Exception as e:
                self._consume_failure_count += 1
                logger.error(
                    f"{self.name} consume loop error (failure {self._consume_failure_count}): {e}"
                )
                
                # CRITICAL FIX: Implement exponential backoff to prevent tight failure loops
                if self._consume_failure_count >= self._max_consume_failures:
                    logger.critical(
                        f"{self.name} exceeded max consume failures ({self._max_consume_failures}), "
                        "stopping service to prevent resource exhaustion"
                    )
                    self._running = False
                    raise RuntimeError(f"Service {self.name} failed too many times") from e
                
                # Calculate exponential backoff delay
                delay = min(
                    self._base_backoff_delay * (self._backoff_multiplier ** (self._consume_failure_count - 1)),
                    self._max_backoff_delay
                )
                
                logger.warning(
                    f"{self.name} backing off for {delay:.2f}s before retry "
                    f"(failure {self._consume_failure_count}/{self._max_consume_failures})"
                )
                
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    logger.info(f"{self.name} consume loop cancelled during backoff")
                    raise
                
                # Continue the loop to retry
    
    async def _handle_message_with_error_handling(self, topic: str, key: str, message: Dict[str, Any], raw_message):
        """
        Handle message with deduplication, error handling, correlation tracking, and manual commits.
        This method wraps the actual message processing with reliability features.
        """
        
        # Start timing for metrics
        process_start = datetime.now(timezone.utc)
        
        # Set up correlation context from incoming message
        correlation_id = message.get('correlation_id')
        event_id = message.get('id')
        
        if correlation_id:
            CorrelationContext.continue_trace(
                correlation_id, event_id, self.name, f"process_{topic}"
            )
        else:
            # Generate new correlation ID if missing
            correlation_id = CorrelationContext.start_new_trace(
                self.name, f"process_{topic}"
            )
        
        # Create correlation-aware logger
        correlation_logger = CorrelationLogger(self.name)
        
        # Check for deduplication
        if self.deduplicator:
            if event_id and await self.deduplicator.is_duplicate(event_id):
                correlation_logger.debug(f"Skipping duplicate event: {event_id}")
                await self.consumer.commit_offset()
                return
        
        # Define processing function for error handler
        async def process_message():
            # CRITICAL FIX: Normalize event type from string to enum
            if isinstance(message.get("type"), str):
                try:
                    message["type"] = EventType(message["type"])
                except ValueError:
                    correlation_logger.warning(f"Unknown event type: {message.get('type')}")
                    # Keep original string value for debugging
            
            await self._handle_message(topic, key, message)
        
        # Define commit function
        async def commit_message():
            await self.consumer.commit_offset()
        
        try:
            # Start trace measurement
            trace_metrics.add_span(correlation_id, self.name, f"process_{topic}")
            
            # Process message
            correlation_logger.debug(f"Processing message from {topic}")
            await process_message()
            
            # Update metrics on successful processing
            await self._update_processing_metrics(topic, raw_message, process_start, success=True)
            
            # Mark as processed if deduplication is enabled
            if self.deduplicator and event_id:
                await self.deduplicator.mark_processed(event_id, {
                    "service": self.name,
                    "topic": topic,
                    "correlation_id": correlation_id,
                    "processed_at": datetime.now(timezone.utc).isoformat()
                })
            
            # CRITICAL: Only commit after successful processing
            await commit_message()
            
            correlation_logger.debug(f"Successfully processed message from {topic}")
            
        except Exception as e:
            correlation_logger.error(f"Failed to process message from {topic}", error=str(e))
            
            # Update error metrics
            await self._update_processing_metrics(topic, raw_message, process_start, success=False, error=e)
            
            # Use error handler with retry logic and DLQ
            handled = await self.error_handler.handle_processing_error(
                raw_message, e, process_message, commit_message
            )
            
            if not handled:
                # Error handler indicates message should be reprocessed
                # Do NOT commit - message will be retried
                correlation_logger.info("Message will be reprocessed after error handling")
    
    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Override this method in subclasses for actual message processing"""
        raise NotImplementedError
    
    async def _update_processing_metrics(self, topic: str, raw_message, start_time: datetime, success: bool, error: Exception = None):
        """Update processing metrics for monitoring"""
        end_time = datetime.now(timezone.utc)
        processing_time = (end_time - start_time).total_seconds()
        
        # Update local metrics
        self._metrics["messages_processed"] += 1
        self._metrics["last_message_time"] = end_time.isoformat()
        self._metrics["processing_times"].append(processing_time)
        
        # Keep only last 100 processing times for memory efficiency
        if len(self._metrics["processing_times"]) > 100:
            self._metrics["processing_times"] = self._metrics["processing_times"][-100:]
        
        # Update topic stats
        if topic not in self._metrics["topic_stats"]:
            self._metrics["topic_stats"][topic] = {
                "messages": 0,
                "errors": 0,
                "avg_processing_time": 0.0,
                "last_processed": None
            }
        
        self._metrics["topic_stats"][topic]["messages"] += 1
        self._metrics["topic_stats"][topic]["last_processed"] = end_time.isoformat()
        
        # Update partition stats if available
        if hasattr(raw_message, 'partition'):
            partition = raw_message.partition
            partition_key = f"{topic}:{partition}"
            if partition_key not in self._metrics["partition_stats"]:
                self._metrics["partition_stats"][partition_key] = {
                    "messages": 0,
                    "errors": 0,
                    "last_processed": None
                }
            self._metrics["partition_stats"][partition_key]["messages"] += 1
            self._metrics["partition_stats"][partition_key]["last_processed"] = end_time.isoformat()
        
        if not success:
            self._metrics["error_count"] += 1
            self._metrics["topic_stats"][topic]["errors"] += 1
            if hasattr(raw_message, 'partition'):
                self._metrics["partition_stats"][partition_key]["errors"] += 1
        
        # Update average processing time for topic
        topic_stats = self._metrics["topic_stats"][topic]
        current_avg = topic_stats["avg_processing_time"]
        message_count = topic_stats["messages"]
        topic_stats["avg_processing_time"] = (current_avg * (message_count - 1) + processing_time) / message_count
        
        # Persist key metrics to Redis for health checks
        if self._redis_client:
            try:
                # Update Redis metrics for health checks
                await self._persist_metrics_to_redis(topic, processing_time, success)
                
                # Push full metrics to collector if interval has passed
                await self._maybe_push_metrics_to_collector()
            except Exception as e:
                logger.warning(f"Failed to persist metrics to Redis: {e}")
    
    async def _persist_metrics_to_redis(self, topic: str, processing_time: float, success: bool):
        """Persist key metrics to Redis for health check monitoring"""
        if not self._redis_client:
            return
        
        current_time = datetime.now(timezone.utc).isoformat()
        
        # For market ticks (shared topic) - FIXED: Use pipeline metrics format consistent with PipelineMetricsCollector
        if topic == "market.ticks":
            # Store simplified timestamp for compatibility with health checker
            market_data = {
                "timestamp": current_time,
                "topic": topic,
                "processed_by": "streaming_client"
            }
            import json
            await self._redis_client.setex("pipeline:market_ticks:market:last", 300, json.dumps(market_data))
            
            # Increment tick count (compatible with pipeline metrics)
            tick_count_key = "pipeline:market_ticks:market:count"
            await self._redis_client.incr(tick_count_key)
            await self._redis_client.expire(tick_count_key, 3600)  # 1 hour expiry for total count
            
        # For broker-specific topics, extract broker from topic name
        elif "signals" in topic:
            # Extract broker from topic (e.g., "paper.signals.raw" -> "paper")
            broker = topic.split('.')[0] if '.' in topic else self.default_broker_namespace
            # FIXED: Use pipeline: prefix to match PipelineMetricsCollector
            broker_key = f"pipeline:signals:{broker}:last"
            # Store as JSON to match PipelineMetricsCollector format
            signal_data = {"timestamp": current_time, "topic": topic}
            await self._redis_client.setex(broker_key, 600, json.dumps(signal_data))
            
            # Signal count - FIXED: Use pipeline: prefix
            signal_count_key = f"pipeline:signals:{broker}:count"
            await self._redis_client.incr(signal_count_key)
            await self._redis_client.expire(signal_count_key, 300)
            
        elif "orders" in topic:
            # Extract broker from topic (e.g., "zerodha.orders.filled" -> "zerodha")
            broker = topic.split('.')[0] if '.' in topic else self.default_broker_namespace
            # FIXED: Use pipeline: prefix to match PipelineMetricsCollector
            order_key = f"pipeline:orders:{broker}:last"
            # Store as JSON to match PipelineMetricsCollector format
            order_data = {"timestamp": current_time, "topic": topic, "success": success}
            await self._redis_client.setex(order_key, 3600, json.dumps(order_data))
            
            # Order counts - FIXED: Use pipeline: prefix
            if success:
                if "filled" in topic:
                    filled_key = f"pipeline:orders:{broker}:count"
                    await self._redis_client.incr(filled_key)
                    await self._redis_client.expire(filled_key, 3600)
            else:
                # For failed orders, we could use a separate key or track in the main count
                failed_key = f"pipeline:orders:{broker}:count"  # Same key for simplicity
                await self._redis_client.incr(failed_key)
                await self._redis_client.expire(failed_key, 3600)
    
    async def _maybe_push_metrics_to_collector(self):
        """Push metrics to collector if interval has passed"""
        current_time = datetime.now(timezone.utc)
        time_since_last_push = (current_time - self._last_metrics_push).total_seconds()
        
        if time_since_last_push >= self._metrics_push_interval:
            try:
                # Get current processing stats
                stats = self.get_processing_stats()
                
                # Cache in Redis for metrics collector
                from core.monitoring.metrics_collector import get_metrics_collector
                collector = get_metrics_collector(self._redis_client)
                await collector.cache_service_metrics(self.name, stats)
                
                self._last_metrics_push = current_time
            except Exception as e:
                logger.warning(f"Failed to push metrics to collector: {e}")
    
    async def _emit_event(self, topic: str, event_type: EventType, 
                         key: str, data: Dict[str, Any], 
                         correlation_id: str = None, causation_id: str = None,
                         broker: str = None):
        """Emit event with standardized envelope and correlation tracking"""
        
        # CRITICAL FIX: Handle shared topics correctly
        from core.schemas.topics import TopicNames
        
        if not broker:
            if topic == TopicNames.MARKET_TICKS:
                # For shared topics, use "market" namespace for market data
                broker = 'market'
            else:
                # For broker-specific topics, extract from topic name
                broker = topic.split('.')[0] if '.' in topic else "unknown"
        
        # Get correlation ID from context or use provided one
        if not correlation_id:
            correlation_id = CorrelationContext.ensure_correlation_id()
        
        envelope = EventEnvelope(
            correlation_id=correlation_id,
            causation_id=causation_id,
            broker=broker,
            type=event_type,
            ts=datetime.now(timezone.utc),
            key=key,
            source=self.name,
            version=1,
            data=data
        )
        
        try:
            await self.producer.send(
                topic=topic,
                key=key,
                value=envelope.model_dump()
            )
            
            # Update metrics on successful publish
            self._metrics["messages_published"] += 1
            
        except Exception as e:
            logger.error(f"Failed to emit event to {topic}: {e}")
            raise
    
    async def get_processing_stats(self) -> Dict[str, Any]:
        """Get enhanced processing statistics for monitoring"""
        current_time = datetime.now(timezone.utc)
        uptime_seconds = (current_time - self._metrics["start_time"]).total_seconds()
        
        # Calculate throughput metrics
        messages_per_second = self._metrics["messages_processed"] / uptime_seconds if uptime_seconds > 0 else 0
        
        # Calculate average processing time
        avg_processing_time = (
            sum(self._metrics["processing_times"]) / len(self._metrics["processing_times"])
            if self._metrics["processing_times"] else 0
        )
        
        # Calculate error rate
        error_rate = (
            self._metrics["error_count"] / self._metrics["messages_processed"] * 100
            if self._metrics["messages_processed"] > 0 else 0
        )
        
        # Get consumer lag using admin client
        partition_lag = await self._calculate_partition_lag()
        
        stats = {
            "service_name": self.name,
            "active_brokers": self.active_brokers,
            "default_broker_namespace": self.default_broker_namespace,
            "is_running": self._running,
            "uptime_seconds": uptime_seconds,
            
            # Throughput metrics
            "messages_processed": self._metrics["messages_processed"],
            "messages_published": self._metrics["messages_published"],
            "messages_per_second": round(messages_per_second, 2),
            
            # Performance metrics  
            "average_processing_time_ms": round(avg_processing_time * 1000, 2),
            "min_processing_time_ms": round(min(self._metrics["processing_times"]) * 1000, 2) if self._metrics["processing_times"] else 0,
            "max_processing_time_ms": round(max(self._metrics["processing_times"]) * 1000, 2) if self._metrics["processing_times"] else 0,
            
            # Error metrics
            "error_count": self._metrics["error_count"],
            "error_rate_percent": round(error_rate, 2),
            
            # Consumer lag metrics
            "consumer_lag": self._build_lag_metrics(partition_lag),
            
            # Topic breakdown
            "topic_stats": self._metrics["topic_stats"],
            "partition_stats": self._metrics["partition_stats"],
            
            # Last activity
            "last_message_time": self._metrics["last_message_time"],
            "start_time": self._metrics["start_time"].isoformat(),
            
            # Integration stats
            "error_handler_stats": self.error_handler.get_error_stats(),
            "dlq_stats": self.dlq_publisher.get_dlq_stats()
        }
        
        if self.deduplicator:
            stats["deduplication_stats"] = self.deduplicator.get_stats()
        
        return stats
    
    def _build_lag_metrics(self, partition_lag: Dict[str, int]) -> Dict[str, Any]:
        """Build enhanced lag metrics from partition lag data"""
        if isinstance(partition_lag, dict) and "error" not in partition_lag:
            # Filter out error values (-1)
            valid_lags = [lag for lag in partition_lag.values() if lag >= 0]
            
            if valid_lags:
                total_lag = sum(valid_lags)
                max_lag = max(valid_lags)
                avg_lag = total_lag / len(valid_lags)
                
                # Identify high lag partitions (configurable threshold)
                high_lag_threshold = 1000
                high_lag_partitions = [
                    part for part, lag in partition_lag.items() 
                    if lag > high_lag_threshold
                ]
                
                return {
                    "total_lag": total_lag,
                    "max_partition_lag": max_lag,
                    "average_partition_lag": round(avg_lag, 2),
                    "partition_count": len(valid_lags),
                    "high_lag_partitions": high_lag_partitions,
                    "partition_details": partition_lag,
                    "last_updated": datetime.fromtimestamp(self._last_lag_update, timezone.utc).isoformat() if self._last_lag_update > 0 else None
                }
            else:
                return {"error": "no_valid_partitions", "details": partition_lag}
        else:
            return {"error": "unable_to_calculate", "details": partition_lag}
    
    async def _calculate_partition_lag(self) -> Dict[str, int]:
        """
        Calculate actual consumer lag across partitions using AdminClient.
        """
        if not self._admin_client:
            if not await self._initialize_admin_client():
                return {"error": "admin_client_unavailable"}
    
        current_time = time.time()
        if (current_time - self._last_lag_update) < self._lag_update_interval:
            return self._partition_lag_cache
    
        try:
            lag_stats = {}
            
            for topic in self.consume_topics:
                try:
                    # Get topic metadata to find partitions
                    metadata = await self._admin_client.describe_topics([topic])
                    if topic not in metadata:
                        continue
                        
                    topic_metadata = metadata[topic]
                    partitions = [TopicPartition(topic, p.id) for p in topic_metadata.partitions]
                    
                    if hasattr(self.consumer, 'position'):
                        # Get high water marks (latest offsets)
                        try:
                            end_offsets = await self.consumer.end_offsets(partitions)
                        except Exception as e:
                            logger.debug(f"Could not get end offsets for {topic}: {e}")
                            continue
                            
                        # Get consumer positions
                        for partition in partitions:
                            try:
                                # Get consumer current position
                                consumer_position = await self.consumer.position(partition)
                                
                                # Get high water mark (latest offset)
                                high_water_mark = end_offsets.get(partition, 0)
                                
                                # Calculate lag
                                if consumer_position is not None:
                                    lag = max(0, high_water_mark - consumer_position)
                                else:
                                    lag = high_water_mark
                                
                                partition_key = f"{topic}-{partition.partition}"
                                lag_stats[partition_key] = lag
                                
                            except Exception as e:
                                logger.debug(f"Could not calculate lag for partition {partition}: {e}")
                                lag_stats[f"{topic}-{partition.partition}"] = -1
                                
                except Exception as e:
                    logger.debug(f"Could not get metadata for topic {topic}: {e}")
                    
            self._partition_lag_cache = lag_stats
            self._last_lag_update = current_time
            return lag_stats
            
        except Exception as e:
            logger.error(f"Failed to calculate consumer lag: {e}")
            return {"error": str(e)}
    
    def reset_metrics(self) -> None:
        """Reset metrics counters (useful for testing or periodic resets)"""
        self._metrics = {
            "messages_processed": 0,
            "messages_published": 0,
            "processing_times": [],
            "error_count": 0,
            "start_time": datetime.now(timezone.utc),
            "last_message_time": None,
            "partition_stats": {},
            "topic_stats": {}
        }
    
    def log_with_trace(self, message: str, level: str = "info", **kwargs):
        """Log with trace context"""
        trace_context = {
            "trace_id": getattr(self, 'current_trace_id', None),
            "correlation_id": getattr(self, 'current_correlation_id', None),
            "service": self.name,
        }
        
        # Get correlation context if available
        correlation_id = CorrelationContext.get_current_correlation_id()
        if correlation_id:
            trace_context["correlation_id"] = correlation_id
        
        log_data = {**trace_context, **kwargs}
        
        # Create correlation-aware logger and use it
        correlation_logger = CorrelationLogger(self.name)
        log_method = getattr(correlation_logger, level, correlation_logger.info)
        log_method(message, **log_data)
    
    def set_trace_context(self, event_envelope: EventEnvelope):
        """Set trace context from event envelope for the current processing"""
        self.current_trace_id = event_envelope.trace_id
        self.current_correlation_id = event_envelope.correlation_id
        self.current_event_id = event_envelope.id