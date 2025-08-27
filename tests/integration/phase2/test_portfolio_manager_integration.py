"""
Integration tests for Portfolio Manager Service.

Tests the complete portfolio tracking pipeline including:
- Multi-broker portfolio state management
- Position tracking and P&L calculation
- Real-time portfolio updates from order fills
- Portfolio reconciliation and drift detection
- Integration with database and cache layers
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
    EventEnvelope, EventType, OrderFilled, PortfolioSnapshot,
    Position, PnlSnapshot
)
from services.portfolio_manager.service import PortfolioManagerService
from core.config.settings import Settings


class TestPortfolioManagerIntegration:
    """Integration tests for Portfolio Manager Service with multi-broker support."""
    
    @pytest.fixture
    def settings(self):
        """Mock settings for portfolio manager testing."""
        settings = MagicMock(spec=Settings)
        settings.kafka = MagicMock()
        settings.kafka.bootstrap_servers = "localhost:19092"
        settings.kafka.consumer_group_id = "test-portfolio-manager"
        settings.active_brokers = ["paper", "zerodha"]
        settings.portfolio = MagicMock()
        settings.portfolio.snapshot_interval = 60  # seconds
        settings.portfolio.reconciliation_interval = 300  # 5 minutes
        settings.portfolio_manager = MagicMock()
        settings.portfolio_manager.reconciliation_interval_seconds = 300
        settings.portfolio_manager.max_pending_orders = 1000
        settings.redpanda = MagicMock()
        settings.redpanda.group_id_prefix = "test-alpha-panda"
        return settings
    
    @pytest.fixture
    def mock_database(self):
        """Mock database for portfolio persistence."""
        db_mock = AsyncMock()
        
        # Mock portfolio retrieval
        async def mock_get_portfolio(broker):
            if broker == "paper":
                return {
                    'cash_balance': Decimal('500000.0'),
                    'total_value': Decimal('750000.0'),
                    'unrealized_pnl': Decimal('25000.0'),
                    'realized_pnl': Decimal('15000.0')
                }
            elif broker == "zerodha":
                return {
                    'cash_balance': Decimal('300000.0'),
                    'total_value': Decimal('450000.0'),
                    'unrealized_pnl': Decimal('12000.0'),
                    'realized_pnl': Decimal('8000.0')
                }
            return {}
        
        db_mock.get_portfolio = mock_get_portfolio
        
        # Mock position retrieval
        async def mock_get_positions(broker):
            base_positions = [
                {
                    'instrument_token': 256265,
                    'quantity': 100 if broker == "paper" else 50,
                    'average_price': Decimal('2500.0'),
                    'current_price': Decimal('2525.0'),
                    'unrealized_pnl': Decimal('2500.0') if broker == "paper" else Decimal('1250.0')
                }
            ]
            return base_positions
        
        db_mock.get_positions = mock_get_positions
        
        # Mock save operations
        db_mock.save_portfolio_snapshot = AsyncMock()
        db_mock.save_position = AsyncMock()
        db_mock.save_pnl_snapshot = AsyncMock()
        
        return db_mock
    
    @pytest.fixture
    def mock_cache(self):
        """Mock Redis cache for real-time portfolio state."""
        cache_mock = AsyncMock()
        
        # Mock portfolio cache data
        portfolio_data = {
            'paper:portfolio:summary': json.dumps({
                'cash_balance': '500000.0',
                'total_value': '750000.0',
                'unrealized_pnl': '25000.0',
                'last_updated': datetime.now(timezone.utc).isoformat()
            }),
            'zerodha:portfolio:summary': json.dumps({
                'cash_balance': '300000.0',
                'total_value': '450000.0',
                'unrealized_pnl': '12000.0',
                'last_updated': datetime.now(timezone.utc).isoformat()
            }),
            'paper:position:256265': json.dumps({
                'quantity': 100,
                'average_price': '2500.0',
                'current_price': '2525.0',
                'unrealized_pnl': '2500.0'
            })
        }
        
        async def mock_get(key):
            return portfolio_data.get(key)
        
        cache_mock.get = mock_get
        cache_mock.set = AsyncMock()
        cache_mock.delete = AsyncMock()
        cache_mock.keys = AsyncMock(return_value=list(portfolio_data.keys()))
        return cache_mock
    
    @pytest.fixture
    def mock_producer(self):
        """Mock Kafka producer for portfolio event publishing."""
        producer_mock = AsyncMock(spec=AIOKafkaProducer)
        producer_mock.send = AsyncMock()
        producer_mock.flush = AsyncMock()
        producer_mock.stop = AsyncMock()
        return producer_mock
    
    @pytest.fixture
    def mock_consumer(self):
        """Mock Kafka consumer for order fill consumption."""
        consumer_mock = AsyncMock(spec=AIOKafkaConsumer)
        consumer_mock.start = AsyncMock()
        consumer_mock.stop = AsyncMock()
        consumer_mock.subscribe = AsyncMock()
        return consumer_mock
    
    @pytest.fixture
    def mock_market_data(self):
        """Mock market data service for current prices."""
        market_data_mock = AsyncMock()
        
        async def mock_get_current_price(instrument_token):
            # Mock current prices for testing
            price_map = {
                256265: Decimal('2525.0'),
                738561: Decimal('1850.0')
            }
            return price_map.get(instrument_token, Decimal('100.0'))
        
        market_data_mock.get_current_price = mock_get_current_price
        return market_data_mock
    
    @pytest.fixture
    def portfolio_manager_service(self, settings, mock_database, mock_cache, 
                                      mock_producer, mock_consumer, mock_market_data):
        """Create Portfolio Manager Service with all mocked dependencies."""
        # Mock RedpandaSettings 
        mock_config = MagicMock()
        mock_config.bootstrap_servers = "localhost:19092"
        
        service = PortfolioManagerService(
            config=mock_config,
            settings=settings,
            redis_client=mock_cache,
            db_manager=mock_database
        )
        
        return service
    
    def create_order_fill(self, broker="paper", instrument_token=256265, 
                         quantity=100, fill_price=Decimal('2500.0')):
        """Helper to create order fill events."""
        return OrderFilled(
            order_id=f"{broker.upper()}_{uuid4().hex[:8]}",
            instrument_token=instrument_token,
            quantity=quantity,
            fill_price=fill_price,
            timestamp=datetime.now(timezone.utc),
            broker=broker,
            side="BUY"  # or "SELL"
        )
    
    def create_fill_envelope(self, order_fill, broker="paper"):
        """Helper to create event envelope with order fill."""
        return EventEnvelope(
            type=EventType.ORDER_FILLED,
            data=order_fill.model_dump(),
            source="trading_engine",
            key=f"{order_fill.instrument_token}:{order_fill.order_id}",
            broker=broker,
            correlation_id=str(uuid4())
        )

    @pytest.mark.asyncio
    async def test_portfolio_manager_initialization(self, portfolio_manager_service):
        """Test Portfolio Manager Service initializes with all dependencies."""
        service = portfolio_manager_service
        
        # Verify service is initialized
        assert service is not None
        assert service.settings is not None
        assert service.portfolio_managers is not None
        assert service.logger is not None
        assert service.orchestrator is not None
        
        # Verify active brokers configuration
        assert "paper" in service.settings.active_brokers
        assert "zerodha" in service.settings.active_brokers
    
    @pytest.mark.asyncio
    async def test_order_fill_processing_buy_order(self, portfolio_manager_service, 
                                                  mock_database, mock_cache):
        """Test processing buy order fill and position update."""
        service = portfolio_manager_service
        order_fill = self.create_order_fill(
            broker="paper", 
            instrument_token=256265,
            quantity=50,
            fill_price=Decimal('2510.0')
        )
        envelope = self.create_fill_envelope(order_fill, broker="paper")
        
        # Process order fill
        await service.process_order_fill(envelope)
        
        # Verify position was updated in cache
        mock_cache.set.assert_called()
        
        # Verify database was updated
        mock_database.save_position.assert_called()
    
    @pytest.mark.asyncio
    async def test_order_fill_processing_sell_order(self, portfolio_manager_service, 
                                                   mock_database, mock_cache):
        """Test processing sell order fill and position reduction."""
        service = portfolio_manager_service
        order_fill = self.create_order_fill(
            broker="paper", 
            instrument_token=256265,
            quantity=-25,  # Sell order
            fill_price=Decimal('2530.0')
        )
        order_fill.side = "SELL"
        envelope = self.create_fill_envelope(order_fill, broker="paper")
        
        # Process order fill
        await service.process_order_fill(envelope)
        
        # Verify position was reduced in cache
        mock_cache.set.assert_called()
        
        # Verify realized P&L was calculated
        mock_database.save_pnl_snapshot.assert_called()
    
    @pytest.mark.asyncio
    async def test_multi_broker_portfolio_isolation(self, portfolio_manager_service, 
                                                   mock_cache):
        """Test portfolio isolation between paper and zerodha brokers."""
        service = portfolio_manager_service
        
        # Create fills for both brokers
        paper_fill = self.create_order_fill(broker="paper", quantity=75)
        zerodha_fill = self.create_order_fill(broker="zerodha", quantity=25)
        
        paper_envelope = self.create_fill_envelope(paper_fill, broker="paper")
        zerodha_envelope = self.create_fill_envelope(zerodha_fill, broker="zerodha")
        
        # Process both fills
        await service.process_order_fill(paper_envelope)
        await service.process_order_fill(zerodha_envelope)
        
        # Verify separate cache keys were used
        cache_calls = [call[0][0] for call in mock_cache.set.call_args_list]
        assert any("paper:" in key for key in cache_calls)
        assert any("zerodha:" in key for key in cache_calls)
    
    @pytest.mark.asyncio
    async def test_portfolio_snapshot_generation(self, portfolio_manager_service, 
                                                mock_producer, mock_market_data):
        """Test portfolio snapshot generation and publishing."""
        service = portfolio_manager_service
        
        # Generate portfolio snapshot
        await service.generate_portfolio_snapshot("paper")
        
        # Verify snapshot was published
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        topic = call_args[0][0]
        assert topic == "paper.portfolio.snapshots"
        
        # Verify market data was used for current prices
        mock_market_data.get_current_price.assert_called()
    
    @pytest.mark.asyncio
    async def test_pnl_calculation_accuracy(self, portfolio_manager_service, mock_cache):
        """Test P&L calculation accuracy for different scenarios."""
        service = portfolio_manager_service
        
        # Test buy then sell with profit
        buy_fill = self.create_order_fill(
            broker="paper", 
            quantity=100, 
            fill_price=Decimal('2500.0')
        )
        sell_fill = self.create_order_fill(
            broker="paper", 
            quantity=-50, 
            fill_price=Decimal('2550.0')
        )
        sell_fill.side = "SELL"
        
        buy_envelope = self.create_fill_envelope(buy_fill, broker="paper")
        sell_envelope = self.create_fill_envelope(sell_fill, broker="paper")
        
        # Process fills in sequence
        await service.process_order_fill(buy_envelope)
        await service.process_order_fill(sell_envelope)
        
        # Verify P&L calculations
        mock_cache.set.assert_called()
        
        # Extract P&L from cache calls
        cache_calls = mock_cache.set.call_args_list
        pnl_calls = [call for call in cache_calls if 'pnl' in str(call)]
        assert len(pnl_calls) > 0
    
    @pytest.mark.asyncio
    async def test_position_reconciliation(self, portfolio_manager_service, 
                                         mock_database, mock_cache):
        """Test position reconciliation between cache and database."""
        service = portfolio_manager_service
        
        # Mock cache-database mismatch
        async def mock_get_with_mismatch(key):
            if 'position' in key:
                return json.dumps({
                    'quantity': 90,  # Different from database (100)
                    'average_price': '2500.0'
                })
            return None
        
        mock_cache.get = mock_get_with_mismatch
        
        # Run reconciliation
        await service.reconcile_positions("paper")
        
        # Verify reconciliation was performed
        mock_database.get_positions.assert_called_with("paper")
        mock_cache.set.assert_called()  # Position corrected
    
    @pytest.mark.asyncio
    async def test_real_time_portfolio_updates(self, portfolio_manager_service, 
                                             mock_producer, mock_market_data):
        """Test real-time portfolio value updates with market price changes."""
        service = portfolio_manager_service
        
        # Mock price change
        async def mock_price_change(instrument_token):
            return Decimal('2600.0')  # Price increased
        
        mock_market_data.get_current_price = mock_price_change
        
        # Trigger portfolio update
        await service.update_portfolio_values("paper")
        
        # Verify updated snapshot was published
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        topic = call_args[0][0]
        assert topic == "paper.portfolio.snapshots"
    
    @pytest.mark.asyncio
    async def test_portfolio_risk_metrics_calculation(self, portfolio_manager_service, 
                                                    mock_database):
        """Test calculation of portfolio risk metrics."""
        service = portfolio_manager_service
        
        # Mock positions for risk calculation
        async def mock_diverse_positions(broker):
            return [
                {
                    'instrument_token': 256265,
                    'quantity': 100,
                    'average_price': Decimal('2500.0'),
                    'current_price': Decimal('2525.0')
                },
                {
                    'instrument_token': 738561,
                    'quantity': 200,
                    'average_price': Decimal('1800.0'),
                    'current_price': Decimal('1850.0')
                }
            ]
        
        mock_database.get_positions = mock_diverse_positions
        
        # Calculate risk metrics
        metrics = await service.calculate_risk_metrics("paper")
        
        # Verify risk metrics are calculated
        assert 'concentration' in metrics
        assert 'volatility' in metrics
        assert 'max_drawdown' in metrics
    
    @pytest.mark.asyncio
    async def test_portfolio_performance_tracking(self, portfolio_manager_service, 
                                                 mock_database, mock_producer):
        """Test portfolio performance tracking and reporting."""
        service = portfolio_manager_service
        
        # Generate performance report
        await service.generate_performance_report("paper")
        
        # Verify performance data was published
        mock_producer.send.assert_called()
        call_args = mock_producer.send.call_args
        topic = call_args[0][0]
        assert "performance" in topic or "pnl" in topic
    
    @pytest.mark.asyncio
    async def test_concurrent_order_fill_processing(self, portfolio_manager_service, 
                                                   mock_cache):
        """Test concurrent processing of multiple order fills."""
        service = portfolio_manager_service
        
        # Create multiple fills for concurrent processing
        fills = [
            self.create_order_fill(broker="paper", instrument_token=256265, quantity=30),
            self.create_order_fill(broker="zerodha", instrument_token=256265, quantity=40),
            self.create_order_fill(broker="paper", instrument_token=738561, quantity=50),
            self.create_order_fill(broker="zerodha", instrument_token=738561, quantity=25)
        ]
        
        envelopes = [
            self.create_fill_envelope(fill, broker=fill.broker) for fill in fills
        ]
        
        # Process all fills concurrently
        await asyncio.gather(
            *[service.process_order_fill(env) for env in envelopes]
        )
        
        # Verify all positions were updated
        assert mock_cache.set.call_count >= len(fills)
    
    @pytest.mark.asyncio
    async def test_portfolio_drift_detection(self, portfolio_manager_service, 
                                           mock_database, mock_producer):
        """Test detection of portfolio drift from target allocation."""
        service = portfolio_manager_service
        
        # Mock target allocation
        target_allocation = {
            256265: Decimal('0.6'),  # 60% allocation
            738561: Decimal('0.4')   # 40% allocation
        }
        
        # Mock current positions that deviate from target
        async def mock_drifted_positions(broker):
            return [
                {
                    'instrument_token': 256265,
                    'quantity': 50,  # Under-allocated
                    'average_price': Decimal('2500.0'),
                    'current_price': Decimal('2525.0')
                },
                {
                    'instrument_token': 738561,
                    'quantity': 300,  # Over-allocated
                    'average_price': Decimal('1800.0'),
                    'current_price': Decimal('1850.0')
                }
            ]
        
        mock_database.get_positions = mock_drifted_positions
        
        # Check for drift
        drift_detected = await service.detect_portfolio_drift("paper", target_allocation)
        
        # Verify drift was detected
        assert drift_detected is True
    
    @pytest.mark.asyncio
    async def test_portfolio_manager_error_handling(self, portfolio_manager_service, 
                                                   mock_database):
        """Test error handling in portfolio operations."""
        service = portfolio_manager_service
        
        # Mock database error
        mock_database.save_position.side_effect = Exception("Database connection lost")
        
        order_fill = self.create_order_fill(broker="paper", quantity=50)
        envelope = self.create_fill_envelope(order_fill, broker="paper")
        
        # Should handle error gracefully
        await service.process_order_fill(envelope)
        
        # Error should be logged and operation should not crash service
    
    @pytest.mark.asyncio
    async def test_portfolio_state_recovery(self, portfolio_manager_service, 
                                          mock_database, mock_cache):
        """Test portfolio state recovery from database after cache failure."""
        service = portfolio_manager_service
        
        # Mock cache miss
        async def mock_cache_miss(key):
            return None
        
        mock_cache.get = mock_cache_miss
        
        # Trigger state recovery
        await service.recover_portfolio_state("paper")
        
        # Verify database was consulted
        mock_database.get_portfolio.assert_called_with("paper")
        mock_database.get_positions.assert_called_with("paper")
        
        # Verify cache was repopulated
        mock_cache.set.assert_called()
    
    @pytest.mark.asyncio
    async def test_portfolio_manager_lifecycle(self, settings, mock_database, 
                                             mock_cache, mock_market_data):
        """Test complete Portfolio Manager Service lifecycle."""
        with patch('services.portfolio_manager.service.AIOKafkaProducer') as mock_producer_cls, \
             patch('services.portfolio_manager.service.AIOKafkaConsumer') as mock_consumer_cls:
            
            mock_producer = AsyncMock()
            mock_consumer = AsyncMock()
            mock_producer_cls.return_value = mock_producer
            mock_consumer_cls.return_value = mock_consumer
            
            # Create service
            service = PortfolioManagerService(
                settings=settings,
                database=mock_database,
                cache=mock_cache,
                market_data_service=mock_market_data
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
    async def test_cross_broker_portfolio_aggregation(self, portfolio_manager_service, 
                                                     mock_database):
        """Test aggregation of portfolio across multiple brokers."""
        service = portfolio_manager_service
        
        # Get aggregated portfolio view
        aggregated = await service.get_aggregated_portfolio()
        
        # Verify data from both brokers was combined
        assert 'paper' in aggregated
        assert 'zerodha' in aggregated
        assert 'total' in aggregated
        
        # Verify totals are calculated correctly
        assert aggregated['total']['cash_balance'] == Decimal('800000.0')  # 500k + 300k
        assert aggregated['total']['total_value'] == Decimal('1200000.0')  # 750k + 450k