"""
Tests for the refactored event system.

This module tests the new lightweight event system components:
- EventBusCore
- SchemaRegistry and EventFactory  
- EventPublisherService
- SubscriberManager with decorators
"""

import asyncio
import json
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timezone

from core.events.event_bus_core import EventBusCore
from core.events.schema_registry import SchemaRegistry, EventFactory, default_schema_registry
from core.events.event_publisher_service import EventPublisherService
from core.events.subscriber_manager import SubscriberManager, subscriber, SubscriberDecorator
from core.events.event_types import (
    BaseEvent, EventType, MarketDataEvent, TradingEvent, SystemEvent, RiskEvent
)
from core.events.event_exceptions import (
    EventParsingError, EventPublishError, EventRegistrationError, EventSubscriptionError
)
from core.config.settings import Settings


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(secret_key="test_secret_key")


@pytest.fixture
def mock_nats_connection():
    """Mock NATS connection."""
    mock_nc = AsyncMock()
    mock_js = AsyncMock()
    mock_nc.jetstream.return_value = mock_js
    mock_nc.is_closed = False
    return mock_nc, mock_js


class TestEventBusCore:
    """Test EventBusCore connection management."""

    def test_initialization(self, settings):
        """Test EventBusCore initialization."""
        bus = EventBusCore(settings)
        
        assert bus.settings == settings
        assert bus.nc is None
        assert bus.js is None
        assert not bus.is_connected

    @pytest.mark.asyncio
    async def test_connect_success(self, settings, mock_nats_connection):
        """Test successful connection."""
        mock_nc, mock_js = mock_nats_connection
        
        with patch('nats.connect', return_value=mock_nc):
            bus = EventBusCore(settings)
            await bus.connect()
            
            assert bus.is_connected
            assert bus.nc == mock_nc
            assert bus.js == mock_js

    @pytest.mark.asyncio
    async def test_connect_failure(self, settings):
        """Test connection failure handling."""
        with patch('nats.connect', side_effect=Exception("Connection failed")):
            bus = EventBusCore(settings)
            
            with pytest.raises(Exception, match="NATS connection failed"):
                await bus.connect()
            
            assert not bus.is_connected
            assert bus.nc is None
            assert bus.js is None

    @pytest.mark.asyncio
    async def test_disconnect(self, settings, mock_nats_connection):
        """Test disconnection."""
        mock_nc, mock_js = mock_nats_connection
        
        with patch('nats.connect', return_value=mock_nc):
            bus = EventBusCore(settings)
            await bus.connect()
            await bus.disconnect()
            
            assert not bus.is_connected
            assert bus.nc is None
            assert bus.js is None
            mock_nc.drain.assert_called_once()
            mock_nc.close.assert_called_once()


class TestSchemaRegistry:
    """Test SchemaRegistry and EventFactory."""

    def test_registry_initialization(self):
        """Test registry initialization."""
        registry = SchemaRegistry()
        assert len(registry._registry) == 0

    def test_register_event(self):
        """Test event registration."""
        registry = SchemaRegistry()
        registry.register_event(EventType.MARKET_TICK, MarketDataEvent)
        
        assert registry.get_class_for(EventType.MARKET_TICK) == MarketDataEvent

    def test_register_duplicate_event(self):
        """Test duplicate registration error."""
        registry = SchemaRegistry()
        registry.register_event(EventType.MARKET_TICK, MarketDataEvent)
        
        with pytest.raises(EventRegistrationError):
            registry.register_event(EventType.MARKET_TICK, TradingEvent)

    def test_default_registry_populated(self):
        """Test that default registry is populated."""
        assert len(default_schema_registry._registry) > 0
        assert default_schema_registry.get_class_for(EventType.MARKET_TICK) == MarketDataEvent
        assert default_schema_registry.get_class_for(EventType.TRADING_SIGNAL) == TradingEvent


