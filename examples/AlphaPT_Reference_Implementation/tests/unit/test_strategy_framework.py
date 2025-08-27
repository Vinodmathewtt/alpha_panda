"""
Unit tests for AlphaPT strategy framework.

Tests strategy management, health monitoring, configuration loading,
and strategy execution lifecycle.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone
from decimal import Decimal

from strategy_manager.strategy_manager import StrategyManager
from strategy_manager.strategy_health_monitor import StrategyHealthMonitor
from strategy_manager.config.config_loader import strategy_config_loader
from core.config.settings import Settings


@pytest.mark.unit
class TestStrategyManager:
    """Test StrategyManager functionality."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.debug = True
        settings.environment = "testing"
        return settings
        
    @pytest.fixture
    def mock_event_bus(self):
        """Create mock event bus."""
        event_bus = Mock()
        event_bus.publish = AsyncMock()
        event_bus.subscribe = AsyncMock()
        return event_bus
        
    @pytest.fixture
    def sample_strategy_config(self):
        """Create sample strategy configuration."""
        return {
            "test_strategy": {
                "strategy_type": "momentum",
                "enabled": True,
                "parameters": {
                    "lookback_periods": 20,
                    "threshold": 0.02
                },
                "instruments": ["RELIANCE", "TCS"],
                "risk_limits": {
                    "max_position_value": 50000,
                    "max_daily_loss": 5000
                },
                "routing": {
                    "paper_trade": True,
                    "zerodha_trade": False
                }
            }
        }
    
    def test_strategy_manager_initialization(self, mock_settings, mock_event_bus):
        """Test StrategyManager initialization."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        assert manager.settings == mock_settings
        assert manager.event_bus == mock_event_bus
        assert manager.strategies == {}
        assert manager.running_strategies == set()
        
    @pytest.mark.asyncio
    async def test_strategy_manager_initialize_success(self, mock_settings, mock_event_bus):
        """Test successful strategy manager initialization."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        with patch.object(manager, '_discover_strategies', return_value=None), \
             patch.object(manager, '_setup_event_subscriptions', return_value=None):
            
            result = await manager.initialize()
            
            assert result is True
            
    @pytest.mark.asyncio
    async def test_strategy_discovery(self, mock_settings, mock_event_bus, sample_strategy_config):
        """Test strategy discovery and registration."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        with patch.object(strategy_config_loader, 'get_enabled_strategies', return_value=sample_strategy_config):
            await manager._discover_strategies()
            
            # Verify strategies were discovered
            assert len(manager.strategies) > 0
            
    @pytest.mark.asyncio
    async def test_start_strategies(self, mock_settings, mock_event_bus):
        """Test starting strategies."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock strategy instance
        mock_strategy = Mock()
        mock_strategy.start = AsyncMock(return_value=True)
        mock_strategy.name = "test_strategy"
        
        manager.strategies = {"test_strategy": mock_strategy}
        
        await manager.start_strategies()
        
        assert "test_strategy" in manager.running_strategies
        mock_strategy.start.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_stop_strategies(self, mock_settings, mock_event_bus):
        """Test stopping strategies."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock strategy instance
        mock_strategy = Mock()
        mock_strategy.stop = AsyncMock(return_value=True)
        mock_strategy.name = "test_strategy"
        
        manager.strategies = {"test_strategy": mock_strategy}
        manager.running_strategies = {"test_strategy"}
        
        await manager.stop_strategies()
        
        assert "test_strategy" not in manager.running_strategies
        mock_strategy.stop.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_process_market_data_event(self, mock_settings, mock_event_bus):
        """Test processing market data events."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.process_market_data = AsyncMock()
        mock_strategy.instruments = [738561]
        
        manager.strategies = {"test_strategy": mock_strategy}
        manager.running_strategies = {"test_strategy"}
        
        # Mock market data event
        market_event = Mock()
        market_event.instrument_token = 738561
        market_event.last_price = 2500.50
        market_event.data = {"volume": 1000000}
        
        await manager._handle_market_data_event(market_event)
        
        mock_strategy.process_market_data.assert_called_once_with(market_event)
        
    @pytest.mark.asyncio
    async def test_strategy_signal_generation(self, mock_settings, mock_event_bus):
        """Test strategy signal generation and publishing."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock strategy that generates signal
        mock_strategy = Mock()
        mock_strategy.name = "test_strategy"
        mock_signal = {
            "strategy_name": "test_strategy",
            "instrument_token": 738561,
            "action": "BUY",
            "quantity": 10,
            "price": Decimal("2500.50"),
            "confidence": 0.85
        }
        mock_strategy.generate_signal = AsyncMock(return_value=mock_signal)
        
        manager.strategies = {"test_strategy": mock_strategy}
        
        # Mock market data
        market_data = {
            "instrument_token": 738561,
            "last_price": 2500.50,
            "volume": 1000000
        }
        
        await manager._process_strategy_signals("test_strategy", market_data)
        
        # Verify signal was generated and published
        mock_strategy.generate_signal.assert_called_once()
        mock_event_bus.publish.assert_called_once()
        
    def test_get_strategy_status(self, mock_settings, mock_event_bus):
        """Test getting strategy status."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock strategies
        mock_strategy1 = Mock()
        mock_strategy1.name = "strategy1"
        mock_strategy1.get_status = Mock(return_value={"status": "running"})
        
        mock_strategy2 = Mock()
        mock_strategy2.name = "strategy2"
        mock_strategy2.get_status = Mock(return_value={"status": "stopped"})
        
        manager.strategies = {
            "strategy1": mock_strategy1,
            "strategy2": mock_strategy2
        }
        manager.running_strategies = {"strategy1"}
        
        status = manager.get_strategy_status()
        
        assert status["total_strategies"] == 2
        assert status["running_strategies"] == 1
        assert "strategy1" in status["strategies"]
        assert "strategy2" in status["strategies"]
        
    @pytest.mark.asyncio
    async def test_health_check(self, mock_settings, mock_event_bus):
        """Test strategy manager health check."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock strategies with health status
        mock_strategy = Mock()
        mock_strategy.name = "test_strategy"
        mock_strategy.get_health = Mock(return_value={"status": "healthy", "last_signal": datetime.now(timezone.utc)})
        
        manager.strategies = {"test_strategy": mock_strategy}
        manager.running_strategies = {"test_strategy"}
        
        health = await manager.health_check()
        
        assert health["status"] == "healthy"
        assert health["total_strategies"] == 1
        assert health["running_strategies"] == 1
        assert "test_strategy" in health["strategy_details"]
        
    @pytest.mark.asyncio
    async def test_cleanup(self, mock_settings, mock_event_bus):
        """Test strategy manager cleanup."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        with patch.object(manager, 'stop_strategies', new_callable=AsyncMock) as mock_stop:
            await manager.cleanup()
            mock_stop.assert_called_once()


