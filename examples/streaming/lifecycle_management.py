"""
Consumer Lifecycle & Commit Management Example

Demonstrates proper partition assignment/revocation handling
for data safety and graceful shutdown patterns.
"""

from typing import Set
from aiokafka import AIOKafkaConsumer
from aiokafka.structs import TopicPartition, OffsetAndMetadata

class StreamProcessor:
    async def start_consumer(self):
        self.consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.settings.redpanda.bootstrap_servers,
            group_id=f"{self.settings.group_id_prefix}.{self.service_name}",
            enable_auto_commit=False,  # CRITICAL: Manual commits only
            auto_offset_reset="earliest",
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000,
        )
        
        # Set up partition assignment/revocation callbacks
        self.consumer.subscribe(
            topics=self.topics,
            listener=PartitionRebalanceListener(self)
        )
        
        await self.consumer.start()

class PartitionRebalanceListener:
    def __init__(self, processor):
        self.processor = processor
        
    async def on_partitions_revoked(self, revoked: Set[TopicPartition]):
        """Called before rebalancing - finish in-flight work"""
        self.processor.logger.info("Partitions being revoked", partitions=len(revoked))
        
        # 1. Stop processing new messages
        self.processor.processing_enabled = False
        
        # 2. Wait for in-flight work to complete
        await self.processor.wait_for_inflight_completion()
        
        # 3. Commit offsets for completed work
        await self.processor.commit_pending_offsets()
        
        # 4. Flush producer
        await self.processor.producer.flush()
        
    async def on_partitions_assigned(self, assigned: Set[TopicPartition]):
        """Called after rebalancing - resume processing"""
        self.processor.logger.info("Partitions assigned", partitions=len(assigned))
        self.processor.processing_enabled = True

# Graceful Shutdown Implementation
async def stop(self):
    """Proper shutdown sequence"""
    self.logger.info("Starting graceful shutdown")
    
    # 1. Stop accepting new messages
    self.running = False
    
    # 2. Wait for in-flight messages to complete
    await self.wait_for_inflight_completion()
    
    # 3. Commit final offsets
    await self.commit_pending_offsets()
    
    # 4. Stop consumer (automatically commits final offsets)
    await self.consumer.stop()
    
    # 5. Stop producer (includes flush)
    await self.producer.stop()
    
    self.logger.info("Graceful shutdown completed")