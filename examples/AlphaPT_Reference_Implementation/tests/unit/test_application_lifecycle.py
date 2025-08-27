"""
Unit tests for AlphaPT application lifecycle management.

Tests the core application initialization, component management,
shutdown handling, and health checks.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

from app.application import AlphaPTApplication
from core.config.settings import Settings


@pytest.mark.unit
class TestApplicationLifecycle:
    """Test application lifecycle management."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for testing."""
        settings = Mock(spec=Settings)
        settings.app_name = "AlphaPT-Test"
        settings.environment = "testing"
        settings.debug = True
        settings.mock_market_feed = True
        settings.paper_trading_enabled = True
        settings.zerodha_trading_enabled = False
        settings.api_host = "127.0.0.1"
        settings.api_port = 8000
        settings.enable_api_server = False
        return settings
    
    def test_application_initialization(self):
        """Test application object initialization."""
        app = AlphaPTApplication()
        
        assert app.app_state is not None
        assert isinstance(app.app_state, dict)
        assert app.running is False
        assert app.shutdown_requested is False
        assert "shutdown_event" in app.app_state
        
    @pytest.mark.asyncio
    async def test_application_banner_display(self):
        """Test startup banner display."""
        app = AlphaPTApplication()
        
        # Should not raise any exceptions
        app.display_startup_banner()
        
        # Banner display is a void method, we just verify it doesn't crash
        assert True
        
    @pytest.mark.asyncio 
    async def test_application_initialize_with_mocked_components(self):
        """Test application initialization with mocked dependencies."""
        app = AlphaPTApplication()
        
        # Mock all the initialization methods
        with patch.object(app, '_init_settings', return_value=True) as mock_init_settings, \
             patch.object(app, '_init_logging', return_value=True) as mock_init_logging, \
             patch.object(app, '_init_database', return_value=True) as mock_init_database, \
             patch.object(app, '_init_event_system', return_value=True) as mock_init_event_system, \
             patch.object(app, '_init_auth_manager', return_value=True) as mock_init_auth, \
             patch.object(app, '_init_storage_manager', return_value=True) as mock_init_storage, \
             patch.object(app, '_init_monitoring', return_value=True) as mock_init_monitoring, \
             patch.object(app, '_init_strategy_manager', return_value=True) as mock_init_strategy, \
             patch.object(app, '_init_risk_manager', return_value=True) as mock_init_risk, \
             patch.object(app, '_init_trading_engines', return_value=True) as mock_init_trading, \
             patch.object(app, '_init_market_feeds', return_value=True) as mock_init_feeds:
            
            result = await app.initialize()
            
            assert result is True
            assert app.running is True
            
            # Verify all initialization methods were called
            mock_init_settings.assert_called_once()
            mock_init_logging.assert_called_once()
            mock_init_database.assert_called_once()
            mock_init_event_system.assert_called_once()
            mock_init_auth.assert_called_once()
            mock_init_storage.assert_called_once()
            mock_init_monitoring.assert_called_once()
            mock_init_strategy.assert_called_once()
            mock_init_risk.assert_called_once()
            mock_init_trading.assert_called_once()
            mock_init_feeds.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_application_initialize_failure_handling(self):
        """Test that initialization failures are handled properly."""
        app = AlphaPTApplication()
        
        # Mock settings initialization to fail
        with patch.object(app, '_init_settings', return_value=False):
            result = await app.initialize()
            
            assert result is False
            assert app.running is False
            
    @pytest.mark.asyncio
    async def test_application_cleanup(self):
        """Test application cleanup process."""
        app = AlphaPTApplication()
        
        # Set up some mock components
        mock_component1 = AsyncMock()
        mock_component2 = AsyncMock()
        mock_component3 = Mock()  # Non-async cleanup
        mock_component3.cleanup = Mock()
        
        app.app_state = {
            "component1": mock_component1,
            "component2": mock_component2, 
            "component3": mock_component3,
            "none_component": None,
            "shutdown_event": asyncio.Event()
        }
        
        await app.cleanup()
        
        # Verify cleanup was called on components that have it
        mock_component1.cleanup.assert_called_once()
        mock_component2.cleanup.assert_called_once()
        mock_component3.cleanup.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_application_stop(self):
        """Test application stop process."""
        app = AlphaPTApplication()
        app.running = True
        app.app_state["shutdown_event"] = asyncio.Event()
        
        with patch.object(app, 'cleanup', new_callable=AsyncMock) as mock_cleanup:
            await app.stop()
            
            assert app.running is False
            assert app.shutdown_requested is True
            assert app.app_state["shutdown_event"].is_set()
            mock_cleanup.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test application health check."""
        app = AlphaPTApplication()
        
        # Mock health check methods for each component
        mock_db_health = {"status": "healthy", "connected": True}
        mock_event_health = {"status": "healthy", "connected": True}
        mock_auth_health = {"status": "healthy", "authenticated": False}
        
        app.app_state = {
            "db_manager": Mock(health_check=AsyncMock(return_value=mock_db_health)),
            "event_bus": Mock(health_check=AsyncMock(return_value=mock_event_health)),
            "auth_manager": Mock(health_check=AsyncMock(return_value=mock_auth_health)),
            "settings": Mock(app_name="AlphaPT-Test", environment="testing"),
            "other_component": None  # Component without health check
        }
        
        health_status = await app.health_check()
        
        assert health_status["status"] in ["healthy", "degraded", "unhealthy"]
        assert "timestamp" in health_status
        assert "components" in health_status
        assert "db_manager" in health_status["components"]
        assert "event_bus" in health_status["components"]
        assert "auth_manager" in health_status["components"]
        
    @pytest.mark.asyncio
    async def test_health_check_with_unhealthy_components(self):
        """Test health check when components are unhealthy."""
        app = AlphaPTApplication()
        
        # Mock unhealthy components
        app.app_state = {
            "db_manager": Mock(health_check=AsyncMock(side_effect=Exception("DB Error"))),
            "event_bus": Mock(health_check=AsyncMock(return_value={"status": "unhealthy"})),
            "settings": Mock(app_name="AlphaPT-Test", environment="testing")
        }
        
        health_status = await app.health_check()
        
        assert health_status["status"] in ["degraded", "unhealthy"]
        assert "components" in health_status
        
    def test_signal_handlers_registration(self):
        """Test that signal handlers are properly registered."""
        app = AlphaPTApplication()
        
        with patch('signal.signal') as mock_signal:
            app._setup_signal_handlers()
            
            # Verify signal handlers were registered
            assert mock_signal.call_count >= 2  # At least SIGINT and SIGTERM
            
    @pytest.mark.asyncio
    async def test_graceful_shutdown_on_signal(self):
        """Test graceful shutdown when receiving signals."""
        app = AlphaPTApplication()
        app.running = True
        app.app_state["shutdown_event"] = asyncio.Event()
        
        with patch.object(app, 'stop', new_callable=AsyncMock) as mock_stop:
            # Simulate signal handler call
            await app._handle_shutdown_signal("SIGINT")
            
            mock_stop.assert_called_once()
            
    def test_component_state_management(self):
        """Test component state management."""
        app = AlphaPTApplication()
        
        # Test setting components
        test_component = Mock()
        app.app_state["test_component"] = test_component
        
        assert app.app_state["test_component"] == test_component
        
        # Test getting non-existent component returns None
        assert app.app_state.get("non_existent") is None


@pytest.mark.unit 
class TestApplicationComponentInitialization:
    """Test individual component initialization methods."""
    
    @pytest.mark.asyncio
    async def test_settings_initialization(self):
        """Test settings initialization."""
        app = AlphaPTApplication()
        
        result = await app._init_settings()
        
        # Settings should be initialized
        assert result is True
        assert app.app_state.get("settings") is not None
        
    @pytest.mark.asyncio
    async def test_logging_initialization_success(self):
        """Test logging initialization success."""
        app = AlphaPTApplication()
        app.app_state["settings"] = Mock()
        
        with patch('core.logging.logger.configure_logging') as mock_configure:
            result = await app._init_logging()
            
            assert result is True
            mock_configure.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_logging_initialization_failure(self):
        """Test logging initialization failure handling."""
        app = AlphaPTApplication()
        app.app_state["settings"] = None
        
        result = await app._init_logging()
        assert result is False
        
    @pytest.mark.asyncio
    async def test_database_initialization_success(self):
        """Test database initialization success."""
        app = AlphaPTApplication()
        
        mock_settings = Mock()
        app.app_state["settings"] = mock_settings
        
        mock_db_manager = AsyncMock()
        mock_db_manager.initialize.return_value = True
        
        with patch('core.database.connection.DatabaseManager', return_value=mock_db_manager):
            result = await app._init_database()
            
            assert result is True
            assert app.app_state["db_manager"] == mock_db_manager
            mock_db_manager.initialize.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_database_initialization_failure(self):
        """Test database initialization failure handling."""
        app = AlphaPTApplication()
        app.app_state["settings"] = None
        
        result = await app._init_database()
        assert result is False
        
    @pytest.mark.asyncio 
    async def test_event_system_initialization_success(self):
        """Test event system initialization success."""
        app = AlphaPTApplication()
        
        mock_settings = Mock()
        app.app_state["settings"] = mock_settings
        
        mock_event_bus = AsyncMock()
        mock_event_bus.connect.return_value = None
        
        with patch('core.events.get_event_bus_core', return_value=mock_event_bus), \
             patch('core.events.create_stream_manager') as mock_create_stream, \
             patch('core.events.create_subscriber_manager') as mock_create_subscriber:
            
            mock_stream_manager = Mock()
            mock_stream_manager.ensure_streams = AsyncMock(return_value=True)
            mock_create_stream.return_value = mock_stream_manager
            
            mock_subscriber_manager = Mock()
            mock_create_subscriber.return_value = mock_subscriber_manager
            
            result = await app._init_event_system()
            
            assert result is True
            assert app.app_state["event_bus"] == mock_event_bus
            assert app.app_state["stream_manager"] == mock_stream_manager
            assert app.app_state["subscriber_manager"] == mock_subscriber_manager
            
    @pytest.mark.asyncio
    async def test_event_system_initialization_failure(self):
        """Test event system initialization failure handling."""
        app = AlphaPTApplication()
        app.app_state["settings"] = None
        
        result = await app._init_event_system()
        assert result is False


@pytest.mark.unit
class TestApplicationIntegration:
    """Test application integration scenarios."""
    
    @pytest.mark.asyncio
    async def test_startup_and_shutdown_cycle(self):
        """Test complete startup and shutdown cycle."""
        app = AlphaPTApplication()
        
        # Mock all component initializations to succeed
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
            
            # Test startup
            result = await app.initialize()
            assert result is True
            assert app.running is True
            
            # Test shutdown
            await app.stop()
            assert app.running is False
            assert app.shutdown_requested is True
            
    @pytest.mark.asyncio
    async def test_partial_initialization_failure(self):
        """Test behavior when some components fail to initialize."""
        app = AlphaPTApplication()
        
        # Mock some components to succeed and others to fail
        with patch.object(app, '_init_settings', return_value=True), \
             patch.object(app, '_init_logging', return_value=True), \
             patch.object(app, '_init_database', return_value=False):  # Database fails
            
            result = await app.initialize()
            assert result is False
            assert app.running is False
            
    @pytest.mark.asyncio
    async def test_application_resilience(self):
        """Test application resilience to component failures."""
        app = AlphaPTApplication()
        
        # Set up components that might fail during operation
        failing_component = Mock()
        failing_component.health_check = AsyncMock(side_effect=Exception("Component failed"))
        
        working_component = Mock()
        working_component.health_check = AsyncMock(return_value={"status": "healthy"})
        
        app.app_state = {
            "failing_component": failing_component,
            "working_component": working_component,
            "settings": Mock(app_name="AlphaPT-Test", environment="testing")
        }
        
        # Health check should still work even if some components fail
        health_status = await app.health_check()
        
        assert "status" in health_status
        assert "components" in health_status
        assert "working_component" in health_status["components"]
        # Failing component should be noted but not crash the health check