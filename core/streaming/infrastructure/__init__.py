"""Infrastructure components for streaming services.

This module provides the foundational infrastructure components for the
refactored streaming architecture using composition over inheritance.
"""

from .message_consumer import MessageConsumer
from .message_producer import MessageProducer

__all__ = ['MessageConsumer', 'MessageProducer']