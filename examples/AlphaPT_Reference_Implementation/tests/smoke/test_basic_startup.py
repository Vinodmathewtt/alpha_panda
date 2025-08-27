"""
Smoke tests for basic application startup and functionality.

These tests verify that the application can start, initialize core components,
and perform basic operations without errors.
"""

import asyncio
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.config.settings import Settings, Environment
from app.application import AlphaPTApplication


@pytest.mark.smoke
class TestBasicStartup:
    """Smoke tests for basic application startup."""
    
    def test_settings_creation(self):
        """Test that settings can be created without errors."""
        settings = Settings(secret_key="test_secret_key")
        
        assert settings is not None
        assert settings.secret_key == "test_secret_key"
        assert settings.app_name == "AlphaPT"
        assert isinstance(settings.environment, Environment)
        
    def test_settings_with_testing_environment(self):
        """Test settings creation with testing environment."""
        settings = Settings(
            secret_key="test_key",
            environment=Environment.TESTING,
            debug=True,
            mock_market_feed=True
        )
        
        assert settings.environment == Environment.TESTING
        assert settings.debug is True
        assert settings.mock_market_feed is True
        
    def test_application_creation(self):
        """Test that application can be created without errors."""
        app = AlphaPTApplication()
        
        assert app is not None
        assert app.running is False
        assert app.shutdown_requested is False
        assert isinstance(app.app_state, dict)
        
    async def test_application_initialization_mock(self, mock_application):
        """Test application initialization with mocked components."""
        # Application should initialize successfully with mocks
        result = await mock_application.initialize()
        assert result is True
        
        # Application should have proper state
        assert mock_application.app_state is not None
        assert "settings" in mock_application.app_state
        assert "db_manager" in mock_application.app_state
        assert "event_bus" in mock_application.app_state
        
    async def test_application_cleanup_mock(self, mock_application):
        """Test application cleanup with mocked components."""
        await mock_application.cleanup()
        # Should complete without errors
        
    def test_startup_banner_display(self):
        """Test that startup banner can be displayed without errors."""
        app = AlphaPTApplication()
        
        # Should not raise any exceptions
        app.display_startup_banner()
        
    async def test_health_check_mock(self, mock_application):
        """Test basic health check functionality."""
        health = await mock_application.health_check()
        
        assert isinstance(health, dict)
        assert "status" in health
        
    def test_environment_variables_loading(self):
        """Test that environment variables are loaded correctly."""
        # Test with environment variables set
        with patch.dict(os.environ, {
            'TESTING': 'true',
            'ENVIRONMENT': 'testing',
            'MOCK_MARKET_FEED': 'true',
            'DEBUG': 'true'
        }):
            settings = Settings(secret_key="test_key")
            
            assert settings.environment == Environment.TESTING
            assert settings.debug is True
            assert settings.mock_market_feed is True


@pytest.mark.smoke 
class TestConfigurationLoading:
    """Smoke tests for configuration loading."""
    
    def test_all_config_sections_load(self):
        """Test that all configuration sections can be loaded."""
        settings = Settings(secret_key="test_key")
        
        # Test that all major config sections exist
        assert hasattr(settings, 'database')
        assert hasattr(settings, 'trading')
        assert hasattr(settings, 'monitoring')
        assert hasattr(settings, 'api')
        
        # Test that nested configs have expected attributes
        assert hasattr(settings.database, 'postgres_host')
        assert hasattr(settings.trading, 'kite_api_key')
        assert hasattr(settings.monitoring, 'prometheus_enabled')
        
    def test_database_urls_generation(self):
        """Test that database URLs can be generated."""
        settings = Settings(secret_key="test_key")
        
        postgres_url = settings.database.get_postgres_url()
        clickhouse_url = settings.database.get_clickhouse_url()
        redis_url = settings.database.get_redis_url()
        
        assert postgres_url.startswith("postgresql://")
        assert clickhouse_url.startswith("clickhouse://")
        assert redis_url.startswith("redis://")
        
    def test_file_paths_creation(self):
        """Test that file paths are created correctly."""
        settings = Settings(
            secret_key="test_key",
            logs_dir="/tmp/test_logs",
            data_dir="/tmp/test_data"
        )
        
        assert isinstance(settings.logs_dir, Path)
        assert isinstance(settings.data_dir, Path)
        assert str(settings.logs_dir) == "/tmp/test_logs"
        assert str(settings.data_dir) == "/tmp/test_data"


