"""
Unit tests for EventEnvelope validation and schema compliance.
Tests critical event schemas that must work with real Kafka/Redis infrastructure.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from uuid import uuid4, UUID
import json
import redis.asyncio as aioredis

from core.schemas.events import (
    EventEnvelope, 
    EventType,
    OrderFilled,
    OrderPlaced,
    OrderFailed,
    MarketData,
    TradingSignal
)


class TestEventEnvelopeValidation:
    """Test EventEnvelope schema validation with real serialization"""
    
    def test_event_envelope_required_fields(self):
        """Test that EventEnvelope enforces all required fields"""
        # Valid envelope
        envelope = EventEnvelope(
            id=str(uuid4()),
            type=EventType.ORDER_FILLED,
            timestamp=datetime.now(),
            source="trading_engine",
            version="1.0",
            correlation_id=str(uuid4()),
            causation_id=str(uuid4()),
            broker="zerodha",
            key="12345",
            data={"test": "data"}
        )
        assert envelope.broker == "zerodha"
        assert envelope.type == EventType.ORDER_FILLED
        
        # Test missing required field raises validation error
        with pytest.raises(Exception):
            EventEnvelope(
                id=str(uuid4()),
                # Missing type - should fail
                timestamp=datetime.now(),
                source="trading_engine",
                version="1.0"
            )
    
    def test_order_filled_schema_compliance(self):
        """Test OrderFilled event has all required fields for Zerodha integration"""
        order_filled = OrderFilled(
            broker="zerodha",
            order_id="ORDER123",
            instrument_token=12345,
            quantity=100,
            fill_price=Decimal("1250.50"),
            timestamp=datetime.now()
        )
        
        # Validate all critical fields exist
        assert order_filled.broker == "zerodha"
        assert order_filled.order_id == "ORDER123"
        assert order_filled.instrument_token == 12345
        assert order_filled.quantity == 100
        assert isinstance(order_filled.fill_price, Decimal)
        assert order_filled.timestamp is not None
    
    def test_order_placed_schema_compliance(self):
        """Test OrderPlaced event schema for trading engine integration"""
        order_placed = OrderPlaced(
            broker="zerodha",
            status="PLACED",
            order_id="ORDER123",
            instrument_token=12345,
            signal_type="BUY",
            quantity=100,
            price=Decimal("1250.00"),
            timestamp=datetime.now()
        )
        
        assert order_placed.broker == "zerodha"
        assert order_placed.status == "PLACED"
        assert order_placed.signal_type == "BUY"
        assert isinstance(order_placed.price, Decimal)
    
    def test_order_failed_schema_compliance(self):
        """Test OrderFailed event schema for error handling"""
        order_failed = OrderFailed(
            broker="zerodha",
            strategy_id="momentum_strategy",
            instrument_token=12345,
            signal_type="SELL",
            quantity=50,
            order_id="ORDER456",
            execution_mode="LIVE",
            error_message="Insufficient funds",
            timestamp=datetime.now()
        )
        
        assert order_failed.broker == "zerodha"
        assert order_failed.strategy_id == "momentum_strategy"
        assert order_failed.execution_mode == "LIVE"
        assert order_failed.error_message == "Insufficient funds"


class TestEventSerializationRoundTrip:
    """Test event serialization/deserialization with real Redis/Kafka data types"""
    
    def test_json_serialization_decimal_preservation(self):
        """Test that Decimal values survive JSON round-trip"""
        original_price = Decimal("1250.75")
        order_filled = OrderFilled(
            broker="zerodha",
            order_id="ORDER789",
            instrument_token=12345,
            quantity=100,
            fill_price=original_price,
            timestamp=datetime.now()
        )
        
        # Serialize to JSON (like Kafka would do)
        json_data = order_filled.model_dump_json()
        parsed_data = json.loads(json_data)
        
        # Reconstruct and verify Decimal precision preserved
        reconstructed = OrderFilled.model_validate(parsed_data)
        assert reconstructed.fill_price == original_price
        assert isinstance(reconstructed.fill_price, Decimal)
    
    def test_datetime_serialization_consistency(self):
        """Test datetime serialization for event timestamps"""
        original_time = datetime.now()
        market_data = MarketData(
            instrument_token=12345,
            last_price=Decimal("1250.50"),
            volume=10000,
            timestamp=original_time
        )
        
        # Test JSON round-trip preserves datetime
        json_data = market_data.model_dump_json()
        reconstructed = MarketData.model_validate_json(json_data)
        
        # Timestamps should be equivalent (allowing for microsecond precision)
        time_diff = abs((reconstructed.timestamp - original_time).total_seconds())
        assert time_diff < 0.001  # Less than 1ms difference
    
    def test_trading_signal_validation(self):
        """Test TradingSignal schema for strategy output validation"""
        signal = TradingSignal(
            strategy_id="mean_reversion",
            instrument_token=12345,
            signal_type="BUY",
            quantity=100,
            price=Decimal("1245.25"),
            confidence=0.85,
            timestamp=datetime.now()
        )
        
        assert signal.strategy_id == "mean_reversion"
        assert signal.signal_type in ["BUY", "SELL"]
        assert 0.0 <= signal.confidence <= 1.0
        assert isinstance(signal.price, Decimal)


@pytest.mark.asyncio
class TestRedisKeyTypeHandling:
    """Test Redis key handling to prevent bytes/string TypeError issues"""
    
    async def test_redis_string_keys_with_decode_responses_true(self):
        """Test Redis operations with decode_responses=True (string mode)"""
        # This test requires real Redis instance on port 6380
        try:
            redis_client = aioredis.Redis(
                host='localhost',
                port=6380,
                decode_responses=True  # Returns strings, not bytes
            )
            
            # Test basic string operations
            await redis_client.set("test:portfolio:zerodha:balance", "150000.50")
            balance = await redis_client.get("test:portfolio:zerodha:balance")
            
            assert isinstance(balance, str)
            assert balance == "150000.50"
            
            # Test hash operations
            await redis_client.hset("test:portfolio:zerodha:positions", "12345", "100")
            position = await redis_client.hget("test:portfolio:zerodha:positions", "12345")
            
            assert isinstance(position, str)
            assert position == "100"
            
            # Cleanup
            await redis_client.delete("test:portfolio:zerodha:balance")
            await redis_client.delete("test:portfolio:zerodha:positions")
            await redis_client.close()
            
        except ConnectionError:
            pytest.skip("Redis not available on localhost:6380")
    
    async def test_redis_bytes_keys_with_decode_responses_false(self):
        """Test Redis operations with decode_responses=False (bytes mode)"""
        try:
            redis_client = aioredis.Redis(
                host='localhost',
                port=6380,
                decode_responses=False  # Returns bytes
            )
            
            # Test basic operations with bytes handling
            await redis_client.set("test:cache:order:123", "FILLED")
            result = await redis_client.get("test:cache:order:123")
            
            assert isinstance(result, bytes)
            assert result.decode('utf-8') == "FILLED"
            
            # Cleanup
            await redis_client.delete("test:cache:order:123")
            await redis_client.close()
            
        except ConnectionError:
            pytest.skip("Redis not available on localhost:6380")


class TestEventTypeEnumCompleteness:
    """Test that all referenced EventType enum values exist"""
    
    def test_critical_event_types_exist(self):
        """Test that critical event types used in production exist"""
        # Test commonly used event types
        assert hasattr(EventType, 'ORDER_FILLED')
        assert hasattr(EventType, 'ORDER_PLACED') 
        assert hasattr(EventType, 'ORDER_FAILED')
        assert hasattr(EventType, 'MARKET_DATA')
        assert hasattr(EventType, 'TRADING_SIGNAL')
        
        # Test error handling event types
        assert hasattr(EventType, 'SYSTEM_ERROR')  # Critical - was missing before
        
        # Verify enum values are strings
        assert isinstance(EventType.ORDER_FILLED, str)
        assert isinstance(EventType.SYSTEM_ERROR, str)
    
    def test_event_type_routing_consistency(self):
        """Test that event types work correctly in routing logic"""
        # Test that event types can be used in topic routing
        event_type = EventType.ORDER_FILLED
        topic_name = f"zerodha.orders.{event_type.lower()}"
        
        assert "zerodha.orders.order_filled" in topic_name or "zerodha.orders.filled" in topic_name
        
        # Test error event routing
        error_event = EventType.SYSTEM_ERROR
        error_topic = f"system.errors.{error_event.lower()}"
        
        assert "system_error" in error_topic.lower()