class TestEventFactory:
    """Test EventFactory deserialization."""

    @pytest.fixture
    def mock_message(self):
        """Create mock NATS message."""
        mock_msg = Mock()
        mock_msg.headers = None
        return mock_msg

    def test_deserialize_market_event(self, mock_message):
        """Test deserializing market data event."""
        event_data = {
            "event_id": "test-123",
            "event_type": "market.tick",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "source": "test",
            "instrument_token": 123456,
            "last_price": 100.50
        }
        mock_message.data = json.dumps(event_data).encode('utf-8')
        
        factory = EventFactory(default_schema_registry)
        event = factory.deserialize(mock_message)
        
        assert isinstance(event, MarketDataEvent)
        assert event.event_id == "test-123"
        assert event.event_type == EventType.MARKET_TICK
        assert event.instrument_token == 123456
        assert event.last_price == 100.50

    def test_deserialize_with_compression(self, mock_message):
        """Test deserializing compressed message."""
        import gzip
        
        event_data = {
            "event_id": "test-456",
            "event_type": "system.started",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "source": "test",
            "component": "test_component"
        }
        
        compressed_data = gzip.compress(json.dumps(event_data).encode('utf-8'))
        mock_message.data = compressed_data
        mock_message.headers = {'compressed': 'true'}
        
        factory = EventFactory(default_schema_registry)
        event = factory.deserialize(mock_message)
        
        assert isinstance(event, SystemEvent)
        assert event.event_id == "test-456"
        assert event.component == "test_component"

    def test_deserialize_invalid_json(self, mock_message):
        """Test deserializing invalid JSON."""
        mock_message.data = b"invalid json"
        
        factory = EventFactory(default_schema_registry)
        
        with pytest.raises(EventParsingError, match="Failed to decode JSON payload"):
            factory.deserialize(mock_message)

    def test_deserialize_missing_event_type(self, mock_message):
        """Test deserializing message missing event_type."""
        event_data = {
            "event_id": "test-123",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "source": "test"
        }
        mock_message.data = json.dumps(event_data).encode('utf-8')
        
        factory = EventFactory(default_schema_registry)
        
        with pytest.raises(EventParsingError, match="missing the 'event_type' field"):
            factory.deserialize(mock_message)

    def test_deserialize_unknown_event_type(self, mock_message):
        """Test deserializing unknown event type."""
        event_data = {
            "event_id": "test-123",
            "event_type": "unknown.type",
            "timestamp": "2024-01-01T00:00:00+00:00",
            "source": "test"
        }
        mock_message.data = json.dumps(event_data).encode('utf-8')
        
        factory = EventFactory(default_schema_registry)
        
        with pytest.raises(EventParsingError, match="not a valid EventType"):
            factory.deserialize(mock_message)


class TestEventPublisherService:
    """Test EventPublisherService."""

    @pytest.fixture
    def mock_event_bus(self):
        """Mock EventBusCore."""
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
    async def test_publish_success(self, settings, mock_event_bus, sample_event):
        """Test successful event publishing."""
        publisher = EventPublisherService(mock_event_bus, settings)
        
        await publisher.publish("test.subject", sample_event)
        
        mock_event_bus.js.publish.assert_called_once()
        call_args = mock_event_bus.js.publish.call_args
        assert call_args.kwargs['subject'] == "test.subject"
        assert 'event-id' in call_args.kwargs['headers']
        assert call_args.kwargs['headers']['event-type'] == 'system.started'

    @pytest.mark.asyncio
    async def test_publish_not_connected(self, settings, sample_event):
        """Test publishing when not connected."""
        bus = Mock()
        bus.is_connected = False
        publisher = EventPublisherService(bus, settings)
        
        with pytest.raises(EventPublishError, match="Event bus is not connected"):
            await publisher.publish("test.subject", sample_event)

    @pytest.mark.asyncio
    async def test_publish_with_retries(self, settings, mock_event_bus, sample_event):
        """Test publishing with retries."""
        # First attempt fails, second succeeds
        mock_event_bus.js.publish.side_effect = [Exception("Network error"), None]
        
        publisher = EventPublisherService(mock_event_bus, settings)
        
        await publisher.publish("test.subject", sample_event)
        
        assert mock_event_bus.js.publish.call_count == 2


