"""
Enhanced Error Handling & DLQ Pattern Example

Demonstrates structured retry pattern with Dead Letter Queue
implementation for production-ready error handling.
"""

import asyncio
import random
from enum import Enum
from typing import Optional
from datetime import datetime

class ErrorType(Enum):
    TRANSIENT = "transient"      # Network timeout, temporary broker unavailability
    POISON = "poison"            # Malformed data, schema violations  
    BUSINESS = "business"        # Strategy logic errors, risk violations
    INFRASTRUCTURE = "infrastructure"  # Database connection, Redis unavailability

class RetryConfig:
    def __init__(self, max_attempts: int = 5, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay  
        self.max_delay = max_delay
        
    def get_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter"""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        return delay * (0.5 + 0.5 * random.random())  # Add jitter

async def handle_processing_error(self, message, error: Exception):
    error_type = self.classify_error(error)
    retry_count = self.get_retry_count(message)
    
    if error_type == ErrorType.POISON:
        # Skip poison messages immediately
        await self.send_to_dlq(message, error, "poison_message")
        await self.commit_offset(message)
        return
        
    if retry_count >= self.retry_config.max_attempts:
        # Exhausted retries - send to DLQ
        await self.send_to_dlq(message, error, "max_retries_exceeded") 
        await self.commit_offset(message)
        return
        
    # Retry with exponential backoff
    delay = self.retry_config.get_delay(retry_count)
    await asyncio.sleep(delay)
    
    # DO NOT commit - will retry on next poll
    self.metrics.increment("message_retry", {
        "error_type": error_type.value,
        "attempt": retry_count + 1
    })

async def send_to_dlq(self, message, error: Exception, reason: str):
    dlq_topic = f"{message.topic}.dlq"
    
    dlq_event = {
        "original_topic": message.topic,
        "original_partition": message.partition,  
        "original_offset": message.offset,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "failure_reason": reason,
        "retry_count": self.get_retry_count(message),
        "failed_at": datetime.utcnow().isoformat(),
        "original_event": message.value,
        "replay_metadata": {
            "consumer_group": self.consumer_group,
            "service_name": self.service_name
        }
    }
    
    await self.producer.send(
        topic=dlq_topic,
        key=message.key,
        value=dlq_event
    )
    
    self.metrics.increment("dlq_message", {
        "original_topic": message.topic,
        "reason": reason
    })