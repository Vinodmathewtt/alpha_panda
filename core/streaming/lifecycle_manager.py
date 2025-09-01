"""
Lifecycle management for streaming components to ensure proper cleanup.
This addresses the unclosed AIOKafkaProducer/Consumer warnings.
"""
import asyncio
from core.logging import get_logger
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError

logger = get_logger("core.streaming.lifecycle_manager", component="streaming")


class StreamingLifecycleManager:
    """
    Manages the lifecycle of streaming components to ensure proper cleanup
    and avoid resource leak warnings.
    """
    
    def __init__(self):
        self.producers: Dict[str, AIOKafkaProducer] = {}
        self.consumers: Dict[str, AIOKafkaConsumer] = {}
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.shutdown_event = asyncio.Event()
    
    async def register_producer(self, name: str, producer: AIOKafkaProducer) -> None:
        """Register a producer for lifecycle management"""
        if name in self.producers:
            logger.warning(f"Producer {name} already registered, replacing")
            await self.cleanup_producer(name)
        
        self.producers[name] = producer
        logger.debug(f"Registered producer: {name}")
    
    async def register_consumer(self, name: str, consumer: AIOKafkaConsumer) -> None:
        """Register a consumer for lifecycle management"""
        if name in self.consumers:
            logger.warning(f"Consumer {name} already registered, replacing")
            await self.cleanup_consumer(name)
        
        self.consumers[name] = consumer
        logger.debug(f"Registered consumer: {name}")
    
    async def register_task(self, name: str, task: asyncio.Task) -> None:
        """Register an async task for lifecycle management"""
        if name in self.running_tasks:
            logger.warning(f"Task {name} already registered, cancelling old task")
            await self.cancel_task(name)
        
        self.running_tasks[name] = task
        logger.debug(f"Registered task: {name}")
    
    async def cleanup_producer(self, name: str) -> None:
        """Clean up a specific producer"""
        if name not in self.producers:
            return
        
        producer = self.producers[name]
        try:
            logger.debug(f"Stopping producer: {name}")
            # CRITICAL: Flush before stopping to prevent data loss
            await asyncio.wait_for(producer.flush(), timeout=5.0)
            await asyncio.wait_for(producer.stop(), timeout=5.0)
            logger.debug(f"Successfully stopped producer: {name}")
        except asyncio.TimeoutError:
            logger.error(f"Timeout stopping producer: {name}")
        except Exception as e:
            logger.error(f"Error stopping producer {name}: {e}")
        finally:
            del self.producers[name]
    
    async def cleanup_consumer(self, name: str) -> None:
        """Clean up a specific consumer"""
        if name not in self.consumers:
            return
        
        consumer = self.consumers[name]
        try:
            logger.debug(f"Stopping consumer: {name}")
            await asyncio.wait_for(consumer.stop(), timeout=5.0)
            logger.debug(f"Successfully stopped consumer: {name}")
        except asyncio.TimeoutError:
            logger.error(f"Timeout stopping consumer: {name}")
        except Exception as e:
            logger.error(f"Error stopping consumer {name}: {e}")
        finally:
            del self.consumers[name]
    
    async def cancel_task(self, name: str) -> None:
        """Cancel a specific task"""
        if name not in self.running_tasks:
            return
        
        task = self.running_tasks[name]
        try:
            logger.debug(f"Cancelling task: {name}")
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except asyncio.CancelledError:
                logger.debug(f"Successfully cancelled task: {name}")
            except asyncio.TimeoutError:
                logger.warning(f"Task {name} did not respond to cancellation")
        except Exception as e:
            logger.error(f"Error cancelling task {name}: {e}")
        finally:
            del self.running_tasks[name]
    
    async def shutdown_all(self, timeout: float = 10.0) -> None:
        """
        Shutdown all registered components in proper order.
        This is the main method to call during application shutdown.
        """
        logger.info("Starting streaming components shutdown")
        self.shutdown_event.set()
        
        try:
            # 1. Cancel all running tasks first
            task_names = list(self.running_tasks.keys())
            logger.debug(f"Cancelling {len(task_names)} tasks")
            for name in task_names:
                await self.cancel_task(name)
            
            # 2. Stop all producers (with flush)
            producer_names = list(self.producers.keys())
            logger.debug(f"Stopping {len(producer_names)} producers")
            for name in producer_names:
                await self.cleanup_producer(name)
            
            # 3. Stop all consumers
            consumer_names = list(self.consumers.keys())
            logger.debug(f"Stopping {len(consumer_names)} consumers")
            for name in consumer_names:
                await self.cleanup_consumer(name)
            
            logger.info("Streaming components shutdown completed successfully")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            raise
    
    def is_shutdown(self) -> bool:
        """Check if shutdown has been initiated"""
        return self.shutdown_event.is_set()
    
    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown to be initiated"""
        await self.shutdown_event.wait()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of managed components"""
        return {
            "producers": list(self.producers.keys()),
            "consumers": list(self.consumers.keys()),
            "tasks": list(self.running_tasks.keys()),
            "shutdown_initiated": self.shutdown_event.is_set()
        }


# Global lifecycle manager instance
_lifecycle_manager: Optional[StreamingLifecycleManager] = None


def get_lifecycle_manager() -> StreamingLifecycleManager:
    """Get the global lifecycle manager instance"""
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = StreamingLifecycleManager()
    return _lifecycle_manager


@asynccontextmanager
async def managed_producer(name: str, producer: AIOKafkaProducer):
    """
    Context manager for producer lifecycle management.
    Ensures proper cleanup even if exceptions occur.
    """
    manager = get_lifecycle_manager()
    await manager.register_producer(name, producer)
    try:
        yield producer
    finally:
        await manager.cleanup_producer(name)


@asynccontextmanager
async def managed_consumer(name: str, consumer: AIOKafkaConsumer):
    """
    Context manager for consumer lifecycle management.
    Ensures proper cleanup even if exceptions occur.
    """
    manager = get_lifecycle_manager()
    await manager.register_consumer(name, consumer)
    try:
        yield consumer
    finally:
        await manager.cleanup_consumer(name)


async def shutdown_all_streaming_components(timeout: float = 10.0) -> None:
    """
    Shutdown all managed streaming components.
    This should be called during application shutdown.
    """
    manager = get_lifecycle_manager()
    await manager.shutdown_all(timeout)


class GracefulShutdownMixin:
    """
    Mixin class for services that need graceful shutdown capabilities.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._shutdown_complete = asyncio.Event()
        self.lifecycle_manager = get_lifecycle_manager()
    
    async def register_for_lifecycle_management(self, name: str):
        """Register this service's components with lifecycle manager"""
        if hasattr(self, 'producer'):
            await self.lifecycle_manager.register_producer(f"{name}_producer", self.producer._producer)
        
        if hasattr(self, 'consumer'):
            await self.lifecycle_manager.register_consumer(f"{name}_consumer", self.consumer._consumer)
        
        if hasattr(self, '_consume_task'):
            await self.lifecycle_manager.register_task(f"{name}_consume_task", self._consume_task)
    
    async def graceful_shutdown(self, timeout: float = 10.0):
        """Perform graceful shutdown of this service"""
        try:
            await asyncio.wait_for(self.stop(), timeout=timeout)
            self._shutdown_complete.set()
        except asyncio.TimeoutError:
            logger.error(f"Shutdown timeout for {self.__class__.__name__}")
            raise
        except Exception as e:
            logger.error(f"Error during shutdown of {self.__class__.__name__}: {e}")
            raise
    
    async def wait_for_shutdown(self):
        """Wait for shutdown to complete"""
        await self._shutdown_complete.wait()
