"""
Integration tests using real Redis, Kafka, and PostgreSQL infrastructure.
These tests validate that services work correctly with actual infrastructure components.
"""

import pytest
import asyncio
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

import redis.asyncio as aioredis
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError
import asyncpg

from core.schemas.events import EventEnvelope, EventType, OrderFilled, MarketData
from core.config.settings import Settings


@pytest.fixture
async def redis_client():
    """Redis client fixture using test infrastructure"""
    client = aioredis.Redis(
        host='localhost',
        port=6380,  # Test Redis port
        decode_responses=True,
        db=1  # Use different DB for tests
    )
    yield client
    # Cleanup
    await client.flushdb()
    await client.close()


@pytest.fixture
async def kafka_producer():
    """Kafka producer fixture for test infrastructure"""
    try:
        producer = AIOKafkaProducer(
            bootstrap_servers=['localhost:19092'],  # Test Kafka port
            acks='all',
            enable_idempotence=True,
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
        )
        await producer.start()
        yield producer
        await producer.stop()
    except KafkaError:
        pytest.skip("Kafka not available on test infrastructure")


@pytest.fixture
async def kafka_consumer():
    """Kafka consumer fixture for test infrastructure"""
    try:
        consumer = AIOKafkaConsumer(
            bootstrap_servers=['localhost:19092'],
            group_id=f'test_group_{uuid.uuid4().hex}',
            enable_auto_commit=False,
            auto_offset_reset='earliest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        await consumer.start()
        yield consumer
        await consumer.stop()
    except KafkaError:
        pytest.skip("Kafka not available on test infrastructure")


@pytest.fixture
async def postgres_connection():
    """PostgreSQL connection fixture for test infrastructure"""
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port=5433,  # Test PostgreSQL port
            user='postgres',
            password='postgres',
            database='alpha_panda_test'
        )
        yield conn
        await conn.close()
    except Exception:
        pytest.skip("PostgreSQL not available on test infrastructure")


@pytest.mark.asyncio
class TestRedisIntegrationPatterns:
    """Test Redis integration patterns used by services"""
    
    async def test_portfolio_cache_operations(self, redis_client):
        """Test portfolio caching patterns with real Redis"""
        broker = "zerodha"
        
        # Test portfolio balance caching
        balance_key = f"{broker}:portfolio:balance"
        await redis_client.set(balance_key, "150000.50")
        
        # Retrieve and validate type handling
        balance = await redis_client.get(balance_key)
        assert balance == "150000.50"
        assert isinstance(balance, str)  # With decode_responses=True
        
        # Test position caching with hash
        positions_key = f"{broker}:portfolio:positions"
        instrument_token = "12345"
        quantity = "100"
        
        await redis_client.hset(positions_key, instrument_token, quantity)
        stored_quantity = await redis_client.hget(positions_key, instrument_token)
        
        assert stored_quantity == quantity
        assert isinstance(stored_quantity, str)
        
        # Test position retrieval
        all_positions = await redis_client.hgetall(positions_key)
        assert instrument_token in all_positions
        assert all_positions[instrument_token] == quantity
    
    async def test_event_deduplication_with_redis(self, redis_client):
        """Test event deduplication using Redis with real client"""
        event_id = str(uuid.uuid4())
        dedup_key = f"event:processed:{event_id}"
        
        # Check if event already processed
        exists = await redis_client.exists(dedup_key)
        assert exists == 0  # Should not exist initially
        
        # Mark event as processed
        await redis_client.setex(dedup_key, 3600, "processed")  # 1 hour TTL
        
        # Verify deduplication works
        exists_now = await redis_client.exists(dedup_key)
        assert exists_now == 1
        
        # Verify TTL is set
        ttl = await redis_client.ttl(dedup_key)
        assert ttl > 0 and ttl <= 3600
    
    async def test_cache_key_isolation_by_broker(self, redis_client):
        """Test that broker cache keys are properly isolated"""
        # Test data for different brokers
        paper_balance = "50000.00"
        zerodha_balance = "100000.00"
        
        # Set balances for different brokers
        await redis_client.set("paper:portfolio:balance", paper_balance)
        await redis_client.set("zerodha:portfolio:balance", zerodha_balance)
        
        # Verify isolation - each broker sees only its own data
        paper_retrieved = await redis_client.get("paper:portfolio:balance")
        zerodha_retrieved = await redis_client.get("zerodha:portfolio:balance")
        
        assert paper_retrieved == paper_balance
        assert zerodha_retrieved == zerodha_balance
        assert paper_retrieved != zerodha_retrieved
        
        # Test pattern-based key retrieval
        paper_keys = await redis_client.keys("paper:*")
        zerodha_keys = await redis_client.keys("zerodha:*")
        
        assert len(paper_keys) >= 1
        assert len(zerodha_keys) >= 1
        assert all(key.startswith("paper:") for key in paper_keys)
        assert all(key.startswith("zerodha:") for key in zerodha_keys)


