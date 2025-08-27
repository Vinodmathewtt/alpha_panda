"""
Unit tests for AlphaPT storage system.

Tests the storage manager, ClickHouse integration, data quality monitoring,
and market data storage/retrieval functionality.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone
from decimal import Decimal

from storage.storage_manager import MarketDataStorageManager
from storage.clickhouse_manager import ClickHouseManager
from storage.data_quality_monitor import DataQualityMonitor
from core.config.settings import Settings


@pytest.mark.unit
class TestStorageManager:
    """Test StorageManager functionality."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.database.clickhouse_host = "localhost"
        settings.database.clickhouse_port = 9000
        settings.database.clickhouse_database = "test_alphapt"
        settings.database.clickhouse_user = "default"
        settings.database.clickhouse_password = ""
        return settings
        
    @pytest.fixture
    def sample_tick_data(self):
        """Create sample tick data."""
        return {
            "instrument_token": 738561,
            "tradingsymbol": "RELIANCE",
            "exchange": "NSE",
            "last_price": 2500.50,
            "last_quantity": 10,
            "volume": 1000000,
            "timestamp": datetime.now(timezone.utc),
            "exchange_timestamp": datetime.now(timezone.utc),
            "ohlc": {
                "open": 2480.00,
                "high": 2520.00,
                "low": 2475.00,
                "close": 2500.50
            }
        }
    
    def test_storage_manager_initialization(self, mock_settings):
        """Test MarketDataStorageManager initialization."""
        event_bus = Mock()
        storage_manager = MarketDataStorageManager(mock_settings, event_bus)
        
        assert storage_manager.settings == mock_settings
        assert storage_manager.event_bus == event_bus
        
    @pytest.mark.asyncio
    async def test_storage_manager_initialize_success(self, mock_settings):
        """Test successful storage manager initialization."""
        event_bus = Mock()
        storage_manager = MarketDataStorageManager(mock_settings, event_bus)
        
        with patch.object(storage_manager, '_initialize_storage', return_value=True):
            result = await storage_manager.initialize()
            assert result is True
            
    @pytest.mark.asyncio
    async def test_storage_manager_initialize_failure(self, mock_settings):
        """Test storage manager initialization failure."""
        storage_manager = StorageManager(mock_settings)
        
        with patch.object(storage_manager.clickhouse_manager, 'initialize', side_effect=Exception("Connection failed")):
            result = await storage_manager.initialize()
            assert result is False
            
    @pytest.mark.asyncio
    async def test_store_tick_success(self, mock_settings, sample_tick_data):
        """Test successful tick storage."""
        storage_manager = StorageManager(mock_settings)
        
        with patch.object(storage_manager.clickhouse_manager, 'store_market_tick', return_value=True) as mock_store, \
             patch.object(storage_manager.data_quality_monitor, 'validate_tick', return_value=True) as mock_validate:
            
            result = await storage_manager.store_tick(sample_tick_data)
            
            assert result is True
            mock_validate.assert_called_once_with(sample_tick_data)
            mock_store.assert_called_once_with(sample_tick_data)
            
    @pytest.mark.asyncio
    async def test_store_tick_validation_failure(self, mock_settings, sample_tick_data):
        """Test tick storage with validation failure."""
        storage_manager = StorageManager(mock_settings)
        
        with patch.object(storage_manager.data_quality_monitor, 'validate_tick', return_value=False):
            result = await storage_manager.store_tick(sample_tick_data)
            assert result is False
            
    @pytest.mark.asyncio
    async def test_get_latest_ticks(self, mock_settings):
        """Test retrieving latest ticks."""
        storage_manager = StorageManager(mock_settings)
        
        expected_ticks = [
            {"instrument_token": 738561, "last_price": 2500.50, "timestamp": datetime.now(timezone.utc)},
            {"instrument_token": 738561, "last_price": 2501.00, "timestamp": datetime.now(timezone.utc)}
        ]
        
        with patch.object(storage_manager.clickhouse_manager, 'get_latest_ticks', return_value=expected_ticks) as mock_get:
            result = await storage_manager.get_latest_ticks(738561, limit=10)
            
            assert result == expected_ticks
            mock_get.assert_called_once_with(738561, limit=10)
            
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, mock_settings):
        """Test health check when all components are healthy."""
        storage_manager = StorageManager(mock_settings)
        
        clickhouse_health = {"status": "healthy", "connected": True}
        quality_health = {"status": "healthy", "processed": 100}
        
        with patch.object(storage_manager.clickhouse_manager, 'health_check', return_value=clickhouse_health), \
             patch.object(storage_manager.data_quality_monitor, 'get_stats', return_value=quality_health):
            
            result = await storage_manager.health_check()
            
            assert result["status"] == "healthy"
            assert result["clickhouse"] == clickhouse_health
            assert result["data_quality"] == quality_health
            
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, mock_settings):
        """Test health check when components are unhealthy."""
        storage_manager = StorageManager(mock_settings)
        
        with patch.object(storage_manager.clickhouse_manager, 'health_check', side_effect=Exception("DB Error")):
            result = await storage_manager.health_check()
            
            assert result["status"] == "unhealthy"
            assert "error" in result
            
    @pytest.mark.asyncio
    async def test_cleanup(self, mock_settings):
        """Test storage manager cleanup."""
        storage_manager = StorageManager(mock_settings)
        
        with patch.object(storage_manager.clickhouse_manager, 'close', return_value=None) as mock_close, \
             patch.object(storage_manager.data_quality_monitor, 'stop', return_value=None) as mock_stop:
            
            await storage_manager.cleanup()
            
            mock_close.assert_called_once()
            mock_stop.assert_called_once()