@pytest.mark.unit
class TestStrategyHealthMonitor:
    """Test StrategyHealthMonitor functionality."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.debug = True
        return settings
        
    @pytest.fixture
    def mock_event_bus(self):
        """Create mock event bus."""
        event_bus = Mock()
        event_bus.subscribe = AsyncMock()
        return event_bus
    
    def test_health_monitor_initialization(self, mock_settings, mock_event_bus):
        """Test health monitor initialization."""
        monitor = StrategyHealthMonitor(mock_settings, mock_event_bus)
        
        assert monitor.settings == mock_settings
        assert monitor.event_bus == mock_event_bus
        assert monitor.strategy_metrics == {}
        
    @pytest.mark.asyncio
    async def test_track_strategy_performance(self, mock_settings, mock_event_bus):
        """Test tracking strategy performance metrics."""
        monitor = StrategyHealthMonitor(mock_settings, mock_event_bus)
        
        strategy_name = "test_strategy"
        signal_data = {
            "strategy_name": strategy_name,
            "action": "BUY",
            "confidence": 0.85,
            "timestamp": datetime.now(timezone.utc)
        }
        
        monitor.track_strategy_signal(strategy_name, signal_data)
        
        assert strategy_name in monitor.strategy_metrics
        assert monitor.strategy_metrics[strategy_name]["total_signals"] == 1
        assert monitor.strategy_metrics[strategy_name]["last_signal_time"] is not None
        
    @pytest.mark.asyncio
    async def test_detect_strategy_issues(self, mock_settings, mock_event_bus):
        """Test detecting strategy health issues."""
        monitor = StrategyHealthMonitor(mock_settings, mock_event_bus)
        
        strategy_name = "test_strategy"
        
        # Initialize metrics
        monitor.strategy_metrics[strategy_name] = {
            "total_signals": 0,
            "successful_signals": 0,
            "failed_signals": 10,  # High failure rate
            "last_signal_time": datetime.now(timezone.utc),
            "avg_processing_time": 5.0,
            "health_score": 0.2  # Low health score
        }
        
        issues = monitor._detect_strategy_issues(strategy_name)
        
        assert len(issues) > 0
        assert any("high failure rate" in issue.lower() for issue in issues)
        
    @pytest.mark.asyncio
    async def test_get_health_summary(self, mock_settings, mock_event_bus):
        """Test getting health summary."""
        monitor = StrategyHealthMonitor(mock_settings, mock_event_bus)
        
        # Add some test metrics
        monitor.strategy_metrics = {
            "strategy1": {
                "total_signals": 100,
                "successful_signals": 95,
                "failed_signals": 5,
                "health_score": 0.95,
                "last_signal_time": datetime.now(timezone.utc)
            },
            "strategy2": {
                "total_signals": 50,
                "successful_signals": 30,
                "failed_signals": 20,
                "health_score": 0.60,
                "last_signal_time": datetime.now(timezone.utc)
            }
        }
        
        summary = await monitor.get_health_summary()
        
        assert summary["total_strategies"] == 2
        assert "healthy_strategies" in summary
        assert "strategy_details" in summary
        assert len(summary["strategy_details"]) == 2


@pytest.mark.unit
class TestStrategyConfigLoader:
    """Test strategy configuration loading."""
    
    def test_get_enabled_strategies(self):
        """Test loading enabled strategy configurations."""
        # Mock configuration files
        mock_config = {
            "momentum_strategy": {
                "strategy_type": "momentum",
                "enabled": True,
                "parameters": {"threshold": 0.02}
            },
            "disabled_strategy": {
                "strategy_type": "mean_reversion",
                "enabled": False,
                "parameters": {"period": 20}
            }
        }
        
        with patch.object(strategy_config_loader, '_load_config_files', return_value=mock_config):
            enabled_strategies = strategy_config_loader.get_enabled_strategies()
            
            # Should only return enabled strategies
            assert "momentum_strategy" in enabled_strategies
            assert "disabled_strategy" not in enabled_strategies
            
    def test_get_strategy_config(self):
        """Test getting individual strategy configuration."""
        mock_config = {
            "test_strategy": {
                "strategy_type": "momentum",
                "enabled": True,
                "parameters": {"threshold": 0.02}
            }
        }
        
        with patch.object(strategy_config_loader, '_load_config_files', return_value=mock_config):
            config = strategy_config_loader.get_strategy_config("test_strategy")
            
            assert config is not None
            assert config["strategy_type"] == "momentum"
            assert config["enabled"] is True
            
    def test_get_strategy_config_not_found(self):
        """Test getting configuration for non-existent strategy."""
        with patch.object(strategy_config_loader, '_load_config_files', return_value={}):
            config = strategy_config_loader.get_strategy_config("non_existent")
            assert config is None
            
    def test_reload_configs(self):
        """Test reloading strategy configurations."""
        # This should not raise exceptions
        strategy_config_loader.reload_configs()
        assert True


@pytest.mark.unit
class TestStrategyExecution:
    """Test strategy execution scenarios."""
    
    @pytest.fixture
    def mock_strategy_instance(self):
        """Create mock strategy instance."""
        strategy = Mock()
        strategy.name = "test_strategy"
        strategy.instruments = [738561, 408065]
        strategy.parameters = {"threshold": 0.02}
        strategy.start = AsyncMock(return_value=True)
        strategy.stop = AsyncMock(return_value=True)
        strategy.process_market_data = AsyncMock()
        strategy.generate_signal = AsyncMock(return_value=None)
        strategy.get_status = Mock(return_value={"status": "running"})
        strategy.get_health = Mock(return_value={"status": "healthy"})
        return strategy
    
    @pytest.mark.asyncio
    async def test_strategy_lifecycle(self, mock_settings, mock_event_bus, mock_strategy_instance):
        """Test complete strategy lifecycle."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        manager.strategies = {"test_strategy": mock_strategy_instance}
        
        # Test start
        await manager.start_strategies()
        assert "test_strategy" in manager.running_strategies
        mock_strategy_instance.start.assert_called_once()
        
        # Test processing data
        market_event = Mock()
        market_event.instrument_token = 738561
        market_event.last_price = 2500.50
        
        await manager._handle_market_data_event(market_event)
        mock_strategy_instance.process_market_data.assert_called_once()
        
        # Test stop
        await manager.stop_strategies()
        assert "test_strategy" not in manager.running_strategies
        mock_strategy_instance.stop.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_strategy_signal_routing(self, mock_settings, mock_event_bus):
        """Test strategy signal routing to different trading engines."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock strategy that generates signals for both paper and live trading
        mock_strategy = Mock()
        mock_strategy.name = "routing_strategy"
        mock_strategy.config = {
            "routing": {
                "paper_trade": True,
                "zerodha_trade": True
            }
        }
        
        signal_data = {
            "strategy_name": "routing_strategy",
            "instrument_token": 738561,
            "action": "BUY",
            "quantity": 10,
            "confidence": 0.85
        }
        
        manager.strategies = {"routing_strategy": mock_strategy}
        
        await manager._publish_trading_signal(signal_data, mock_strategy.config)
        
        # Should publish to both paper trading and live trading subjects
        assert mock_event_bus.publish.call_count >= 1
        
    @pytest.mark.asyncio
    async def test_multiple_strategy_coordination(self, mock_settings, mock_event_bus):
        """Test coordination between multiple strategies."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Create multiple mock strategies
        strategies = {}
        for i in range(3):
            strategy_name = f"strategy_{i}"
            mock_strategy = Mock()
            mock_strategy.name = strategy_name
            mock_strategy.instruments = [738561 + i]
            mock_strategy.start = AsyncMock(return_value=True)
            mock_strategy.process_market_data = AsyncMock()
            strategies[strategy_name] = mock_strategy
        
        manager.strategies = strategies
        
        # Start all strategies
        await manager.start_strategies()
        
        # Verify all strategies are running
        assert len(manager.running_strategies) == 3
        for strategy in strategies.values():
            strategy.start.assert_called_once()
            
        # Test market data distribution
        market_event = Mock()
        market_event.instrument_token = 738561  # Matches strategy_0
        
        await manager._handle_market_data_event(market_event)
        
        # Only strategy_0 should receive this market data
        strategies["strategy_0"].process_market_data.assert_called_once()
        strategies["strategy_1"].process_market_data.assert_not_called()
        strategies["strategy_2"].process_market_data.assert_not_called()


