"""
Unit tests for core configuration components.

Tests the settings, configuration loading, validation, and environment handling.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from pydantic import ValidationError

from core.config.settings import Settings, Environment, LogLevel
from core.config.database_config import DatabaseConfig
from core.config.trading_config import TradingConfig
from core.config.monitoring_config import MonitoringConfig


@pytest.mark.unit
class TestSettings:
    """Test the main Settings configuration class."""
    
    def test_settings_initialization_with_defaults(self):
        """Test settings initialization with default values."""
        # Clear testing environment for this specific test
        import os
        original_env = os.environ.get('ENVIRONMENT')
        if 'ENVIRONMENT' in os.environ:
            del os.environ['ENVIRONMENT']
        
        try:
            settings = Settings(secret_key="test_key")
            
            assert settings.app_name == "AlphaPT"
            assert settings.environment == Environment.DEVELOPMENT
            assert settings.debug is True
            assert settings.log_level == LogLevel.INFO
            assert settings.secret_key == "test_key"
        finally:
            # Restore original environment
            if original_env:
                os.environ['ENVIRONMENT'] = original_env
        
    def test_settings_initialization_with_custom_values(self):
        """Test settings initialization with custom values."""
        settings = Settings(
            secret_key="custom_key",
            app_name="CustomApp",
            environment=Environment.PRODUCTION,
            debug=False,
            log_level=LogLevel.ERROR
        )
        
        assert settings.app_name == "CustomApp"
        assert settings.environment == Environment.PRODUCTION
        assert settings.debug is False
        assert settings.log_level == LogLevel.ERROR
        assert settings.secret_key == "custom_key"
        
    def test_settings_environment_validation(self):
        """Test environment enum validation."""
        # Valid environments
        for env in [Environment.DEVELOPMENT, Environment.STAGING, Environment.PRODUCTION, Environment.TESTING]:
            settings = Settings(secret_key="test", environment=env)
            assert settings.environment == env
            
    def test_settings_log_level_validation(self):
        """Test log level enum validation."""
        # Valid log levels
        for level in [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]:
            settings = Settings(secret_key="test", log_level=level)
            assert settings.log_level == level
            
    def test_settings_secret_key_required(self):
        """Test that secret_key is required."""
        with pytest.raises(ValidationError):
            Settings()  # Missing secret_key should raise validation error
            
    def test_settings_file_paths_creation(self):
        """Test that file paths are created correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                secret_key="test",
                logs_dir=Path(tmpdir) / "logs",
                data_dir=Path(tmpdir) / "data"
            )
            
            assert settings.logs_dir == Path(tmpdir) / "logs"
            assert settings.data_dir == Path(tmpdir) / "data"
            
    def test_settings_boolean_fields(self):
        """Test boolean configuration fields."""
        settings = Settings(
            secret_key="test",
            debug=True,
            mock_market_feed=True,
            paper_trading_enabled=True,
            zerodha_trading_enabled=False
        )
        
        assert settings.debug is True
        assert settings.mock_market_feed is True
        assert settings.paper_trading_enabled is True
        assert settings.zerodha_trading_enabled is False
        
    def test_settings_nested_configs(self):
        """Test that nested configuration objects are created."""
        settings = Settings(secret_key="test")
        
        # Check that nested configs exist and are proper types
        assert hasattr(settings, 'database')
        assert isinstance(settings.database, DatabaseConfig)
        
        assert hasattr(settings, 'trading')
        assert isinstance(settings.trading, TradingConfig)
        
        assert hasattr(settings, 'monitoring')
        assert isinstance(settings.monitoring, MonitoringConfig)


@pytest.mark.unit
class TestDatabaseConfig:
    """Test database configuration."""
    
    def test_database_config_defaults(self):
        """Test database configuration default values."""
        config = DatabaseConfig()
        
        assert config.postgres_host == "localhost"
        assert config.postgres_port == 5432
        assert config.postgres_user == "alphaPT"
        assert config.postgres_password == "alphaPT123"
        assert config.postgres_database == "alphaPT"
        
        assert config.clickhouse_host == "localhost"
        assert config.clickhouse_port == 8123
        assert config.clickhouse_user == "default"
        assert config.clickhouse_database == "alphaPT"
        
        assert config.redis_host == "localhost"
        assert config.redis_port == 6379
        assert config.redis_db == 0
        
    def test_database_config_custom_values(self):
        """Test database configuration with custom values."""
        config = DatabaseConfig(
            postgres_host="custom-pg-host",
            postgres_port=5433,
            clickhouse_host="custom-ch-host",
            redis_host="custom-redis-host"
        )
        
        assert config.postgres_host == "custom-pg-host"
        assert config.postgres_port == 5433
        assert config.clickhouse_host == "custom-ch-host"
        assert config.redis_host == "custom-redis-host"
        
    def test_database_urls_generation(self):
        """Test database URL generation."""
        config = DatabaseConfig()
        
        # Test PostgreSQL URL
        postgres_url = config.get_postgres_url()
        expected_postgres = "postgresql://alphaPT:alphaPT123@localhost:5432/alphaPT"
        assert postgres_url == expected_postgres
        
        # Test ClickHouse URL  
        clickhouse_url = config.get_clickhouse_url()
        expected_clickhouse = "clickhouse://default@localhost:8123/alphaPT"
        assert clickhouse_url == expected_clickhouse
        
        # Test Redis URL
        redis_url = config.get_redis_url()
        expected_redis = "redis://localhost:6379/0"
        assert redis_url == expected_redis