@pytest.mark.unit
class TestClickHouseManager:
    """Test ClickHouseManager functionality."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.database.clickhouse_host = "localhost"
        settings.database.clickhouse_port = 9000
        settings.database.clickhouse_database = "test_alphapt"
        settings.database.clickhouse_user = "default"
        settings.database.clickhouse_password = ""
        return settings
        
    def test_clickhouse_manager_initialization(self, mock_settings):
        """Test ClickHouseManager initialization."""
        manager = ClickHouseManager(mock_settings)
        
        assert manager.settings == mock_settings
        assert manager.client is None
        assert not manager.connected
        
    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_settings):
        """Test successful ClickHouse initialization."""
        manager = ClickHouseManager(mock_settings)
        
        mock_client = AsyncMock()
        mock_client.execute.return_value = None
        
        with patch('aioclickhouse.create_client', return_value=mock_client):
            result = await manager.initialize()
            
            assert result is True
            assert manager.client == mock_client
            assert manager.connected is True
            
    @pytest.mark.asyncio
    async def test_initialize_failure(self, mock_settings):
        """Test ClickHouse initialization failure."""
        manager = ClickHouseManager(mock_settings)
        
        with patch('aioclickhouse.create_client', side_effect=Exception("Connection failed")):
            result = await manager.initialize()
            
            assert result is False
            assert manager.client is None
            assert manager.connected is False
            
    @pytest.mark.asyncio
    async def test_store_market_tick(self, mock_settings):
        """Test storing market tick data."""
        manager = ClickHouseManager(mock_settings)
        manager.client = AsyncMock()
        manager.connected = True
        
        tick_data = {
            "instrument_token": 738561,
            "tradingsymbol": "RELIANCE",
            "last_price": 2500.50,
            "volume": 1000000,
            "timestamp": datetime.now(timezone.utc)
        }
        
        result = await manager.store_market_tick(tick_data)
        
        assert result is True
        manager.client.execute.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_store_market_tick_not_connected(self, mock_settings):
        """Test storing tick when not connected."""
        manager = ClickHouseManager(mock_settings)
        manager.connected = False
        
        tick_data = {"instrument_token": 738561}
        result = await manager.store_market_tick(tick_data)
        
        assert result is False
        
    @pytest.mark.asyncio
    async def test_get_latest_ticks(self, mock_settings):
        """Test retrieving latest ticks."""
        manager = ClickHouseManager(mock_settings)
        manager.client = AsyncMock()
        manager.connected = True
        
        expected_data = [
            (738561, 2500.50, datetime.now(timezone.utc)),
            (738561, 2501.00, datetime.now(timezone.utc))
        ]
        manager.client.execute.return_value = expected_data
        
        result = await manager.get_latest_ticks(738561, limit=10)
        
        assert len(result) == 2
        assert result[0]["instrument_token"] == 738561
        assert result[0]["last_price"] == 2500.50
        manager.client.execute.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, mock_settings):
        """Test health check when ClickHouse is healthy."""
        manager = ClickHouseManager(mock_settings)
        manager.client = AsyncMock()
        manager.connected = True
        
        manager.client.execute.return_value = [(1,)]
        
        result = await manager.health_check()
        
        assert result["status"] == "healthy"
        assert result["connected"] is True
        
    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, mock_settings):
        """Test health check when ClickHouse is unhealthy."""
        manager = ClickHouseManager(mock_settings)
        manager.connected = False
        
        result = await manager.health_check()
        
        assert result["status"] == "unhealthy"
        assert result["connected"] is False


@pytest.mark.unit
class TestDataQualityMonitor:
    """Test DataQualityMonitor functionality."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        return settings
        
    def test_data_quality_monitor_initialization(self, mock_settings):
        """Test DataQualityMonitor initialization."""
        monitor = DataQualityMonitor(mock_settings)
        
        assert monitor.settings == mock_settings
        assert monitor.stats["total_ticks"] == 0
        assert monitor.stats["valid_ticks"] == 0
        assert monitor.stats["invalid_ticks"] == 0
        
    def test_validate_tick_valid(self, mock_settings):
        """Test validating a valid tick."""
        monitor = DataQualityMonitor(mock_settings)
        
        valid_tick = {
            "instrument_token": 738561,
            "last_price": 2500.50,
            "volume": 1000000,
            "timestamp": datetime.now(timezone.utc)
        }
        
        result = monitor.validate_tick(valid_tick)
        
        assert result is True
        assert monitor.stats["total_ticks"] == 1
        assert monitor.stats["valid_ticks"] == 1
        assert monitor.stats["invalid_ticks"] == 0
        
    def test_validate_tick_invalid_missing_fields(self, mock_settings):
        """Test validating tick with missing required fields."""
        monitor = DataQualityMonitor(mock_settings)
        
        invalid_tick = {
            "instrument_token": 738561,
            # Missing last_price and other required fields
        }
        
        result = monitor.validate_tick(invalid_tick)
        
        assert result is False
        assert monitor.stats["total_ticks"] == 1
        assert monitor.stats["valid_ticks"] == 0
        assert monitor.stats["invalid_ticks"] == 1
        
    def test_validate_tick_invalid_negative_price(self, mock_settings):
        """Test validating tick with negative price."""
        monitor = DataQualityMonitor(mock_settings)
        
        invalid_tick = {
            "instrument_token": 738561,
            "last_price": -100.0,  # Negative price is invalid
            "volume": 1000000,
            "timestamp": datetime.now(timezone.utc)
        }
        
        result = monitor.validate_tick(invalid_tick)
        
        assert result is False
        assert monitor.stats["invalid_ticks"] == 1
        
    def test_validate_tick_invalid_future_timestamp(self, mock_settings):
        """Test validating tick with future timestamp."""
        monitor = DataQualityMonitor(mock_settings)
        
        future_time = datetime.now(timezone.utc).replace(year=2030)
        invalid_tick = {
            "instrument_token": 738561,
            "last_price": 2500.50,
            "volume": 1000000,
            "timestamp": future_time  # Future timestamp is invalid
        }
        
        result = monitor.validate_tick(invalid_tick)
        
        assert result is False
        assert monitor.stats["invalid_ticks"] == 1
        
    def test_get_stats(self, mock_settings):
        """Test getting quality statistics."""
        monitor = DataQualityMonitor(mock_settings)
        
        # Process some ticks
        valid_tick = {
            "instrument_token": 738561,
            "last_price": 2500.50,
            "volume": 1000000,
            "timestamp": datetime.now(timezone.utc)
        }
        invalid_tick = {"instrument_token": 738561}
        
        monitor.validate_tick(valid_tick)
        monitor.validate_tick(invalid_tick)
        
        stats = monitor.get_stats()
        
        assert stats["status"] == "healthy"
        assert stats["total_ticks"] == 2
        assert stats["valid_ticks"] == 1
        assert stats["invalid_ticks"] == 1
        assert stats["quality_ratio"] == 0.5
        
    def test_start_stop(self, mock_settings):
        """Test starting and stopping the monitor."""
        monitor = DataQualityMonitor(mock_settings)
        
        # Start should not raise exceptions
        monitor.start()
        assert True
        
        # Stop should not raise exceptions
        monitor.stop()
        assert True


