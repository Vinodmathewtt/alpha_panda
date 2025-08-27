"""
Pytest configuration and fixtures for AlphaPT testing infrastructure.

This module provides shared fixtures and configurations for all test types:
- Unit tests: Individual component testing with mocked dependencies
- Integration tests: Component interaction testing with minimal external dependencies
- E2E tests: Full workflow testing with real or test external services
- Smoke/Sanity tests: Basic functionality validation
"""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict, Generator, Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

# Set testing environment before any imports
os.environ["TESTING"] = "true"
os.environ["ENVIRONMENT"] = "testing"
os.environ["MOCK_MARKET_FEED"] = "true"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    from core.config.settings import Settings
    
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            secret_key="test_secret_key_123",
            environment="testing",
            debug=True,
            app_name="AlphaPT-Test",
            logs_dir=Path(tmpdir) / "logs",
            mock_market_feed=True,
            paper_trading_enabled=True,
            zerodha_trading_enabled=False,
        )
        yield settings


@pytest.fixture
async def mock_database_manager(mock_settings):
    """Mock database manager for testing."""
    from core.database.connection import DatabaseManager
    
    db_manager = Mock(spec=DatabaseManager)
    db_manager.settings = mock_settings
    db_manager.initialize = AsyncMock(return_value=True)
    db_manager.close = AsyncMock()
    db_manager.cleanup = AsyncMock()
    db_manager.health_check = AsyncMock(return_value={"status": "healthy"})
    db_manager.execute_query = AsyncMock()
    db_manager.get_connection = AsyncMock()
    
    yield db_manager


@pytest.fixture
async def mock_event_bus(mock_settings):
    """Mock event bus for testing (updated for new system)."""
    from core.events import EventBusCore
    
    event_bus = Mock(spec=EventBusCore)
    event_bus.settings = mock_settings
    event_bus.connect = AsyncMock(return_value=True)
    event_bus.disconnect = AsyncMock()
    event_bus.is_connected = True
    event_bus.nc = AsyncMock()
    event_bus.js = AsyncMock()
    
    yield event_bus


@pytest.fixture
async def mock_auth_manager(mock_settings, mock_database_manager):
    """Mock authentication manager for testing."""
    from core.auth.auth_manager import AuthManager
    
    auth_manager = Mock(spec=AuthManager)
    auth_manager.settings = mock_settings
    auth_manager.db_manager = mock_database_manager
    auth_manager.initialize = AsyncMock(return_value=True)
    auth_manager.cleanup = AsyncMock()
    auth_manager.is_authenticated = Mock(return_value=False)
    auth_manager.get_access_token = Mock(return_value=None)
    auth_manager.set_access_token = AsyncMock()
    auth_manager.authenticate_zerodha = AsyncMock()
    auth_manager.get_profile = Mock(return_value=None)
    auth_manager.get_session_info = Mock(return_value=None)
    
    yield auth_manager


@pytest.fixture
async def mock_storage_manager(mock_settings):
    """Mock storage manager for testing."""
    from storage.storage_manager import StorageManager
    
    storage_manager = Mock(spec=StorageManager)
    storage_manager.settings = mock_settings
    storage_manager.initialize = AsyncMock(return_value=True)
    storage_manager.cleanup = AsyncMock()
    storage_manager.store_tick = AsyncMock()
    storage_manager.get_latest_ticks = AsyncMock(return_value=[])
    storage_manager.health_check = AsyncMock(return_value={"status": "healthy"})
    
    yield storage_manager


@pytest.fixture
async def mock_strategy_manager(mock_settings, mock_event_bus):
    """Mock strategy manager for testing."""
    from strategy_manager.strategy_manager import StrategyManager
    
    strategy_manager = Mock(spec=StrategyManager)
    strategy_manager.settings = mock_settings
    strategy_manager.event_bus = mock_event_bus
    strategy_manager.initialize = AsyncMock(return_value=True)
    strategy_manager.cleanup = AsyncMock()
    strategy_manager.start_strategies = AsyncMock()
    strategy_manager.stop_strategies = AsyncMock()
    strategy_manager.get_strategy_status = Mock(return_value={})
    strategy_manager.health_check = AsyncMock(return_value={"status": "healthy"})
    
    yield strategy_manager


