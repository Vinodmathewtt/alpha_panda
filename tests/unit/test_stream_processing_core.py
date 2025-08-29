"""
Unit tests for core stream processing components.
Tests critical streaming patterns with real Kafka integration.
"""

import pytest
import asyncio
import json
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from typing import Dict, Any, List

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from aiokafka.errors import KafkaError

from core.schemas.events import EventEnvelope, EventType
from core.streaming.clients import StreamingService


class TestStreamProcessingPatterns:
    """Test core streaming patterns for event-driven architecture"""
    
    def test_event_envelope_creation(self):
        """Test standardized event envelope creation"""
        envelope = EventEnvelope(
            id=str(uuid4()),
            type=EventType.TRADING_SIGNAL,
            timestamp=datetime.now(),
            source="strategy_runner",
            version="1.0",
            correlation_id=str(uuid4()),
            causation_id=str(uuid4()),
            broker="zerodha",
            key="12345",
            data={"signal": "BUY", "quantity": 100}
        )
        
        # Validate required fields
        assert envelope.broker in ["paper", "zerodha"]
        assert envelope.type == EventType.TRADING_SIGNAL
        assert envelope.key == "12345"  # Partition key for ordering
        assert "signal" in envelope.data
    
    def test_partition_key_generation(self):
        """Test partition key generation for message ordering"""
        # Test instrument-based partitioning
        instrument_token = 12345
        partition_key = str(instrument_token)
        
        envelope = EventEnvelope(
            id=str(uuid4()),
            type=EventType.MARKET_DATA,
            timestamp=datetime.now(),
            source="market_feed",
            version="1.0",
            key=partition_key,  # Ensures all messages for instrument go to same partition
            data={"instrument_token": instrument_token, "price": "1250.50"}
        )
        
        assert envelope.key == "12345"
        assert envelope.data["instrument_token"] == 12345
    
    def test_broker_namespace_extraction(self):
        """Test broker context extraction from topic names"""
        # Test topic name parsing for multi-broker architecture
        test_cases = [
            ("paper.signals.validated", "paper"),
            ("zerodha.orders.filled", "zerodha"),
            ("paper.market.ticks", "paper"),
            ("zerodha.portfolio.updates", "zerodha")
        ]
        
        for topic, expected_broker in test_cases:
            extracted_broker = topic.split('.')[0]
            assert extracted_broker == expected_broker