@pytest.mark.unit
class TestStorageIntegration:
    """Test storage system integration scenarios."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.database.clickhouse_host = "localhost"
        settings.database.clickhouse_port = 9000
        settings.database.clickhouse_database = "test_alphapt"
        return settings
    
    @pytest.mark.asyncio
    async def test_end_to_end_tick_storage(self, mock_settings):
        """Test complete tick storage workflow."""
        storage_manager = StorageManager(mock_settings)
        
        # Mock successful initialization
        with patch.object(storage_manager.clickhouse_manager, 'initialize', return_value=True), \
             patch.object(storage_manager.data_quality_monitor, 'start'):
            
            await storage_manager.initialize()
            
            # Mock successful tick processing
            tick_data = {
                "instrument_token": 738561,
                "last_price": 2500.50,
                "volume": 1000000,
                "timestamp": datetime.now(timezone.utc)
            }
            
            with patch.object(storage_manager.data_quality_monitor, 'validate_tick', return_value=True), \
                 patch.object(storage_manager.clickhouse_manager, 'store_market_tick', return_value=True):
                
                result = await storage_manager.store_tick(tick_data)
                assert result is True
                
    @pytest.mark.asyncio
    async def test_bulk_tick_storage(self, mock_settings):
        """Test storing multiple ticks efficiently."""
        storage_manager = StorageManager(mock_settings)
        
        # Generate multiple tick records
        ticks = []
        for i in range(100):
            tick = {
                "instrument_token": 738561,
                "last_price": 2500.0 + i * 0.1,
                "volume": 1000000 + i * 1000,
                "timestamp": datetime.now(timezone.utc)
            }
            ticks.append(tick)
        
        # Mock batch processing
        with patch.object(storage_manager.data_quality_monitor, 'validate_tick', return_value=True), \
             patch.object(storage_manager.clickhouse_manager, 'store_market_tick', return_value=True) as mock_store:
            
            # Store all ticks
            results = []
            for tick in ticks:
                result = await storage_manager.store_tick(tick)
                results.append(result)
            
            # Verify all ticks were processed
            assert all(results)
            assert mock_store.call_count == 100
            
    @pytest.mark.asyncio
    async def test_storage_resilience_to_failures(self, mock_settings):
        """Test storage system resilience to component failures."""
        storage_manager = StorageManager(mock_settings)
        
        tick_data = {
            "instrument_token": 738561,
            "last_price": 2500.50,
            "volume": 1000000,
            "timestamp": datetime.now(timezone.utc)
        }
        
        # Test resilience to ClickHouse failures
        with patch.object(storage_manager.data_quality_monitor, 'validate_tick', return_value=True), \
             patch.object(storage_manager.clickhouse_manager, 'store_market_tick', side_effect=Exception("DB Error")):
            
            result = await storage_manager.store_tick(tick_data)
            # Should handle the error gracefully
            assert result is False