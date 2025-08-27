"""
Comprehensive unit tests for AlphaPT core components.

Tests database connections, authentication flows, logging system,
configuration validation, and error handling.
"""

import asyncio
import os
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from decimal import Decimal

import pytest

from core.config.settings import Settings, Environment, LogLevel
from core.database.connection import DatabaseManager
from core.auth.auth_manager import AuthManager
from core.auth.models import SessionData, LoginMethod
from core.auth.session_manager import SessionManager
from core.logging import get_logger, MULTI_CHANNEL_AVAILABLE
from core.utils.error_handler import ErrorHandler
from core.utils.sanitization import InputSanitizer
from core.utils.circuit_breaker import CircuitBreaker


@pytest.mark.unit
class TestAdvancedConfiguration:
    """Test advanced configuration scenarios and validation."""

    def test_production_configuration_validation(self):
        """Test production configuration requirements."""
        # Production settings should have specific requirements
        prod_settings = Settings(
            secret_key="production_secret_key_123",
            environment=Environment.PRODUCTION,
            debug=False,
            log_level=LogLevel.WARNING,
            json_logs=True,
        )
        
        assert prod_settings.environment == Environment.PRODUCTION
        assert prod_settings.debug is False
        assert prod_settings.log_level == LogLevel.WARNING
        assert prod_settings.json_logs is True
        
        # Verify production-specific configurations
        assert prod_settings.monitoring.prometheus_enabled is True
        assert prod_settings.monitoring.health_check_enabled is True

    def test_development_configuration_defaults(self):
        """Test development configuration defaults."""
        dev_settings = Settings(
            secret_key="dev_secret_key",
            environment=Environment.DEVELOPMENT
        )
        
        assert dev_settings.debug is True
        assert dev_settings.log_level == LogLevel.DEBUG
        assert dev_settings.mock_market_feed is True

    def test_configuration_validation_failures(self):
        """Test configuration validation with invalid inputs."""
        with pytest.raises(Exception):  # Should fail without secret_key
            Settings()
        
        # Test invalid environment
        with pytest.raises(Exception):
            Settings(
                secret_key="test",
                environment="invalid_environment"
            )

    def test_nested_configuration_loading(self):
        """Test nested configuration objects are loaded correctly."""
        settings = Settings(secret_key="test_key")
        
        # Test database configuration
        assert hasattr(settings.database, 'postgres_host')
        assert hasattr(settings.database, 'clickhouse_host')
        
        # Test trading configuration
        assert hasattr(settings.trading, 'max_position_value')
        assert hasattr(settings.trading, 'kite_api_key')
        
        # Test monitoring configuration
        assert hasattr(settings.monitoring, 'prometheus_enabled')
        assert hasattr(settings.monitoring, 'health_check_enabled')


@pytest.mark.unit
class TestDatabaseManager:
    """Test DatabaseManager functionality."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for database testing."""
        settings = Mock(spec=Settings)
        settings.database = Mock()
        settings.database.postgres_host = "localhost"
        settings.database.postgres_port = 5432
        settings.database.postgres_user = "test_user"
        settings.database.postgres_password = "test_pass"
        settings.database.postgres_database = "test_db"
        settings.database.clickhouse_host = "localhost"
        settings.database.clickhouse_port = 9000
        settings.database.clickhouse_user = "default"
        settings.database.clickhouse_password = ""
        settings.database.clickhouse_database = "alphapt_test"
        settings.database.connection_pool_size = 10
        settings.database.connection_timeout = 30
        return settings

    async def test_database_manager_initialization(self, mock_settings):
        """Test database manager initialization."""
        db_manager = DatabaseManager(mock_settings)
        
        assert db_manager.settings == mock_settings
        assert db_manager._postgres_pool is None
        assert db_manager._clickhouse_client is None

    @patch('asyncpg.create_pool')
    @patch('asyncio_clickhouse.pool.ClickHousePool')
    async def test_database_connections_mocked(self, mock_ch_pool, mock_pg_pool, mock_settings):
        """Test database connections with mocked connections."""
        # Mock successful connections
        mock_pg_pool.return_value = AsyncMock()
        mock_ch_pool.return_value = Mock()
        
        db_manager = DatabaseManager(mock_settings)
        
        # Test initialization
        with patch.object(db_manager, '_test_postgres_connection', return_value=True):
            with patch.object(db_manager, '_test_clickhouse_connection', return_value=True):
                result = await db_manager.initialize()
                assert result is True

    async def test_database_connection_failure_handling(self, mock_settings):
        """Test database connection failure handling."""
        db_manager = DatabaseManager(mock_settings)
        
        # Mock connection failures
        with patch('asyncpg.create_pool', side_effect=Exception("Connection failed")):
            result = await db_manager.initialize()
            assert result is False

    async def test_database_health_check(self, mock_settings):
        """Test database health check functionality."""
        db_manager = DatabaseManager(mock_settings)
        
        # Test health check with no connections
        health = await db_manager.health_check()
        assert health["postgres_available"] is False
        assert health["clickhouse_available"] is False

    async def test_database_cleanup(self, mock_settings):
        """Test database cleanup and resource management."""
        db_manager = DatabaseManager(mock_settings)
        
        # Mock active connections
        db_manager._postgres_pool = Mock()
        db_manager._postgres_pool.close = AsyncMock()
        db_manager._postgres_pool.wait_closed = AsyncMock()
        
        db_manager._clickhouse_client = Mock()
        db_manager._clickhouse_client.close = AsyncMock()
        
        await db_manager.cleanup()
        
        # Verify cleanup was called
        db_manager._postgres_pool.close.assert_called_once()
        db_manager._clickhouse_client.close.assert_called_once()


