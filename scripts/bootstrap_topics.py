# CRITICAL - Create topics with proper partitions
import asyncio
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from core.schemas.topics import TopicConfig
from core.config.settings import Settings


async def create_topics():
    """Create all required topics with proper partition counts"""
    
    settings = Settings()
    admin_client = AIOKafkaAdminClient(
        bootstrap_servers=settings.redpanda.bootstrap_servers,
        client_id="alpha-panda-admin"
    )
    
    try:
        await admin_client.start()
        print("Connected to Redpanda admin API")
        
        # Get existing topics
        metadata = await admin_client.describe_cluster()
        existing_topics = await admin_client.list_topics()
        
        # Create topics that don't exist
        topics_to_create = []
        
        for topic_name, config in TopicConfig.CONFIGS.items():
            if topic_name not in existing_topics:
                new_topic = NewTopic(
                    name=topic_name,
                    num_partitions=config["partitions"],
                    replication_factor=config["replication_factor"],
                    topic_configs=config.get("config", {})
                )
                topics_to_create.append(new_topic)
                print(f"Will create topic: {topic_name} with {config['partitions']} partitions")
            else:
                print(f"Topic already exists: {topic_name}")
        
        if topics_to_create:
            await admin_client.create_topics(topics_to_create)
            print(f"Successfully created {len(topics_to_create)} topics")
            
            # Verify topic creation
            await asyncio.sleep(2)  # Wait for topic creation to propagate
            updated_topics = await admin_client.list_topics()
            
            for topic in topics_to_create:
                if topic.name in updated_topics:
                    print(f"✓ Verified topic: {topic.name}")
                else:
                    print(f"✗ Failed to verify topic: {topic.name}")
        else:
            print("All topics already exist")
            
    except Exception as e:
        print(f"Error creating topics: {e}")
        raise
    finally:
        await admin_client.close()


async def main():
    """Bootstrap topics for Alpha Panda"""
    print("Bootstrapping Alpha Panda topics...")
    await create_topics()
    print("Topic bootstrap complete!")


if __name__ == "__main__":
    asyncio.run(main())