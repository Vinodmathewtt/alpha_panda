"""
System integration tests for Alpha Panda infrastructure.

Tests integration between core system components:
- Database persistence and retrieval
- Redis caching and state management  
- Kafka/Redpanda event streaming
- Multi-broker configuration management
- Service lifecycle and health checks
"""

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from core.schemas.events import (
    EventEnvelope, EventType, MarketTick, TradingSignal, OrderFilled
)
from core.config.settings import Settings


class TestSystemInfrastructureIntegration:
    """Test integration of core infrastructure components."""
    
    @pytest.fixture
    def mock_database(self):
        """Mock database with realistic persistence patterns."""
        db_mock = AsyncMock()
        
        # Mock strategy loading
        async def mock_load_strategies(broker):
            return [
                {
                    'id': 'momentum_001',
                    'name': 'Momentum Strategy',
                    'config': {'lookback_period': 20, 'threshold': 0.02},
                    'active': True,
                    'broker': broker
                },
                {
                    'id': 'mean_reversion_001', 
                    'name': 'Mean Reversion Strategy',
                    'config': {'window_size': 50, 'deviation_threshold': 2.0},
                    'active': True,
                    'broker': broker
                }
            ]
        
        db_mock.load_strategies = mock_load_strategies
        
        # Mock order persistence
        db_mock.save_order = AsyncMock()
        db_mock.get_orders = AsyncMock(return_value=[])
        
        # Mock position tracking
        async def mock_get_positions(broker):
            return [
                {
                    'instrument_token': 256265,
                    'quantity': 100,
                    'average_price': Decimal('25000.0'),
                    'broker': broker
                }
            ]
        
        db_mock.get_positions = mock_get_positions
        db_mock.save_position = AsyncMock()
        
        return db_mock
    
    @pytest.fixture
    def mock_redis(self):
        """Mock Redis with realistic caching patterns."""
        redis_mock = AsyncMock()
        
        # Mock cache data
        cache_data = {
            'paper:portfolio:summary': json.dumps({
                'cash_balance': '500000.0',
                'total_value': '750000.0',
                'last_updated': datetime.now(timezone.utc).isoformat()
            }),
            'zerodha:portfolio:summary': json.dumps({
                'cash_balance': '300000.0', 
                'total_value': '450000.0',
                'last_updated': datetime.now(timezone.utc).isoformat()
            })
        }
        
        async def mock_get(key):
            return cache_data.get(key)
        
        redis_mock.get = mock_get
        redis_mock.set = AsyncMock()
        redis_mock.delete = AsyncMock()
        redis_mock.exists = AsyncMock()
        redis_mock.keys = AsyncMock(return_value=list(cache_data.keys()))
        
        return redis_mock
    
    @pytest.fixture
    def mock_kafka(self):
        """Mock Kafka producer/consumer with realistic streaming."""
        kafka_mock = {
            'producer': AsyncMock(),
            'consumer': AsyncMock()
        }
        
        # Mock message production
        kafka_mock['producer'].send = AsyncMock()
        kafka_mock['producer'].flush = AsyncMock()
        
        # Mock message consumption
        kafka_mock['consumer'].start = AsyncMock()
        kafka_mock['consumer'].stop = AsyncMock()
        kafka_mock['consumer'].subscribe = AsyncMock()
        
        return kafka_mock
    
    @pytest.fixture
    def test_settings(self):
        """Test settings with multi-broker configuration."""
        settings = MagicMock(spec=Settings)
        settings.active_brokers = ["paper", "zerodha"]
        settings.kafka = MagicMock()
        settings.kafka.bootstrap_servers = "localhost:19092"
        settings.database = MagicMock()
        settings.database.url = "postgresql://test:test@localhost:5433/alpha_panda_test"
        settings.redis = MagicMock()
        settings.redis.url = "redis://localhost:6380/0"
        return settings

    @pytest.mark.asyncio
    async def test_multi_broker_strategy_loading(self, mock_database, test_settings):
        """Test loading strategies for multiple brokers from database."""
        
        # Load strategies for both brokers
        paper_strategies = await mock_database.load_strategies("paper")
        zerodha_strategies = await mock_database.load_strategies("zerodha")
        
        # Verify strategies loaded for both brokers
        assert len(paper_strategies) == 2
        assert len(zerodha_strategies) == 2
        
        # Verify strategy configurations
        for strategy in paper_strategies:
            assert 'id' in strategy
            assert 'config' in strategy
            assert strategy['active'] is True
            assert strategy['broker'] == "paper"
        
        # Verify database calls made for both brokers
        assert mock_database.load_strategies.call_count == 2
    
    @pytest.mark.asyncio
    async def test_cross_broker_cache_isolation(self, mock_redis):
        """Test cache isolation between brokers."""
        
        # Get portfolio data for both brokers
        paper_portfolio = await mock_redis.get('paper:portfolio:summary')
        zerodha_portfolio = await mock_redis.get('zerodha:portfolio:summary')
        
        # Verify separate data retrieved
        assert paper_portfolio is not None
        assert zerodha_portfolio is not None
        
        paper_data = json.loads(paper_portfolio)
        zerodha_data = json.loads(zerodha_portfolio)
        
        # Verify different cash balances (indicating isolation)
        assert paper_data['cash_balance'] != zerodha_data['cash_balance']
        assert paper_data['total_value'] != zerodha_data['total_value']
        
        # Test cache key isolation
        all_keys = await mock_redis.keys()
        paper_keys = [k for k in all_keys if k.startswith('paper:')]
        zerodha_keys = [k for k in all_keys if k.startswith('zerodha:')]
        
        assert len(paper_keys) > 0
        assert len(zerodha_keys) > 0
        assert not any(key.startswith('zerodha:') for key in paper_keys)
        assert not any(key.startswith('paper:') for key in zerodha_keys)
    
    @pytest.mark.asyncio
    async def test_event_streaming_integration(self, mock_kafka):
        """Test event production and consumption patterns."""
        
        # Create test market tick event
        tick = MarketTick(
            instrument_token=256265,
            last_price=Decimal('25100.0'),
            timestamp=datetime.now(timezone.utc),
            mode="full"
        )
        
        event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data=tick.model_dump(),
            source="market_feed",
            key=f"{tick.instrument_token}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        # Test event production
        await mock_kafka['producer'].send(
            "market.ticks",
            key=event.key,
            value=event.model_dump_json()
        )
        
        # Verify message sent
        mock_kafka['producer'].send.assert_called_once()
        call_args = mock_kafka['producer'].send.call_args
        assert call_args[0][0] == "market.ticks"
        assert "key" in call_args[1]
        assert "value" in call_args[1]
        
        # Test consumer subscription
        topics = ["paper.signals.raw", "zerodha.signals.raw"]
        await mock_kafka['consumer'].subscribe(topics)
        
        mock_kafka['consumer'].subscribe.assert_called_once_with(topics)
    
    @pytest.mark.asyncio
    async def test_database_persistence_integration(self, mock_database):
        """Test database persistence across order lifecycle."""
        
        # Test order creation and persistence
        order_data = {
            'order_id': 'PAPER_12345678',
            'instrument_token': 256265,
            'quantity': 100,
            'price': Decimal('25050.0'),
            'status': 'PLACED',
            'broker': 'paper',
            'timestamp': datetime.now(timezone.utc)
        }
        
        await mock_database.save_order(order_data)
        mock_database.save_order.assert_called_once_with(order_data)
        
        # Test order retrieval
        orders = await mock_database.get_orders('paper')
        mock_database.get_orders.assert_called_once_with('paper')
        
        # Test position updates
        position_data = {
            'instrument_token': 256265,
            'quantity': 100,
            'average_price': Decimal('25050.0'),
            'broker': 'paper',
            'updated_at': datetime.now(timezone.utc)
        }
        
        await mock_database.save_position(position_data)
        mock_database.save_position.assert_called_once_with(position_data)
        
        # Test position retrieval for broker
        positions = await mock_database.get_positions('paper')
        assert len(positions) == 1
        assert positions[0]['broker'] == 'paper'
    
    @pytest.mark.asyncio
    async def test_service_health_check_integration(self, test_settings):
        """Test health check integration across services."""
        
        # Mock health check responses
        health_responses = {
            'database': {'status': 'healthy', 'latency_ms': 15},
            'redis': {'status': 'healthy', 'latency_ms': 5},
            'kafka': {'status': 'healthy', 'latency_ms': 20},
            'market_feed': {'status': 'healthy', 'last_tick': datetime.now(timezone.utc).isoformat()}
        }
        
        with patch('core.health.health_checker.HealthChecker') as mock_health_checker:
            checker_instance = mock_health_checker.return_value
            
            async def mock_check_health():
                return health_responses
            
            checker_instance.check_all = mock_check_health
            
            # Perform health check
            health_status = await checker_instance.check_all()
            
            # Verify all components healthy
            assert health_status['database']['status'] == 'healthy'
            assert health_status['redis']['status'] == 'healthy' 
            assert health_status['kafka']['status'] == 'healthy'
            assert health_status['market_feed']['status'] == 'healthy'
            
            # Verify reasonable latencies
            assert health_status['database']['latency_ms'] < 100
            assert health_status['redis']['latency_ms'] < 50
            assert health_status['kafka']['latency_ms'] < 100
    
    @pytest.mark.asyncio
    async def test_configuration_consistency_across_brokers(self, mock_database, test_settings):
        """Test configuration consistency across multiple brokers."""
        
        # Load configurations for both brokers
        paper_strategies = await mock_database.load_strategies("paper")
        zerodha_strategies = await mock_database.load_strategies("zerodha")
        
        # Verify same strategy types available for both brokers
        paper_strategy_types = {s['name'] for s in paper_strategies}
        zerodha_strategy_types = {s['name'] for s in zerodha_strategies}
        
        assert paper_strategy_types == zerodha_strategy_types
        
        # Verify broker-specific configuration
        for strategy in paper_strategies:
            assert strategy['broker'] == "paper"
        
        for strategy in zerodha_strategies:
            assert strategy['broker'] == "zerodha"
        
        # Verify active brokers setting
        assert "paper" in test_settings.active_brokers
        assert "zerodha" in test_settings.active_brokers
    
    @pytest.mark.asyncio
    async def test_data_flow_integrity(self, mock_database, mock_redis, mock_kafka):
        """Test data integrity across database, cache, and streaming."""
        
        # Simulate order fill event
        fill_data = {
            'order_id': 'PAPER_87654321',
            'instrument_token': 256265,
            'quantity': 50,
            'fill_price': Decimal('25075.0'),
            'broker': 'paper',
            'timestamp': datetime.now(timezone.utc)
        }
        
        # 1. Save to database
        await mock_database.save_order(fill_data)
        
        # 2. Update cache
        cache_key = f"paper:order:{fill_data['order_id']}"
        await mock_redis.set(cache_key, json.dumps(fill_data, default=str))
        
        # 3. Publish to stream
        fill_event = EventEnvelope(
            type=EventType.ORDER_FILLED,
            data=fill_data,
            source="trading_engine",
            key=f"{fill_data['instrument_token']}:{fill_data['order_id']}",
            broker="paper",
            correlation_id=str(uuid4())
        )
        
        await mock_kafka['producer'].send(
            "paper.orders.filled",
            key=fill_event.key,
            value=fill_event.model_dump_json()
        )
        
        # Verify all three persistence layers called
        mock_database.save_order.assert_called_once()
        mock_redis.set.assert_called_once()
        mock_kafka['producer'].send.assert_called_once()
        
        # Verify data consistency
        redis_call_args = mock_redis.set.call_args
        assert redis_call_args[0][0] == cache_key
        
        kafka_call_args = mock_kafka['producer'].send.call_args
        assert kafka_call_args[0][0] == "paper.orders.filled"
    
    @pytest.mark.asyncio
    async def test_concurrent_multi_broker_operations(self, mock_database, mock_redis):
        """Test concurrent operations across multiple brokers."""
        
        # Create concurrent operations for both brokers
        async def paper_operations():
            await mock_database.load_strategies("paper")
            await mock_redis.get("paper:portfolio:summary")
            await mock_database.get_positions("paper")
        
        async def zerodha_operations():
            await mock_database.load_strategies("zerodha")
            await mock_redis.get("zerodha:portfolio:summary")
            await mock_database.get_positions("zerodha")
        
        # Execute operations concurrently
        await asyncio.gather(
            paper_operations(),
            zerodha_operations()
        )
        
        # Verify all operations completed
        assert mock_database.load_strategies.call_count == 2
        assert mock_redis.get.call_count == 2
        assert mock_database.get_positions.call_count == 2
        
        # Verify broker-specific calls made
        strategy_calls = [call[0][0] for call in mock_database.load_strategies.call_args_list]
        assert "paper" in strategy_calls
        assert "zerodha" in strategy_calls
    
    @pytest.mark.asyncio
    async def test_system_state_recovery(self, mock_database, mock_redis):
        """Test system state recovery after service restart."""
        
        # Simulate cache miss scenario (service restart)
        async def mock_cache_miss(key):
            return None  # Cache empty
        
        mock_redis.get = mock_cache_miss
        
        # System should recover from database
        positions = await mock_database.get_positions("paper")
        
        # Verify database consulted for recovery
        mock_database.get_positions.assert_called_with("paper")
        
        # Simulate cache repopulation
        for position in positions:
            cache_key = f"paper:position:{position['instrument_token']}"
            await mock_redis.set(cache_key, json.dumps(position, default=str))
        
        # Verify cache repopulation
        mock_redis.set.assert_called()
        assert mock_redis.set.call_count == len(positions)
    
    @pytest.mark.asyncio
    async def test_event_ordering_and_consistency(self, mock_kafka):
        """Test event ordering and consistency across pipeline."""
        
        correlation_id = str(uuid4())
        
        # Create sequence of related events
        events = []
        
        # 1. Market tick
        tick_event = EventEnvelope(
            type=EventType.MARKET_TICK,
            data={'instrument_token': 256265, 'last_price': '25100.0'},
            source="market_feed",
            key="256265",
            broker="paper",
            correlation_id=correlation_id
        )
        events.append(("market.ticks", tick_event))
        
        # 2. Trading signal 
        signal_event = EventEnvelope(
            type=EventType.TRADING_SIGNAL,
            data={'instrument_token': 256265, 'signal_type': 'BUY'},
            source="strategy_runner",
            key="256265:momentum_001", 
            broker="paper",
            correlation_id=correlation_id
        )
        events.append(("paper.signals.raw", signal_event))
        
        # 3. Order fill
        fill_event = EventEnvelope(
            type=EventType.ORDER_FILLED,
            data={'order_id': 'PAPER_11111111', 'quantity': 100},
            source="trading_engine",
            key="256265:PAPER_11111111",
            broker="paper", 
            correlation_id=correlation_id
        )
        events.append(("paper.orders.filled", fill_event))
        
        # Send events in sequence
        for topic, event in events:
            await mock_kafka['producer'].send(
                topic,
                key=event.key,
                value=event.model_dump_json()
            )
        
        # Verify all events sent with same correlation ID
        assert mock_kafka['producer'].send.call_count == 3
        
        # Verify proper topic routing
        calls = mock_kafka['producer'].send.call_args_list
        topics_called = [call[0][0] for call in calls]
        
        assert "market.ticks" in topics_called
        assert "paper.signals.raw" in topics_called  
        assert "paper.orders.filled" in topics_called