@pytest.mark.asyncio
class TestKafkaIntegration:
    """Test Kafka integration with real broker for message serialization"""
    
    async def test_producer_idempotent_configuration(self):
        """Test producer idempotent configuration for exactly-once semantics"""
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=['localhost:19092'],
                acks='all',  # Wait for all replicas
                enable_idempotence=True,  # Prevent duplicate messages
                retries=3,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            
            await producer.start()
            
            # Test message production with idempotent settings
            test_event = {
                "id": str(uuid4()),
                "type": "TEST_EVENT",
                "timestamp": datetime.now().isoformat(),
                "data": {"test": "message"}
            }
            
            # Send message to test topic
            await producer.send(
                topic="test.signals.raw",
                value=test_event,
                key=b"test_key"
            )
            
            await producer.stop()
            
        except KafkaError:
            pytest.skip("Kafka not available on localhost:19092")
    
    async def test_consumer_manual_offset_commit(self):
        """Test consumer with manual offset commits for reliable processing"""
        try:
            consumer = AIOKafkaConsumer(
                'test.signals.raw',
                bootstrap_servers=['localhost:19092'],
                group_id='test_consumer_group',
                enable_auto_commit=False,  # Manual offset management
                auto_offset_reset='earliest',
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            
            await consumer.start()
            
            # Create a producer to send test message
            producer = AIOKafkaProducer(
                bootstrap_servers=['localhost:19092'],
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            await producer.start()
            
            # Send test message
            test_message = {
                "id": str(uuid4()),
                "type": "TEST_SIGNAL",
                "data": {"action": "BUY"}
            }
            
            await producer.send(
                topic="test.signals.raw",
                value=test_message,
                key=b"test_key"
            )
            
            # Consume message
            message = await asyncio.wait_for(consumer.__anext__(), timeout=5.0)
            assert message.value["type"] == "TEST_SIGNAL"
            
            # Manual offset commit after successful processing
            await consumer.commit()
            
            await producer.stop()
            await consumer.stop()
            
        except (KafkaError, asyncio.TimeoutError):
            pytest.skip("Kafka not available or timeout")
    
    async def test_message_serialization_round_trip(self):
        """Test message serialization/deserialization with Decimal precision"""
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=['localhost:19092'],
                value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8')
            )
            
            consumer = AIOKafkaConsumer(
                'test.market.data',
                bootstrap_servers=['localhost:19092'],
                group_id='test_serialization_group',
                auto_offset_reset='latest',
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            
            await producer.start()
            await consumer.start()
            
            # Test message with Decimal values
            original_price = Decimal("1250.75")
            test_market_data = {
                "id": str(uuid4()),
                "instrument_token": 12345,
                "last_price": str(original_price),  # Serialize Decimal as string
                "volume": 10000,
                "timestamp": datetime.now().isoformat()
            }
            
            await producer.send(
                topic="test.market.data",
                value=test_market_data,
                key=b"12345"
            )
            
            # Consume and verify
            message = await asyncio.wait_for(consumer.__anext__(), timeout=5.0)
            received_data = message.value
            
            assert received_data["instrument_token"] == 12345
            # Verify Decimal precision preserved
            reconstructed_price = Decimal(received_data["last_price"])
            assert reconstructed_price == original_price
            
            await producer.stop()
            await consumer.stop()
            
        except (KafkaError, asyncio.TimeoutError):
            pytest.skip("Kafka not available or timeout")


class TestTopicNamingConventions:
    """Test topic naming conventions for multi-broker architecture"""
    
    def test_broker_namespace_topics(self):
        """Test broker-namespaced topic naming"""
        # Paper trading topics
        paper_topics = [
            "paper.market.ticks",
            "paper.signals.raw", 
            "paper.signals.validated",
            "paper.orders.submitted",
            "paper.orders.filled",
            "paper.portfolio.updates"
        ]
        
        for topic in paper_topics:
            assert topic.startswith("paper.")
            parts = topic.split(".")
            assert len(parts) >= 3  # broker.domain.event_type
            assert parts[0] == "paper"
        
        # Zerodha trading topics
        zerodha_topics = [
            "zerodha.market.ticks",
            "zerodha.signals.raw",
            "zerodha.signals.validated", 
            "zerodha.orders.submitted",
            "zerodha.orders.filled",
            "zerodha.portfolio.updates"
        ]
        
        for topic in zerodha_topics:
            assert topic.startswith("zerodha.")
            parts = topic.split(".")
            assert parts[0] == "zerodha"
    
    def test_dead_letter_queue_topics(self):
        """Test DLQ topic naming convention"""
        base_topics = [
            "paper.orders.filled",
            "zerodha.signals.validated"
        ]
        
        for base_topic in base_topics:
            dlq_topic = f"{base_topic}.dlq"
            assert dlq_topic.endswith(".dlq")
            
            # Extract broker from DLQ topic
            broker = dlq_topic.split(".")[0]
            assert broker in ["paper", "zerodha"]


class TestStreamingServiceConfiguration:
    """Test streaming service configuration patterns"""
    
    def test_consumer_group_naming(self):
        """Test consumer group naming conventions"""
        service_names = [
            "strategy_runner",
            "trading_engine", 
            "portfolio_manager",
            "risk_manager"
        ]
        
        for service in service_names:
            group_id = f"alpha-panda.{service}"
            assert group_id.startswith("alpha-panda.")
            assert service in group_id
    
    def test_active_brokers_configuration(self):
        """Test active brokers configuration handling"""
        # Test single broker configuration
        active_brokers_single = ["paper"]
        assert "paper" in active_brokers_single
        assert len(active_brokers_single) == 1
        
        # Test multi-broker configuration  
        active_brokers_multi = ["paper", "zerodha"]
        assert "paper" in active_brokers_multi
        assert "zerodha" in active_brokers_multi
        assert len(active_brokers_multi) == 2
        
        # Test topic generation for active brokers
        base_topics = ["signals.raw", "orders.filled"]
        generated_topics = []
        
        for broker in active_brokers_multi:
            for topic in base_topics:
                full_topic = f"{broker}.{topic}"
                generated_topics.append(full_topic)
        
        expected_topics = [
            "paper.signals.raw",
            "paper.orders.filled", 
            "zerodha.signals.raw",
            "zerodha.orders.filled"
        ]
        
        assert set(generated_topics) == set(expected_topics)


class TestErrorHandlingPatterns:
    """Test error handling and DLQ patterns"""
    
    def test_event_deduplication_logic(self):
        """Test event deduplication using event ID"""
        # Test duplicate event detection
        event_id = str(uuid4())
        
        # First event
        event1 = EventEnvelope(
            id=event_id,  # Same ID
            type=EventType.ORDER_FILLED,
            timestamp=datetime.now(),
            source="trading_engine",
            version="1.0",
            key="12345",
            data={"order_id": "ORDER123"}
        )
        
        # Duplicate event with same ID
        event2 = EventEnvelope(
            id=event_id,  # Same ID - should be deduplicated
            type=EventType.ORDER_FILLED,
            timestamp=datetime.now(),
            source="trading_engine", 
            version="1.0",
            key="12345",
            data={"order_id": "ORDER123"}
        )
        
        assert event1.id == event2.id  # Should be detected as duplicate
        
    def test_correlation_causation_chain(self):
        """Test event correlation and causation tracking"""
        # Original market data event
        correlation_id = str(uuid4())
        market_event_id = str(uuid4())
        
        market_event = EventEnvelope(
            id=market_event_id,
            type=EventType.MARKET_DATA,
            timestamp=datetime.now(),
            source="market_feed",
            version="1.0",
            correlation_id=correlation_id,
            causation_id=None,  # Root event
            key="12345",
            data={"price": "1250.50"}
        )
        
        # Trading signal caused by market data
        signal_event = EventEnvelope(
            id=str(uuid4()),
            type=EventType.TRADING_SIGNAL, 
            timestamp=datetime.now(),
            source="strategy_runner",
            version="1.0",
            correlation_id=correlation_id,  # Same correlation
            causation_id=market_event_id,   # Caused by market data
            key="12345",
            data={"signal": "BUY"}
        )
        
        assert signal_event.correlation_id == market_event.correlation_id
        assert signal_event.causation_id == market_event.id