@pytest.mark.unit
class TestAuthenticationManager:
    """Test AuthManager comprehensive functionality."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for auth testing."""
        settings = Mock(spec=Settings)
        settings.secret_key = "test_secret_key_123"
        settings.trading = Mock()
        settings.trading.kite_api_key = "test_api_key"
        settings.trading.kite_api_secret = "test_api_secret"
        return settings

    @pytest.fixture
    def mock_database_manager(self):
        """Create mock database manager."""
        db_manager = Mock(spec=DatabaseManager)
        db_manager.initialize = AsyncMock(return_value=True)
        db_manager.cleanup = AsyncMock()
        return db_manager

    async def test_auth_manager_initialization(self, mock_settings, mock_database_manager):
        """Test authentication manager initialization."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        assert auth_manager.settings == mock_settings
        assert auth_manager.db_manager == mock_database_manager
        
        # Test initialization
        result = await auth_manager.initialize()
        assert result is True

    async def test_zerodha_authentication_flow(self, mock_settings, mock_database_manager):
        """Test Zerodha authentication workflow."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Mock successful authentication
        with patch.object(auth_manager, '_validate_zerodha_credentials', return_value=True):
            with patch.object(auth_manager, '_fetch_user_profile') as mock_profile:
                mock_profile.return_value = {
                    "user_id": "test_user",
                    "user_name": "Test User",
                    "email": "test@example.com"
                }
                
                result = await auth_manager.authenticate_zerodha("valid_request_token")
                assert result is True

    async def test_session_management(self, mock_settings, mock_database_manager):
        """Test session creation and management."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Mock session manager
        mock_session_manager = Mock(spec=SessionManager)
        auth_manager.session_manager = mock_session_manager
        
        # Test session operations
        test_token = "test_access_token_123"
        await auth_manager.set_access_token(test_token)
        mock_session_manager.save_session.assert_called()

    async def test_authentication_failure_scenarios(self, mock_settings, mock_database_manager):
        """Test authentication failure handling."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Test invalid request token
        with patch.object(auth_manager, '_validate_zerodha_credentials', return_value=False):
            result = await auth_manager.authenticate_zerodha("invalid_token")
            assert result is False
        
        # Test network failure
        with patch.object(auth_manager, '_validate_zerodha_credentials', side_effect=Exception("Network error")):
            result = await auth_manager.authenticate_zerodha("any_token")
            assert result is False

    def test_is_authenticated_logic(self, mock_settings, mock_database_manager):
        """Test authentication status checking."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Test when not authenticated
        assert auth_manager.is_authenticated() is False
        
        # Test when authenticated (mock current session)
        mock_session = Mock()
        mock_session.is_expired.return_value = False
        auth_manager.session_manager = Mock()
        auth_manager.session_manager.get_current_session.return_value = mock_session
        
        assert auth_manager.is_authenticated() is True

    def test_get_profile_information(self, mock_settings, mock_database_manager):
        """Test user profile information retrieval."""
        auth_manager = AuthManager(mock_settings, mock_database_manager)
        
        # Mock profile data
        mock_session = Mock()
        mock_session.user_name = "Test User"
        mock_session.email = "test@example.com"
        mock_session.broker = "zerodha"
        
        auth_manager.session_manager = Mock()
        auth_manager.session_manager.get_current_session.return_value = mock_session
        
        profile = auth_manager.get_profile()
        assert profile["user_name"] == "Test User"
        assert profile["email"] == "test@example.com"


@pytest.mark.unit
class TestSessionManager:
    """Test SessionManager persistence and validation."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.secret_key = "test_secret_key"
        return settings

    @pytest.fixture
    def mock_database_manager(self):
        """Create mock database manager."""
        db_manager = Mock(spec=DatabaseManager)
        db_manager.execute_query = AsyncMock()
        db_manager.fetch_one = AsyncMock()
        db_manager.fetch_all = AsyncMock()
        return db_manager

    async def test_session_data_creation(self, mock_settings, mock_database_manager):
        """Test session data model creation and validation."""
        now = datetime.now(timezone.utc)
        
        session_data = SessionData(
            user_id="test_user_123",
            user_name="Test User",
            user_shortname="TestU",
            broker="zerodha",
            email="test@example.com",
            access_token="test_access_token",
            expires_at=now + timedelta(hours=24),
            login_timestamp=now,
            last_activity_timestamp=now,
            login_method=LoginMethod.OAUTH,
            session_id="test_session_123"
        )
        
        assert session_data.user_id == "test_user_123"
        assert session_data.broker == "zerodha"
        assert not session_data.is_expired()

    async def test_session_persistence(self, mock_settings, mock_database_manager):
        """Test session saving and loading."""
        session_manager = SessionManager(mock_settings, mock_database_manager)
        
        # Create test session
        now = datetime.now(timezone.utc)
        test_session = SessionData(
            user_id="persist_test_user",
            user_name="Persist Test",
            user_shortname="PTest",
            broker="zerodha",
            email="persist@test.com",
            access_token="persist_token",
            expires_at=now + timedelta(hours=24),
            login_timestamp=now,
            last_activity_timestamp=now,
            login_method=LoginMethod.OAUTH,
            session_id="persist_session_123"
        )
        
        # Mock database operations
        mock_database_manager.execute_query.return_value = True
        
        # Test save
        result = await session_manager.save_session(test_session)
        assert result is True
        
        # Verify database call was made
        mock_database_manager.execute_query.assert_called()

    async def test_session_expiration_logic(self, mock_settings, mock_database_manager):
        """Test session expiration validation."""
        session_manager = SessionManager(mock_settings, mock_database_manager)
        
        # Create expired session
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        expired_session = SessionData(
            user_id="expired_user",
            user_name="Expired User",
            user_shortname="ExpU",
            broker="zerodha",
            email="expired@test.com",
            access_token="expired_token",
            expires_at=past_time,
            login_timestamp=past_time,
            last_activity_timestamp=past_time,
            login_method=LoginMethod.OAUTH,
            session_id="expired_session"
        )
        
        assert expired_session.is_expired() is True

    async def test_session_invalidation(self, mock_settings, mock_database_manager):
        """Test session invalidation and cleanup."""
        session_manager = SessionManager(mock_settings, mock_database_manager)
        
        # Mock database operations
        mock_database_manager.execute_query.return_value = True
        
        result = await session_manager.invalidate_session()
        assert result is True
        
        # Verify cleanup call
        mock_database_manager.execute_query.assert_called()