@pytest.mark.unit
class TestStrategyRiskIntegration:
    """Test strategy integration with risk management."""
    
    @pytest.mark.asyncio
    async def test_strategy_risk_check_before_signal(self, mock_settings, mock_event_bus):
        """Test that strategies check risk before generating signals."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock risk manager
        mock_risk_manager = Mock()
        mock_risk_manager.check_pre_trade_risk = AsyncMock(return_value={"approved": False, "reason": "Position limit exceeded"})
        
        manager.risk_manager = mock_risk_manager
        
        signal_data = {
            "strategy_name": "test_strategy",
            "instrument_token": 738561,
            "action": "BUY",
            "quantity": 100,  # Large quantity that might exceed limits
            "price": Decimal("2500.00")
        }
        
        # Should not publish signal if risk check fails
        result = await manager._validate_and_publish_signal(signal_data)
        
        assert result is False
        mock_event_bus.publish.assert_not_called()
        
    @pytest.mark.asyncio
    async def test_strategy_position_tracking(self, mock_settings, mock_event_bus):
        """Test that strategies track their positions correctly."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock strategy with position tracking
        mock_strategy = Mock()
        mock_strategy.name = "position_strategy"
        mock_strategy.positions = {}
        mock_strategy.update_position = Mock()
        
        manager.strategies = {"position_strategy": mock_strategy}
        
        # Mock order fill event
        fill_event = Mock()
        fill_event.strategy_name = "position_strategy"
        fill_event.instrument_token = 738561
        fill_event.quantity = 10
        fill_event.price = Decimal("2500.00")
        fill_event.action = "BUY"
        
        await manager._handle_order_fill_event(fill_event)
        
        # Strategy should update its position
        mock_strategy.update_position.assert_called_once_with(fill_event)


