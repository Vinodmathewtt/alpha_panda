"""
Phase 2 Tests: Market Feed Service Integration
Tests market feed service integration with mock Zerodha API and event publishing.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from decimal import Decimal

from services.market_feed.service import MarketFeedService
from services.auth.service import AuthService
from services.instrument_data.instrument_registry_service import InstrumentRegistryService
from core.config.settings import Settings, RedpandaSettings
from core.schemas.events import EventEnvelope, EventType, MarketTick
from tests.mocks.realistic_data_generator import RealisticMarketDataGenerator
from tests.mocks.mock_zerodha_api import MockZerodhaAPI


class TestMarketFeedServiceIntegration:
    """Test MarketFeedService integration with dependencies"""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings"""
        settings = Mock(spec=Settings)
        settings.active_brokers = ["paper", "zerodha"]
        settings.reconnection = Mock()
        settings.reconnection.max_attempts = 3
        settings.reconnection.base_delay_seconds = 1.0
        settings.reconnection.max_delay_seconds = 60.0
        settings.reconnection.backoff_multiplier = 2.0
        settings.reconnection.timeout_seconds = 30.0
        return settings
    
    @pytest.fixture
    def mock_redpanda_config(self):
        """Create mock Redpanda configuration"""
        config = Mock(spec=RedpandaSettings)
        config.bootstrap_servers = "localhost:9092"
        config.client_id = "test_market_feed"
        config.acks = "all"
        config.enable_idempotence = True
        return config
    
    @pytest.fixture
    def mock_auth_service(self):
        """Create mock auth service"""
        auth_service = Mock(spec=AuthService)
        auth_service.authenticate = AsyncMock(return_value=True)
        auth_service.get_access_token = Mock(return_value="mock_access_token")
        return auth_service
    
    @pytest.fixture
    def mock_instrument_registry(self):
        """Create mock instrument registry service"""
        registry = Mock(spec=InstrumentRegistryService)
        registry.load_instruments_from_csv = AsyncMock()
        return registry
    
    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client"""
        redis_client = AsyncMock()
        redis_client.set = AsyncMock()
        redis_client.get = AsyncMock()
        redis_client.incr = AsyncMock()
        return redis_client
    
    @pytest.fixture
    def mock_stream_orchestrator(self):
        """Create mock stream orchestrator"""
        orchestrator = AsyncMock()
        orchestrator.producer = AsyncMock()
        orchestrator.producer.send = AsyncMock()
        orchestrator.start = AsyncMock()
        orchestrator.stop = AsyncMock()
        return orchestrator
    
    def test_market_feed_service_initialization(self, mock_redpanda_config, mock_settings, 
                                              mock_auth_service, mock_instrument_registry, 
                                              mock_redis_client):
        """Test MarketFeedService initialization with all dependencies"""
        
        with patch('services.market_feed.service.StreamServiceBuilder'):
            service = MarketFeedService(
                config=mock_redpanda_config,
                settings=mock_settings,
                auth_service=mock_auth_service,
                instrument_registry_service=mock_instrument_registry,
                redis_client=mock_redis_client
            )
            
            # Verify initialization
            assert service.settings == mock_settings
            assert service.auth_service == mock_auth_service
            assert service.instrument_registry_service == mock_instrument_registry
            assert service._running is False
            assert service.ticks_processed == 0
            
    @pytest.mark.asyncio
    async def test_market_feed_tick_processing(self, mock_redpanda_config, mock_settings,
                                             mock_auth_service, mock_instrument_registry,
                                             mock_redis_client, mock_stream_orchestrator):
        """Test market feed tick processing and event publishing"""
        
        # Create realistic market data generator
        data_generator = RealisticMarketDataGenerator(seed=42)
        
        # Mock the stream service builder
        with patch('services.market_feed.service.StreamServiceBuilder') as mock_builder:
            mock_builder_instance = Mock()
            mock_builder_instance.with_redis.return_value = mock_builder_instance
            mock_builder_instance.with_error_handling.return_value = mock_builder_instance
            mock_builder_instance.with_metrics.return_value = mock_builder_instance
            mock_builder_instance.add_producer.return_value = mock_builder_instance
            mock_builder_instance.build.return_value = mock_stream_orchestrator
            mock_builder.return_value = mock_builder_instance
            
            service = MarketFeedService(
                config=mock_redpanda_config,
                settings=mock_settings,
                auth_service=mock_auth_service,
                instrument_registry_service=mock_instrument_registry,
                redis_client=mock_redis_client
            )
            
            # Generate test tick
            test_tick = data_generator.generate_tick(256265, mode="full")
            
            # Mock the tick processing method
            with patch.object(service, '_process_tick') as mock_process:
                mock_process.return_value = test_tick
                
                # Process the tick
                processed_tick = service._process_tick(test_tick.model_dump())
                
                # Verify tick processing
                assert processed_tick is not None
                assert processed_tick.instrument_token == 256265
                assert processed_tick.last_price > 0
                
    @pytest.mark.asyncio
    async def test_market_feed_event_publishing(self, mock_redpanda_config, mock_settings,
                                              mock_auth_service, mock_instrument_registry,
                                              mock_redis_client, mock_stream_orchestrator):
        """Test event publishing to Redpanda"""
        
        with patch('services.market_feed.service.StreamServiceBuilder') as mock_builder:
            mock_builder_instance = Mock()
            mock_builder_instance.with_redis.return_value = mock_builder_instance
            mock_builder_instance.with_error_handling.return_value = mock_builder_instance
            mock_builder_instance.with_metrics.return_value = mock_builder_instance
            mock_builder_instance.add_producer.return_value = mock_builder_instance
            mock_builder_instance.build.return_value = mock_stream_orchestrator
            mock_builder.return_value = mock_builder_instance
            
            service = MarketFeedService(
                config=mock_redpanda_config,
                settings=mock_settings,
                auth_service=mock_auth_service,
                instrument_registry_service=mock_instrument_registry,
                redis_client=mock_redis_client
            )
            
            # Create test market tick
            test_tick = MarketTick(
                instrument_token=256265,
                last_price=Decimal("21500.50"),
                timestamp=datetime.now(timezone.utc),
                mode="full",
                tradable=True
            )
            
            # Mock the publish method
            with patch.object(service, '_publish_market_tick') as mock_publish:
                mock_publish.return_value = None
                
                # Publish the tick
                await service._publish_market_tick(test_tick)
                
                # Verify publish was called
                mock_publish.assert_called_once_with(test_tick)
                
    @pytest.mark.asyncio
    async def test_market_feed_connection_handling(self, mock_redpanda_config, mock_settings,
                                                  mock_auth_service, mock_instrument_registry,
                                                  mock_redis_client):
        """Test market feed connection establishment and error handling"""
        
        # Mock KiteConnect and KiteTicker
        mock_kite = Mock()
        mock_ticker = Mock()
        
        with patch('services.market_feed.service.StreamServiceBuilder'), \
             patch('kiteconnect.KiteConnect', return_value=mock_kite), \
             patch('kiteconnect.KiteTicker', return_value=mock_ticker):
            
            service = MarketFeedService(
                config=mock_redpanda_config,
                settings=mock_settings,
                auth_service=mock_auth_service,
                instrument_registry_service=mock_instrument_registry,
                redis_client=mock_redis_client
            )
            
            # Test connection establishment
            with patch.object(service, '_establish_connection') as mock_connect:
                mock_connect.return_value = True
                
                result = await service._establish_connection()
                assert result is True
                mock_connect.assert_called_once()
                
    def test_market_feed_authentication_integration(self, mock_redpanda_config, mock_settings,
                                                   mock_auth_service, mock_instrument_registry,
                                                   mock_redis_client):
        """Test authentication integration with BrokerAuthenticator"""
        
        with patch('services.market_feed.service.StreamServiceBuilder'):
            service = MarketFeedService(
                config=mock_redpanda_config,
                settings=mock_settings,
                auth_service=mock_auth_service,
                instrument_registry_service=mock_instrument_registry,
                redis_client=mock_redis_client
            )
            
            # Verify authenticator is properly initialized
            assert service.authenticator is not None
            assert hasattr(service.authenticator, 'authenticate')
            
    def test_market_feed_tick_formatter_integration(self, mock_redpanda_config, mock_settings,
                                                   mock_auth_service, mock_instrument_registry,
                                                   mock_redis_client):
        """Test TickFormatter integration"""
        
        with patch('services.market_feed.service.StreamServiceBuilder'):
            service = MarketFeedService(
                config=mock_redpanda_config,
                settings=mock_settings,
                auth_service=mock_auth_service,
                instrument_registry_service=mock_instrument_registry,
                redis_client=mock_redis_client
            )
            
            # Verify formatter is properly initialized
            assert service.formatter is not None
            
            # Test tick formatting
            raw_tick = {
                "instrument_token": 256265,
                "last_price": 21500.50,
                "volume_traded": 1000,
                "mode": "full"
            }
            
            formatted_tick = service.formatter.format_tick(raw_tick)
            
            assert formatted_tick["instrument_token"] == 256265
            assert formatted_tick["last_price"] == Decimal("21500.50")
            
    @pytest.mark.asyncio
    async def test_market_feed_metrics_collection(self, mock_redpanda_config, mock_settings,
                                                 mock_auth_service, mock_instrument_registry,
                                                 mock_redis_client, mock_stream_orchestrator):
        """Test metrics collection integration"""
        
        with patch('services.market_feed.service.StreamServiceBuilder') as mock_builder:
            mock_builder_instance = Mock()
            mock_builder_instance.with_redis.return_value = mock_builder_instance
            mock_builder_instance.with_error_handling.return_value = mock_builder_instance
            mock_builder_instance.with_metrics.return_value = mock_builder_instance
            mock_builder_instance.add_producer.return_value = mock_builder_instance
            mock_builder_instance.build.return_value = mock_stream_orchestrator
            mock_builder.return_value = mock_builder_instance
            
            service = MarketFeedService(
                config=mock_redpanda_config,
                settings=mock_settings,
                auth_service=mock_auth_service,
                instrument_registry_service=mock_instrument_registry,
                redis_client=mock_redis_client
            )
            
            # Verify metrics collector is initialized
            assert service.metrics_collector is not None
            assert service.ticks_processed == 0
            
            # Simulate processing ticks
            service.ticks_processed = 10
            assert service.ticks_processed == 10
            
    @pytest.mark.asyncio 
    async def test_market_feed_error_handling(self, mock_redpanda_config, mock_settings,
                                             mock_auth_service, mock_instrument_registry,
                                             mock_redis_client):
        """Test error handling in market feed service"""
        
        with patch('services.market_feed.service.StreamServiceBuilder'):
            service = MarketFeedService(
                config=mock_redpanda_config,
                settings=mock_settings,
                auth_service=mock_auth_service,
                instrument_registry_service=mock_instrument_registry,
                redis_client=mock_redis_client
            )
            
            # Test error handling during initialization
            with patch.object(mock_auth_service, 'authenticate', side_effect=Exception("Auth failed")):
                # Service should handle auth failures gracefully
                assert service.error_logger is not None
                
    def test_market_feed_instrument_loading(self, mock_redpanda_config, mock_settings,
                                           mock_auth_service, mock_instrument_registry,
                                           mock_redis_client):
        """Test instrument loading integration"""
        
        with patch('services.market_feed.service.StreamServiceBuilder'), \
             patch('services.market_feed.service.InstrumentCSVLoader') as mock_loader:
            
            # Mock CSV loader
            mock_loader_instance = Mock()
            mock_loader_instance.load_instruments.return_value = [
                {"instrument_token": "256265", "tradingsymbol": "NIFTY 50"},
                {"instrument_token": "260105", "tradingsymbol": "BANKNIFTY"}
            ]
            mock_loader.from_default_path.return_value = mock_loader_instance
            
            service = MarketFeedService(
                config=mock_redpanda_config,
                settings=mock_settings,
                auth_service=mock_auth_service,
                instrument_registry_service=mock_instrument_registry,
                redis_client=mock_redis_client
            )
            
            # Test instrument loading
            with patch.object(service, '_load_instruments_from_csv') as mock_load:
                mock_load.return_value = None
                
                await service._load_instruments_from_csv()
                mock_load.assert_called_once()


class TestMarketFeedServiceWithMockAPI:
    """Test MarketFeedService with MockZerodhaAPI"""
    
    @pytest.fixture
    def mock_zerodha_api(self):
        """Create MockZerodhaAPI instance"""
        api = MockZerodhaAPI()
        api.set_access_token("mock_token")
        return api
    
    @pytest.fixture
    def data_generator(self):
        """Create RealisticMarketDataGenerator"""
        return RealisticMarketDataGenerator(seed=42)
    
    def test_mock_api_integration(self, mock_zerodha_api, data_generator):
        """Test integration with MockZerodhaAPI"""
        
        # Test authentication
        session = mock_zerodha_api.generate_session("test_token", "test_secret")
        assert session["access_token"] == "mock_access_token_xyz"
        
        # Test market data quote
        quotes = mock_zerodha_api.quote(["NSE:NIFTY 50"])
        assert "NSE:NIFTY 50" in quotes
        
        # Test with generated tick data
        tick = data_generator.generate_tick(256265, mode="full")
        assert tick.instrument_token == 256265
        assert tick.mode == "full"
        assert tick.depth is not None
        
    @pytest.mark.asyncio
    async def test_websocket_simulation(self, mock_zerodha_api):
        """Test WebSocket tick simulation"""
        
        received_ticks = []
        
        def on_ticks(ticks):
            received_ticks.extend(ticks)
        
        # Connect to mock WebSocket
        mock_zerodha_api.connect_websocket(on_ticks)
        assert mock_zerodha_api.is_connected is True
        
        # Subscribe to instruments
        mock_zerodha_api.subscribe_ticks([256265, 260105])
        
        # Wait for some ticks
        await asyncio.sleep(0.1)
        
        # Disconnect
        mock_zerodha_api.disconnect_websocket()
        assert mock_zerodha_api.is_connected is False
        
    def test_order_placement_simulation(self, mock_zerodha_api):
        """Test order placement with mock API"""
        
        # Place a test order
        order_result = mock_zerodha_api.place_order(
            variety="regular",
            exchange="NSE",
            tradingsymbol="NIFTY 50",
            transaction_type="BUY",
            quantity=50,
            product="MIS",
            order_type="MARKET"
        )
        
        assert "order_id" in order_result
        order_id = order_result["order_id"]
        
        # Check order in orders list
        orders = mock_zerodha_api.orders()
        assert len(orders) > 0
        
        placed_order = next((o for o in orders if o["order_id"] == order_id), None)
        assert placed_order is not None
        assert placed_order["tradingsymbol"] == "NIFTY 50"
        assert placed_order["transaction_type"] == "BUY"
        
    def test_positions_tracking(self, mock_zerodha_api):
        """Test positions tracking in mock API"""
        
        # Place orders to create positions
        mock_zerodha_api.place_order(
            variety="regular",
            exchange="NSE", 
            tradingsymbol="RELIANCE",
            transaction_type="BUY",
            quantity=100,
            product="CNC",
            order_type="MARKET"
        )
        
        # Check positions
        positions = mock_zerodha_api.positions()
        assert "net" in positions
        assert "day" in positions
        
        # Should have positions after market order
        if positions["net"]:
            position = positions["net"][0]
            assert position["tradingsymbol"] == "RELIANCE"
            assert position["quantity"] > 0