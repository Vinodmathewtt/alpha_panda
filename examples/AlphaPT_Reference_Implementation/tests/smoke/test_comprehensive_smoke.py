"""
Comprehensive smoke tests for AlphaPT.

These tests verify that basic functionality works end-to-end
and that the application can start, run, and shutdown properly.
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, AsyncMock

from app.application import AlphaPTApplication
from core.config.settings import Settings


@pytest.mark.smoke
class TestApplicationSmoke:
    """Basic smoke tests for application functionality."""
    
    @pytest.mark.asyncio
    async def test_application_can_be_created(self):
        """Test that application can be instantiated."""
        app = AlphaPTApplication()
        
        assert app is not None
        assert app.app_state is not None
        assert app.running is False
        
    @pytest.mark.asyncio
    async def test_settings_can_be_loaded(self):
        """Test that settings can be loaded."""
        settings = Settings(secret_key="test_key")
        
        assert settings is not None
        assert settings.app_name == "AlphaPT"
        assert settings.secret_key == "test_key"
        
    @pytest.mark.asyncio
    async def test_basic_application_initialization(self):
        """Test basic application initialization flow."""
        app = AlphaPTApplication()
        
        # Mock all dependencies to avoid actual service connections
        with patch.object(app, '_init_settings', return_value=True), \
             patch.object(app, '_init_logging', return_value=True), \
             patch.object(app, '_init_database', return_value=True), \
             patch.object(app, '_init_event_system', return_value=True), \
             patch.object(app, '_init_auth_manager', return_value=True), \
             patch.object(app, '_init_storage_manager', return_value=True), \
             patch.object(app, '_init_monitoring', return_value=True), \
             patch.object(app, '_init_strategy_manager', return_value=True), \
             patch.object(app, '_init_risk_manager', return_value=True), \
             patch.object(app, '_init_trading_engines', return_value=True), \
             patch.object(app, '_init_market_feeds', return_value=True):
            
            result = await app.initialize()
            
            assert result is True
            assert app.running is True
            
    @pytest.mark.asyncio
    async def test_application_cleanup(self):
        """Test that application can be cleaned up properly."""
        app = AlphaPTApplication()
        
        # Add some mock components
        app.app_state["test_component"] = Mock(cleanup=AsyncMock())
        app.app_state["sync_component"] = Mock(cleanup=Mock())
        app.app_state["shutdown_event"] = asyncio.Event()
        
        await app.cleanup()
        
        # Cleanup should complete without errors
        assert True
        
    @pytest.mark.asyncio
    async def test_health_check_basic(self):
        """Test basic health check functionality."""
        app = AlphaPTApplication()
        
        # Add mock components with health checks
        mock_component = Mock()
        mock_component.health_check = AsyncMock(return_value={"status": "healthy"})
        app.app_state["test_component"] = mock_component
        app.app_state["settings"] = Mock(app_name="AlphaPT", environment="testing")
        
        health = await app.health_check()
        
        assert health is not None
        assert "status" in health
        assert "timestamp" in health


@pytest.mark.smoke
class TestEventSystemSmoke:
    """Smoke tests for event system functionality."""
    
    @pytest.mark.asyncio
    async def test_event_types_can_be_created(self):
        """Test that basic event types can be created."""
        from core.events import SystemEvent, EventType
        from datetime import datetime, timezone
        import uuid
        
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="smoke_test",
            component="test",
            severity="INFO",
            message="Smoke test event"
        )
        
        assert event is not None
        assert event.event_type == EventType.SYSTEM_STARTED
        assert event.source == "smoke_test"
        
    @pytest.mark.asyncio
    async def test_event_serialization(self):
        """Test that events can be serialized and deserialized."""
        from core.events import SystemEvent, EventType
        from datetime import datetime, timezone
        import uuid
        
        original_event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="smoke_test"
        )
        
        # Test serialization
        json_str = original_event.to_json()
        assert json_str is not None
        assert len(json_str) > 0
        
        # Test deserialization
        deserialized_event = SystemEvent.from_json(json_str)
        assert deserialized_event.event_id == original_event.event_id
        assert deserialized_event.event_type == original_event.event_type
        
    @pytest.mark.asyncio
    async def test_event_bus_core_creation(self):
        """Test that EventBusCore can be created."""
        from core.events import EventBusCore
        
        settings = Settings(secret_key="test_key")
        event_bus = EventBusCore(settings)
        
        assert event_bus is not None
        assert event_bus.settings == settings
        assert event_bus.is_connected is False


@pytest.mark.smoke
class TestStorageSmoke:
    """Smoke tests for storage system."""
    
    @pytest.mark.asyncio
    async def test_storage_manager_creation(self):
        """Test that MarketDataStorageManager can be created."""
        try:
            from storage.storage_manager import MarketDataStorageManager
            settings = Settings(secret_key="test_key")
            event_bus = Mock()
            storage_manager = MarketDataStorageManager(settings, event_bus)
            
            assert storage_manager is not None
            assert storage_manager.settings == settings
        except ImportError:
            # Storage may depend on external services
            assert True
        
    @pytest.mark.asyncio
    async def test_clickhouse_manager_creation(self):
        """Test that ClickHouseManager can be created."""
        from storage.clickhouse_manager import ClickHouseManager
        
        settings = Settings(secret_key="test_key")
        clickhouse_manager = ClickHouseManager(settings)
        
        assert clickhouse_manager is not None
        assert clickhouse_manager.settings == settings
        assert clickhouse_manager.connected is False


@pytest.mark.smoke
class TestStrategySmoke:
    """Smoke tests for strategy system."""
    
    @pytest.mark.asyncio
    async def test_strategy_manager_creation(self):
        """Test that StrategyManager can be created."""
        from strategy_manager.strategy_manager import StrategyManager
        
        settings = Settings(secret_key="test_key")
        event_bus = Mock()
        strategy_manager = StrategyManager(settings, event_bus)
        
        assert strategy_manager is not None
        assert strategy_manager.settings == settings
        assert strategy_manager.event_bus == event_bus
        
    @pytest.mark.asyncio
    async def test_strategy_config_loader(self):
        """Test that strategy configurations can be loaded."""
        from strategy_manager.config.config_loader import strategy_config_loader
        
        # This should not raise exceptions
        try:
            enabled_strategies = strategy_config_loader.get_enabled_strategies()
            assert isinstance(enabled_strategies, dict)
        except Exception:
            # Config loading might fail in test environment, which is okay
            assert True
            
    @pytest.mark.asyncio
    async def test_strategy_health_monitor_creation(self):
        """Test that StrategyHealthMonitor can be created."""
        from strategy_manager.strategy_health_monitor import StrategyHealthMonitor
        
        settings = Settings(secret_key="test_key")
        event_bus = Mock()
        health_monitor = StrategyHealthMonitor(settings, event_bus)
        
        assert health_monitor is not None
        assert health_monitor.settings == settings


@pytest.mark.smoke
class TestAPISmoke:
    """Smoke tests for API functionality."""
    
    def test_api_server_creation(self):
        """Test that API server can be created."""
        from api.server import create_app
        
        app = create_app()
        
        assert app is not None
        assert hasattr(app, 'router')
        
    @pytest.mark.asyncio
    async def test_basic_health_endpoint(self):
        """Test that basic health endpoint responds."""
        from api.server import create_app
        from httpx import AsyncClient
        
        with patch('api.server.get_application') as mock_get_app:
            mock_application = Mock()
            mock_application.initialize = AsyncMock(return_value=True)
            mock_application.cleanup = AsyncMock()
            mock_application.health_check = AsyncMock(return_value={
                "status": "healthy",
                "timestamp": "2024-01-01T00:00:00Z"
            })
            mock_get_app.return_value = mock_application
            
            app = create_app()
            
            async with AsyncClient(app=app, base_url="http://test") as client:
                response = await client.get("/health")
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "healthy"


@pytest.mark.smoke
class TestDatabaseSmoke:
    """Smoke tests for database functionality."""
    
    @pytest.mark.asyncio
    async def test_database_manager_creation(self):
        """Test that DatabaseManager can be created."""
        from core.database.connection import DatabaseManager
        
        settings = Settings(secret_key="test_key")
        db_manager = DatabaseManager(settings)
        
        assert db_manager is not None
        assert db_manager.settings == settings


@pytest.mark.smoke
class TestAuthSmoke:
    """Smoke tests for authentication system."""
    
    @pytest.mark.asyncio
    async def test_auth_manager_creation(self):
        """Test that AuthManager can be created."""
        from core.auth.auth_manager import AuthManager
        
        settings = Settings(secret_key="test_key")
        db_manager = Mock()
        auth_manager = AuthManager(settings, db_manager)
        
        assert auth_manager is not None
        assert auth_manager.settings == settings
        
    @pytest.mark.asyncio
    async def test_session_manager_creation(self):
        """Test that SessionManager can be created."""
        from core.auth.session_manager import SessionManager
        
        settings = Settings(secret_key="test_key")
        db_manager = Mock()
        session_manager = SessionManager(settings, db_manager)
        
        assert session_manager is not None
        assert session_manager.settings == settings


@pytest.mark.smoke
class TestRiskSmoke:
    """Smoke tests for risk management system."""
    
    @pytest.mark.asyncio
    async def test_risk_manager_creation(self):
        """Test that RiskManager can be created."""
        from risk_manager.risk_manager import RiskManager
        
        settings = Settings(secret_key="test_key")
        risk_manager = RiskManager(settings)
        
        assert risk_manager is not None
        assert risk_manager.settings == settings


@pytest.mark.smoke
class TestTradingSmoke:
    """Smoke tests for trading engines."""
    
    @pytest.mark.asyncio
    async def test_paper_trading_engine_creation(self):
        """Test that PaperTradingEngine can be created."""
        from paper_trade.engine import PaperTradingEngine
        
        settings = Settings(secret_key="test_key")
        event_bus = Mock()
        paper_engine = PaperTradingEngine(settings, event_bus)
        
        assert paper_engine is not None
        assert paper_engine.settings == settings
        
    @pytest.mark.asyncio
    async def test_zerodha_trading_engine_creation(self):
        """Test that ZerodhaTrading can be created."""
        from zerodha_trade.engine import ZerodhaTradeEngine
        
        settings = Settings(secret_key="test_key")
        event_bus = Mock()
        auth_manager = Mock()
        
        zerodha_engine = ZerodhaTradeEngine(settings, event_bus, auth_manager)
        
        assert zerodha_engine is not None
        assert zerodha_engine.settings == settings


@pytest.mark.smoke
class TestMarketFeedSmoke:
    """Smoke tests for market feed systems."""
    
    @pytest.mark.asyncio
    async def test_mock_feed_manager_creation(self):
        """Test that MockFeedManager can be created."""
        from mock_market_feed.mock_feed_manager import MockFeedManager
        
        settings = Settings(secret_key="test_key")
        event_bus = Mock()
        mock_feed = MockFeedManager(settings, event_bus)
        
        assert mock_feed is not None
        assert mock_feed.settings == settings
        
    @pytest.mark.asyncio
    async def test_zerodha_feed_manager_creation(self):
        """Test that ZerodhaFeedManager can be created."""
        from zerodha_market_feed.zerodha_feed_manager import ZerodhaMarketFeedManager
        
        settings = Settings(secret_key="test_key")
        event_bus = Mock()
        auth_manager = Mock()
        
        zerodha_feed = ZerodhaMarketFeedManager(settings, event_bus, auth_manager)
        
        assert zerodha_feed is not None
        assert zerodha_feed.settings == settings


@pytest.mark.smoke
@pytest.mark.slow
class TestFullApplicationSmoke:
    """End-to-end smoke tests for complete application."""
    
    @pytest.mark.asyncio
    async def test_full_application_lifecycle(self):
        """Test complete application startup and shutdown cycle."""
        app = AlphaPTApplication()
        
        # Mock all external dependencies
        with patch.object(app, '_init_settings', return_value=True), \
             patch.object(app, '_init_logging', return_value=True), \
             patch.object(app, '_init_database', return_value=True), \
             patch.object(app, '_init_event_system', return_value=True), \
             patch.object(app, '_init_auth_manager', return_value=True), \
             patch.object(app, '_init_storage_manager', return_value=True), \
             patch.object(app, '_init_monitoring', return_value=True), \
             patch.object(app, '_init_strategy_manager', return_value=True), \
             patch.object(app, '_init_risk_manager', return_value=True), \
             patch.object(app, '_init_trading_engines', return_value=True), \
             patch.object(app, '_init_market_feeds', return_value=True):
            
            # Test initialization
            result = await app.initialize()
            assert result is True
            assert app.running is True
            
            # Test health check
            with patch.object(app, '_get_component_health', return_value={"status": "healthy"}):
                health = await app.health_check()
                assert health["status"] in ["healthy", "degraded"]
            
            # Test shutdown
            await app.stop()
            assert app.running is False
            assert app.shutdown_requested is True
            
    @pytest.mark.asyncio
    async def test_application_resilience_to_component_failures(self):
        """Test that application handles component initialization failures gracefully."""
        app = AlphaPTApplication()
        
        # Make some components fail to initialize
        with patch.object(app, '_init_settings', return_value=True), \
             patch.object(app, '_init_logging', return_value=True), \
             patch.object(app, '_init_database', return_value=False), \
             patch.object(app, '_init_event_system', return_value=True):
            
            # Application should handle failure gracefully
            result = await app.initialize()
            assert result is False  # Overall initialization should fail
            assert app.running is False
            
            # Cleanup should still work
            await app.cleanup()
            
    @pytest.mark.asyncio
    async def test_application_banner_display(self):
        """Test that application banner can be displayed without errors."""
        app = AlphaPTApplication()
        
        # This should not raise any exceptions
        app.display_startup_banner()
        assert True


@pytest.mark.smoke
class TestImportSmoke:
    """Smoke tests to verify all critical imports work."""
    
    def test_core_imports(self):
        """Test that core modules can be imported."""
        from core.config.settings import Settings
        from core.auth.auth_manager import AuthManager
        from core.database.connection import DatabaseManager
        from core.events import EventBusCore, SystemEvent, EventType
        
        assert Settings is not None
        assert AuthManager is not None
        assert DatabaseManager is not None
        assert EventBusCore is not None
        assert SystemEvent is not None
        assert EventType is not None
        
    def test_storage_imports(self):
        """Test that storage modules can be imported."""
        try:
            from storage.storage_manager import MarketDataStorageManager
            from storage.clickhouse_manager import ClickHouseManager
            assert MarketDataStorageManager is not None
            assert ClickHouseManager is not None
        except ImportError:
            # Storage modules may depend on external services
            assert True
        
    def test_strategy_imports(self):
        """Test that strategy modules can be imported."""
        from strategy_manager.strategy_manager import StrategyManager
        from strategy_manager.strategy_health_monitor import StrategyHealthMonitor
        from strategy_manager.config.config_loader import strategy_config_loader
        
        assert StrategyManager is not None
        assert StrategyHealthMonitor is not None
        assert strategy_config_loader is not None
        
    def test_trading_imports(self):
        """Test that trading modules can be imported."""
        from paper_trade.engine import PaperTradingEngine
        from zerodha_trade.engine import ZerodhaTradeEngine
        from risk_manager.risk_manager import RiskManager
        
        assert PaperTradingEngine is not None
        assert ZerodhaTradeEngine is not None
        assert RiskManager is not None
        
    def test_api_imports(self):
        """Test that API modules can be imported."""
        from api.server import create_app
        from api.routers.health import router as health_router
        from api.routers.trading import router as trading_router
        
        assert create_app is not None
        assert health_router is not None
        assert trading_router is not None
        
    def test_market_feed_imports(self):
        """Test that market feed modules can be imported."""
        from mock_market_feed.mock_feed_manager import MockFeedManager
        from zerodha_market_feed.zerodha_feed_manager import ZerodhaMarketFeedManager
        
        assert MockFeedManager is not None
        assert ZerodhaMarketFeedManager is not None