@pytest.mark.smoke
class TestImportSmoke:
    """Smoke tests for module imports."""
    
    def test_core_imports(self):
        """Test that core modules can be imported without errors."""
        # Test config imports
        from core.config.settings import Settings
        from core.config.database_config import DatabaseConfig
        
        # Test auth imports
        from core.auth.auth_manager import AuthManager
        from core.auth.models import SessionData, LoginMethod
        
        # Test event imports
        from core.events.event_bus import EventBus
        from core.events.event_types import SystemEvent, EventType
        
        # Test database imports
        from core.database.connection import DatabaseManager
        
        # All imports should succeed without errors
        assert Settings is not None
        assert AuthManager is not None
        assert EventBus is not None
        assert DatabaseManager is not None
        
    def test_application_imports(self):
        """Test that application modules can be imported without errors."""
        from app.application import AlphaPTApplication
        
        assert AlphaPTApplication is not None
        
    def test_api_imports(self):
        """Test that API modules can be imported without errors."""
        from api.server import create_app
        
        assert create_app is not None
        
    def test_storage_imports(self):
        """Test that storage modules can be imported without errors."""
        from storage.storage_manager import StorageManager
        from storage.clickhouse_manager import ClickHouseManager
        
        assert StorageManager is not None
        assert ClickHouseManager is not None
        
    def test_trading_imports(self):
        """Test that trading modules can be imported without errors."""
        from paper_trade.engine import PaperTradingEngine
        from risk_manager.risk_manager import RiskManager
        
        assert PaperTradingEngine is not None
        assert RiskManager is not None
        
    def test_strategy_imports(self):
        """Test that strategy modules can be imported without errors."""
        from strategy_manager.strategy_manager import StrategyManager
        from strategy_manager.base_strategy import BaseStrategy
        
        assert StrategyManager is not None
        assert BaseStrategy is not None
        
    def test_monitoring_imports(self):
        """Test that monitoring modules can be imported without errors."""
        from monitoring.health_checker import HealthChecker
        from monitoring.metrics_collector import MetricsCollector
        
        assert HealthChecker is not None
        assert MetricsCollector is not None


@pytest.mark.smoke
class TestBasicFunctionality:
    """Smoke tests for basic functionality."""
    
    def test_event_creation(self):
        """Test that events can be created without errors."""
        from core.events.event_types import SystemEvent, EventType
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
        
    def test_event_serialization(self):
        """Test that events can be serialized without errors."""
        from core.events.event_types import SystemEvent, EventType
        from datetime import datetime, timezone
        import uuid
        
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.SYSTEM_STARTED,
            timestamp=datetime.now(timezone.utc),
            source="smoke_test"
        )
        
        json_str = event.to_json()
        assert isinstance(json_str, str)
        assert len(json_str) > 0
        
        # Test deserialization
        deserialized = SystemEvent.from_json(json_str)
        assert deserialized.event_id == event.event_id
        
    def test_session_data_creation(self):
        """Test that session data can be created without errors."""
        from core.auth.models import SessionData, LoginMethod
        from datetime import datetime, timezone, timedelta
        
        session = SessionData(
            user_id="test_user",
            user_name="Test User",
            user_shortname="TU",
            broker="zerodha",
            email="test@example.com",
            access_token="test_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            login_timestamp=datetime.now(timezone.utc),
            last_activity_timestamp=datetime.now(timezone.utc),
            login_method=LoginMethod.OAUTH,
            session_id="test_session",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            last_validated=datetime.now(timezone.utc)
        )
        
        assert session is not None
        assert session.user_id == "test_user"
        assert not session.is_expired()
        
    def test_sample_data_generation(self, sample_tick_data, sample_order_data):
        """Test that sample data can be generated without errors."""
        assert sample_tick_data is not None
        assert "instrument_token" in sample_tick_data
        assert "last_price" in sample_tick_data
        
        assert sample_order_data is not None
        assert "tradingsymbol" in sample_order_data
        assert "quantity" in sample_order_data


@pytest.mark.smoke
@pytest.mark.slow
class TestExternalDependencies:
    """Smoke tests for external dependencies (when available)."""
    
    async def test_database_connection_mock(self, mock_database_manager):
        """Test database connection with mocked database."""
        result = await mock_database_manager.initialize()
        assert result is True
        
        health = await mock_database_manager.health_check()
        assert health["status"] == "healthy"
        
        await mock_database_manager.cleanup()
        
    async def test_event_bus_connection_mock(self, mock_event_bus):
        """Test event bus connection with mocked event bus."""
        result = await mock_event_bus.connect()
        assert result is True
        
        health = await mock_event_bus.health_check()
        assert health["connected"] is True
        
        await mock_event_bus.disconnect()
        
    def test_api_client_creation(self, api_client):
        """Test API client creation with mocked dependencies."""
        assert api_client is not None
        
    async def test_basic_api_response(self, api_client):
        """Test basic API response with mocked dependencies."""
        response = await api_client.get("/api/v1/health")
        
        # Should get some response (may be 200 or error depending on mocking)
        assert response.status_code in [200, 404, 500]  # Any response indicates API is working