@pytest.fixture
async def mock_risk_manager(mock_settings):
    """Mock risk manager for testing."""
    from risk_manager.risk_manager import RiskManager
    
    risk_manager = Mock(spec=RiskManager)
    risk_manager.settings = mock_settings
    risk_manager.initialize = AsyncMock(return_value=True)
    risk_manager.cleanup = AsyncMock()
    risk_manager.check_risk = AsyncMock(return_value={"approved": True})
    risk_manager.health_check = AsyncMock(return_value={"status": "healthy"})
    
    yield risk_manager


@pytest.fixture
async def mock_paper_trading_engine(mock_settings):
    """Mock paper trading engine for testing."""
    from paper_trade.engine import PaperTradingEngine
    
    engine = Mock(spec=PaperTradingEngine)
    engine.settings = mock_settings
    engine.initialize = AsyncMock(return_value=True)
    engine.cleanup = AsyncMock()
    engine.place_order = AsyncMock(return_value={"order_id": "test_order_123"})
    engine.get_positions = AsyncMock(return_value=[])
    engine.get_orders = AsyncMock(return_value=[])
    engine.health_check = AsyncMock(return_value={"status": "healthy"})
    
    yield engine


@pytest.fixture
async def mock_market_feed_manager(mock_settings, mock_event_bus):
    """Mock market feed manager for testing."""
    from mock_market_feed.mock_feed_manager import MockFeedManager
    
    feed_manager = Mock(spec=MockFeedManager)
    feed_manager.settings = mock_settings
    feed_manager.event_bus = mock_event_bus
    feed_manager.initialize = AsyncMock(return_value=True)
    feed_manager.cleanup = AsyncMock()
    feed_manager.start_feed = AsyncMock()
    feed_manager.stop_feed = AsyncMock()
    feed_manager.subscribe_instruments = AsyncMock()
    feed_manager.health_check = AsyncMock(return_value={"status": "healthy"})
    
    yield feed_manager


@pytest.fixture
async def app_state_mock(
    mock_settings,
    mock_database_manager,
    mock_event_bus,
    mock_auth_manager,
    mock_storage_manager,
    mock_strategy_manager,
    mock_risk_manager,
    mock_paper_trading_engine,
    mock_market_feed_manager,
):
    """Complete mock application state for testing."""
    return {
        "settings": mock_settings,
        "db_manager": mock_database_manager,
        "event_bus": mock_event_bus,
        "auth_manager": mock_auth_manager,
        "storage_manager": mock_storage_manager,
        "strategy_manager": mock_strategy_manager,
        "risk_manager": mock_risk_manager,
        "paper_trading_engine": mock_paper_trading_engine,
        "mock_feed_manager": mock_market_feed_manager,
        "metrics_collector": Mock(),
        "business_metrics": Mock(),
        "health_checker": Mock(),
        "zerodha_feed_manager": None,
        "zerodha_trading_engine": None,
        "api_server": None,
        "shutdown_event": asyncio.Event(),
    }


@pytest.fixture
async def mock_application(app_state_mock):
    """Mock AlphaPT application for testing."""
    from app.application import AlphaPTApplication
    
    app = Mock(spec=AlphaPTApplication)
    app.app_state = app_state_mock
    app.running = False
    app.shutdown_requested = False
    
    # Mock methods
    app.initialize = AsyncMock(return_value=True)
    app.cleanup = AsyncMock()
    app.stop = AsyncMock()
    app.health_check = AsyncMock(return_value={"status": "healthy"})
    app.display_startup_banner = Mock()
    
    yield app


@pytest.fixture
async def api_client(mock_application):
    """FastAPI test client with mocked application dependencies."""
    from api.server import create_app
    
    # Create app with mocked dependencies
    with patch('api.server.get_application', return_value=mock_application):
        app = create_app()
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client