@pytest.mark.unit
class TestStrategyPerformanceTracking:
    """Test strategy performance tracking and analytics."""
    
    @pytest.mark.asyncio
    async def test_strategy_pnl_calculation(self, mock_settings, mock_event_bus):
        """Test strategy P&L calculation."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock strategy with position and P&L tracking
        mock_strategy = Mock()
        mock_strategy.name = "pnl_strategy"
        mock_strategy.calculate_pnl = Mock(return_value={"realized_pnl": 1500.0, "unrealized_pnl": 250.0})
        
        manager.strategies = {"pnl_strategy": mock_strategy}
        
        pnl = manager.get_strategy_pnl("pnl_strategy")
        
        assert pnl["realized_pnl"] == 1500.0
        assert pnl["unrealized_pnl"] == 250.0
        mock_strategy.calculate_pnl.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_strategy_performance_metrics(self, mock_settings, mock_event_bus):
        """Test comprehensive strategy performance metrics."""
        manager = StrategyManager(mock_settings, mock_event_bus)
        
        # Mock strategy with performance data
        mock_strategy = Mock()
        mock_strategy.name = "perf_strategy"
        mock_strategy.get_performance_metrics = Mock(return_value={
            "total_trades": 50,
            "winning_trades": 35,
            "losing_trades": 15,
            "win_rate": 0.70,
            "avg_win": 150.0,
            "avg_loss": -80.0,
            "sharpe_ratio": 1.5,
            "max_drawdown": -500.0
        })
        
        manager.strategies = {"perf_strategy": mock_strategy}
        
        metrics = manager.get_strategy_performance("perf_strategy")
        
        assert metrics["win_rate"] == 0.70
        assert metrics["sharpe_ratio"] == 1.5
        assert metrics["total_trades"] == 50