from typing import Dict, Any, Callable, Awaitable, Optional, List
from core.config.settings import RedpandaSettings, Settings
from ..infrastructure.message_consumer import MessageConsumer
from ..infrastructure.message_producer import MessageProducer
from ..reliability.reliability_layer import ReliabilityLayer
from ..reliability.deduplication_manager import DeduplicationManager
from ..reliability.error_handler import ErrorHandler
from ..reliability.metrics_collector import MetricsCollector
from ..orchestration.service_orchestrator import ServiceOrchestrator
from ..error_handling import DLQPublisher
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector


class StreamServiceBuilder:
    """Builder pattern for creating streaming services with composition."""
    
    def __init__(self, service_name: str, config: RedpandaSettings, settings: Settings):
        self.service_name = service_name
        self.config = config
        self.settings = settings
        self.orchestrator = ServiceOrchestrator(service_name)
        
        # Default reliability components
        self._redis_client = None
        self._deduplicator = None
        self._error_handler = None
        self._metrics_collector = None
        self._dlq_publisher = None
        self._prometheus: PrometheusMetricsCollector | None = None
    
    def with_redis(self, redis_client) -> 'StreamServiceBuilder':
        """Configure Redis for deduplication and metrics."""
        self._redis_client = redis_client
        self._deduplicator = DeduplicationManager(redis_client, self.service_name)
        return self
    
    def with_error_handling(self, error_handler: Optional[ErrorHandler] = None) -> 'StreamServiceBuilder':
        """Configure custom error handling."""
        if error_handler:
            self._error_handler = error_handler
        else:
            # Create default error handler with DLQ publisher
            if not self._dlq_publisher:
                # Create a producer for DLQ if we don't have one
                dlq_tuning = self._resolve_producer_tuning(f"{self.service_name}-dlq")
                dlq_producer = MessageProducer(self.config, f"{self.service_name}-dlq", tuning=dlq_tuning)
                # Initialize without callback; we'll attach metrics in with_metrics if available
                self._dlq_publisher = DLQPublisher(dlq_producer, self.service_name)
            
            self._error_handler = ErrorHandler(
                self.service_name,
                self._dlq_publisher
            )
        return self
    
    def with_metrics(self, metrics_collector: Optional[MetricsCollector] = None) -> 'StreamServiceBuilder':
        """Configure metrics collection."""
        self._metrics_collector = metrics_collector or MetricsCollector(self.service_name)
        # Attach DLQ metrics callback if DLQ publisher already exists
        if self._dlq_publisher:
            async def _on_dlq(topic: str, event: dict):
                try:
                    broker = topic.split('.')[0] if '.' in topic else 'unknown'
                    await self._metrics_collector.record_failure("dlq", broker_context=broker)
                    if self._prometheus:
                        try:
                            self._prometheus.record_dlq_message(self.service_name, broker)
                        except Exception:
                            pass
                except Exception:
                    pass
            self._dlq_publisher.set_on_dlq_callback(_on_dlq)
        return self

    def with_prometheus(self, prom: PrometheusMetricsCollector | None) -> 'StreamServiceBuilder':
        """Optionally attach Prometheus metrics for DLQ recording."""
        self._prometheus = prom
        # If a DLQ publisher already exists and has a callback, it will pick this up on next set
        if self._dlq_publisher and hasattr(self._dlq_publisher, 'set_on_dlq_callback'):
            # Re-attach to include Prometheus in the closure
            async def _on_dlq(topic: str, event: dict):
                try:
                    broker = topic.split('.')[0] if '.' in topic else 'unknown'
                    if self._metrics_collector:
                        await self._metrics_collector.record_failure("dlq", broker_context=broker)
                    if self._prometheus:
                        self._prometheus.record_dlq_message(self.service_name, broker)
                except Exception:
                    pass
            self._dlq_publisher.set_on_dlq_callback(_on_dlq)
        return self
    
    def with_dlq_publisher(self, dlq_publisher: DLQPublisher) -> 'StreamServiceBuilder':
        """Configure custom DLQ publisher."""
        self._dlq_publisher = dlq_publisher
        return self
    
    def add_consumer_handler(
        self,
        topics: List[str],
        group_id: str,
        handler_func: Callable[[Dict[str, Any], str], Awaitable[None]]  # Updated: topic-aware handler
    ) -> 'StreamServiceBuilder':
        """Add a consumer with topic-aware handler function."""
        
        # Create consumer
        consumer = MessageConsumer(self.config, topics, group_id)
        
        # Create reliability layer with topic-aware handler
        reliability_layer = ReliabilityLayer(
            service_name=self.service_name,
            handler_func=handler_func,  # Now topic-aware
            consumer=consumer,
            deduplicator=self._deduplicator,
            error_handler=self._error_handler,
            metrics_collector=self._metrics_collector
        )
        
        # Add to orchestrator
        self.orchestrator.add_consumer_flow(consumer, reliability_layer)
        return self
    
    def add_producer(self) -> 'StreamServiceBuilder':
        """Add a producer."""
        tuning = self._resolve_producer_tuning(self.service_name)
        producer = MessageProducer(self.config, self.service_name, tuning=tuning)
        self.orchestrator.add_producer(producer)
        return self

    def _resolve_producer_tuning(self, name: str) -> Dict[str, Any]:
        """Resolve per-service producer tuning from settings, with 'default' fallback."""
        try:
            cfg = getattr(self.settings, 'producer_tuning', {}) or {}
            # Convert Pydantic models to dicts if necessary
            def as_dict(v):
                try:
                    return v.model_dump(exclude_none=True)  # pydantic v2
                except Exception:
                    return dict(v) if isinstance(v, dict) else {}
            if name in cfg:
                return as_dict(cfg[name])
            if 'default' in cfg:
                return as_dict(cfg['default'])
        except Exception:
            pass
        return {}
    
    def build(self) -> ServiceOrchestrator:
        """Build the final service orchestrator."""
        return self.orchestrator
    
    def build_with_defaults(
        self, 
        redis_client=None,
        enable_deduplication: bool = True,
        enable_error_handling: bool = True,
        enable_metrics: bool = True
    ) -> ServiceOrchestrator:
        """Build service with sensible defaults."""
        if redis_client and enable_deduplication:
            self.with_redis(redis_client)
        
        if enable_error_handling:
            self.with_error_handling()
        
        if enable_metrics:
            self.with_metrics()
        
        return self.build()
