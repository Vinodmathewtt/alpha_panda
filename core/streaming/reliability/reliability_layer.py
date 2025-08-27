import logging
from typing import Callable, Awaitable, Dict, Any, Optional
from datetime import datetime, timezone

from .deduplication_manager import DeduplicationManager
from .error_handler import ErrorHandler  
from .metrics_collector import MetricsCollector
from ..correlation import CorrelationContext, CorrelationLogger

logger = logging.getLogger(__name__)

class ReliabilityLayer:
    """Wraps business logic with cross-cutting reliability concerns."""
    
    def __init__(
        self,
        service_name: str,
        handler_func: Callable[[Dict[str, Any], str], Awaitable[None]],  # Updated: now topic-aware
        consumer,  # MessageConsumer instance
        deduplicator: Optional[DeduplicationManager] = None,
        error_handler: Optional[ErrorHandler] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        self.service_name = service_name
        self.handler_func = handler_func
        self.consumer = consumer
        self.deduplicator = deduplicator
        self.error_handler = error_handler
        self.metrics_collector = metrics_collector or MetricsCollector(service_name)
        self.correlation_logger = CorrelationLogger(service_name)
    
    async def process_message(self, raw_message: Dict[str, Any]) -> None:
        """Process a message with topic context and all reliability features."""
        message_value = raw_message['value']
        topic = raw_message['topic']  # Extract topic from raw message
        event_id = message_value.get('id')
        correlation_id = message_value.get('correlation_id')
        
        # Extract broker from topic for enhanced logging
        broker = topic.split('.')[0] if '.' in topic else 'unknown'
        
        # 1. Set up correlation context with broker information
        if correlation_id:
            CorrelationContext.continue_trace(
                correlation_id, event_id, self.service_name, 
                f"process_{topic}", extra_context={"broker": broker}
            )
        else:
            correlation_id = CorrelationContext.start_new_trace(
                self.service_name, f"process_{topic}", 
                extra_context={"broker": broker}
            )
        
        # 2. Check for duplicates (broker-aware caching)
        if (self.deduplicator and event_id and 
            await self.deduplicator.is_duplicate(event_id, broker_context=broker)):
            self.correlation_logger.debug("Skipping duplicate event", 
                                        event_id=event_id, broker=broker, topic=topic)
            await self.consumer.commit(raw_message)
            return
        
        # 3. Process with error handling and metrics
        start_time = datetime.now(timezone.utc)
        try:
            # Execute business logic with topic context
            await self.handler_func(message_value, topic)
            
            # Commit and mark as processed
            await self.consumer.commit(raw_message)
            if self.deduplicator and event_id:
                await self.deduplicator.mark_processed(event_id, broker_context=broker)
            
            # Record success metrics with broker context
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.correlation_logger.debug("Message processed successfully", 
                                        duration_ms=duration * 1000,
                                        broker=broker, topic=topic)
            
            if self.metrics_collector:
                await self.metrics_collector.record_success(duration, broker_context=broker)
        
        except Exception as e:
            self.correlation_logger.error("Failed to process message", 
                                        error=str(e), broker=broker, topic=topic)
            
            if self.error_handler:
                # Error handler manages retries, DLQ, and commits
                await self.error_handler.handle_processing_error_async(
                    raw_message, e, 
                    processing_func=lambda: self.handler_func(message_value, topic),
                    commit_func=lambda: self.consumer.commit(raw_message),
                    broker_context=broker
                )
            else:
                # Simple error handling - log and commit to avoid reprocessing
                logger.error(f"Unhandled processing error for {broker}: {e}")
                await self.consumer.commit(raw_message)
            
            if self.metrics_collector:
                await self.metrics_collector.record_failure(str(e), broker_context=broker)