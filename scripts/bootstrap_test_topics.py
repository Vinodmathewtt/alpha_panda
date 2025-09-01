#!/usr/bin/env python3
"""
Bootstrap Kafka topics for testing

This script creates all necessary Kafka topics for Alpha Panda testing
with appropriate partition counts and configurations.
"""

import asyncio
import sys
from aiokafka import AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdmin, NewTopic
from aiokafka.errors import TopicAlreadyExistsError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Topic configurations for testing
TEST_TOPICS = {
    # Market data (shared)
    "market.ticks": {"partitions": 3, "replication_factor": 1},
    
    # Paper trading topics
    "paper.signals.raw": {"partitions": 3, "replication_factor": 1},
    "paper.signals.validated": {"partitions": 3, "replication_factor": 1},
    "paper.signals.rejected": {"partitions": 3, "replication_factor": 1},
    "paper.orders.submitted": {"partitions": 3, "replication_factor": 1},
    "paper.orders.filled": {"partitions": 3, "replication_factor": 1},
    "paper.orders.failed": {"partitions": 3, "replication_factor": 1},
    
    # Zerodha trading topics
    "zerodha.signals.raw": {"partitions": 3, "replication_factor": 1},
    "zerodha.signals.validated": {"partitions": 3, "replication_factor": 1},
    "zerodha.signals.rejected": {"partitions": 3, "replication_factor": 1},
    "zerodha.orders.submitted": {"partitions": 3, "replication_factor": 1},
    "zerodha.orders.filled": {"partitions": 3, "replication_factor": 1},
    "zerodha.orders.failed": {"partitions": 3, "replication_factor": 1},

    # PnL snapshots (per broker)
    "paper.pnl.snapshots": {"partitions": 3, "replication_factor": 1},
    "zerodha.pnl.snapshots": {"partitions": 3, "replication_factor": 1},
    
    # Dead letter queue topics
    "paper.signals.raw.dlq": {"partitions": 1, "replication_factor": 1},
    "paper.orders.submitted.dlq": {"partitions": 1, "replication_factor": 1},
    "zerodha.signals.raw.dlq": {"partitions": 1, "replication_factor": 1},
    "zerodha.orders.submitted.dlq": {"partitions": 1, "replication_factor": 1},
}


async def create_topics(bootstrap_servers="localhost:19092"):
    """Create all test topics"""
    admin_client = AIOKafkaAdmin(bootstrap_servers=bootstrap_servers)
    
    try:
        await admin_client.start()
        
        # Create topic objects
        topics_to_create = []
        for topic_name, config in TEST_TOPICS.items():
            topic = NewTopic(
                name=topic_name,
                num_partitions=config["partitions"],
                replication_factor=config["replication_factor"]
            )
            topics_to_create.append(topic)
        
        # Create topics
        logger.info(f"Creating {len(topics_to_create)} topics...")
        
        try:
            await admin_client.create_topics(topics_to_create)
            logger.info("Successfully created all topics")
        except TopicAlreadyExistsError as e:
            logger.info("Some topics already exist, continuing...")
        except Exception as e:
            logger.error(f"Error creating topics: {e}")
            raise
        
        # List created topics to verify
        metadata = await admin_client.list_consumer_groups()
        logger.info("Topic creation completed")
        
    except Exception as e:
        logger.error(f"Failed to create topics: {e}")
        sys.exit(1)
    finally:
        await admin_client.close()


async def verify_topics(bootstrap_servers="localhost:19092"):
    """Verify that all topics were created successfully"""
    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        enable_idempotence=True,
        acks='all'
    )
    
    try:
        await producer.start()
        
        # Get cluster metadata
        metadata = await producer.client.fetch_metadata()
        
        created_topics = set(metadata.topics.keys())
        expected_topics = set(TEST_TOPICS.keys())
        
        missing_topics = expected_topics - created_topics
        if missing_topics:
            logger.error(f"Missing topics: {missing_topics}")
            return False
        
        logger.info(f"Successfully verified {len(expected_topics)} topics")
        
        # Log topic details
        for topic_name in expected_topics:
            topic_metadata = metadata.topics[topic_name]
            partition_count = len(topic_metadata.partitions)
            logger.info(f"Topic: {topic_name} - Partitions: {partition_count}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to verify topics: {e}")
        return False
    finally:
        await producer.stop()


async def main():
    """Main function to bootstrap test topics"""
    logger.info("Alpha Panda Test Topic Bootstrap")
    logger.info("=" * 40)
    
    # Check if we're running in test environment
    bootstrap_servers = "localhost:19092"  # Test Redpanda port
    
    try:
        # Create topics
        await create_topics(bootstrap_servers)
        
        # Verify topics were created
        await asyncio.sleep(2)  # Give topics time to be created
        success = await verify_topics(bootstrap_servers)
        
        if success:
            logger.info("✅ Test topic bootstrap completed successfully!")
            sys.exit(0)
        else:
            logger.error("❌ Test topic verification failed!")
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Bootstrap cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