@pytest.fixture
def sample_tick_data():
    """Sample market tick data for testing."""
    return {
        "instrument_token": 738561,
        "tradingsymbol": "RELIANCE",
        "last_price": 2500.50,
        "last_quantity": 10,
        "average_price": 2499.75,
        "volume": 1000000,
        "buy_quantity": 500000,
        "sell_quantity": 500000,
        "ohlc": {
            "open": 2480.00,
            "high": 2520.00,
            "low": 2475.00,
            "close": 2500.50,
        },
        "timestamp": datetime.now(timezone.utc),
        "exchange_timestamp": datetime.now(timezone.utc),
    }


@pytest.fixture
def sample_order_data():
    """Sample order data for testing."""
    return {
        "tradingsymbol": "RELIANCE",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "order_type": "LIMIT",
        "quantity": 10,
        "price": 2500.00,
        "product": "MIS",
        "validity": "DAY",
        "disclosed_quantity": 0,
        "trigger_price": 0,
        "squareoff": 0,
        "stoploss": 0,
        "trailing_stoploss": 0,
    }


@pytest.fixture
def sample_strategy_config():
    """Sample strategy configuration for testing."""
    return {
        "name": "test_momentum_strategy",
        "strategy_type": "momentum",
        "enabled": True,
        "parameters": {
            "lookback_periods": 20,
            "threshold": 0.02,
            "position_size": 1000,
        },
        "instruments": ["RELIANCE", "TCS", "INFY"],
        "risk_limits": {
            "max_position_value": 50000,
            "max_daily_loss": 5000,
        },
        "routing": {
            "paper_trade": True,
            "zerodha_trade": False,
        },
    }


@pytest.fixture
async def real_database_manager(mock_settings):
    """Real database manager for integration testing."""
    from core.database.connection import DatabaseManager
    
    db_manager = DatabaseManager(mock_settings)
    try:
        await db_manager.initialize()
        yield db_manager
    finally:
        await db_manager.cleanup()


@pytest.fixture
async def real_event_bus(mock_settings):
    """Real event bus for integration testing (updated for new system)."""
    from core.events import EventBusCore
    
    event_bus = EventBusCore(mock_settings)
    try:
        await event_bus.connect()
        yield event_bus
    finally:
        await event_bus.disconnect()


# Test data generators
def generate_test_instruments(count: int = 10):
    """Generate test instrument data."""
    instruments = []
    for i in range(count):
        instruments.append({
            "instrument_token": 700000 + i,
            "tradingsymbol": f"TEST{i:03d}",
            "name": f"Test Company {i}",
            "exchange": "NSE",
            "segment": "NSE",
            "expiry": "",
            "strike": 0.0,
            "instrument_type": "EQ",
            "lot_size": 1,
            "tick_size": 0.05,
        })
    return instruments


def generate_test_ticks(instrument_token: int, count: int = 100):
    """Generate test tick data."""
    ticks = []
    base_price = 1000.0
    
    for i in range(count):
        price_change = (i % 20 - 10) * 0.5  # Random price movement
        current_price = base_price + price_change
        
        tick = {
            "instrument_token": instrument_token,
            "last_price": current_price,
            "last_quantity": 10 + (i % 50),
            "average_price": current_price - 0.25,
            "volume": (i + 1) * 1000,
            "buy_quantity": 500000,
            "sell_quantity": 500000,
            "ohlc": {
                "open": base_price,
                "high": current_price + 5,
                "low": current_price - 5,
                "close": current_price,
            },
            "timestamp": datetime.now(timezone.utc),
        }
        ticks.append(tick)
        
    return ticks


# Performance testing fixtures
@pytest.fixture
def performance_config():
    """Configuration for performance testing."""
    return {
        "tick_generation_rate": 100,  # ticks per second
        "test_duration": 10,  # seconds
        "max_latency_ms": 10,  # maximum acceptable latency
        "target_throughput": 1000,  # ticks per second
    }


# Markers for test categorization
pytestmark = [
    pytest.mark.asyncio,
]