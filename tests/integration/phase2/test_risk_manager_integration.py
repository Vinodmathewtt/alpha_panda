"""
Integration tests for Risk Manager Service.

Tests the complete risk validation pipeline including:
- Signal validation and risk checks
- Position size limits and exposure management
- Risk rule enforcement across multiple brokers
- Error handling and rejection patterns
- Integration with mock database and cache
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
    MarketTick, OrderPlaced
)
from services.risk_manager.service import RiskManagerService
from core.config.settings import Settings


class TestRiskManagerIntegration:
    """Integration tests for Risk Manager Service with full dependency stack."""
    
    @pytest.fixture
    def settings(self):
        """Mock settings for risk manager testing."""
        settings = MagicMock(spec=Settings)
        settings.kafka = MagicMock()
        settings.kafka.bootstrap_servers = "localhost:19092"
        settings.kafka.consumer_group_id = "test-risk-manager"
        settings.active_brokers = ["paper", "zerodha"]
        settings.risk_manager = MagicMock()
        settings.risk_manager.max_position_size = Decimal('100000')
        settings.risk_manager.max_daily_loss = Decimal('50000')
        settings.risk_manager.max_portfolio_exposure = Decimal('0.95')
        return settings
    
    @pytest.fixture
    def mock_database(self):
        """Mock database for risk configuration."""
        db_mock = AsyncMock()
        
        # Mock risk rules
        async def mock_get_risk_rules(broker):
            return {
                'max_position_size': Decimal('50000'),
                'max_single_order': Decimal('10000'),
                'allowed_instruments': [256265, 738561],
                'max_leverage': Decimal('2.0')
            }
        
        db_mock.get_risk_rules = mock_get_risk_rules
        
        # Mock position data
        async def mock_get_positions(broker):
            return [
                {
                    'instrument_token': 256265,
                    'quantity': 100,
                    'average_price': Decimal('2500.0'),
                    'pnl': Decimal('1500.0')
                }
            ]
        
        db_mock.get_positions = mock_get_positions
        return db_mock
    
    @pytest.fixture
    def mock_cache(self):
        """Mock Redis cache for position tracking."""
        cache_mock = AsyncMock()
        
        # Mock position cache
        position_data = {
            'paper:positions:256265': json.dumps({
                'quantity': 100,
                'average_price': '2500.0',
                'total_value': '250000.0'
            }),
            'zerodha:positions:256265': json.dumps({
                'quantity': 50,
                'average_price': '2510.0',
                'total_value': '125500.0'
            })
        }
        
        async def mock_get(key):
            return position_data.get(key)
        
        cache_mock.get = mock_get
        cache_mock.set = AsyncMock()
        return cache_mock
    
    @pytest.fixture
    def mock_producer(self):
        """Mock Kafka producer for signal publishing."""
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
    async def risk_manager_service(self, settings, mock_database, mock_cache, 
                                 mock_producer, mock_consumer):
        """Create Risk Manager Service with all mocked dependencies."""
        with patch('services.risk_manager.service.AIOKafkaProducer', return_value=mock_producer), \
             patch('services.risk_manager.service.AIOKafkaConsumer', return_value=mock_consumer):
            
            service = RiskManagerService(
                settings=settings,
                database=mock_database,
                cache=mock_cache
            )
            
            # Mock the async initialization
            await service.initialize()
            return service
    
    def create_trading_signal(self, broker="paper", instrument_token=256265, 
                            signal_type=SignalType.BUY, quantity=100):
        """Helper to create test trading signals."""
        return TradingSignal(
            strategy_id="test_strategy",
            instrument_token=instrument_token,
            signal_type=signal_type,
            quantity=quantity,
            price=Decimal('2500.0'),
            timestamp=datetime.now(timezone.utc),
            broker=broker
        )
    
    def create_event_envelope(self, signal, broker="paper"):
        """Helper to create event envelope with trading signal."""
        return EventEnvelope(
            type=EventType.TRADING_SIGNAL,
            data=signal.model_dump(),
            source="strategy_runner",
            key=f"{signal.instrument_token}:{signal.strategy_id}",
            broker=broker,
            correlation_id=str(uuid4())
        )

    @pytest.mark.asyncio
    async def test_risk_manager_initialization(self, risk_manager_service):
        """Test Risk Manager Service initializes correctly with all dependencies."""
        service = risk_manager_service
        
        # Verify service is initialized
        assert service is not None
        assert service.settings is not None
        assert service.database is not None
        assert service.cache is not None
        
        # Verify active brokers configuration
        assert "paper" in service.settings.active_brokers
        assert "zerodha" in service.settings.active_brokers
    
    @pytest.mark.asyncio
    async def test_signal_validation_success(self, risk_manager_service, mock_producer):
        """Test successful signal validation and approval."""
        service = risk_manager_service
        signal = self.create_trading_signal(broker="paper", quantity=50)
        envelope = self.create_event_envelope(signal, broker="paper")
        
        # Process the signal
        result = await service.validate_signal(envelope)
        
        # Verify validation passed
        assert result is True
        
        # Verify approved signal was published
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        topic = call_args[0][0]
        assert topic == "paper.signals.validated"
    
    @pytest.mark.asyncio
    async def test_signal_rejection_oversized_position(self, risk_manager_service, mock_producer):
        """Test signal rejection for oversized position."""
        service = risk_manager_service
        # Create oversized signal
        signal = self.create_trading_signal(broker="paper", quantity=100000)  # Exceeds max
        envelope = self.create_event_envelope(signal, broker="paper")
        
        # Process the signal
        result = await service.validate_signal(envelope)
        
        # Verify validation failed
        assert result is False
        
        # Verify rejection was published
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        topic = call_args[0][0]
        assert topic == "paper.signals.rejected"
    
    @pytest.mark.asyncio
    async def test_multi_broker_risk_isolation(self, risk_manager_service, mock_producer):
        """Test risk isolation between paper and zerodha brokers."""
        service = risk_manager_service
        
        # Create signals for both brokers
        paper_signal = self.create_trading_signal(broker="paper", quantity=75)
        zerodha_signal = self.create_trading_signal(broker="zerodha", quantity=75)
        
        paper_envelope = self.create_event_envelope(paper_signal, broker="paper")
        zerodha_envelope = self.create_event_envelope(zerodha_signal, broker="zerodha")
        
        # Process both signals
        paper_result = await service.validate_signal(paper_envelope)
        zerodha_result = await service.validate_signal(zerodha_envelope)
        
        # Both should pass with separate risk limits
        assert paper_result is True
        assert zerodha_result is True
        
        # Verify separate topics used
        assert mock_producer.send.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_position_size_risk_check(self, risk_manager_service, mock_database):
        """Test position size risk checking with existing positions."""
        service = risk_manager_service
        
        # Mock existing large position
        async def mock_large_position(broker):
            return [
                {
                    'instrument_token': 256265,
                    'quantity': 900,  # Large existing position
                    'average_price': Decimal('2500.0'),
                    'pnl': Decimal('15000.0')
                }
            ]
        
        mock_database.get_positions = mock_large_position
        
        # Try to add more to existing large position
        signal = self.create_trading_signal(broker="paper", quantity=200)
        envelope = self.create_event_envelope(signal, broker="paper")
        
        result = await service.validate_signal(envelope)
        
        # Should be rejected due to position size limits
        assert result is False
    
    @pytest.mark.asyncio
    async def test_instrument_whitelist_check(self, risk_manager_service):
        """Test instrument whitelist validation."""
        service = risk_manager_service
        
        # Create signal for non-whitelisted instrument
        signal = self.create_trading_signal(
            broker="paper", 
            instrument_token=999999,  # Not in allowed list
            quantity=50
        )
        envelope = self.create_event_envelope(signal, broker="paper")
        
        result = await service.validate_signal(envelope)
        
        # Should be rejected due to instrument not in whitelist
        assert result is False
    
    @pytest.mark.asyncio
    async def test_daily_loss_limit_check(self, risk_manager_service, mock_cache):
        """Test daily loss limit enforcement."""
        service = risk_manager_service
        
        # Mock large daily loss in cache
        async def mock_large_loss(key):
            if 'daily_pnl' in key:
                return json.dumps({'pnl': '-60000.0'})  # Exceeds max daily loss
            return None
        
        mock_cache.get = mock_large_loss
        
        # Try to place new trade when daily loss exceeded
        signal = self.create_trading_signal(broker="paper", quantity=50)
        envelope = self.create_event_envelope(signal, broker="paper")
        
        result = await service.validate_signal(envelope)
        
        # Should be rejected due to daily loss limit
        assert result is False
    
    @pytest.mark.asyncio
    async def test_risk_manager_error_handling(self, risk_manager_service, mock_database):
        """Test error handling when risk checks fail."""
        service = risk_manager_service
        
        # Mock database error
        mock_database.get_risk_rules.side_effect = Exception("Database error")
        
        signal = self.create_trading_signal(broker="paper", quantity=50)
        envelope = self.create_event_envelope(signal, broker="paper")
        
        # Should handle error gracefully
        result = await service.validate_signal(envelope)
        
        # Should default to rejection on error
        assert result is False
    
    @pytest.mark.asyncio
    async def test_signal_processing_with_market_data(self, risk_manager_service):
        """Test signal validation with current market conditions."""
        service = risk_manager_service
        
        # Create market tick for context
        market_tick = MarketTick(
            instrument_token=256265,
            last_price=Decimal('2550.0'),
            volume=1000,
            timestamp=datetime.now(timezone.utc),
            mode="full"
        )
        
        # Process market data first
        await service.update_market_context(market_tick)
        
        # Now validate signal with market context
        signal = self.create_trading_signal(
            broker="paper", 
            instrument_token=256265,
            quantity=50
        )
        envelope = self.create_event_envelope(signal, broker="paper")
        
        result = await service.validate_signal(envelope)
        
        # Should pass with valid market context
        assert result is True
    
    @pytest.mark.asyncio
    async def test_concurrent_signal_validation(self, risk_manager_service):
        """Test concurrent signal validation for multiple brokers."""
        service = risk_manager_service
        
        # Create multiple signals for concurrent processing
        signals = [
            (self.create_trading_signal(broker="paper", quantity=30), "paper"),
            (self.create_trading_signal(broker="zerodha", quantity=40), "zerodha"),
            (self.create_trading_signal(broker="paper", quantity=25), "paper")
        ]
        
        envelopes = [self.create_event_envelope(sig, broker) for sig, broker in signals]
        
        # Process all signals concurrently
        results = await asyncio.gather(
            *[service.validate_signal(env) for env in envelopes]
        )
        
        # All should pass
        assert all(results)
    
    @pytest.mark.asyncio
    async def test_risk_manager_lifecycle(self, settings, mock_database, mock_cache):
        """Test complete Risk Manager Service lifecycle."""
        with patch('services.risk_manager.service.AIOKafkaProducer') as mock_producer_cls, \
             patch('services.risk_manager.service.AIOKafkaConsumer') as mock_consumer_cls:
            
            mock_producer = AsyncMock()
            mock_consumer = AsyncMock()
            mock_producer_cls.return_value = mock_producer
            mock_consumer_cls.return_value = mock_consumer
            
            # Create service
            service = RiskManagerService(
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