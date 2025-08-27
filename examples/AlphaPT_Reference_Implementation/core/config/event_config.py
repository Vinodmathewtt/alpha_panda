"""Event system configuration settings."""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker configuration for event system."""
    
    enabled: bool = Field(default=True, description="Enable circuit breaker functionality")
    failure_threshold: int = Field(default=5, description="Number of failures before opening circuit breaker")
    recovery_timeout_seconds: float = Field(default=30.0, description="Time to wait before attempting recovery")
    half_open_max_calls: int = Field(default=3, description="Max calls in half-open state")


class EventValidationConfig(BaseModel):
    """Event validation configuration."""
    
    enabled: bool = Field(default=True, description="Enable event validation")
    schema_validation: bool = Field(default=False, description="Enable JSON schema validation")
    max_event_size_bytes: int = Field(default=1024 * 1024, description="Maximum event size in bytes (1MB)")
    required_fields: list[str] = Field(
        default=["event_id", "event_type", "timestamp", "source"],
        description="Required fields for all events"
    )


class PerformanceMonitoringConfig(BaseModel):
    """Performance monitoring configuration for event system."""
    
    enabled: bool = Field(default=True, description="Enable performance monitoring")
    percentile_tracking: bool = Field(default=True, description="Track performance percentiles")
    metrics_collection_interval_seconds: float = Field(default=60.0, description="Metrics collection interval")
    max_tracking_entries: int = Field(default=10000, description="Maximum tracking entries in memory")


class StreamManagementConfig(BaseModel):
    """Stream management configuration."""
    
    auto_cleanup_enabled: bool = Field(default=True, description="Enable automatic stream cleanup")
    cleanup_interval_hours: int = Field(default=24, description="Stream cleanup interval in hours")
    max_stream_age_hours: int = Field(default=168, description="Maximum stream age before cleanup (7 days)")
    
    # Stream-specific settings
    market_data_retention_hours: int = Field(default=24, description="Market data stream retention")
    trading_retention_hours: int = Field(default=168, description="Trading stream retention (7 days)")
    system_retention_hours: int = Field(default=72, description="System stream retention (3 days)")


class DeadLetterQueueConfig(BaseModel):
    """Dead letter queue configuration."""
    
    enabled: bool = Field(default=True, description="Enable dead letter queue")
    max_retry_attempts: int = Field(default=3, description="Maximum retry attempts before sending to DLQ")
    dlq_retention_hours: int = Field(default=168, description="DLQ message retention (7 days)")
    dlq_subject_prefix: str = Field(default="dlq", description="DLQ subject prefix")


class PublishingConfig(BaseModel):
    """Configuration for the event publishing service."""
    
    max_retries: int = Field(3, description="Maximum number of retries for a failed publish")
    retry_delay_seconds: float = Field(0.5, description="Initial delay in seconds for retries")
    publish_timeout_seconds: float = Field(5.0, description="Timeout for each individual publish attempt")
    compression_enabled: bool = Field(True, description="Enable gzip compression for event payloads")


class SubscriptionConfig(BaseModel):
    """Configuration for the event subscription service."""
    
    default_ack_wait_seconds: int = Field(30, description="Default acknowledgment wait time")
    default_max_deliver: int = Field(3, description="Default maximum delivery attempts")
    batch_size: int = Field(100, description="Default batch size for message processing")


class EventSystemConfig(BaseModel):
    """Event system configuration."""
    
    # Core settings
    enable_correlation_tracking: bool = Field(default=True, description="Enable correlation ID tracking")
    default_publish_timeout_seconds: float = Field(default=10.0, description="Default publish timeout")
    subscriber_timeout_seconds: float = Field(default=30.0, description="Subscriber callback timeout")
    
    # New refactored event system configurations
    publishing: PublishingConfig = Field(default_factory=PublishingConfig)
    subscription: SubscriptionConfig = Field(default_factory=SubscriptionConfig)
    
    # Component configurations
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    validation: EventValidationConfig = Field(default_factory=EventValidationConfig)
    performance: PerformanceMonitoringConfig = Field(default_factory=PerformanceMonitoringConfig)
    stream_management: StreamManagementConfig = Field(default_factory=StreamManagementConfig)
    dead_letter_queue: DeadLetterQueueConfig = Field(default_factory=DeadLetterQueueConfig)
    
    # High-performance publisher settings
    high_performance_enabled: bool = Field(default=False, description="Enable high-performance publisher")
    batch_max_size: int = Field(default=1000, description="Maximum batch size for high-performance publisher")
    batch_max_wait_ms: float = Field(default=50.0, description="Maximum batch wait time")
    compression_enabled: bool = Field(default=True, description="Enable event compression")
    
    # Development and debugging
    detailed_logging: bool = Field(default=False, description="Enable detailed event system logging")
    debug_mode: bool = Field(default=False, description="Enable debug mode for event system")