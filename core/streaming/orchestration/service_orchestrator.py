import asyncio
from core.logging import get_logger
from typing import List, Optional
from ..infrastructure.message_consumer import MessageConsumer
from ..infrastructure.message_producer import MessageProducer
from ..reliability.reliability_layer import ReliabilityLayer

logger = get_logger("core.streaming.service_orchestrator", component="streaming")


class ServiceOrchestrator:
    """Orchestrates the composition of streaming service components."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.consumers: List[MessageConsumer] = []
        self.producers: List[MessageProducer] = []
        self.reliability_layers: List[ReliabilityLayer] = []
        self._running = False
        self._consumption_tasks: List[asyncio.Task] = []
    
    def add_consumer_flow(
        self, 
        consumer: MessageConsumer,
        reliability_layer: ReliabilityLayer
    ) -> None:
        """Add a consumer flow with reliability layer."""
        self.consumers.append(consumer)
        self.reliability_layers.append(reliability_layer)
    
    def add_producer(self, producer: MessageProducer) -> None:
        """Add a producer."""
        self.producers.append(producer)
    
    async def start(self) -> None:
        """Start all components."""
        if self._running:
            return
        
        logger.info(f"Starting service orchestrator for {self.service_name}")
        
        # Start producers
        for producer in self.producers:
            await producer.start()
        
        # Start consumers
        for consumer in self.consumers:
            await consumer.start()
        
        # Start consumption loops
        self._consumption_tasks = []
        for consumer, reliability_layer in zip(self.consumers, self.reliability_layers):
            task = asyncio.create_task(
                self._consumption_loop(consumer, reliability_layer)
            )
            self._consumption_tasks.append(task)
        
        self._running = True
        logger.info(f"Service orchestrator started for {self.service_name}")
    
    async def stop(self) -> None:
        """Stop all components gracefully."""
        if not self._running:
            return
        
        logger.info(f"Stopping service orchestrator for {self.service_name}")
        
        # Cancel consumption tasks
        for task in self._consumption_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._consumption_tasks:
            await asyncio.gather(*self._consumption_tasks, return_exceptions=True)
        
        # Stop consumers
        for consumer in self.consumers:
            await consumer.stop()
        
        # Stop producers
        for producer in self.producers:
            await producer.stop()
        
        self._running = False
        logger.info(f"Service orchestrator stopped for {self.service_name}")
    
    async def _consumption_loop(
        self, 
        consumer: MessageConsumer, 
        reliability_layer: ReliabilityLayer
    ) -> None:
        """Run the consumption loop for a consumer."""
        try:
            async for message in consumer.consume():
                await reliability_layer.process_message(message)
        except asyncio.CancelledError:
            # Graceful shutdown
            logger.info(f"Consumption loop cancelled for {consumer.topics}")
        except Exception as e:
            logger.error(f"Fatal error in consumption loop: {e}")
            # In production, you might want to restart the loop
            raise
    
    def is_running(self) -> bool:
        """Check if orchestrator is running."""
        return self._running
    
    def get_status(self) -> dict:
        """Get status summary of all components."""
        return {
            "service_name": self.service_name,
            "running": self._running,
            "consumers": len(self.consumers),
            "producers": len(self.producers),
            "consumption_tasks": len([t for t in self._consumption_tasks if not t.done()]),
            "completed_tasks": len([t for t in self._consumption_tasks if t.done()]),
        }
