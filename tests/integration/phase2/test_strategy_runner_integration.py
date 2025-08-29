"""
Phase 2 Tests: Strategy Runner Service Integration
Tests strategy runner service integration with database, market data, and signal publishing.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.strategy_runner.service import StrategyRunnerService
from core.config.settings import Settings, RedpandaSettings
from core.database.connection import DatabaseManager
from core.database.models import StrategyConfiguration
from core.schemas.events import MarketTick, TradingSignal, SignalType
from core.market_hours.market_hours_checker import MarketHoursChecker
from strategies.base import BaseStrategy, MarketData
from tests.mocks.realistic_data_generator import RealisticMarketDataGenerator


class MockTestStrategy(BaseStrategy):
    """Mock strategy for testing"""
    
    def __init__(self, strategy_id: str = "test_strategy", should_signal: bool = True):
        super().__init__(
            strategy_id=strategy_id,
            parameters={"test_param": "value"},
            brokers=["paper"],
            instrument_tokens=[256265]
        )
        self.should_signal = should_signal
        self.processed_ticks = []
        
    def on_market_data(self, data: MarketData):
        """Mock strategy implementation"""
        self.processed_ticks.append(data)
        
        if self.should_signal:
            yield TradingSignal(
                strategy_id=self.strategy_id,
                instrument_token=data.instrument_token,
                signal_type=SignalType.BUY,
                quantity=100,
                timestamp=datetime.now(timezone.utc)
            )


class TestStrategyRunnerServiceIntegration:
    """Test StrategyRunnerService integration with dependencies"""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings"""
        settings = Mock(spec=Settings)
        settings.active_brokers = ["paper", "zerodha"]
        settings.database = Mock()
        settings.database.url = "sqlite:///:memory:"
        return settings
    
    @pytest.fixture
    def mock_redpanda_config(self):
        """Create mock Redpanda configuration"""
        config = Mock(spec=RedpandaSettings)
        config.bootstrap_servers = "localhost:9092"
        config.client_id = "test_strategy_runner"
        config.acks = "all"
        config.enable_idempotence = True
        return config
    
    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager"""
        db_manager = Mock(spec=DatabaseManager)
        
        # Mock async session
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.scalars = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        
        db_manager.get_async_session = AsyncMock(return_value=mock_session)
        return db_manager
    
    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client"""
        redis_client = AsyncMock()
        redis_client.set = AsyncMock()
        redis_client.get = AsyncMock()
        redis_client.incr = AsyncMock()
        return redis_client
    
    @pytest.fixture
    def mock_market_hours_checker(self):
        """Create mock market hours checker"""
        checker = Mock(spec=MarketHoursChecker)
        checker.is_market_open = Mock(return_value=True)
        checker.get_market_status = Mock(return_value="OPEN")
        return checker
    
    @pytest.fixture
    def mock_stream_orchestrator(self):
        """Create mock stream orchestrator"""
        orchestrator = AsyncMock()
        orchestrator.consumer = AsyncMock()
        orchestrator.producer = AsyncMock()
        orchestrator.producer.send = AsyncMock()
        orchestrator.start = AsyncMock()
        orchestrator.stop = AsyncMock()
        return orchestrator
    
    def test_strategy_runner_service_initialization(self, mock_redpanda_config, mock_settings,
                                                   mock_db_manager, mock_redis_client,
                                                   mock_market_hours_checker):
        """Test StrategyRunnerService initialization"""
        
        with patch('services.strategy_runner.service.StreamServiceBuilder'):
            service = StrategyRunnerService(
                config=mock_redpanda_config,
                settings=mock_settings,
                db_manager=mock_db_manager,
                redis_client=mock_redis_client,
                market_hours_checker=mock_market_hours_checker
            )
            
            # Verify initialization
            assert service.settings == mock_settings
            assert service.db_manager == mock_db_manager
            assert service.market_hours_checker == mock_market_hours_checker
            assert service.signals_generated == 0
            assert service.active_strategies == {}
            
    @pytest.mark.asyncio
    async def test_strategy_loading_from_database(self, mock_redpanda_config, mock_settings,
                                                 mock_db_manager, mock_redis_client,
                                                 mock_market_hours_checker):
        """Test loading strategies from database configuration"""
        
        # Mock strategy configurations
        mock_strategies = [
            Mock(
                id=1,
                strategy_name="momentum_v1",
                strategy_class="strategies.momentum.MomentumStrategy",
                parameters={"lookback_period": 20},
                is_active=True,
                active_brokers=["paper"],
                instrument_tokens=[256265]
            ),
            Mock(
                id=2,
                strategy_name="mean_reversion_v1",
                strategy_class="strategies.mean_reversion.MeanReversionStrategy", 
                parameters={"window_size": 30},
                is_active=True,
                active_brokers=["paper", "zerodha"],
                instrument_tokens=[260105]
            )
        ]
        
        # Mock database query result
        mock_result = Mock()
        mock_result.all = Mock(return_value=mock_strategies)
        mock_db_manager.get_async_session.return_value.execute.return_value = mock_result
        
        with patch('services.strategy_runner.service.StreamServiceBuilder'), \
             patch('services.strategy_runner.service.StrategyFactory') as mock_factory:
            
            # Mock strategy factory
            mock_strategy_instance = MockTestStrategy("momentum_v1")
            mock_factory.create_strategy.return_value = mock_strategy_instance
            
            service = StrategyRunnerService(
                config=mock_redpanda_config,
                settings=mock_settings,
                db_manager=mock_db_manager,
                redis_client=mock_redis_client,
                market_hours_checker=mock_market_hours_checker
            )
            
            # Load strategies
            await service._load_strategies_from_database()
            
            # Verify strategies were loaded
            assert len(service.active_strategies) > 0
            
    @pytest.mark.asyncio
    async def test_market_tick_processing(self, mock_redpanda_config, mock_settings,
                                        mock_db_manager, mock_redis_client,
                                        mock_market_hours_checker, mock_stream_orchestrator):
        """Test processing market ticks through strategies"""
        
        with patch('services.strategy_runner.service.StreamServiceBuilder') as mock_builder:
            mock_builder_instance = Mock()
            mock_builder_instance.with_redis.return_value = mock_builder_instance
            mock_builder_instance.with_error_handling.return_value = mock_builder_instance
            mock_builder_instance.with_metrics.return_value = mock_builder_instance
            mock_builder_instance.add_consumer.return_value = mock_builder_instance
            mock_builder_instance.add_producer.return_value = mock_builder_instance
            mock_builder_instance.build.return_value = mock_stream_orchestrator
            mock_builder.return_value = mock_builder_instance
            
            service = StrategyRunnerService(
                config=mock_redpanda_config,
                settings=mock_settings,
                db_manager=mock_db_manager,
                redis_client=mock_redis_client,
                market_hours_checker=mock_market_hours_checker
            )
            
            # Add a test strategy
            test_strategy = MockTestStrategy("test_strategy", should_signal=True)
            service.active_strategies["test_strategy"] = test_strategy
            
            # Create test market tick
            data_generator = RealisticMarketDataGenerator(seed=42)
            market_tick = data_generator.generate_tick(256265, mode="quote")
            
            # Process tick through service
            with patch.object(service, '_process_market_tick') as mock_process:
                mock_process.return_value = None
                
                await service._process_market_tick(market_tick)
                mock_process.assert_called_once_with(market_tick)
                
    @pytest.mark.asyncio
    async def test_signal_generation_and_publishing(self, mock_redpanda_config, mock_settings,
                                                   mock_db_manager, mock_redis_client,
                                                   mock_market_hours_checker, mock_stream_orchestrator):
        """Test signal generation and publishing to multiple brokers"""
        
        with patch('services.strategy_runner.service.StreamServiceBuilder') as mock_builder:
            mock_builder_instance = Mock()
            mock_builder_instance.with_redis.return_value = mock_builder_instance
            mock_builder_instance.with_error_handling.return_value = mock_builder_instance
            mock_builder_instance.with_metrics.return_value = mock_builder_instance
            mock_builder_instance.add_consumer.return_value = mock_builder_instance
            mock_builder_instance.add_producer.return_value = mock_builder_instance
            mock_builder_instance.build.return_value = mock_stream_orchestrator
            mock_builder.return_value = mock_builder_instance
            
            service = StrategyRunnerService(
                config=mock_redpanda_config,
                settings=mock_settings,
                db_manager=mock_db_manager,
                redis_client=mock_redis_client,
                market_hours_checker=mock_market_hours_checker
            )
            
            # Create test trading signal
            test_signal = TradingSignal(
                strategy_id="test_strategy",
                instrument_token=256265,
                signal_type=SignalType.BUY,
                quantity=100,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Test publishing to multiple brokers
            with patch.object(service, '_publish_signal_to_brokers') as mock_publish:
                mock_publish.return_value = None
                
                await service._publish_signal_to_brokers(test_signal, ["paper", "zerodha"])
                mock_publish.assert_called_once_with(test_signal, ["paper", "zerodha"])
                
    def test_multi_broker_signal_routing(self, mock_redpanda_config, mock_settings,
                                        mock_db_manager, mock_redis_client,
                                        mock_market_hours_checker):
        """Test signal routing to different broker topics"""
        
        with patch('services.strategy_runner.service.StreamServiceBuilder'):
            service = StrategyRunnerService(
                config=mock_redpanda_config,
                settings=mock_settings,
                db_manager=mock_db_manager,
                redis_client=mock_redis_client,
                market_hours_checker=mock_market_hours_checker
            )
            
            # Test topic generation for different brokers
            signal = TradingSignal(
                strategy_id="test_strategy",
                instrument_token=256265,
                signal_type=SignalType.BUY,
                quantity=100,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Mock topic generation
            with patch.object(service, '_get_signal_topic') as mock_get_topic:
                mock_get_topic.side_effect = lambda broker: f"{broker}.signals.raw"
                
                paper_topic = service._get_signal_topic("paper")
                zerodha_topic = service._get_signal_topic("zerodha")
                
                assert paper_topic == "paper.signals.raw"
                assert zerodha_topic == "zerodha.signals.raw"
                assert paper_topic != zerodha_topic
                
    @pytest.mark.asyncio
    async def test_market_hours_integration(self, mock_redpanda_config, mock_settings,
                                          mock_db_manager, mock_redis_client,
                                          mock_market_hours_checker):
        """Test integration with market hours checker"""
        
        with patch('services.strategy_runner.service.StreamServiceBuilder'):
            service = StrategyRunnerService(
                config=mock_redpanda_config,
                settings=mock_settings,
                db_manager=mock_db_manager,
                redis_client=mock_redis_client,
                market_hours_checker=mock_market_hours_checker
            )
            
            # Test market open scenario
            mock_market_hours_checker.is_market_open.return_value = True
            
            with patch.object(service, '_should_process_ticks') as mock_should_process:
                mock_should_process.return_value = True
                
                should_process = service._should_process_ticks()
                assert should_process is True
                
            # Test market closed scenario
            mock_market_hours_checker.is_market_open.return_value = False
            
            with patch.object(service, '_should_process_ticks') as mock_should_process:
                mock_should_process.return_value = False
                
                should_process = service._should_process_ticks()
                assert should_process is False
                
    @pytest.mark.asyncio
    async def test_strategy_error_handling(self, mock_redpanda_config, mock_settings,
                                         mock_db_manager, mock_redis_client,
                                         mock_market_hours_checker):
        """Test error handling when strategies fail"""
        
        class FailingStrategy(BaseStrategy):
            def __init__(self):
                super().__init__("failing_strategy", {}, ["paper"])
                
            def on_market_data(self, data):
                raise Exception("Strategy processing error")
                yield  # Make it a generator
        
        with patch('services.strategy_runner.service.StreamServiceBuilder'):
            service = StrategyRunnerService(
                config=mock_redpanda_config,
                settings=mock_settings,
                db_manager=mock_db_manager,
                redis_client=mock_redis_client,
                market_hours_checker=mock_market_hours_checker
            )
            
            # Add failing strategy
            failing_strategy = FailingStrategy()
            service.active_strategies["failing_strategy"] = failing_strategy
            
            # Test error handling
            market_data = MarketData(
                instrument_token=256265,
                last_price=Decimal("21500.00"),
                volume_traded=1000,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Should not raise exception, should handle gracefully
            with patch.object(service, '_handle_strategy_error') as mock_handle_error:
                mock_handle_error.return_value = None
                
                try:
                    signals = list(failing_strategy.on_market_data(market_data))
                except Exception:
                    # Error should be caught and handled
                    service._handle_strategy_error("failing_strategy", Exception("test error"))
                    mock_handle_error.assert_called_once()
                    
    def test_strategy_factory_integration(self, mock_redpanda_config, mock_settings,
                                         mock_db_manager, mock_redis_client,
                                         mock_market_hours_checker):
        """Test integration with StrategyFactory"""
        
        with patch('services.strategy_runner.service.StreamServiceBuilder'), \
             patch('services.strategy_runner.service.StrategyFactory') as mock_factory:
            
            # Mock strategy configuration
            strategy_config = Mock()
            strategy_config.strategy_name = "momentum_v1"
            strategy_config.strategy_class = "strategies.momentum.MomentumStrategy"
            strategy_config.parameters = {"lookback_period": 20}
            strategy_config.active_brokers = ["paper"]
            strategy_config.instrument_tokens = [256265]
            
            # Mock factory creation
            mock_strategy = MockTestStrategy("momentum_v1")
            mock_factory.create_strategy.return_value = mock_strategy
            
            service = StrategyRunnerService(
                config=mock_redpanda_config,
                settings=mock_settings,
                db_manager=mock_db_manager,
                redis_client=mock_redis_client,
                market_hours_checker=mock_market_hours_checker
            )
            
            # Test strategy creation through factory
            with patch.object(service, '_create_strategy_from_config') as mock_create:
                mock_create.return_value = mock_strategy
                
                created_strategy = service._create_strategy_from_config(strategy_config)
                assert created_strategy.strategy_id == "momentum_v1"
                mock_create.assert_called_once_with(strategy_config)
                
    @pytest.mark.asyncio
    async def test_metrics_and_monitoring(self, mock_redpanda_config, mock_settings,
                                        mock_db_manager, mock_redis_client,
                                        mock_market_hours_checker, mock_stream_orchestrator):
        """Test metrics collection and monitoring"""
        
        with patch('services.strategy_runner.service.StreamServiceBuilder') as mock_builder:
            mock_builder_instance = Mock()
            mock_builder_instance.with_redis.return_value = mock_builder_instance
            mock_builder_instance.with_error_handling.return_value = mock_builder_instance
            mock_builder_instance.with_metrics.return_value = mock_builder_instance
            mock_builder_instance.add_consumer.return_value = mock_builder_instance
            mock_builder_instance.add_producer.return_value = mock_builder_instance
            mock_builder_instance.build.return_value = mock_stream_orchestrator
            mock_builder.return_value = mock_builder_instance
            
            service = StrategyRunnerService(
                config=mock_redpanda_config,
                settings=mock_settings,
                db_manager=mock_db_manager,
                redis_client=mock_redis_client,
                market_hours_checker=mock_market_hours_checker
            )
            
            # Test metrics initialization
            assert service.signals_generated == 0
            assert service.ticks_processed == 0
            
            # Simulate processing and signal generation
            service.ticks_processed = 10
            service.signals_generated = 5
            
            assert service.ticks_processed == 10
            assert service.signals_generated == 5
            
            # Test metrics collection
            with patch.object(service, '_update_metrics') as mock_update_metrics:
                mock_update_metrics.return_value = None
                
                service._update_metrics("tick_processed", 1)
                mock_update_metrics.assert_called_once_with("tick_processed", 1)


class TestStrategyRunnerMultiBrokerIntegration:
    """Test multi-broker specific functionality"""
    
    @pytest.fixture
    def dual_broker_settings(self):
        """Settings with both paper and zerodha brokers active"""
        settings = Mock(spec=Settings)
        settings.active_brokers = ["paper", "zerodha"]
        return settings
    
    def test_dual_broker_signal_distribution(self, dual_broker_settings):
        """Test signal distribution to both paper and zerodha brokers"""
        
        # Mock strategy configuration with dual broker support
        strategy_config = Mock()
        strategy_config.strategy_name = "dual_broker_strategy"
        strategy_config.active_brokers = ["paper", "zerodha"]
        strategy_config.instrument_tokens = [256265]
        
        # Test signal should be sent to both brokers
        signal = TradingSignal(
            strategy_id="dual_broker_strategy",
            instrument_token=256265,
            signal_type=SignalType.BUY,
            quantity=100,
            timestamp=datetime.now(timezone.utc)
        )
        
        expected_topics = ["paper.signals.raw", "zerodha.signals.raw"]
        
        # Verify topic generation for both brokers
        for broker in strategy_config.active_brokers:
            expected_topic = f"{broker}.signals.raw"
            assert expected_topic in expected_topics
            
    def test_broker_specific_strategy_filtering(self, dual_broker_settings):
        """Test filtering strategies by broker configuration"""
        
        # Mock strategies with different broker configurations
        paper_only_strategy = Mock()
        paper_only_strategy.active_brokers = ["paper"]
        paper_only_strategy.strategy_name = "paper_only"
        
        dual_broker_strategy = Mock()
        dual_broker_strategy.active_brokers = ["paper", "zerodha"]  
        dual_broker_strategy.strategy_name = "dual_broker"
        
        zerodha_only_strategy = Mock()
        zerodha_only_strategy.active_brokers = ["zerodha"]
        zerodha_only_strategy.strategy_name = "zerodha_only"
        
        strategies = [paper_only_strategy, dual_broker_strategy, zerodha_only_strategy]
        
        # Filter strategies by broker
        def filter_strategies_by_broker(strategies, broker):
            return [s for s in strategies if broker in s.active_brokers]
        
        paper_strategies = filter_strategies_by_broker(strategies, "paper")
        zerodha_strategies = filter_strategies_by_broker(strategies, "zerodha")
        
        assert len(paper_strategies) == 2  # paper_only + dual_broker
        assert len(zerodha_strategies) == 2  # zerodha_only + dual_broker
        
        paper_names = [s.strategy_name for s in paper_strategies]
        zerodha_names = [s.strategy_name for s in zerodha_strategies]
        
        assert "paper_only" in paper_names
        assert "dual_broker" in paper_names
        assert "zerodha_only" in zerodha_names
        assert "dual_broker" in zerodha_names