@pytest.mark.unit
class TestTradingConfig:
    """Test trading configuration."""
    
    def test_trading_config_defaults(self):
        """Test trading configuration default values."""
        config = TradingConfig()
        
        assert config.kite_api_key == ""
        assert config.kite_api_secret == ""
        assert config.max_position_value == 100000
        assert config.max_daily_loss == 10000
        assert config.order_timeout == 30
        
    def test_trading_config_custom_values(self):
        """Test trading configuration with custom values."""
        config = TradingConfig(
            kite_api_key="test_key",
            kite_api_secret="test_secret",
            max_position_value=50000,
            max_daily_loss=5000
        )
        
        assert config.kite_api_key == "test_key"
        assert config.kite_api_secret == "test_secret"
        assert config.max_position_value == 50000
        assert config.max_daily_loss == 5000
        
    def test_trading_config_validation(self):
        """Test trading configuration validation."""
        # Test positive values validation
        with pytest.raises(ValidationError):
            TradingConfig(max_position_value=-1000)
            
        with pytest.raises(ValidationError):
            TradingConfig(max_daily_loss=-500)
            
        with pytest.raises(ValidationError):
            TradingConfig(order_timeout=-10)


@pytest.mark.unit
class TestMonitoringConfig:
    """Test monitoring configuration."""
    
    def test_monitoring_config_defaults(self):
        """Test monitoring configuration default values."""
        config = MonitoringConfig()
        
        assert config.prometheus_enabled is True
        assert config.prometheus_port == 8080
        assert config.health_check_enabled is True
        assert config.health_check_interval == 30
        assert config.log_file_enabled is True
        assert config.log_console_enabled is True
        
    def test_monitoring_config_custom_values(self):
        """Test monitoring configuration with custom values."""
        config = MonitoringConfig(
            prometheus_enabled=False,
            prometheus_port=9090,
            health_check_interval=60,
            log_file_enabled=False
        )
        
        assert config.prometheus_enabled is False
        assert config.prometheus_port == 9090
        assert config.health_check_interval == 60
        assert config.log_file_enabled is False


@pytest.mark.unit
class TestEnvironmentVariableLoading:
    """Test loading configuration from environment variables."""
    
    def test_env_var_loading(self):
        """Test that environment variables are properly loaded."""
        with patch.dict(os.environ, {
            'APP_NAME': 'TestApp',
            'ENVIRONMENT': 'production',
            'DEBUG': 'false',
            'LOG_LEVEL': 'ERROR'
        }):
            settings = Settings(secret_key="test")
            
            assert settings.app_name == 'TestApp'
            assert settings.environment == Environment.PRODUCTION
            assert settings.debug is False
            assert settings.log_level == LogLevel.ERROR
            
    def test_nested_env_var_loading(self):
        """Test that nested configuration environment variables are loaded."""
        with patch.dict(os.environ, {
            'DATABASE__POSTGRES_HOST': 'env-pg-host',
            'DATABASE__POSTGRES_PORT': '5433',
            'TRADING__MAX_POSITION_VALUE': '75000',
            'MONITORING__PROMETHEUS_PORT': '9091'
        }):
            settings = Settings(secret_key="test")
            
            assert settings.database.postgres_host == 'env-pg-host'
            assert settings.database.postgres_port == 5433
            assert settings.trading.max_position_value == 75000
            assert settings.monitoring.prometheus_port == 9091
            
    def test_env_file_loading(self):
        """Test loading configuration from .env file."""
        env_content = """
APP_NAME=EnvFileApp
ENVIRONMENT=staging
DEBUG=true
SECRET_KEY=env_secret_key
DATABASE__POSTGRES_HOST=env-file-host
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            env_file_path = f.name
            
        try:
            with patch.dict(os.environ, {'ENV_FILE': env_file_path}):
                settings = Settings(_env_file=env_file_path)
                
                assert settings.app_name == 'EnvFileApp'
                assert settings.environment == Environment.STAGING
                assert settings.debug is True
                assert settings.secret_key == 'env_secret_key'
                assert settings.database.postgres_host == 'env-file-host'
        finally:
            os.unlink(env_file_path)


@pytest.mark.unit
class TestConfigurationValidation:
    """Test configuration validation logic."""
    
    def test_required_fields_validation(self):
        """Test that required configuration fields are validated."""
        # secret_key is required
        with pytest.raises(ValidationError):
            Settings()
            
    def test_field_type_validation(self):
        """Test that field types are properly validated."""
        # Test invalid port number
        with pytest.raises(ValidationError):
            Settings(secret_key="test", api_port="invalid_port")
            
        # Test invalid boolean
        with pytest.raises(ValidationError):
            Settings(secret_key="test", debug="not_a_boolean")
            
    def test_enum_validation(self):
        """Test that enum fields are properly validated."""
        # Invalid environment
        with pytest.raises(ValidationError):
            Settings(secret_key="test", environment="invalid_env")
            
        # Invalid log level
        with pytest.raises(ValidationError):
            Settings(secret_key="test", log_level="INVALID_LEVEL")
            
    def test_path_validation(self):
        """Test that path fields are properly validated."""
        settings = Settings(
            secret_key="test",
            logs_dir="/tmp/test_logs",
            data_dir="/tmp/test_data"
        )
        
        assert isinstance(settings.logs_dir, Path)
        assert isinstance(settings.data_dir, Path)
        assert str(settings.logs_dir) == "/tmp/test_logs"
        assert str(settings.data_dir) == "/tmp/test_data"
        
    def test_production_config_validation(self):
        """Test production environment configuration validation."""
        # Production should have specific requirements
        settings = Settings(
            secret_key="prod_secret_key_very_long_and_secure",
            environment=Environment.PRODUCTION,
            debug=False,
            log_level=LogLevel.INFO
        )
        
        assert settings.environment == Environment.PRODUCTION
        assert settings.debug is False
        assert len(settings.secret_key) > 10  # Should be long enough for production