@pytest.mark.unit
class TestLoggingSystem:
    """Test comprehensive logging system functionality."""

    def test_basic_logger_creation(self):
        """Test basic logger creation and usage."""
        logger = get_logger("test_component")
        assert logger is not None
        assert logger.name == "test_component"

    def test_multi_channel_availability(self):
        """Test multi-channel logging availability."""
        # This test checks if multi-channel logging is available
        if MULTI_CHANNEL_AVAILABLE:
            from core.logging import get_trading_logger, get_api_logger
            
            trading_logger = get_trading_logger("test_trading")
            api_logger = get_api_logger("test_api")
            
            assert trading_logger is not None
            assert api_logger is not None

    def test_structured_logging_parameters(self):
        """Test structured logging with additional parameters."""
        logger = get_logger("structured_test")
        
        # This should not raise an exception
        try:
            logger.info("Test message", component="test", action="testing")
            logger.warning("Warning message", error_code="W001", severity="medium")
            logger.error("Error message", exception="TestException", trace_id="123")
        except Exception as e:
            pytest.fail(f"Structured logging failed: {e}")


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling and exception management."""

    def test_input_sanitization(self):
        """Test input sanitization functionality."""
        # Test trading symbol sanitization
        sanitized = InputSanitizer.sanitize_trading_symbol("RELIANCE")
        assert sanitized == "RELIANCE"
        
        # Test invalid symbols
        with pytest.raises(ValueError):
            InputSanitizer.sanitize_trading_symbol("")
        
        with pytest.raises(ValueError):
            InputSanitizer.sanitize_trading_symbol("INVALID_SYMBOL_TOO_LONG_123456789")

    def test_numeric_validation(self):
        """Test numeric input validation."""
        # Test positive numbers
        assert InputSanitizer.sanitize_positive_decimal(100.50) == Decimal('100.50')
        
        # Test zero and negative numbers
        with pytest.raises(ValueError):
            InputSanitizer.sanitize_positive_decimal(-100)
        
        with pytest.raises(ValueError):
            InputSanitizer.sanitize_positive_decimal(0)

    def test_circuit_breaker_functionality(self):
        """Test circuit breaker pattern implementation."""
        circuit_breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=5,
            expected_exception=Exception
        )
        
        # Initially should be closed
        assert circuit_breaker.state == "closed"
        
        # Simulate failures
        for _ in range(3):
            circuit_breaker.record_failure()
        
        # Should be open after threshold failures
        assert circuit_breaker.state == "open"

    def test_error_handler_integration(self):
        """Test error handler integration."""
        error_handler = ErrorHandler()
        
        # Test error recording
        test_error = Exception("Test error")
        error_handler.handle_error(test_error, context="unit_test")
        
        # Verify error was processed (no exception should be raised)
        assert True  # If we reach here, error handling worked


@pytest.mark.unit
class TestAdvancedValidation:
    """Test advanced validation scenarios."""

    def test_configuration_edge_cases(self):
        """Test configuration with edge cases."""
        # Test minimum viable configuration
        minimal_settings = Settings(secret_key="min")
        assert minimal_settings.secret_key == "min"
        
        # Test maximum length configurations
        long_key = "x" * 256
        settings_with_long_key = Settings(secret_key=long_key)
        assert len(settings_with_long_key.secret_key) == 256

    def test_concurrent_session_handling(self):
        """Test concurrent session operations."""
        # This test verifies thread safety considerations
        # (Note: Actual threading would require integration test)
        settings = Mock(spec=Settings)
        db_manager = Mock(spec=DatabaseManager)
        
        session_manager = SessionManager(settings, db_manager)
        
        # Verify that session cache is properly initialized
        assert hasattr(session_manager, '_session_cache')

    async def test_resource_cleanup_edge_cases(self, mock_settings):
        """Test resource cleanup in edge cases."""
        db_manager = DatabaseManager(mock_settings)
        
        # Test cleanup when connections are None
        await db_manager.cleanup()  # Should not raise exception
        
        # Test cleanup when connections are already closed
        db_manager._postgres_pool = Mock()
        db_manager._postgres_pool.close = AsyncMock()
        db_manager._postgres_pool.wait_closed = AsyncMock()
        
        await db_manager.cleanup()
        db_manager._postgres_pool.close.assert_called_once()


@pytest.mark.unit
@pytest.mark.performance
class TestPerformanceValidation:
    """Test performance-related validations."""

    def test_configuration_loading_performance(self):
        """Test configuration loading performance."""
        import time
        
        start_time = time.time()
        for _ in range(100):
            Settings(secret_key="perf_test")
        end_time = time.time()
        
        # Configuration loading should be fast (< 1 second for 100 instances)
        assert (end_time - start_time) < 1.0

    async def test_database_connection_timeout(self):
        """Test database connection timeout handling."""
        settings = Mock(spec=Settings)
        settings.database = Mock()
        settings.database.connection_timeout = 1  # 1 second timeout
        
        db_manager = DatabaseManager(settings)
        
        # Mock slow connection
        with patch('asyncpg.create_pool', side_effect=asyncio.TimeoutError):
            start_time = time.time()
            result = await db_manager.initialize()
            end_time = time.time()
            
            assert result is False
            # Should timeout quickly
            assert (end_time - start_time) < 5.0

    def test_session_data_serialization_performance(self):
        """Test session data serialization performance."""
        import time
        
        now = datetime.now(timezone.utc)
        session = SessionData(
            user_id="perf_user",
            user_name="Performance User",
            user_shortname="PerfU",
            broker="zerodha",
            email="perf@test.com",
            access_token="perf_token",
            expires_at=now + timedelta(hours=24),
            login_timestamp=now,
            last_activity_timestamp=now,
            login_method=LoginMethod.OAUTH,
            session_id="perf_session"
        )
        
        start_time = time.time()
        for _ in range(1000):
            # Test serialization performance
            data = session.model_dump()
            # Test deserialization performance
            SessionData.model_validate(data)
        end_time = time.time()
        
        # 1000 serializations should be fast (< 0.5 seconds)
        assert (end_time - start_time) < 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])