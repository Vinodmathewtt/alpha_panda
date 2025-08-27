"""
Pytest configuration and shared fixtures for Alpha Panda tests.
"""
import pytest
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

from core.config.settings import Settings, DatabaseSettings, RedpandaSettings, PaperTradingSettings, ZerodhaSettings
from core.schemas.events import EventEnvelope, EventType
from core.database.connection import DatabaseManager

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def test_settings():
    """Test settings configuration."""
    return Settings(
        environment="testing",
        database=DatabaseSettings(
            postgres_url="postgresql://test:test@localhost:5432/test_alpha_panda"
        ),
        redpanda=RedpandaSettings(
            bootstrap_servers="localhost:9092",
            group_id_prefix="test-alpha-panda"
        ),
        broker_namespace="paper",
        paper_trading=PaperTradingSettings(
            enabled=True,
            slippage_percent=0.1,
            commission_percent=0.05
        ),
        zerodha=ZerodhaSettings(
            enabled=False,
            api_key="test_key",
            api_secret="test_secret"
        )
    )

@pytest.fixture
async def mock_db_manager():
    """Mock database manager for testing."""
    mock_db = AsyncMock(spec=DatabaseManager)
    mock_session = AsyncMock()
    mock_db.get_session.return_value.__aenter__.return_value = mock_session
    return mock_db

@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer for testing."""
    producer = AsyncMock()
    producer.send.return_value = None
    producer.stop.return_value = None
    return producer

@pytest.fixture  
def mock_kafka_consumer():
    """Mock Kafka consumer for testing."""
    consumer = AsyncMock()
    consumer.start.return_value = None
    consumer.stop.return_value = None
    return consumer

@pytest.fixture
def event_collector():
    """Collect emitted events for testing."""
    collected_events = []
    
    def collect_event(topic: str, event_type: EventType, key: str, data: Dict[str, Any]):
        collected_events.append({
            "topic": topic,
            "event_type": event_type,
            "key": key,
            "data": data
        })
    
    return collected_events, collect_event

@pytest.fixture
def mock_event_envelope():
    """Factory for creating mock event envelopes."""
    def _create_envelope(
        event_type: EventType = EventType.MARKET_TICK,
        correlation_id: str = None,
        causation_id: str = None,
        broker: str = "paper",
        data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())
        
        envelope = {
            "id": str(uuid.uuid4()),
            "correlation_id": correlation_id,
            "broker": broker,
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            "key": "test_key",
            "source": "test_service",
            "version": "1.0.0",
            "data": data or {}
        }
        
        if causation_id:
            envelope["causation_id"] = causation_id
            
        return envelope
    
    return _create_envelope