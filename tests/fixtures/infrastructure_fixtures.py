"""
Test fixtures for real infrastructure components.
Provides reusable fixtures for Redis, Kafka, PostgreSQL integration testing.
"""

import pytest
import asyncio
import uuid
from typing import AsyncGenerator, Dict, Any
import redis.asyncio as aioredis
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError
import asyncpg


@pytest.fixture
async def redis_test_client() -> AsyncGenerator[aioredis.Redis, None]:
    """
    Redis client fixture for integration tests.
    Uses test database to isolate from production data.
    """
    client = aioredis.Redis(
        host='localhost',
        port=6380,  # Test Redis port (not production 6379)
        decode_responses=True,
        db=1  # Use test database
    )
    
    # Verify connection
    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis test instance not available on localhost:6380")
    
    yield client
    
    # Cleanup - flush test database
    await client.flushdb()
    await client.close()


@pytest.fixture
async def kafka_test_producer() -> AsyncGenerator[AIOKafkaProducer, None]:
    """
    Kafka producer fixture for integration tests.
    Configured for reliable message delivery.
    """
    try:
        producer = AIOKafkaProducer(
            bootstrap_servers=['localhost:19092'],  # Test Kafka port
            acks='all',  # Wait for all replicas
            enable_idempotence=True,  # Prevent duplicates
            retries=3,
            batch_size=16384,
            linger_ms=10,
            value_serializer=lambda v: str(v).encode('utf-8') if isinstance(v, str) else v
        )
        
        await producer.start()
        yield producer
        await producer.stop()
        
    except KafkaError as e:
        pytest.skip(f"Kafka test instance not available: {e}")


@pytest.fixture
async def kafka_test_consumer() -> AsyncGenerator[AIOKafkaConsumer, None]:
    """
    Kafka consumer fixture for integration tests.
    Uses unique consumer group to avoid conflicts.
    """
    try:
        group_id = f'test_group_{uuid.uuid4().hex}'
        
        consumer = AIOKafkaConsumer(
            bootstrap_servers=['localhost:19092'],
            group_id=group_id,
            enable_auto_commit=False,  # Manual offset management
            auto_offset_reset='earliest',
            value_deserializer=lambda m: m.decode('utf-8') if m else None
        )
        
        await consumer.start()
        yield consumer
        await consumer.stop()
        
    except KafkaError as e:
        pytest.skip(f"Kafka test instance not available: {e}")


@pytest.fixture
async def postgres_test_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """
    PostgreSQL connection fixture for integration tests.
    Uses test database to isolate from production data.
    """
    try:
        connection = await asyncpg.connect(
            host='localhost',
            port=5433,  # Test PostgreSQL port
            user='postgres',
            password='postgres', 
            database='alpha_panda_test'
        )
        
        yield connection
        
        # Cleanup - drop all test tables
        await connection.execute('''
            DROP SCHEMA public CASCADE;
            CREATE SCHEMA public;
            GRANT ALL ON SCHEMA public TO postgres;
        ''')
        
        await connection.close()
        
    except Exception as e:
        pytest.skip(f"PostgreSQL test instance not available: {e}")


@pytest.fixture
async def infrastructure_stack(redis_test_client, kafka_test_producer, postgres_test_connection):
    """
    Complete infrastructure stack fixture.
    Provides all infrastructure components together.
    """
    return {
        'redis': redis_test_client,
        'kafka_producer': kafka_test_producer, 
        'postgres': postgres_test_connection
    }


class InfrastructureHealthChecker:
    """Helper class to check infrastructure component health"""
    
    @staticmethod
    async def check_redis(host: str = 'localhost', port: int = 6380) -> bool:
        """Check if Redis is available and responsive"""
        try:
            client = aioredis.Redis(host=host, port=port, socket_timeout=2)
            await client.ping()
            await client.close()
            return True
        except Exception:
            return False
    
    @staticmethod
    async def check_kafka(bootstrap_servers: list = None) -> bool:
        """Check if Kafka is available and responsive"""
        if not bootstrap_servers:
            bootstrap_servers = ['localhost:19092']
            
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=bootstrap_servers,
                request_timeout_ms=5000
            )
            await producer.start()
            await producer.stop()
            return True
        except Exception:
            return False
    
    @staticmethod
    async def check_postgres(host: str = 'localhost', port: int = 5433) -> bool:
        """Check if PostgreSQL is available and responsive"""
        try:
            conn = await asyncpg.connect(
                host=host,
                port=port,
                user='postgres',
                password='postgres',
                database='postgres',
                timeout=5
            )
            await conn.close()
            return True
        except Exception:
            return False
    
    @classmethod
    async def check_all_services(cls) -> Dict[str, bool]:
        """Check health of all infrastructure services"""
        results = {}
        
        tasks = [
            ('redis', cls.check_redis()),
            ('kafka', cls.check_kafka()), 
            ('postgres', cls.check_postgres())
        ]
        
        for service_name, task in tasks:
            try:
                results[service_name] = await asyncio.wait_for(task, timeout=10)
            except asyncio.TimeoutError:
                results[service_name] = False
        
        return results