@pytest.mark.asyncio 
class TestKafkaIntegrationPatterns:
    """Test Kafka integration patterns used by services"""
    
    async def test_multi_broker_topic_routing(self, kafka_producer, kafka_consumer):
        """Test multi-broker topic routing with real Kafka"""
        # Test topics for different brokers
        paper_topic = "paper.signals.validated"
        zerodha_topic = "zerodha.signals.validated"
        
        # Subscribe to both topics
        await kafka_consumer.subscribe([paper_topic, zerodha_topic])
        
        # Send signal to paper broker
        paper_signal = {
            "id": str(uuid.uuid4()),
            "type": "TRADING_SIGNAL",
            "broker": "paper",
            "strategy_id": "momentum_test",
            "instrument_token": 12345,
            "signal_type": "BUY",
            "quantity": 100,
            "timestamp": datetime.now().isoformat()
        }
        
        await kafka_producer.send(
            topic=paper_topic,
            value=paper_signal,
            key=b"12345"  # Partition key for ordering
        )
        
        # Send signal to zerodha broker
        zerodha_signal = {
            "id": str(uuid.uuid4()),
            "type": "TRADING_SIGNAL", 
            "broker": "zerodha",
            "strategy_id": "momentum_test",
            "instrument_token": 12345,
            "signal_type": "SELL",
            "quantity": 50,
            "timestamp": datetime.now().isoformat()
        }
        
        await kafka_producer.send(
            topic=zerodha_topic,
            value=zerodha_signal,
            key=b"12345"
        )
        
        # Consume messages and verify routing
        messages_received = []
        timeout_count = 0
        
        while len(messages_received) < 2 and timeout_count < 10:
            try:
                message = await asyncio.wait_for(kafka_consumer.__anext__(), timeout=1.0)
                messages_received.append(message)
            except asyncio.TimeoutError:
                timeout_count += 1
                continue
        
        assert len(messages_received) >= 2
        
        # Verify messages are routed to correct topics
        topic_messages = {msg.topic: msg.value for msg in messages_received}
        
        if paper_topic in topic_messages:
            paper_msg = topic_messages[paper_topic]
            assert paper_msg["broker"] == "paper"
            assert paper_msg["signal_type"] == "BUY"
        
        if zerodha_topic in topic_messages:
            zerodha_msg = topic_messages[zerodha_topic]
            assert zerodha_msg["broker"] == "zerodha" 
            assert zerodha_msg["signal_type"] == "SELL"
    
    async def test_event_envelope_serialization(self, kafka_producer, kafka_consumer):
        """Test EventEnvelope serialization/deserialization with real Kafka"""
        test_topic = "test.events.envelope"
        await kafka_consumer.subscribe([test_topic])
        
        # Create EventEnvelope with Decimal values
        order_filled = OrderFilled(
            broker="zerodha",
            order_id="ORDER_123",
            instrument_token=12345,
            quantity=100,
            fill_price=Decimal("1250.75"),
            timestamp=datetime.now()
        )
        
        envelope = EventEnvelope(
            id=str(uuid.uuid4()),
            type=EventType.ORDER_FILLED,
            timestamp=datetime.now(),
            source="trading_engine",
            version="1.0",
            correlation_id=str(uuid.uuid4()),
            causation_id=str(uuid.uuid4()),
            broker="zerodha",
            key="12345",
            data=order_filled.model_dump()
        )
        
        # Send envelope through Kafka
        await kafka_producer.send(
            topic=test_topic,
            value=envelope.model_dump(),
            key=envelope.key.encode('utf-8')
        )
        
        # Receive and reconstruct
        try:
            message = await asyncio.wait_for(kafka_consumer.__anext__(), timeout=5.0)
            received_data = message.value
            
            # Reconstruct envelope
            reconstructed_envelope = EventEnvelope.model_validate(received_data)
            
            # Verify data integrity
            assert reconstructed_envelope.type == EventType.ORDER_FILLED
            assert reconstructed_envelope.broker == "zerodha"
            assert reconstructed_envelope.key == "12345"
            
            # Reconstruct order data
            reconstructed_order = OrderFilled.model_validate(reconstructed_envelope.data)
            assert reconstructed_order.fill_price == order_filled.fill_price
            assert reconstructed_order.order_id == order_filled.order_id
            
        except asyncio.TimeoutError:
            pytest.fail("Failed to receive message from Kafka within timeout")
    
    async def test_partition_key_ordering(self, kafka_producer, kafka_consumer):
        """Test message ordering within partitions using partition keys"""
        test_topic = "test.ordering.partition"
        await kafka_consumer.subscribe([test_topic])
        
        instrument_token = "12345"
        partition_key = instrument_token.encode('utf-8')
        
        # Send multiple messages with same partition key (should maintain order)
        messages_sent = []
        for i in range(5):
            message = {
                "id": str(uuid.uuid4()),
                "sequence": i,
                "instrument_token": int(instrument_token),
                "price": f"125{i}.50",
                "timestamp": datetime.now().isoformat()
            }
            messages_sent.append(message)
            
            await kafka_producer.send(
                topic=test_topic,
                value=message,
                key=partition_key  # Same partition key ensures ordering
            )
        
        # Consume messages and verify ordering
        messages_received = []
        timeout_count = 0
        
        while len(messages_received) < 5 and timeout_count < 10:
            try:
                message = await asyncio.wait_for(kafka_consumer.__anext__(), timeout=1.0)
                messages_received.append(message)
            except asyncio.TimeoutError:
                timeout_count += 1
                continue
        
        assert len(messages_received) >= 5
        
        # Verify messages are in order (same partition key guarantees ordering)
        received_sequences = [msg.value["sequence"] for msg in messages_received]
        assert received_sequences == sorted(received_sequences)