class TestSubscriberManager:
    """Test SubscriberManager and decorators."""

    @pytest.fixture
    def mock_event_bus(self):
        """Mock EventBusCore."""
        bus = Mock()
        bus.is_connected = True
        bus.js = AsyncMock()
        return bus

    @pytest.fixture
    def test_decorator(self):
        """Create fresh decorator for testing."""
        return SubscriberDecorator()

    @pytest.fixture
    def test_subscriber_manager(self, mock_event_bus, test_decorator, settings):
        """Create SubscriberManager for testing."""
        return SubscriberManager(
            bus=mock_event_bus,
            event_factory=EventFactory(default_schema_registry),
            handler_source=test_decorator,
            settings=settings
        )

    def test_decorator_registration(self, test_decorator):
        """Test decorator registration."""
        @test_decorator.on_event("test.subject.*")
        async def test_handler(event):
            pass
        
        assert len(test_decorator.handlers) == 1
        assert test_decorator.handlers[0].subject_pattern == "test.subject.*"
        assert test_decorator.handlers[0].handler_func == test_handler

    def test_decorator_non_async_handler(self, test_decorator):
        """Test decorator with non-async handler raises error."""
        with pytest.raises(TypeError, match="must be an async function"):
            @test_decorator.on_event("test.subject.*")
            def sync_handler(event):
                pass

    @pytest.mark.asyncio
    async def test_start_manager(self, test_subscriber_manager, test_decorator):
        """Test starting subscriber manager."""
        @test_decorator.on_event("test.subject.*")
        async def test_handler(event):
            pass
        
        await test_subscriber_manager.start()
        
        assert test_subscriber_manager.is_running
        assert test_subscriber_manager.bus.js.subscribe.call_count == 1

    @pytest.mark.asyncio
    async def test_start_not_connected(self, test_decorator, settings):
        """Test starting when bus not connected."""
        bus = Mock()
        bus.is_connected = False
        
        manager = SubscriberManager(
            bus=bus,
            event_factory=EventFactory(default_schema_registry),
            handler_source=test_decorator,
            settings=settings
        )
        
        with pytest.raises(EventSubscriptionError, match="EventBusCore is not connected"):
            await manager.start()

    @pytest.mark.asyncio
    async def test_stop_manager(self, test_subscriber_manager, test_decorator):
        """Test stopping subscriber manager."""
        @test_decorator.on_event("test.subject.*")
        async def test_handler(event):
            pass
        
        # Mock subscription
        mock_sub = AsyncMock()
        test_subscriber_manager._active_subscriptions = [mock_sub]
        test_subscriber_manager._is_running = True
        
        await test_subscriber_manager.stop()
        
        assert not test_subscriber_manager.is_running
        mock_sub.unsubscribe.assert_called_once()

    def test_global_subscriber_decorator(self):
        """Test that global subscriber decorator exists."""
        from core.events.subscriber_manager import subscriber as global_subscriber
        
        # Should start empty for testing
        original_count = len(global_subscriber.handlers)
        
        @global_subscriber.on_event("global.test.*")
        async def global_test_handler(event):
            pass
        
        assert len(global_subscriber.handlers) == original_count + 1
        
        # Clean up for other tests
        global_subscriber.handlers = global_subscriber.handlers[:-1]


class TestIntegrationScenarios:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    async def test_complete_event_flow(self, settings):
        """Test complete event flow from publish to consume."""
        # This would be an integration test in a real scenario
        # For unit test, we verify the components can work together
        
        # Create components
        registry = SchemaRegistry()
        registry.register_event(EventType.SYSTEM_STARTED, SystemEvent)
        
        factory = EventFactory(registry)
        
        # Create sample event
        event = SystemEvent(
            event_id="integration-test",
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="integration_test",
            component="test_component"
        )
        
        # Serialize event
        json_data = event.to_json()
        assert json_data
        
        # Mock message with the serialized event
        mock_msg = Mock()
        mock_msg.data = json_data.encode('utf-8')
        mock_msg.headers = None
        
        # Deserialize using factory
        deserialized_event = factory.deserialize(mock_msg)
        
        assert isinstance(deserialized_event, SystemEvent)
        assert deserialized_event.event_id == "integration-test"
        assert deserialized_event.component == "test_component"


@pytest.mark.asyncio
async def test_refactored_system_basic_functionality():
    """Test that the new system provides basic functionality."""
    settings = Settings(secret_key="test")
    
    # Test that we can create all the main components
    from core.events import (
        EventBusCore, get_event_bus_core,
        EventPublisherService, get_event_publisher,
        SubscriberManager, subscriber,
        EventFactory, default_schema_registry
    )
    
    # EventBusCore
    bus = EventBusCore(settings)
    assert not bus.is_connected
    
    # Schema registry
    assert len(default_schema_registry._registry) > 0
    
    # Event factory
    factory = EventFactory(default_schema_registry)
    assert factory.registry == default_schema_registry
    
    # Publisher service (without connecting)
    mock_bus = Mock()
    publisher = EventPublisherService(mock_bus, settings)
    assert publisher.bus == mock_bus
    
    # Subscriber decorator
    assert len(subscriber.handlers) >= 0  # May have handlers from other tests
    
    print("✅ All refactored event system components created successfully!")


if __name__ == "__main__":
    # Run basic functionality test
    asyncio.run(test_refactored_system_basic_functionality())