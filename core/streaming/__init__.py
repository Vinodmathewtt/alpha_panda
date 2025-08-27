"""Streaming module for message processing and Kafka integration.

This module provides both the legacy StreamProcessor pattern and the new
composition-based streaming architecture.
"""

# Legacy pattern (for backward compatibility)
from .clients import StreamProcessor

# New composition-based architecture
from .infrastructure import MessageConsumer, MessageProducer
from .reliability import (
    ReliabilityLayer, 
    DeduplicationManager, 
    ErrorHandler, 
    MetricsCollector
)
from .orchestration import ServiceOrchestrator, LifecycleCoordinator
from .patterns import StreamServiceBuilder

# Utility modules
from . import correlation
from . import deduplication
from . import error_handling
from . import lifecycle_manager

__all__ = [
    # Legacy
    'StreamProcessor',
    
    # New architecture - Infrastructure
    'MessageConsumer',
    'MessageProducer',
    
    # New architecture - Reliability
    'ReliabilityLayer',
    'DeduplicationManager',
    'ErrorHandler', 
    'MetricsCollector',
    
    # New architecture - Orchestration
    'ServiceOrchestrator',
    'LifecycleCoordinator',
    
    # New architecture - Patterns
    'StreamServiceBuilder',
    
    # Utility modules
    'correlation',
    'deduplication',
    'error_handling',
    'lifecycle_manager',
]