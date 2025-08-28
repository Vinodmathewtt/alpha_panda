import asyncio
import json
import logging
from typing import List, AsyncGenerator, Dict, Any, Optional
from aiokafka import AIOKafkaConsumer
from aiokafka.structs import TopicPartition
from core.config.settings import RedpandaSettings

logger = logging.getLogger(__name__)

class MessageConsumer:
    """Pure message consumption without business logic concerns."""
    
    def __init__(self, config: RedpandaSettings, topics: List[str], group_id: str):
        self.config = config
        self.topics = topics
        self.group_id = group_id
        self._consumer: Optional[AIOKafkaConsumer] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the Kafka consumer."""
        if self._running:
            return
        
        self._consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=self.config.bootstrap_servers,
            client_id=f"{self.config.client_id}-consumer",
            group_id=self.group_id,
            auto_offset_reset='earliest',
            enable_auto_commit=False,  # Manual commits only
            session_timeout_ms=30000,
            heartbeat_interval_ms=10000,
            max_poll_records=50,
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        
        await self._consumer.start()
        self._running = True
        logger.info(f"Message consumer started for topics: {self.topics}")
    
    async def stop(self) -> None:
        """Stop the Kafka consumer."""
        if not self._running or not self._consumer:
            return
        
        await self._consumer.stop()
        self._running = False
        logger.info("Message consumer stopped")
    
    async def consume(self) -> AsyncGenerator[Dict[str, Any], None]:
        """Yield raw messages from Kafka."""
        if not self._running:
            await self.start()
        
        try:
            async for message in self._consumer:
                yield {
                    'topic': message.topic,
                    'key': message.key.decode('utf-8') if message.key else None,
                    'value': message.value,
                    'partition': message.partition,
                    'offset': message.offset,
                    'timestamp': message.timestamp,
                    '_raw_message': message  # For commit operations
                }
        except Exception as e:
            logger.error(f"Error in message consumption: {e}")
            raise
    
    async def commit(self, message: Optional[Dict[str, Any]] = None) -> None:
        """Commit message offset."""
        if not self._consumer:
            raise RuntimeError("Consumer not started")
        
        try:
            if message and '_raw_message' in message:
                # Commit specific message
                tp = TopicPartition(message['_raw_message'].topic, message['_raw_message'].partition)
                await self._consumer.commit({tp: message['_raw_message'].offset + 1})
            else:
                # Commit current position
                await self._consumer.commit()
        except Exception as e:
            logger.error(f"Failed to commit offset: {e}")
            raise