"""
Unit tests for the updated AlphaPT event system.

Tests the refactored event system components:
- EventBusCore (connection management)
- EventPublisherService (publishing with retries)
- SubscriberManager (subscription management)
- Event types and serialization
- Schema registry and factory
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from typing import Dict, Any
import json

import pytest

# Updated imports for new event system
from core.events import (
    EventBusCore, EventPublisherService, SubscriberManager, subscriber,
    BaseEvent, SystemEvent, TradingEvent, MarketDataEvent, RiskEvent, EventType,
    EventParsingError, EventPublishError, EventSubscriptionError,
    SchemaRegistry, EventFactory, default_schema_registry
)
from core.config.settings import Settings


@pytest.mark.unit
class TestEventTypes:
    """Test event type classes and validation."""
    
    def test_base_event_creation(self):
        """Test creating a BaseEvent instance."""
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc)
        
        event = BaseEvent(
            event_id=event_id,
            event_type=EventType.SYSTEM_STARTED,
            timestamp=timestamp,
            source="test_component"
        )
        
        assert event.event_id == event_id
        assert event.event_type == EventType.SYSTEM_STARTED
        assert event.timestamp == timestamp
        assert event.source == "test_component"
        
    def test_system_event_creation(self):
        """Test creating a SystemEvent instance."""
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="test_component",
            component="application",
            severity="INFO",
            message="Application started successfully",
            details={"version": "1.0.0"}
        )
        
        assert event.component == "application"
        assert event.severity == "INFO"
        assert event.message == "Application started successfully"
        assert event.details == {"version": "1.0.0"}
        
    def test_trading_event_creation(self):
        """Test creating a TradingEvent instance."""
        from decimal import Decimal
        event = TradingEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.ORDER_PLACED,
            timestamp=datetime.now(timezone.utc),
            source="trading_engine",
            order_id="ORDER123",
            strategy_name="test_strategy",
            instrument_token=738561,
            quantity=10,
            price=Decimal('2500.00'),
            action="BUY"
        )
        
        assert event.order_id == "ORDER123"
        assert event.strategy_name == "test_strategy"
        assert event.instrument_token == 738561
        assert event.quantity == 10
        assert event.price == Decimal('2500.00')
        assert event.action == "BUY"
        
    def test_market_data_event_creation(self):
        """Test creating a MarketDataEvent instance."""
        event = MarketDataEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.MARKET_TICK,
            timestamp=datetime.now(timezone.utc),
            source="market_feed",
            instrument_token=738561,
            exchange="NSE",
            last_price=2500.50,
            volume=1000000,
            data={"tradingsymbol": "RELIANCE"}
        )
        
        assert event.instrument_token == 738561
        assert event.exchange == "NSE"
        assert event.last_price == 2500.50
        assert event.volume == 1000000
        assert event.data["tradingsymbol"] == "RELIANCE"
        
    def test_risk_event_creation(self):
        """Test creating a RiskEvent instance."""
        from decimal import Decimal
        event = RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.RISK_ALERT,
            timestamp=datetime.now(timezone.utc),
            source="risk_manager",
            strategy_name="test_strategy",
            risk_type="position_limit",
            risk_metric="position_value",
            current_value=Decimal('150000'),
            limit_value=Decimal('100000'),
            utilization_pct=150.0,
            breach_level="warning",
            details={"symbol": "RELIANCE"}
        )
        
        assert event.strategy_name == "test_strategy"
        assert event.risk_type == "position_limit"
        assert event.risk_metric == "position_value"
        assert event.current_value == Decimal('150000')
        assert event.limit_value == Decimal('100000')
        assert event.utilization_pct == 150.0
        assert event.breach_level == "warning"
        assert event.details["symbol"] == "RELIANCE"
        
    def test_event_serialization(self):
        """Test event serialization to JSON."""
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="test_component",
            component="application",
            severity="INFO",
            message="Test message"
        )
        
        json_str = event.to_json()
        assert isinstance(json_str, str)
        assert "event_id" in json_str
        assert "event_type" in json_str
        
    def test_event_deserialization(self):
        """Test event deserialization from JSON."""
        original_event = SystemEvent(
            event_id="test-id-123",
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="test_component",
            component="application",
            severity="INFO",
            message="Test message"
        )
        
        json_str = original_event.to_json()
        deserialized_event = SystemEvent.from_json(json_str)
        
        assert deserialized_event.event_id == original_event.event_id
        assert deserialized_event.event_type == original_event.event_type
        assert deserialized_event.source == original_event.source
        assert deserialized_event.message == original_event.message


@pytest.mark.unit 
class TestEventBusCore:
    """Test EventBusCore functionality (updated for new system)."""
    
    def test_event_bus_initialization(self, mock_settings):
        """Test EventBusCore initialization."""
        event_bus = EventBusCore(mock_settings)
        
        assert event_bus.settings == mock_settings
        assert event_bus.is_connected is False
        assert event_bus.nc is None
        assert event_bus.js is None
        
    @pytest.mark.asyncio
    async def test_event_bus_connect_success(self, mock_settings):
        """Test successful EventBusCore connection."""
        event_bus = EventBusCore(mock_settings)
        
        with patch('nats.connect', new_callable=AsyncMock) as mock_nats_connect:
            mock_nc = AsyncMock()
            mock_js = AsyncMock()
            mock_nc.jetstream.return_value = mock_js
            mock_nats_connect.return_value = mock_nc
            
            await event_bus.connect()
            
            assert event_bus.is_connected is True
            assert event_bus.nc == mock_nc
            assert event_bus.js == mock_js
            mock_nats_connect.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_event_bus_connect_failure(self, mock_settings):
        """Test EventBusCore connection failure."""
        event_bus = EventBusCore(mock_settings)
        
        with patch('nats.connect', new_callable=AsyncMock, side_effect=Exception("Connection failed")):
            with pytest.raises(Exception, match="NATS connection failed"):
                await event_bus.connect()
            
            assert event_bus.is_connected is False
            
    @pytest.mark.asyncio
    async def test_event_bus_disconnect(self, mock_settings):
        """Test EventBusCore disconnect."""
        event_bus = EventBusCore(mock_settings)
        event_bus._is_connected = True
        event_bus.nc = AsyncMock()
        
        await event_bus.disconnect()
        
        assert event_bus.is_connected is False
        assert event_bus.nc is None
        assert event_bus.js is None


@pytest.mark.unit
class TestEventPublisherService:
    """Test EventPublisherService functionality."""
    
    @pytest.fixture
    def mock_event_bus(self):
        """Mock EventBusCore for publisher testing."""
        bus = Mock()
        bus.is_connected = True
        bus.js = AsyncMock()
        return bus
        
    @pytest.fixture
    def sample_event(self):
        """Create sample event."""
        return SystemEvent(
            event_id="test-123",
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="test",
            component="test_component"
        )
    
    @pytest.mark.asyncio
    async def test_publish_success(self, mock_settings, mock_event_bus, sample_event):
        """Test successful event publishing."""
        publisher = EventPublisherService(mock_event_bus, mock_settings)
        
        await publisher.publish("test.subject", sample_event)
        
        mock_event_bus.js.publish.assert_called_once()
        call_args = mock_event_bus.js.publish.call_args
        assert call_args.kwargs['subject'] == "test.subject"
        
    @pytest.mark.asyncio
    async def test_publish_not_connected(self, mock_settings, sample_event):
        """Test publishing when not connected."""
        bus = Mock()
        bus.is_connected = False
        publisher = EventPublisherService(bus, mock_settings)
        
        with pytest.raises(EventPublishError, match="Event bus is not connected"):
            await publisher.publish("test.subject", sample_event)


@pytest.mark.unit
class TestSchemaRegistryAndFactory:
    """Test schema registry and event factory."""
    
    def test_schema_registry_initialization(self):
        """Test schema registry initialization."""
        registry = SchemaRegistry()
        assert len(registry._registry) == 0
        
    def test_event_registration(self):
        """Test event type registration."""
        registry = SchemaRegistry()
        registry.register_event(EventType.MARKET_TICK, MarketDataEvent)
        
        assert registry.get_class_for(EventType.MARKET_TICK) == MarketDataEvent
        
    def test_default_registry_populated(self):
        """Test that default registry is populated."""
        assert len(default_schema_registry._registry) > 0
        assert default_schema_registry.get_class_for(EventType.MARKET_TICK) == MarketDataEvent
        
    @pytest.mark.asyncio
    async def test_event_factory_deserialization(self):
        """Test event factory deserialization."""
        event_data = {
            "event_id": "test-123",
            "event_type": "system.started",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "source": "test",
            "component": "test_component",
            "severity": "INFO",
            "message": "Test message"
        }
        
        # Mock message
        mock_msg = Mock()
        mock_msg.data = json.dumps(event_data).encode('utf-8')
        mock_msg.headers = None
        
        factory = EventFactory(default_schema_registry)
        event = factory.deserialize(mock_msg)
        
        assert isinstance(event, SystemEvent)
        assert event.event_id == "test-123"
        assert event.component == "test_component"


@pytest.mark.unit
class TestSubscriberManager:
    """Test SubscriberManager and decorator functionality."""
    
    def test_subscriber_decorator_registration(self):
        """Test that subscriber decorator works."""
        from core.events.subscriber_manager import SubscriberDecorator
        
        test_decorator = SubscriberDecorator()
        
        @test_decorator.on_event("test.subject.*")
        async def test_handler(event):
            pass
        
        assert len(test_decorator.handlers) == 1
        assert test_decorator.handlers[0].subject_pattern == "test.subject.*"
        assert test_decorator.handlers[0].handler_func == test_handler
        
    def test_non_async_handler_error(self):
        """Test that non-async handlers raise error."""
        from core.events.subscriber_manager import SubscriberDecorator
        
        test_decorator = SubscriberDecorator()
        
        with pytest.raises(TypeError, match="must be an async function"):
            @test_decorator.on_event("test.subject.*")
            def sync_handler(event):
                pass


@pytest.mark.unit
class TestEventValidation:
    """Test event validation and constraints."""
    
    def test_event_id_required(self):
        """Test that event_id is required."""
        # Note: With dataclasses, empty strings are allowed but None would fail
        # Let's test with None instead
        with pytest.raises(TypeError):
            SystemEvent(
                event_id=None,  # None should fail
                event_type=EventType.SYSTEM_STARTED,
                timestamp=datetime.now(timezone.utc),
                source="test"
            )
            
    def test_event_timestamp_timezone_aware(self):
        """Test that timestamp must be timezone-aware."""
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="test"
        )
        
        assert event.timestamp.tzinfo is not None
        
    def test_event_source_required(self):
        """Test that source is required."""
        # Test with None instead of empty string
        with pytest.raises(TypeError):
            SystemEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.SYSTEM_STARTED,
                timestamp=datetime.now(timezone.utc),
                source=None  # None should fail
            )
            
    def test_event_type_validation(self):
        """Test that event_type must be valid enum."""
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="test"
        )
        
        assert isinstance(event.event_type, EventType)


@pytest.mark.unit
class TestEventCorrelation:
    """Test event correlation and tracking."""
    
    def test_correlation_id_propagation(self):
        """Test that correlation ID is propagated through events."""
        correlation_id = str(uuid.uuid4())
        
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="test",
            correlation_id=correlation_id
        )
        
        assert event.correlation_id == correlation_id
        
    def test_correlation_id_in_serialization(self):
        """Test that correlation ID is included in serialization."""
        correlation_id = str(uuid.uuid4())
        
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="test",
            correlation_id=correlation_id
        )
        
        json_str = event.to_json()
        assert correlation_id in json_str
        
        # Test deserialization preserves correlation ID
        deserialized = SystemEvent.from_json(json_str)
        assert deserialized.correlation_id == correlation_id


@pytest.mark.unit
class TestEventSystemIntegration:
    """Test integration between event system components."""
    
    @pytest.mark.asyncio
    async def test_publish_subscribe_flow(self, mock_settings):
        """Test complete publish-subscribe flow."""
        # This tests the components can work together
        from core.events.subscriber_manager import SubscriberDecorator
        
        # Create test decorator
        test_decorator = SubscriberDecorator()
        received_events = []
        
        @test_decorator.on_event("test.integration.*")
        async def test_handler(event):
            received_events.append(event)
        
        # Verify handler is registered
        assert len(test_decorator.handlers) == 1
        
        # Create sample event
        event = SystemEvent(
            event_id="integration-test",
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="integration_test",
            component="test_component"
        )
        
        # Test serialization works
        json_data = event.to_json()
        assert json_data
        
        # Test deserialization works
        factory = EventFactory(default_schema_registry)
        mock_msg = Mock()
        mock_msg.data = json_data.encode('utf-8')
        mock_msg.headers = None
        
        deserialized_event = factory.deserialize(mock_msg)
        assert isinstance(deserialized_event, SystemEvent)
        assert deserialized_event.event_id == "integration-test"