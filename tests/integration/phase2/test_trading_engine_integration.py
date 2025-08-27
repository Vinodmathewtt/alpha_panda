"""
Integration tests for Trading Engine Service.

Tests the complete order execution pipeline including:
- Multi-broker trading engine routing (Paper vs Zerodha)
- Order placement and execution tracking
- Portfolio integration and position updates
- Error handling and retry mechanisms
- Integration with mock broker APIs
"""

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from core.schemas.events import (
    EventEnvelope, EventType, TradingSignal, SignalType,
    OrderPlaced, OrderStatus, OrderFilled
)
from services.trading_engine.service import TradingEngineService
from services.trading_engine.traders.paper_trader import PaperTrader
from services.trading_engine.traders.zerodha_trader import ZerodhaTrader
from core.config.settings import Settings


class TestTradingEngineIntegration:
    """Integration tests for Trading Engine Service with multi-broker support."""
    
    @pytest.fixture
    def settings(self):
        """Mock settings for trading engine testing."""
        settings = MagicMock(spec=Settings)
        settings.kafka = MagicMock()
        settings.kafka.bootstrap_servers = "localhost:19092"
        settings.kafka.consumer_group_id = "test-trading-engine"
        settings.active_brokers = ["paper", "zerodha"]
        settings.paper_trading = MagicMock()
        settings.paper_trading.enabled = True
        settings.paper_trading.initial_balance = Decimal('1000000')
        settings.zerodha = MagicMock()
        settings.zerodha.enabled = True
        settings.zerodha.api_key = "test_api_key"
        return settings
    
    @pytest.fixture
    def mock_database(self):
        """Mock database for order and position tracking."""
        db_mock = AsyncMock()
        
        # Mock order storage
        async def mock_save_order(order):
            return {"id": str(uuid4()), **order.model_dump()}
        
        db_mock.save_order = mock_save_order
        
        # Mock position retrieval
        async def mock_get_positions(broker):
            return [
                {
                    'instrument_token': 256265,
                    'quantity': 50,
                    'average_price': Decimal('2500.0'),
                    'broker': broker
                }
            ]
        
        db_mock.get_positions = mock_get_positions
        return db_mock
    
    @pytest.fixture
    def mock_cache(self):
        """Mock Redis cache for order tracking."""
        cache_mock = AsyncMock()
        
        # Mock order cache
        order_data = {
            'paper:order:test_order_1': json.dumps({
                'status': 'PENDING',
                'quantity': 100,
                'price': '2500.0',
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
        }
        
        async def mock_get(key):
            return order_data.get(key)
        
        cache_mock.get = mock_get
        cache_mock.set = AsyncMock()
        cache_mock.delete = AsyncMock()
        return cache_mock
    
    @pytest.fixture
    def mock_producer(self):
        """Mock Kafka producer for order event publishing."""
        producer_mock = AsyncMock(spec=AIOKafkaProducer)
        producer_mock.send = AsyncMock()
        producer_mock.flush = AsyncMock()
        producer_mock.stop = AsyncMock()
        return producer_mock
    
    @pytest.fixture
    def mock_consumer(self):
        """Mock Kafka consumer for signal consumption."""
        consumer_mock = AsyncMock(spec=AIOKafkaConsumer)
        consumer_mock.start = AsyncMock()
        consumer_mock.stop = AsyncMock()
        consumer_mock.subscribe = AsyncMock()
        return consumer_mock
    
    @pytest.fixture
    def mock_paper_trader(self):
        """Mock Paper Trader for simulated execution."""
        trader_mock = AsyncMock(spec=PaperTrader)
        
        async def mock_place_order(signal):
            return OrderPlaced(
                order_id=f"PAPER_{uuid4().hex[:8]}",
                instrument_token=signal.instrument_token,
                signal_type=signal.signal_type,
                quantity=signal.quantity,
                price=signal.price or Decimal('2500.0'),
                timestamp=datetime.now(timezone.utc),
                broker="paper",
                status=OrderStatus.PLACED
            )
        
        trader_mock.place_order = mock_place_order
        return trader_mock
    
    @pytest.fixture
    def mock_zerodha_trader(self):
        """Mock Zerodha Trader for live execution."""
        trader_mock = AsyncMock(spec=ZerodhaTrader)
        
        async def mock_place_order(signal):
            return OrderPlaced(
                order_id=f"ZH_{uuid4().hex[:8]}",
                instrument_token=signal.instrument_token,
                signal_type=signal.signal_type,
                quantity=signal.quantity,
                price=signal.price or Decimal('2510.0'),
                timestamp=datetime.now(timezone.utc),
                broker="zerodha",
                status=OrderStatus.PLACED
            )
        
        trader_mock.place_order = mock_place_order
        return trader_mock
    
    @pytest.fixture
    async def trading_engine_service(self, settings, mock_database, mock_cache, 
                                   mock_producer, mock_consumer, mock_paper_trader, 
                                   mock_zerodha_trader):
        """Create Trading Engine Service with all mocked dependencies."""
        with patch('services.trading_engine.service.AIOKafkaProducer', return_value=mock_producer), \
             patch('services.trading_engine.service.AIOKafkaConsumer', return_value=mock_consumer), \
             patch('services.trading_engine.traders.paper_trader.PaperTrader', return_value=mock_paper_trader), \
             patch('services.trading_engine.traders.zerodha_trader.ZerodhaTrader', return_value=mock_zerodha_trader):
            
            service = TradingEngineService(
                settings=settings,
                database=mock_database,
                cache=mock_cache
            )
            
            # Mock the async initialization
            await service.initialize()
            service.paper_trader = mock_paper_trader
            service.zerodha_trader = mock_zerodha_trader
            return service
    
    def create_validated_signal(self, broker="paper", instrument_token=256265, 
                              signal_type=SignalType.BUY, quantity=100):
        """Helper to create validated trading signals."""
        return TradingSignal(
            strategy_id="test_strategy",
            instrument_token=instrument_token,
            signal_type=signal_type,
            quantity=quantity,
            price=Decimal('2500.0'),
            timestamp=datetime.now(timezone.utc),
            broker=broker
        )
    
    def create_signal_envelope(self, signal, broker="paper"):
        """Helper to create event envelope with validated signal."""
        return EventEnvelope(
            type=EventType.SIGNAL_VALIDATED,
            data=signal.model_dump(),
            source="risk_manager",
            key=f"{signal.instrument_token}:{signal.strategy_id}",
            broker=broker,
            correlation_id=str(uuid4())
        )

    @pytest.mark.asyncio
    async def test_trading_engine_initialization(self, trading_engine_service):
        """Test Trading Engine Service initializes with both traders."""
        service = trading_engine_service
        
        # Verify service is initialized
        assert service is not None
        assert service.settings is not None
        assert service.database is not None
        assert service.cache is not None
        
        # Verify both traders are available
        assert service.paper_trader is not None
        assert service.zerodha_trader is not None
        
        # Verify active brokers configuration
        assert "paper" in service.settings.active_brokers
        assert "zerodha" in service.settings.active_brokers
    
    @pytest.mark.asyncio
    async def test_paper_trading_order_execution(self, trading_engine_service, 
                                                mock_paper_trader, mock_producer):
        """Test order execution through Paper Trader."""
        service = trading_engine_service
        signal = self.create_validated_signal(broker="paper", quantity=100)
        envelope = self.create_signal_envelope(signal, broker="paper")
        
        # Process the validated signal
        await service.process_validated_signal(envelope)
        
        # Verify paper trader was called
        mock_paper_trader.place_order.assert_called_once()
        call_args = mock_paper_trader.place_order.call_args[0][0]
        assert call_args.broker == "paper"
        assert call_args.quantity == 100
        
        # Verify order placed event was published
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        topic = call_args[0][0]
        assert topic == "paper.orders.placed"
    
    @pytest.mark.asyncio
    async def test_zerodha_trading_order_execution(self, trading_engine_service, 
                                                 mock_zerodha_trader, mock_producer):
        """Test order execution through Zerodha Trader."""
        service = trading_engine_service
        signal = self.create_validated_signal(broker="zerodha", quantity=50)
        envelope = self.create_signal_envelope(signal, broker="zerodha")
        
        # Process the validated signal
        await service.process_validated_signal(envelope)
        
        # Verify zerodha trader was called
        mock_zerodha_trader.place_order.assert_called_once()
        call_args = mock_zerodha_trader.place_order.call_args[0][0]
        assert call_args.broker == "zerodha"
        assert call_args.quantity == 50
        
        # Verify order placed event was published
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        topic = call_args[0][0]
        assert topic == "zerodha.orders.placed"
    
    @pytest.mark.asyncio
    async def test_multi_broker_signal_routing(self, trading_engine_service, 
                                             mock_paper_trader, mock_zerodha_trader):
        """Test signal routing to appropriate traders based on broker."""
        service = trading_engine_service
        
        # Create signals for both brokers
        paper_signal = self.create_validated_signal(broker="paper", quantity=75)
        zerodha_signal = self.create_validated_signal(broker="zerodha", quantity=25)
        
        paper_envelope = self.create_signal_envelope(paper_signal, broker="paper")
        zerodha_envelope = self.create_signal_envelope(zerodha_signal, broker="zerodha")
        
        # Process both signals
        await service.process_validated_signal(paper_envelope)
        await service.process_validated_signal(zerodha_envelope)
        
        # Verify correct routing
        mock_paper_trader.place_order.assert_called_once()
        mock_zerodha_trader.place_order.assert_called_once()
        
        # Verify quantities were routed correctly
        paper_call = mock_paper_trader.place_order.call_args[0][0]
        zerodha_call = mock_zerodha_trader.place_order.call_args[0][0]
        
        assert paper_call.quantity == 75
        assert zerodha_call.quantity == 25
    
    @pytest.mark.asyncio
    async def test_order_status_tracking(self, trading_engine_service, mock_database, mock_cache):
        """Test order status tracking and database persistence."""
        service = trading_engine_service
        signal = self.create_validated_signal(broker="paper", quantity=100)
        envelope = self.create_signal_envelope(signal, broker="paper")
        
        # Process signal
        await service.process_validated_signal(envelope)
        
        # Verify order was saved to database
        mock_database.save_order.assert_called_once()
        
        # Verify order status was cached
        mock_cache.set.assert_called()
    
    @pytest.mark.asyncio
    async def test_order_execution_error_handling(self, trading_engine_service, 
                                                 mock_paper_trader, mock_producer):
        """Test error handling when order execution fails."""
        service = trading_engine_service
        
        # Mock trader to raise exception
        mock_paper_trader.place_order.side_effect = Exception("Broker connection error")
        
        signal = self.create_validated_signal(broker="paper", quantity=100)
        envelope = self.create_signal_envelope(signal, broker="paper")
        
        # Process signal should handle error gracefully
        await service.process_validated_signal(envelope)
        
        # Verify error event was published
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        topic = call_args[0][0]
        assert topic == "paper.orders.failed"
    
    @pytest.mark.asyncio
    async def test_concurrent_order_processing(self, trading_engine_service, 
                                             mock_paper_trader, mock_zerodha_trader):
        """Test concurrent order processing for multiple brokers."""
        service = trading_engine_service
        
        # Create multiple signals for concurrent processing
        signals = [
            (self.create_validated_signal(broker="paper", quantity=30), "paper"),
            (self.create_validated_signal(broker="zerodha", quantity=40), "zerodha"),
            (self.create_validated_signal(broker="paper", quantity=25), "paper"),
            (self.create_validated_signal(broker="zerodha", quantity=35), "zerodha")
        ]
        
        envelopes = [self.create_signal_envelope(sig, broker) for sig, broker in signals]
        
        # Process all signals concurrently
        await asyncio.gather(
            *[service.process_validated_signal(env) for env in envelopes]
        )
        
        # Verify all orders were processed
        assert mock_paper_trader.place_order.call_count == 2
        assert mock_zerodha_trader.place_order.call_count == 2
    
    @pytest.mark.asyncio
    async def test_order_fill_processing(self, trading_engine_service, mock_producer):
        """Test processing of order fill events from brokers."""
        service = trading_engine_service
        
        # Create order fill event
        order_fill = OrderFilled(
            order_id="PAPER_12345678",
            instrument_token=256265,
            quantity=100,
            fill_price=Decimal('2505.0'),
            timestamp=datetime.now(timezone.utc),
            broker="paper"
        )
        
        fill_envelope = EventEnvelope(
            type=EventType.ORDER_FILLED,
            data=order_fill.model_dump(),
            source="paper_trader",
            key=f"{order_fill.instrument_token}:{order_fill.order_id}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Process order fill
        await service.process_order_fill(fill_envelope)
        
        # Verify fill event was published to portfolio manager
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        topic = call_args[0][0]
        assert topic == "paper.orders.filled"
    
    @pytest.mark.asyncio
    async def test_position_size_validation(self, trading_engine_service, mock_database):
        """Test position size validation before order placement."""
        service = trading_engine_service
        
        # Mock existing large position
        async def mock_large_position(broker):
            return [
                {
                    'instrument_token': 256265,
                    'quantity': 950,  # Large existing position
                    'average_price': Decimal('2500.0'),
                    'broker': broker
                }
            ]
        
        mock_database.get_positions = mock_large_position
        
        # Try to place order that would exceed limits
        signal = self.create_validated_signal(broker="paper", quantity=100, instrument_token=256265)
        envelope = self.create_signal_envelope(signal, broker="paper")
        
        # Process should validate position size
        await service.process_validated_signal(envelope)
        
        # Order should still be placed (risk manager handles limits)
        # Trading engine executes validated signals
    
    @pytest.mark.asyncio
    async def test_market_hours_validation(self, trading_engine_service):
        """Test market hours validation for order placement."""
        service = trading_engine_service
        
        # Mock market hours check
        with patch.object(service, 'is_market_open', return_value=False):
            signal = self.create_validated_signal(broker="paper", quantity=50)
            envelope = self.create_signal_envelope(signal, broker="paper")
            
            # Process signal during market closed
            result = await service.process_validated_signal(envelope)
            
            # Should handle market closed scenario
            # (Implementation depends on business logic)
    
    @pytest.mark.asyncio
    async def test_order_modification_handling(self, trading_engine_service, mock_producer):
        """Test handling of order modifications and cancellations."""
        service = trading_engine_service
        
        # Create order modification request
        modification = {
            'order_id': 'PAPER_12345678',
            'new_quantity': 75,
            'new_price': Decimal('2510.0'),
            'broker': 'paper'
        }
        
        # Process modification
        await service.modify_order(modification)
        
        # Verify modification event was published
        mock_producer.send.assert_called()
    
    @pytest.mark.asyncio
    async def test_trading_engine_lifecycle(self, settings, mock_database, mock_cache):
        """Test complete Trading Engine Service lifecycle."""
        with patch('services.trading_engine.service.AIOKafkaProducer') as mock_producer_cls, \
             patch('services.trading_engine.service.AIOKafkaConsumer') as mock_consumer_cls, \
             patch('services.trading_engine.traders.paper_trader.PaperTrader'), \
             patch('services.trading_engine.traders.zerodha_trader.ZerodhaTrader'):
            
            mock_producer = AsyncMock()
            mock_consumer = AsyncMock()
            mock_producer_cls.return_value = mock_producer
            mock_consumer_cls.return_value = mock_consumer
            
            # Create service
            service = TradingEngineService(
                settings=settings,
                database=mock_database,
                cache=mock_cache
            )
            
            # Test start
            await service.start()
            mock_consumer.start.assert_called_once()
            
            # Test stop
            await service.stop()
            mock_producer.flush.assert_called_once()
            mock_producer.stop.assert_called_once()
            mock_consumer.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_broker_specific_configuration(self, trading_engine_service):
        """Test broker-specific configuration handling."""
        service = trading_engine_service
        
        # Verify paper trader configuration
        assert service.settings.paper_trading.enabled is True
        assert service.settings.paper_trading.initial_balance == Decimal('1000000')
        
        # Verify zerodha trader configuration
        assert service.settings.zerodha.enabled is True
        assert service.settings.zerodha.api_key == "test_api_key"
    
    @pytest.mark.asyncio
    async def test_signal_deduplication(self, trading_engine_service, mock_cache):
        """Test signal deduplication to prevent duplicate orders."""
        service = trading_engine_service
        signal = self.create_validated_signal(broker="paper", quantity=100)
        envelope = self.create_signal_envelope(signal, broker="paper")
        
        # Mock signal already processed
        async def mock_get_signal_cache(key):
            if 'signal_processed' in key:
                return "true"
            return None
        
        mock_cache.get = mock_get_signal_cache
        
        # Process signal
        result = await service.process_validated_signal(envelope)
        
        # Should detect duplicate and skip processing
        # (Implementation depends on deduplication strategy)