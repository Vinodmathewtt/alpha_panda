"""
DLQ Replay Tool Example

Demonstrates how to replay failed messages from Dead Letter Queue
back to original topics for reprocessing.
"""

from typing import Optional
from uuid import uuid4
from datetime import datetime

# CLI command: python cli.py replay-dlq --topic paper.orders.filled.dlq --limit 100
async def replay_from_dlq(self, dlq_topic: str, limit: Optional[int] = None):
    """Replay failed messages from DLQ back to original topic"""
    consumer = await self.create_consumer([dlq_topic], "dlq_replay_tool")
    replayed_count = 0
    
    async for message in consumer:
        dlq_event = message.value
        original_topic = dlq_event["original_topic"]
        original_event = dlq_event["original_event"]
        
        # Replay to original topic with new event_id
        original_event["id"] = str(uuid4())  # New event ID
        original_event["replay_metadata"] = {
            "replayed_from": dlq_topic,
            "replayed_at": datetime.utcnow().isoformat(),
            "original_failure": dlq_event["failure_reason"]
        }
        
        await self.producer.send(
            topic=original_topic,
            key=message.key,
            value=original_event
        )
        
        await consumer.commit()
        replayed_count += 1
        
        if limit and replayed_count >= limit:
            break
    
    await consumer.stop()
    return replayed_count