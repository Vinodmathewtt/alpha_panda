"""
Offset Commit Strategy Example

Demonstrates proper manual offset commit pattern for data safety
and exactly-once processing guarantees.
"""

from typing import List
from aiokafka import ConsumerRecord
from aiokafka.structs import TopicPartition, OffsetAndMetadata

# DISABLE auto-commit in consumer config
consumer_config = {
    "enable_auto_commit": False,  # CRITICAL: Manual commits only
    "auto_offset_reset": "earliest",
    "group_id": f"{settings.group_id_prefix}.{service_name}"
}

# Manual commit pattern
async def process_message_batch(self, messages: List[ConsumerRecord]):
    for message in messages:
        try:
            # 1. Check for duplicates
            if await self.is_duplicate(message.value["id"]):
                continue
                
            # 2. Process message with all side effects
            await self.handle_message(message.value)
            
            # 3. Commit offset ONLY after success
            await self.consumer.commit({
                TopicPartition(message.topic, message.partition): 
                OffsetAndMetadata(message.offset + 1, None)
            })
            
        except Exception as e:
            # DO NOT commit on failure - will retry on rebalance
            await self.handle_processing_error(message, e)