@pytest.mark.asyncio
class TestDatabaseIntegrationPatterns:
    """Test database integration patterns used by services"""
    
    async def test_strategy_configuration_storage(self, postgres_connection):
        """Test strategy configuration storage and retrieval"""
        # Create test table (simplified schema)
        await postgres_connection.execute('''
            CREATE TABLE IF NOT EXISTS test_strategies (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                config JSONB NOT NULL,
                active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert test strategy configuration
        strategy_config = {
            "strategy_type": "momentum",
            "parameters": {
                "lookback_period": 20,
                "threshold": 0.02
            },
            "instruments": [12345, 67890],
            "brokers": ["paper", "zerodha"]
        }
        
        await postgres_connection.execute('''
            INSERT INTO test_strategies (name, config)
            VALUES ($1, $2)
        ''', 'test_momentum', json.dumps(strategy_config))
        
        # Retrieve and validate
        row = await postgres_connection.fetchrow('''
            SELECT name, config, active FROM test_strategies 
            WHERE name = $1
        ''', 'test_momentum')
        
        assert row['name'] == 'test_momentum'
        assert row['active'] is True
        
        retrieved_config = json.loads(row['config'])
        assert retrieved_config['strategy_type'] == 'momentum'
        assert retrieved_config['parameters']['lookback_period'] == 20
        assert 12345 in retrieved_config['instruments']
        
        # Cleanup
        await postgres_connection.execute('DROP TABLE test_strategies')
    
    async def test_instrument_metadata_storage(self, postgres_connection):
        """Test instrument metadata storage for trading"""
        # Create instruments table
        await postgres_connection.execute('''
            CREATE TABLE IF NOT EXISTS test_instruments (
                token INTEGER PRIMARY KEY,
                symbol VARCHAR(50) NOT NULL,
                exchange VARCHAR(20) NOT NULL,
                lot_size INTEGER NOT NULL,
                tick_size DECIMAL(10,4) NOT NULL
            )
        ''')
        
        # Insert test instrument data
        instruments = [
            (12345, 'RELIANCE', 'NSE', 1, Decimal('0.05')),
            (67890, 'TCS', 'NSE', 1, Decimal('0.05')),
            (54321, 'INFY', 'NSE', 1, Decimal('0.05'))
        ]
        
        for token, symbol, exchange, lot_size, tick_size in instruments:
            await postgres_connection.execute('''
                INSERT INTO test_instruments (token, symbol, exchange, lot_size, tick_size)
                VALUES ($1, $2, $3, $4, $5)
            ''', token, symbol, exchange, lot_size, tick_size)
        
        # Test instrument lookup
        reliance = await postgres_connection.fetchrow('''
            SELECT * FROM test_instruments WHERE token = $1
        ''', 12345)
        
        assert reliance['symbol'] == 'RELIANCE'
        assert reliance['exchange'] == 'NSE'
        assert reliance['tick_size'] == Decimal('0.05')
        
        # Test bulk instrument retrieval
        all_instruments = await postgres_connection.fetch('''
            SELECT token, symbol FROM test_instruments 
            ORDER BY token
        ''')
        
        assert len(all_instruments) == 3
        assert all_instruments[0]['token'] == 12345
        
        # Cleanup
        await postgres_connection.execute('DROP TABLE test_instruments')
    
    async def test_transaction_rollback_behavior(self, postgres_connection):
        """Test database transaction behavior for order processing"""
        # Create test table
        await postgres_connection.execute('''
            CREATE TABLE IF NOT EXISTS test_orders (
                id SERIAL PRIMARY KEY,
                order_id VARCHAR(50) UNIQUE NOT NULL,
                status VARCHAR(20) NOT NULL,
                amount DECIMAL(15,2) NOT NULL
            )
        ''')
        
        # Test successful transaction
        async with postgres_connection.transaction():
            await postgres_connection.execute('''
                INSERT INTO test_orders (order_id, status, amount)
                VALUES ($1, $2, $3)
            ''', 'ORDER_001', 'PLACED', Decimal('125000.50'))
        
        # Verify order was committed
        order = await postgres_connection.fetchrow('''
            SELECT * FROM test_orders WHERE order_id = $1
        ''', 'ORDER_001')
        assert order is not None
        assert order['status'] == 'PLACED'
        
        # Test transaction rollback on error
        try:
            async with postgres_connection.transaction():
                await postgres_connection.execute('''
                    INSERT INTO test_orders (order_id, status, amount)
                    VALUES ($1, $2, $3)
                ''', 'ORDER_002', 'PLACED', Decimal('75000.25'))
                
                # Simulate error condition
                raise Exception("Simulated error")
                
        except Exception:
            pass  # Expected to fail
        
        # Verify rollback worked
        rolled_back_order = await postgres_connection.fetchrow('''
            SELECT * FROM test_orders WHERE order_id = $1
        ''', 'ORDER_002')
        assert rolled_back_order is None  # Should not exist due to rollback
        
        # Cleanup
        await postgres_connection.execute('DROP TABLE test_orders')


@pytest.mark.asyncio
class TestCrossServiceIntegration:
    """Test integration patterns across multiple infrastructure components"""
    
    async def test_end_to_end_order_flow(self, redis_client, kafka_producer, kafka_consumer, postgres_connection):
        """Test complete order flow across Redis, Kafka, and PostgreSQL"""
        # Setup database
        await postgres_connection.execute('''
            CREATE TABLE IF NOT EXISTS test_orders (
                order_id VARCHAR(50) PRIMARY KEY,
                status VARCHAR(20),
                broker VARCHAR(20),
                instrument_token INTEGER,
                quantity INTEGER,
                price DECIMAL(15,2)
            )
        ''')
        
        # Setup Kafka topics
        order_topic = "test.orders.placed"
        fill_topic = "test.orders.filled" 
        
        await kafka_consumer.subscribe([order_topic, fill_topic])
        
        # Step 1: Place order (database storage)
        order_id = f"ORDER_{uuid.uuid4().hex[:8]}"
        await postgres_connection.execute('''
            INSERT INTO test_orders (order_id, status, broker, instrument_token, quantity, price)
            VALUES ($1, $2, $3, $4, $5, $6)
        ''', order_id, 'PLACED', 'zerodha', 12345, 100, Decimal('1250.50'))
        
        # Step 2: Send order placed event (Kafka)
        order_placed_event = {
            "id": str(uuid.uuid4()),
            "type": "ORDER_PLACED",
            "order_id": order_id,
            "broker": "zerodha", 
            "status": "PLACED",
            "timestamp": datetime.now().isoformat()
        }
        
        await kafka_producer.send(
            topic=order_topic,
            value=order_placed_event,
            key=order_id.encode('utf-8')
        )
        
        # Step 3: Cache order status (Redis)
        cache_key = f"zerodha:orders:status:{order_id}"
        await redis_client.set(cache_key, "PLACED")
        
        # Step 4: Simulate order fill
        fill_price = Decimal('1251.25')
        
        # Update database
        await postgres_connection.execute('''
            UPDATE test_orders SET status = $1, price = $2 
            WHERE order_id = $3
        ''', 'FILLED', fill_price, order_id)
        
        # Send fill event  
        order_filled_event = {
            "id": str(uuid.uuid4()),
            "type": "ORDER_FILLED",
            "order_id": order_id,
            "broker": "zerodha",
            "fill_price": str(fill_price),
            "quantity": 100,
            "timestamp": datetime.now().isoformat()
        }
        
        await kafka_producer.send(
            topic=fill_topic,
            value=order_filled_event,
            key=order_id.encode('utf-8')
        )
        
        # Update cache
        await redis_client.set(cache_key, "FILLED")
        
        # Step 5: Verify end-to-end consistency
        
        # Check database state
        db_order = await postgres_connection.fetchrow('''
            SELECT * FROM test_orders WHERE order_id = $1
        ''', order_id)
        assert db_order['status'] == 'FILLED'
        assert db_order['price'] == fill_price
        
        # Check cache state
        cached_status = await redis_client.get(cache_key)
        assert cached_status == 'FILLED'
        
        # Check Kafka messages
        messages_received = []
        timeout_count = 0
        
        while len(messages_received) < 2 and timeout_count < 10:
            try:
                message = await asyncio.wait_for(kafka_consumer.__anext__(), timeout=1.0)
                messages_received.append(message)
            except asyncio.TimeoutError:
                timeout_count += 1
                continue
        
        assert len(messages_received) >= 2
        
        # Verify message contents
        placed_messages = [msg for msg in messages_received if msg.topic == order_topic]
        filled_messages = [msg for msg in messages_received if msg.topic == fill_topic]
        
        assert len(placed_messages) >= 1
        assert len(filled_messages) >= 1
        
        placed_msg = placed_messages[0].value
        assert placed_msg['order_id'] == order_id
        assert placed_msg['type'] == 'ORDER_PLACED'
        
        filled_msg = filled_messages[0].value  
        assert filled_msg['order_id'] == order_id
        assert filled_msg['type'] == 'ORDER_FILLED'
        assert Decimal(filled_msg['fill_price']) == fill_price
        
        # Cleanup
        await postgres_connection.execute('DROP TABLE test_orders')
        await redis_client.delete(cache_key)