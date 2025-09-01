"""
CRITICAL - Create topics with proper partitions and environment overlays

Supports environment-aware overrides so production can set higher
replication factors and partitions without changing source.

Environment controls:
- SETTINGS__ENVIRONMENT or Settings.environment: development|testing|production
- REDPANDA_BROKER_COUNT: int (optional, default 1)
- TOPIC_PARTITIONS_MULTIPLIER: float (optional, default 1.0)
- CREATE_DLQ_FOR_ALL: bool-like (optional, default true) to create per-topic .dlq
"""

import os
import math
import asyncio
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from core.schemas.topics import TopicConfig
from core.config.settings import Settings


def _as_bool(val: str, default: bool = True) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _effective_topic_config(config: dict, env: str, broker_count: int, partitions_multiplier: float) -> dict:
    """Compute environment-aware topic config."""
    base_partitions = int(config.get("partitions", 1))
    base_rf = int(config.get("replication_factor", 1))

    # Partitions overlay
    partitions = max(1, int(math.ceil(base_partitions * max(0.1, partitions_multiplier))))

    # Replication overlay: prefer RF>=3 in production, capped by broker_count
    if env == "production":
        target_rf = 3 if broker_count >= 3 else broker_count
    else:
        target_rf = min(base_rf, broker_count) if broker_count > 0 else base_rf
    replication_factor = max(1, target_rf)

    return {
        "partitions": partitions,
        "replication_factor": replication_factor,
        "config": config.get("config", {}),
    }


async def create_topics():
    """Create all required topics with proper partition counts and overlays"""
    
    settings = Settings()
    admin_client = AIOKafkaAdminClient(
        bootstrap_servers=settings.redpanda.bootstrap_servers,
        client_id="alpha-panda-admin"
    )
    
    try:
        await admin_client.start()
        print("Connected to Redpanda admin API")
        
        # Resolve overlays
        env = (str(settings.environment) or "development").lower()
        # Enum may print like 'Environment.DEVELOPMENT'; normalize
        if "." in env:
            env = env.split(".")[-1]
        broker_count = int(os.getenv("REDPANDA_BROKER_COUNT", "1"))
        partitions_multiplier = float(os.getenv("TOPIC_PARTITIONS_MULTIPLIER", "1.0"))
        create_dlq_for_all = _as_bool(os.getenv("CREATE_DLQ_FOR_ALL", "true"))

        print(f"Environment: {env}; brokers={broker_count}; partitions_multiplier={partitions_multiplier}; dlq_all={create_dlq_for_all}")

        # Get existing topics
        metadata = await admin_client.describe_cluster()
        existing_topics = await admin_client.list_topics()

        # Create topics that don't exist
        topics_to_create = []

        base_configs = TopicConfig.CONFIGS.copy()
        for topic_name, config in base_configs.items():
            eff = _effective_topic_config(config, env, broker_count, partitions_multiplier)
            if topic_name not in existing_topics:
                new_topic = NewTopic(
                    name=topic_name,
                    num_partitions=eff["partitions"],
                    replication_factor=eff["replication_factor"],
                    topic_configs=eff.get("config", {})
                )
                topics_to_create.append(new_topic)
                print(f"Will create topic: {topic_name} with {eff['partitions']} partitions, RF={eff['replication_factor']}")
            else:
                print(f"Topic already exists: {topic_name}")

            # Optional: create per-topic DLQ for all topics (skip if already a DLQ topic)
            if create_dlq_for_all and not topic_name.endswith(".dlq"):
                dlq_name = f"{topic_name}.dlq"
                if dlq_name not in existing_topics:
                    dlq_eff = _effective_topic_config(config, env, broker_count, partitions_multiplier)
                    # DLQ typically needs fewer partitions
                    dlq_eff["partitions"] = max(1, dlq_eff["partitions"] // 2)
                    new_dlq = NewTopic(
                        name=dlq_name,
                        num_partitions=dlq_eff["partitions"],
                        replication_factor=dlq_eff["replication_factor"],
                        topic_configs=dlq_eff.get("config", {})
                    )
                    topics_to_create.append(new_dlq)
                    print(f"Will create DLQ topic: {dlq_name} with {dlq_eff['partitions']} partitions, RF={dlq_eff['replication_factor']}")
        
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
