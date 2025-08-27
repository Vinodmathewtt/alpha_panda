"""
Circuit breaker pattern implementation for service resilience.
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable, Any
import logging


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit tripped, failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker for service resilience"""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Exception = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED
        
        self.logger = logging.getLogger(f"{__name__}.CircuitBreaker")
    
    async def __call__(self, func: Callable) -> Any:
        """Execute function with circuit breaker protection"""
        
        # If circuit is OPEN, check if we should try recovery
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.logger.info("Circuit breaker moving to HALF_OPEN for testing")
            else:
                raise RuntimeError("Circuit breaker is OPEN - failing fast")
        
        try:
            # Execute the function
            result = await func() if asyncio.iscoroutinefunction(func) else func()
            
            # If we're in HALF_OPEN and succeeded, reset circuit
            if self.state == CircuitState.HALF_OPEN:
                self._reset()
                self.logger.info("Circuit breaker reset to CLOSED - service recovered")
            
            return result
            
        except self.expected_exception as e:
            self._record_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if not self.last_failure_time:
            return True
        
        return datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)
    
    def _record_failure(self):
        """Record a failure and potentially trip the circuit"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.logger.error(
                f"Circuit breaker TRIPPED - {self.failure_count} failures, "
                f"entering OPEN state for {self.recovery_timeout}s"
            )
    
    def _reset(self):
        """Reset circuit breaker to normal operation"""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED