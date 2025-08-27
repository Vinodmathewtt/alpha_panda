"""
Message Publishing Pattern Example

Demonstrates standardized message publishing using EventEnvelope
format with proper partitioning keys for ordering guarantees.
"""

from datetime import datetime
from core.schemas.events import EventEnvelope, EventType
from core.schemas.topics import TopicNames, PartitioningKeys

# Always use EventEnvelope format
envelope = EventEnvelope(
    type=EventType.MARKET_TICK,
    ts=datetime.utcnow(),
    key=PartitioningKeys.market_tick_key(instrument_token),
    source="service_name",
    version=1,
    data=market_tick.model_dump()
)

# Send with mandatory key (within async function)
async def publish_message():
    await producer.send(
        topic="market.ticks",
        key=envelope.key,
        value=envelope.model_dump()
    )