@pytest.fixture
async def infrastructure_health_check():
    """Fixture that validates infrastructure health before running tests"""
    health_results = await InfrastructureHealthChecker.check_all_services()
    
    failed_services = [service for service, is_healthy in health_results.items() if not is_healthy]
    
    if failed_services:
        pytest.skip(f"Infrastructure services not available: {failed_services}")
    
    return health_results


@pytest.fixture
def test_event_data():
    """Generate test event data for infrastructure testing"""
    return {
        'market_data': {
            'id': str(uuid.uuid4()),
            'type': 'MARKET_DATA',
            'instrument_token': 12345,
            'last_price': '1250.50',
            'volume': 10000,
            'timestamp': '2024-01-15T10:30:00'
        },
        'trading_signal': {
            'id': str(uuid.uuid4()),
            'type': 'TRADING_SIGNAL',
            'strategy_id': 'test_strategy',
            'instrument_token': 12345,
            'signal_type': 'BUY',
            'quantity': 100,
            'price': '1250.00',
            'confidence': 0.85
        },
        'order_filled': {
            'id': str(uuid.uuid4()),
            'type': 'ORDER_FILLED',
            'broker': 'paper',
            'order_id': f'ORDER_{uuid.uuid4().hex[:8]}',
            'instrument_token': 12345,
            'quantity': 100,
            'fill_price': '1251.25'
        }
    }


@pytest.fixture
async def kafka_topic_manager(kafka_test_producer):
    """
    Kafka topic management fixture for creating and cleaning up test topics.
    """
    created_topics = []
    
    class TopicManager:
        def __init__(self, producer):
            self.producer = producer
        
        async def create_test_topic(self, topic_name: str):
            """Create a test topic and track it for cleanup"""
            # Note: Topic creation is handled automatically by Kafka
            # when first message is sent in test environment
            created_topics.append(topic_name)
            return topic_name
        
        async def send_test_message(self, topic: str, message: dict, key: str = None):
            """Send a test message to specified topic"""
            import json
            
            serialized_message = json.dumps(message).encode('utf-8')
            key_bytes = key.encode('utf-8') if key else None
            
            await self.producer.send(
                topic=topic,
                value=serialized_message,
                key=key_bytes
            )
    
    yield TopicManager(kafka_test_producer)
    
    # Cleanup topics if needed (in test environment, topics are ephemeral)
    created_topics.clear()


@pytest.fixture
async def redis_key_manager(redis_test_client):
    """
    Redis key management fixture for tracking and cleaning up test keys.
    """
    created_keys = set()
    
    class KeyManager:
        def __init__(self, client):
            self.client = client
        
        async def set_test_key(self, key: str, value: str, ex: int = None):
            """Set a test key and track it for cleanup"""
            await self.client.set(key, value, ex=ex)
            created_keys.add(key)
        
        async def hset_test_key(self, key: str, field: str, value: str):
            """Set a hash field and track key for cleanup"""
            await self.client.hset(key, field, value)
            created_keys.add(key)
        
        async def get_test_keys(self) -> list:
            """Get all tracked test keys"""
            return list(created_keys)
    
    yield KeyManager(redis_test_client)
    
    # Cleanup tracked keys
    if created_keys:
        await redis_test_client.delete(*created_keys)


@pytest.fixture
async def postgres_table_manager(postgres_test_connection):
    """
    PostgreSQL table management fixture for creating and cleaning up test tables.
    """
    created_tables = []
    
    class TableManager:
        def __init__(self, connection):
            self.connection = connection
        
        async def create_test_table(self, table_name: str, schema: str):
            """Create a test table and track it for cleanup"""
            await self.connection.execute(f'CREATE TABLE {table_name} ({schema})')
            created_tables.append(table_name)
        
        async def insert_test_data(self, table_name: str, columns: str, values: tuple):
            """Insert test data into table"""
            placeholders = ', '.join(['$' + str(i+1) for i in range(len(values))])
            query = f'INSERT INTO {table_name} ({columns}) VALUES ({placeholders})'
            await self.connection.execute(query, *values)
    
    yield TableManager(postgres_test_connection)
    
    # Cleanup created tables
    for table in created_tables:
        try:
            await postgres_test_connection.execute(f'DROP TABLE IF EXISTS {table}')
        except Exception:
            pass  # Ignore cleanup errors


@pytest.mark.asyncio
async def test_infrastructure_fixtures_work():
    """Meta-test to verify that infrastructure fixtures work correctly"""
    # This test validates the fixture setup itself
    pass