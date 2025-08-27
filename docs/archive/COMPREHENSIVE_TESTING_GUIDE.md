# Alpha Panda - Comprehensive Testing Guide

*Advanced Testing Strategies for Production-Ready Trading Systems*

## 📋 Table of Contents

1. [Overview](#overview)
2. [Integration Testing with Full Service Mocking](#integration-testing-with-full-service-mocking)
3. [Enhanced Error Handling & Retry Testing](#enhanced-error-handling--retry-testing)
4. [End-to-End Pipeline Testing](#end-to-end-pipeline-testing)
5. [Testing Infrastructure Setup](#testing-infrastructure-setup)
6. [Performance & Load Testing](#performance--load-testing)
7. [Testing Best Practices](#testing-best-practices)

## Overview

This guide provides comprehensive strategies for testing the Alpha Panda trading system at multiple levels, from isolated unit tests to full end-to-end pipeline validation. The testing approach follows the Test Pyramid pattern with emphasis on reliability, performance, and real-world scenario simulation.

### Testing Philosophy

```
                    E2E Tests (Few)
                 ┌─────────────────────┐
                 │  Real Infrastructure │
                 │  Full Pipeline Flow  │
                 └─────────────────────┘
                    
              Integration Tests (Some)
           ┌─────────────────────────────┐
           │    Service Interactions     │
           │    Component Integration    │
           │    Mock Infrastructure      │
           └─────────────────────────────┘
           
                Unit Tests (Many)
         ┌─────────────────────────────────┐
         │        Pure Functions           │
         │       Business Logic            │
         │      Component Isolation        │
         └─────────────────────────────────┘
```

## Integration Testing with Full Service Mocking

### Architecture Overview

Integration tests validate service interactions and data flow without requiring external infrastructure. This approach provides fast feedback while testing realistic scenarios.

### Implementation Strategy

#### 1. Service Mock Framework

Create a comprehensive service mocking framework that simulates all external dependencies:

```python
# tests/integration/mocks/service_mocks.py

import asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from decimal import Decimal

from core.schemas.events import EventEnvelope, EventType, MarketTick, TradingSignal


class MockRedpandaService:
    """Mock Redpanda/Kafka service for integration testing"""
    
    def __init__(self):
        self.topics: Dict[str, List[Dict]] = {}
        self.consumers: Dict[str, List] = {}
        self.producers: List[AsyncMock] = []
        self.message_handlers = {}
    
    async def create_topic(self, topic_name: str, partitions: int = 3):
        """Create a mock topic"""
        self.topics[topic_name] = []
    
    async def publish_message(self, topic: str, key: str, value: Dict[str, Any]):
        """Publish message to mock topic"""
        if topic not in self.topics:
            await self.create_topic(topic)
        
        message = {
            "topic": topic,
            "key": key,
            "value": value,
            "timestamp": datetime.now(timezone.utc),
            "partition": 0,
            "offset": len(self.topics[topic])
        }
        self.topics[topic].append(message)
        
        # Trigger any registered handlers
        if topic in self.message_handlers:
            for handler in self.message_handlers[topic]:
                await handler(message)
    
    async def consume_messages(self, topic: str, group_id: str) -> List[Dict]:
        """Consume messages from mock topic"""
        return self.topics.get(topic, [])
    
    def register_message_handler(self, topic: str, handler):
        """Register handler for automatic message processing"""
        if topic not in self.message_handlers:
            self.message_handlers[topic] = []
        self.message_handlers[topic].append(handler)


class MockDatabaseService:
    """Mock database service for integration testing"""
    
    def __init__(self):
        self.strategies = []
        self.sessions = []
        self.configurations = {}
    
    async def get_active_strategies(self) -> List[Dict]:
        """Return mock active strategies"""
        return [
            {
                "id": "momentum_test_1",
                "strategy_type": "SimpleMomentumStrategy",
                "instruments": [738561, 2714625],
                "parameters": {
                    "lookback_period": 20,
                    "momentum_threshold": 0.02,
                    "position_size": 100
                },
                "is_active": True,
                "zerodha_trading_enabled": False
            },
            {
                "id": "mean_reversion_test_1", 
                "strategy_type": "MeanReversionStrategy",
                "instruments": [738561],
                "parameters": {
                    "lookback_period": 50,
                    "deviation_threshold": 2.0,
                    "position_size": 50
                },
                "is_active": True,
                "zerodha_trading_enabled": True
            }
        ]
    
    async def save_trading_session(self, session_data: Dict):
        """Save trading session data"""
        self.sessions.append(session_data)


class MockRedisService:
    """Mock Redis service for integration testing"""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.expiry: Dict[str, datetime] = {}
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from mock Redis"""
        if key in self.expiry and datetime.now() > self.expiry[key]:
            del self.data[key]
            del self.expiry[key]
            return None
        return self.data.get(key)
    
    async def set(self, key: str, value: str, ttl: Optional[int] = None):
        """Set value in mock Redis"""
        self.data[key] = value
        if ttl:
            self.expiry[key] = datetime.now() + timedelta(seconds=ttl)
    
    async def keys(self, pattern: str) -> List[str]:
        """Get keys matching pattern"""
        import fnmatch
        return [k for k in self.data.keys() if fnmatch.fnmatch(k, pattern)]


class IntegrationTestEnvironment:
    """Complete integration testing environment"""
    
    def __init__(self):
        self.redpanda = MockRedpandaService()
        self.database = MockDatabaseService() 
        self.redis = MockRedisService()
        self.market_data_generator = MockMarketDataGenerator()
        
    async def setup(self):
        """Setup integration test environment"""
        # Create all required topics
        topics = [
            "market.ticks",
            "paper.signals.raw", "paper.signals.validated", "paper.signals.rejected",
            "paper.orders.submitted", "paper.orders.filled", "paper.orders.failed",
            "zerodha.signals.raw", "zerodha.signals.validated", "zerodha.signals.rejected", 
            "zerodha.orders.submitted", "zerodha.orders.filled", "zerodha.orders.failed"
        ]
        
        for topic in topics:
            await self.redpanda.create_topic(topic)
    
    async def teardown(self):
        """Clean up test environment"""
        self.redpanda.topics.clear()
        self.database.strategies.clear()
        self.redis.data.clear()


class MockMarketDataGenerator:
    """Generate realistic market data for testing"""
    
    def __init__(self):
        self.base_prices = {
            738561: Decimal("2500.00"),  # Mock NIFTY
            2714625: Decimal("45000.00")  # Mock BANKNIFTY
        }
        self.price_history = {}
    
    def generate_tick(self, instrument_token: int, 
                     price_change_percent: float = 0.0,
                     volume: int = 1000) -> MarketTick:
        """Generate realistic market tick"""
        if instrument_token not in self.price_history:
            self.price_history[instrument_token] = []
        
        base_price = self.base_prices.get(instrument_token, Decimal("100.00"))
        
        # Apply price change
        if price_change_percent != 0.0:
            price_change = base_price * Decimal(str(price_change_percent))
            new_price = base_price + price_change
        else:
            # Random small fluctuation
            import random
            fluctuation = random.uniform(-0.001, 0.001)  # 0.1% max fluctuation
            new_price = base_price * (1 + fluctuation)
        
        self.base_prices[instrument_token] = new_price
        
        tick = MarketTick(
            instrument_token=instrument_token,
            last_price=new_price,
            volume=volume,
            timestamp=datetime.now(timezone.utc),
            ohlc={
                "open": new_price * Decimal("0.998"),
                "high": new_price * Decimal("1.002"), 
                "low": new_price * Decimal("0.997"),
                "close": new_price
            }
        )
        
        self.price_history[instrument_token].append(tick)
        return tick
    
    def generate_trend_data(self, instrument_token: int, 
                           trend_direction: str, 
                           num_ticks: int = 20) -> List[MarketTick]:
        """Generate trending market data for strategy testing"""
        ticks = []
        
        if trend_direction == "upward":
            price_changes = [0.002, 0.001, 0.003, 0.0015, 0.0025]  # 0.1-0.3% increases
        elif trend_direction == "downward":
            price_changes = [-0.002, -0.001, -0.003, -0.0015, -0.0025]  # 0.1-0.3% decreases
        else:  # sideways
            price_changes = [0.0005, -0.0003, 0.0002, -0.0001, 0.0004]  # Small fluctuations
        
        for i in range(num_ticks):
            change = price_changes[i % len(price_changes)]
            tick = self.generate_tick(instrument_token, change)
            ticks.append(tick)
            
            # Small delay simulation
            await asyncio.sleep(0.01)
        
        return ticks
```

#### 2. Complete Service Integration Tests

```python
# tests/integration/test_complete_service_integration.py

import pytest
import asyncio
from unittest.mock import patch
from typing import List, Dict

from tests.integration.mocks.service_mocks import IntegrationTestEnvironment
from services.strategy_runner.service import StrategyRunnerService
from services.risk_manager.service import RiskManagerService
from services.trading_engine.service import TradingEngineService
from services.portfolio_manager.service import PortfolioManagerService
from core.schemas.events import EventType
from core.config.settings import Settings


@pytest.mark.integration
class TestCompleteServiceIntegration:
    """Test complete service integration with full mocking"""
    
    @pytest.fixture
    async def test_environment(self):
        """Setup complete test environment"""
        env = IntegrationTestEnvironment()
        await env.setup()
        yield env
        await env.teardown()
    
    @pytest.fixture
    async def services(self, test_environment, test_settings):
        """Setup all services with mocked dependencies"""
        services = {}
        
        with patch('core.database.connection.DatabaseManager') as mock_db, \
             patch('redis.asyncio.from_url') as mock_redis, \
             patch('core.streaming.clients.AIOKafkaProducer'), \
             patch('core.streaming.clients.AIOKafkaConsumer'):
            
            # Setup mocked database
            mock_db.return_value = test_environment.database
            
            # Setup mocked Redis
            mock_redis.return_value = test_environment.redis
            
            # Initialize services
            services['strategy_runner'] = StrategyRunnerService(
                test_settings.redpanda, test_settings, mock_db.return_value
            )
            
            services['risk_manager'] = RiskManagerService(
                test_settings.redpanda, test_settings
            )
            
            services['trading_engine'] = TradingEngineService(
                test_settings.redpanda, test_settings, mock_db.return_value
            )
            
            services['portfolio_manager'] = PortfolioManagerService(
                test_settings.redpanda, test_settings, test_environment.redis
            )
            
            # Replace producers/consumers with mocked versions
            for service_name, service in services.items():
                service.producer = test_environment.redpanda
                service.consumer = test_environment.redpanda
        
        yield services
        
        # Cleanup services
        for service in services.values():
            await service.stop()
    
    @pytest.mark.asyncio
    async def test_complete_trading_pipeline_paper_mode(self, services, test_environment):
        """Test complete trading pipeline in paper trading mode"""
        # Start all services
        for service in services.values():
            await service.start()
        
        # Generate market data that should trigger momentum strategy
        market_generator = test_environment.market_data_generator
        upward_ticks = await market_generator.generate_trend_data(
            738561, "upward", 25  # Generate 25 ticks with upward trend
        )
        
        # Simulate market feed publishing ticks
        signals_generated = []
        orders_placed = []
        portfolio_updates = []
        
        # Register handlers to capture events
        async def capture_signals(message):
            if message["value"].get("type") == EventType.TRADING_SIGNAL:
                signals_generated.append(message)
        
        async def capture_orders(message):
            if message["value"].get("type") == EventType.ORDER_FILLED:
                orders_placed.append(message)
        
        test_environment.redpanda.register_message_handler(
            "paper.signals.raw", capture_signals
        )
        test_environment.redpanda.register_message_handler(
            "paper.orders.filled", capture_orders
        )
        
        # Publish market ticks
        for tick in upward_ticks:
            await test_environment.redpanda.publish_message(
                "market.ticks",
                str(tick.instrument_token),
                {
                    "type": EventType.MARKET_TICK,
                    "data": tick.dict(),
                    "timestamp": tick.timestamp.isoformat()
                }
            )
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        # Verify pipeline execution
        assert len(signals_generated) > 0, "Should generate trading signals"
        assert len(orders_placed) > 0, "Should place orders"
        
        # Verify signal quality
        signal = signals_generated[0]["value"]["data"]
        assert signal["strategy_id"] == "momentum_test_1"
        assert signal["signal_type"] in ["BUY", "SELL"]
        assert signal["quantity"] > 0
        
        # Verify order execution
        order = orders_placed[0]["value"]["data"] 
        assert order["execution_mode"] == "paper"
        assert order["fill_price"] > 0
        
        # Verify portfolio updates
        portfolio_keys = await test_environment.redis.keys("paper:portfolio:*")
        assert len(portfolio_keys) > 0, "Should update portfolio cache"
    
    @pytest.mark.asyncio
    async def test_risk_manager_signal_rejection(self, services, test_environment):
        """Test risk manager properly rejects invalid signals"""
        await services['risk_manager'].start()
        
        # Create oversized signal that should be rejected
        oversized_signal = {
            "type": EventType.TRADING_SIGNAL,
            "data": {
                "strategy_id": "momentum_test_1",
                "instrument_token": 738561,
                "signal_type": "BUY",
                "quantity": 10000,  # Intentionally large quantity
                "price": 2500.00,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }
        
        rejected_signals = []
        
        async def capture_rejections(message):
            if message["value"].get("type") == EventType.REJECTED_SIGNAL:
                rejected_signals.append(message)
        
        test_environment.redpanda.register_message_handler(
            "paper.signals.rejected", capture_rejections
        )
        
        # Publish oversized signal
        await test_environment.redpanda.publish_message(
            "paper.signals.raw",
            "momentum_test_1:738561", 
            oversized_signal
        )
        
        await asyncio.sleep(0.2)
        
        # Verify rejection
        assert len(rejected_signals) > 0, "Should reject oversized signal"
        rejection = rejected_signals[0]["value"]["data"]
        assert "position_size" in rejection["rejection_reason"].lower()
    
    @pytest.mark.asyncio
    async def test_dual_broker_isolation(self, services, test_environment):
        """Test complete isolation between paper and zerodha brokers"""
        # Start relevant services
        await services['strategy_runner'].start()
        await services['risk_manager'].start()
        
        paper_signals = []
        zerodha_signals = []
        
        # Register separate handlers
        async def capture_paper_signals(message):
            paper_signals.append(message)
        
        async def capture_zerodha_signals(message):
            zerodha_signals.append(message)
        
        test_environment.redpanda.register_message_handler(
            "paper.signals.raw", capture_paper_signals
        )
        test_environment.redpanda.register_message_handler(
            "zerodha.signals.raw", capture_zerodha_signals
        )
        
        # Generate market tick
        tick = test_environment.market_data_generator.generate_tick(738561, 0.025)  # 2.5% move
        
        await test_environment.redpanda.publish_message(
            "market.ticks",
            str(tick.instrument_token),
            {
                "type": EventType.MARKET_TICK,
                "data": tick.dict()
            }
        )
        
        await asyncio.sleep(0.3)
        
        # Both strategies should generate signals in their respective brokers
        assert len(paper_signals) > 0, "Should generate paper signals"
        assert len(zerodha_signals) > 0, "Should generate zerodha signals"
        
        # Verify broker isolation
        for signal in paper_signals:
            assert "paper" in signal["topic"]
            assert signal["value"].get("broker") == "paper"
        
        for signal in zerodha_signals:
            assert "zerodha" in signal["topic"] 
            assert signal["value"].get("broker") == "zerodha"
```

## Enhanced Error Handling & Retry Testing

### Strategy Overview

Comprehensive error handling testing validates the system's resilience under various failure conditions, including transient failures, poison messages, and infrastructure outages.

### Implementation Framework

#### 1. Error Simulation Framework

```python
# tests/unit/test_enhanced_error_handling.py

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from datetime import datetime, timedelta
from typing import Dict, List, Callable

from core.streaming.error_handling import (
    ErrorHandler, DLQPublisher, ErrorClassifier, ErrorType, RetryConfig
)


class ErrorSimulator:
    """Simulate various error conditions for testing"""
    
    def __init__(self):
        self.failure_count = 0
        self.failure_pattern = []
        self.failure_types = []
    
    def set_failure_pattern(self, pattern: List[bool]):
        """Set pattern of failures (True = fail, False = succeed)"""
        self.failure_pattern = pattern
        self.failure_count = 0
    
    def set_failure_types(self, error_types: List[Exception]):
        """Set types of errors to simulate"""
        self.failure_types = error_types
    
    async def simulate_operation(self):
        """Simulate an operation that may fail"""
        if (self.failure_count < len(self.failure_pattern) and 
            self.failure_pattern[self.failure_count]):
            
            error_index = min(self.failure_count, len(self.failure_types) - 1)
            error = self.failure_types[error_index]
            self.failure_count += 1
            raise error
        
        self.failure_count += 1
        return "success"


@pytest.mark.unit
class TestEnhancedErrorHandling:
    """Enhanced error handling and retry logic tests"""
    
    @pytest.fixture
    def error_simulator(self):
        return ErrorSimulator()
    
    @pytest.fixture
    def mock_message(self):
        """Create mock message for testing"""
        message = AsyncMock()
        message.topic = "test.topic"
        message.key = b"test_key"
        message.value = {"test": "data"}
        message.partition = 0
        message.offset = 123
        message.timestamp = datetime.now().timestamp() * 1000
        return message
    
    @pytest.mark.asyncio
    async def test_transient_error_retry_with_exponential_backoff(
        self, error_simulator, mock_message
    ):
        """Test retry logic with exponential backoff for transient errors"""
        
        # Setup error pattern: fail 3 times, then succeed
        error_simulator.set_failure_pattern([True, True, True, False])
        error_simulator.set_failure_types([ConnectionError("Network timeout")])
        
        retry_config = RetryConfig(
            max_attempts=5,
            base_delay=0.1,  # Short delay for testing
            exponential_base=2.0,
            jitter=False  # Disable jitter for predictable testing
        )
        
        mock_dlq = AsyncMock()
        error_handler = ErrorHandler("test_service", mock_dlq, retry_config)
        
        start_time = datetime.now()
        
        result = await error_handler.handle_processing_error(
            mock_message,
            ConnectionError("Network timeout"),
            error_simulator.simulate_operation,
            AsyncMock()  # commit function
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Should succeed after retries
        assert result == True
        
        # Verify exponential backoff timing (0.1 + 0.2 + 0.4 = 0.7s minimum)
        assert duration >= 0.6, f"Expected delay from backoff, got {duration}s"
        
        # Verify DLQ was not used (successful retry)
        mock_dlq.send_to_dlq.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_poison_message_immediate_dlq(self, mock_message):
        """Test poison messages go immediately to DLQ without retries"""
        mock_dlq = AsyncMock()
        error_handler = ErrorHandler("test_service", mock_dlq)
        
        async def poison_processor():
            raise ValueError("Invalid JSON format")
        
        start_time = datetime.now()
        
        result = await error_handler.handle_processing_error(
            mock_message,
            ValueError("Invalid JSON format"), 
            poison_processor,
            AsyncMock()
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Should be handled immediately without retries
        assert result == True
        assert duration < 0.1, "Poison messages should not be retried"
        
        # Verify sent to DLQ
        mock_dlq.send_to_dlq.assert_called_once()
        
        # Verify DLQ message content
        dlq_call = mock_dlq.send_to_dlq.call_args
        assert dlq_call[0][1].__class__.__name__ == "ValueError"
        assert "poison" in dlq_call[0][2].lower()
    
    @pytest.mark.asyncio 
    async def test_max_retries_exhausted_goes_to_dlq(self, error_simulator, mock_message):
        """Test that exhausted retries send message to DLQ"""
        
        # Setup: Always fail
        error_simulator.set_failure_pattern([True] * 10)
        error_simulator.set_failure_types([ConnectionError("Persistent network failure")])
        
        retry_config = RetryConfig(max_attempts=3, base_delay=0.01)
        mock_dlq = AsyncMock()
        error_handler = ErrorHandler("test_service", mock_dlq, retry_config)
        
        result = await error_handler.handle_processing_error(
            mock_message,
            ConnectionError("Persistent network failure"),
            error_simulator.simulate_operation,
            AsyncMock()
        )
        
        # Should eventually give up and send to DLQ
        assert result == True
        mock_dlq.send_to_dlq.assert_called_once()
        
        # Verify retry exhaustion in DLQ metadata
        dlq_call = mock_dlq.send_to_dlq.call_args
        assert "max_retries_exceeded" in dlq_call[0][2].lower()
    
    @pytest.mark.asyncio
    async def test_authentication_error_special_handling(self, mock_message):
        """Test authentication errors get special handling"""
        mock_dlq = AsyncMock()
        error_handler = ErrorHandler("test_service", mock_dlq)
        
        class AuthenticationError(Exception):
            pass
        
        async def auth_failure():
            raise AuthenticationError("Invalid API credentials")
        
        with patch('core.streaming.error_handling.handle_auth_degradation') as mock_auth_handler:
            mock_auth_handler.return_value = {"degraded": True, "fallback_mode": "mock_data"}
            
            result = await error_handler.handle_processing_error(
                mock_message,
                AuthenticationError("Invalid API credentials"),
                auth_failure,
                AsyncMock()
            )
            
            # Should trigger auth degradation handler
            mock_auth_handler.assert_called_once()
            assert result == True
    
    @pytest.mark.asyncio
    async def test_dlq_message_structure_and_metadata(self, mock_message):
        """Test DLQ message contains proper structure and metadata"""
        mock_producer = AsyncMock()
        dlq_publisher = DLQPublisher(mock_producer, "test_service")
        
        error = ValueError("Test error message")
        
        await dlq_publisher.send_to_dlq(
            mock_message, 
            error, 
            "Integration test failure",
            error_type=ErrorType.POISON,
            retry_count=0
        )
        
        # Verify producer was called with correct structure
        mock_producer.send.assert_called_once()
        call_args = mock_producer.send.call_args
        
        dlq_topic = call_args.kwargs["topic"]
        dlq_message = call_args.kwargs["value"]
        
        # Verify DLQ topic naming
        assert dlq_topic == "test.topic.dlq"
        
        # Verify DLQ message structure
        assert "dlq_metadata" in dlq_message
        assert "failure_info" in dlq_message
        assert "original_message" in dlq_message
        assert "replay_metadata" in dlq_message
        
        # Verify metadata content
        dlq_meta = dlq_message["dlq_metadata"]
        assert dlq_meta["original_topic"] == "test.topic"
        assert dlq_meta["service_name"] == "test_service"
        
        failure_info = dlq_message["failure_info"]
        assert failure_info["error_type"] == "poison"
        assert failure_info["error_class"] == "ValueError"
        assert failure_info["retry_count"] == 0
        
        replay_meta = dlq_message["replay_metadata"]
        assert replay_meta["can_replay"] == False  # Poison messages can't be replayed
        assert replay_meta["requires_manual_review"] == True
    
    @pytest.mark.asyncio
    async def test_error_classification_accuracy(self):
        """Test error classification for different error types"""
        classifier = ErrorClassifier()
        
        # Test transient errors
        transient_errors = [
            ConnectionError("Network unreachable"),
            TimeoutError("Request timeout"),
            Exception("KafkaTimeoutError: Timeout waiting for response")
        ]
        
        for error in transient_errors:
            error_type = classifier.classify_error(error)
            assert error_type in [ErrorType.TRANSIENT, ErrorType.BUSINESS], f"Failed for {error}"
        
        # Test poison message errors
        poison_errors = [
            ValueError("Invalid value format"),
            KeyError("Required field missing"),
            TypeError("Expected int, got str"),
            Exception("JSONDecodeError: Invalid JSON")
        ]
        
        for error in poison_errors:
            error_type = classifier.classify_error(error)
            assert error_type in [ErrorType.POISON, ErrorType.BUSINESS], f"Failed for {error}"
    
    @pytest.mark.asyncio
    async def test_concurrent_error_handling(self, mock_message):
        """Test error handler under concurrent load"""
        mock_dlq = AsyncMock()
        error_handler = ErrorHandler("test_service", mock_dlq)
        
        async def failing_operation():
            await asyncio.sleep(0.01)  # Simulate work
            raise ConnectionError("Concurrent failure")
        
        # Run 10 concurrent error handling operations
        tasks = []
        for i in range(10):
            task = error_handler.handle_processing_error(
                mock_message,
                ConnectionError(f"Concurrent failure {i}"),
                failing_operation,
                AsyncMock()
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        
        # All should be handled
        assert all(results)
        
        # Verify stats tracking works under concurrency
        stats = error_handler.get_error_stats()
        assert stats["total_errors"] >= 10


class TestDLQReplaySystem:
    """Test Dead Letter Queue replay system"""
    
    @pytest.mark.asyncio
    async def test_dlq_replay_tool(self):
        """Test DLQ replay functionality"""
        # This would test a DLQ replay tool that processes failed messages
        # Implementation would depend on specific replay requirements
        pass
    
    @pytest.mark.asyncio
    async def test_dlq_monitoring_and_alerting(self):
        """Test DLQ monitoring triggers appropriate alerts"""
        # Test monitoring system that alerts when DLQ accumulates messages
        pass
```

#### 2. Chaos Engineering Tests

```python
# tests/integration/test_chaos_engineering.py

import pytest
import asyncio
import random
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta


@pytest.mark.chaos
class TestChaosEngineering:
    """Chaos engineering tests for system resilience"""
    
    @pytest.mark.asyncio
    async def test_random_service_failures(self, services, test_environment):
        """Test system resilience with random service failures"""
        
        # Start all services
        for service in services.values():
            await service.start()
        
        chaos_duration = 30  # 30 seconds of chaos
        failure_probability = 0.1  # 10% chance of failure per operation
        
        async def chaos_monkey():
            """Randomly inject failures into services"""
            while True:
                await asyncio.sleep(random.uniform(0.1, 1.0))
                
                if random.random() < failure_probability:
                    # Randomly pick a service to fail
                    service_name = random.choice(list(services.keys()))
                    service = services[service_name]
                    
                    # Inject random failure
                    with patch.object(service, '_handle_message', side_effect=Exception("Chaos failure")):
                        await asyncio.sleep(random.uniform(0.1, 0.5))
        
        # Run chaos monkey for specified duration
        chaos_task = asyncio.create_task(chaos_monkey())
        
        # Generate continuous market data during chaos
        for i in range(100):
            tick = test_environment.market_data_generator.generate_tick(738561)
            await test_environment.redpanda.publish_message(
                "market.ticks", str(tick.instrument_token), {"type": "MARKET_TICK", "data": tick.dict()}
            )
            await asyncio.sleep(0.1)
        
        chaos_task.cancel()
        
        # Verify system continued to function despite failures
        # (This would check that some signals were still generated, orders placed, etc.)
        messages = await test_environment.redpanda.consume_messages("paper.signals.raw", "test")
        assert len(messages) > 0, "System should continue functioning during chaos"
    
    @pytest.mark.asyncio
    async def test_infrastructure_outage_simulation(self, services):
        """Test system behavior during infrastructure outages"""
        
        # Simulate database outage
        with patch('core.database.connection.DatabaseManager.get_session', 
                  side_effect=Exception("Database connection failed")):
            
            # System should gracefully degrade
            strategy_runner = services['strategy_runner']
            
            # Should handle database failures gracefully
            with pytest.raises(Exception):
                await strategy_runner._load_strategies()
        
        # Simulate Redis outage  
        with patch('redis.asyncio.from_url', side_effect=Exception("Redis unavailable")):
            portfolio_manager = services['portfolio_manager']
            
            # Should continue functioning without cache
            # (Implementation would depend on graceful degradation strategy)
            pass
    
    @pytest.mark.asyncio
    async def test_kafka_partition_rebalancing(self, services, test_environment):
        """Test system behavior during Kafka partition rebalancing"""
        
        # Simulate partition rebalancing by temporarily disconnecting consumers
        for service_name, service in services.items():
            original_consumer = service.consumer
            
            # Temporarily replace consumer with failing one
            failing_consumer = AsyncMock()
            failing_consumer.consume.side_effect = Exception("Rebalancing in progress")
            service.consumer = failing_consumer
            
            await asyncio.sleep(0.5)  # Brief outage
            
            # Restore consumer
            service.consumer = original_consumer
        
        # Verify system recovers after rebalancing
        # Would check that message processing resumes normally
```

## End-to-End Pipeline Testing

### Infrastructure Requirements

End-to-end testing requires real infrastructure to validate the complete system behavior under realistic conditions.

### Docker Compose Test Environment

```yaml
# docker-compose.test.yml

version: '3.8'
services:
  redpanda-test:
    image: docker.redpanda.com/vectorized/redpanda:latest
    container_name: redpanda-test
    command:
      - redpanda
      - start
      - --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:19092
      - --advertise-kafka-addr internal://redpanda-test:9092,external://localhost:19092
      - --pandaproxy-addr internal://0.0.0.0:8082,external://0.0.0.0:18082
      - --advertise-pandaproxy-addr internal://redpanda-test:8082,external://localhost:18082
      - --schema-registry-addr internal://0.0.0.0:8081,external://0.0.0.0:18081
      - --rpc-addr redpanda-test:33145
      - --advertise-rpc-addr redpanda-test:33145
      - --smp 1
      - --memory 1G
      - --mode dev-container
      - --default-log-level=info
    ports:
      - "19092:19092"
      - "18081:18081" 
      - "18082:18082"
    healthcheck:
      test: ["CMD-SHELL", "rpk cluster info"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres-test:
    image: postgres:15-alpine
    container_name: postgres-test
    environment:
      POSTGRES_USER: alpha_panda_test
      POSTGRES_PASSWORD: test_password
      POSTGRES_DB: alpha_panda_test
    ports:
      - "5433:5432"
    volumes:
      - postgres_test_data:/var/lib/postgresql/data
      - ./scripts/init_test_db.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U alpha_panda_test"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis-test:
    image: redis:7-alpine
    container_name: redis-test
    ports:
      - "6380:6379"
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  alpha-panda-test:
    build:
      context: .
      dockerfile: Dockerfile.test
    container_name: alpha-panda-test
    depends_on:
      redpanda-test:
        condition: service_healthy
      postgres-test:
        condition: service_healthy
      redis-test:
        condition: service_healthy
    environment:
      - ENVIRONMENT=testing
      - DATABASE__POSTGRES_URL=postgresql+asyncpg://alpha_panda_test:test_password@postgres-test:5432/alpha_panda_test
      - REDPANDA__BOOTSTRAP_SERVERS=redpanda-test:9092
      - REDIS__URL=redis://redis-test:6379/0
      - ZERODHA__ENABLED=false  # Disable for testing
      - PAPER_TRADING__ENABLED=true
    volumes:
      - ./tests/e2e:/app/tests/e2e
      - ./logs:/app/logs
    command: ["python", "-m", "pytest", "tests/e2e/", "-v"]

volumes:
  postgres_test_data:
```

### E2E Test Implementation

```python
# tests/e2e/test_complete_pipeline.py

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict

import psycopg2
import redis
from kafka import KafkaProducer, KafkaConsumer


@pytest.mark.e2e
class TestCompletePipeline:
    """End-to-end pipeline tests with real infrastructure"""
    
    @pytest.fixture(scope="session")
    async def infrastructure_health_check(self):
        """Verify all infrastructure services are healthy"""
        
        # Check Redpanda
        try:
            producer = KafkaProducer(
                bootstrap_servers=['localhost:19092'],
                value_serializer=lambda x: json.dumps(x).encode('utf-8')
            )
            producer.close()
        except Exception as e:
            pytest.skip(f"Redpanda not available: {e}")
        
        # Check PostgreSQL
        try:
            conn = psycopg2.connect(
                host="localhost",
                port=5433,
                database="alpha_panda_test", 
                user="alpha_panda_test",
                password="test_password"
            )
            conn.close()
        except Exception as e:
            pytest.skip(f"PostgreSQL not available: {e}")
        
        # Check Redis
        try:
            r = redis.Redis(host='localhost', port=6380, db=0)
            r.ping()
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")
    
    @pytest.fixture
    async def kafka_producer(self):
        """Create Kafka producer for test data"""
        producer = KafkaProducer(
            bootstrap_servers=['localhost:19092'],
            key_serializer=str.encode,
            value_serializer=lambda x: json.dumps(x, default=str).encode('utf-8'),
            acks='all'
        )
        yield producer
        producer.close()
    
    @pytest.fixture
    async def kafka_consumer(self):
        """Create Kafka consumer for verification"""
        consumer = KafkaConsumer(
            bootstrap_servers=['localhost:19092'],
            auto_offset_reset='earliest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='test_consumer_' + str(datetime.now().timestamp())
        )
        yield consumer
        consumer.close()
    
    @pytest.mark.asyncio
    async def test_full_trading_pipeline_paper_mode(
        self, infrastructure_health_check, kafka_producer, kafka_consumer
    ):
        """Test complete trading pipeline from tick to portfolio update"""
        
        # Subscribe to output topics
        kafka_consumer.subscribe([
            'paper.signals.raw',
            'paper.signals.validated', 
            'paper.orders.filled'
        ])
        
        # Generate market data that should trigger momentum strategy
        instrument_token = 738561
        base_price = 2500.00
        
        # Generate upward trending ticks (should trigger BUY signal)
        ticks = []
        for i in range(25):
            price = base_price * (1 + (i * 0.001))  # 0.1% increase per tick
            tick = {
                "type": "market_tick",
                "data": {
                    "instrument_token": instrument_token,
                    "last_price": price,
                    "volume": 1000 + (i * 10),
                    "timestamp": datetime.now().isoformat(),
                    "ohlc": {
                        "open": price * 0.998,
                        "high": price * 1.002,
                        "low": price * 0.997,
                        "close": price
                    }
                }
            }
            ticks.append(tick)
        
        # Publish market ticks
        for tick in ticks:
            kafka_producer.send(
                'market.ticks',
                key=str(instrument_token),
                value=tick
            )
            await asyncio.sleep(0.1)  # 100ms between ticks
        
        kafka_producer.flush()
        
        # Collect pipeline events
        signals_raw = []
        signals_validated = []
        orders_filled = []
        
        # Wait for and collect events (timeout after 30 seconds)
        timeout = datetime.now() + timedelta(seconds=30)
        
        while datetime.now() < timeout:
            message_batch = kafka_consumer.poll(timeout_ms=1000)
            
            for topic_partition, messages in message_batch.items():
                topic = topic_partition.topic
                
                for message in messages:
                    if topic == 'paper.signals.raw':
                        signals_raw.append(message.value)
                    elif topic == 'paper.signals.validated':
                        signals_validated.append(message.value)
                    elif topic == 'paper.orders.filled':
                        orders_filled.append(message.value)
            
            # Break if we've collected expected events
            if signals_raw and signals_validated and orders_filled:
                break
        
        # Verify pipeline execution
        assert len(signals_raw) > 0, "Should generate raw trading signals"
        assert len(signals_validated) > 0, "Should validate trading signals"
        assert len(orders_filled) > 0, "Should fill orders"
        
        # Verify signal progression
        raw_signal = signals_raw[0]["data"]
        validated_signal = signals_validated[0]["data"]
        filled_order = orders_filled[0]["data"]
        
        # Check signal consistency
        assert raw_signal["strategy_id"] == "momentum_test_1"
        assert raw_signal["signal_type"] == "BUY"  # Upward trend should trigger BUY
        assert raw_signal["instrument_token"] == instrument_token
        
        # Check validation preserves core data
        assert validated_signal["original_signal"]["strategy_id"] == raw_signal["strategy_id"]
        
        # Check order execution
        assert filled_order["strategy_id"] == raw_signal["strategy_id"]
        assert filled_order["execution_mode"] == "paper"
        assert filled_order["fill_price"] > 0
        
        # Verify portfolio updates in Redis
        r = redis.Redis(host='localhost', port=6380, db=0)
        portfolio_key = f"paper:portfolio:{raw_signal['strategy_id']}"
        portfolio_data = r.get(portfolio_key)
        
        assert portfolio_data is not None, "Should update portfolio cache"
        portfolio = json.loads(portfolio_data)
        assert portfolio["total_value"] > 0
    
    @pytest.mark.asyncio
    async def test_dual_broker_complete_isolation(
        self, infrastructure_health_check, kafka_producer, kafka_consumer
    ):
        """Test complete isolation between paper and zerodha brokers"""
        
        # Subscribe to both broker topics
        kafka_consumer.subscribe([
            'paper.signals.raw', 'paper.orders.filled',
            'zerodha.signals.raw', 'zerodha.orders.filled'
        ])
        
        # Generate market tick that should trigger both strategies
        tick = {
            "type": "market_tick",
            "data": {
                "instrument_token": 738561,
                "last_price": 2500.00 * 1.025,  # 2.5% increase
                "volume": 1000,
                "timestamp": datetime.now().isoformat()
            }
        }
        
        kafka_producer.send('market.ticks', key='738561', value=tick)
        kafka_producer.flush()
        
        # Collect events from both brokers
        paper_events = []
        zerodha_events = []
        
        timeout = datetime.now() + timedelta(seconds=20)
        
        while datetime.now() < timeout:
            message_batch = kafka_consumer.poll(timeout_ms=1000)
            
            for topic_partition, messages in message_batch.items():
                topic = topic_partition.topic
                
                for message in messages:
                    if topic.startswith('paper.'):
                        paper_events.append((topic, message.value))
                    elif topic.startswith('zerodha.'):
                        zerodha_events.append((topic, message.value))
            
            if paper_events and zerodha_events:
                break
        
        # Verify both brokers processed the tick
        assert len(paper_events) > 0, "Paper broker should process ticks"
        assert len(zerodha_events) > 0, "Zerodha broker should process ticks"
        
        # Verify complete data isolation
        for topic, event in paper_events:
            assert "paper" in topic
            if "broker" in event:
                assert event["broker"] == "paper"
        
        for topic, event in zerodha_events:
            assert "zerodha" in topic
            if "broker" in event:
                assert event["broker"] == "zerodha"
        
        # Verify Redis isolation
        r = redis.Redis(host='localhost', port=6380, db=0)
        paper_keys = r.keys("paper:*")
        zerodha_keys = r.keys("zerodha:*")
        
        # Should have separate cache namespaces
        assert len(paper_keys) > 0, "Should have paper cache keys"
        assert len(zerodha_keys) > 0, "Should have zerodha cache keys"
        
        # Verify no key overlap
        paper_prefixes = {key.decode().split(':')[0] for key in paper_keys}
        zerodha_prefixes = {key.decode().split(':')[0] for key in zerodha_keys}
        assert paper_prefixes.isdisjoint(zerodha_prefixes), "Cache namespaces should not overlap"
    
    @pytest.mark.asyncio
    async def test_system_recovery_after_restart(
        self, infrastructure_health_check, kafka_producer
    ):
        """Test system recovery and state consistency after restart"""
        
        # This test would:
        # 1. Start the system and generate some trading activity
        # 2. Stop the system (simulate restart)
        # 3. Restart the system
        # 4. Verify state recovery and continued operation
        
        # Generate pre-restart activity
        for i in range(10):
            tick = {
                "type": "market_tick", 
                "data": {
                    "instrument_token": 738561,
                    "last_price": 2500.00 + i,
                    "volume": 1000,
                    "timestamp": datetime.now().isoformat()
                }
            }
            kafka_producer.send('market.ticks', key='738561', value=tick)
        
        kafka_producer.flush()
        await asyncio.sleep(5)  # Allow processing
        
        # Check pre-restart state
        r = redis.Redis(host='localhost', port=6380, db=0)
        pre_restart_keys = r.keys("*")
        
        # Simulate restart (Redis persists, Kafka retains messages)
        # In real test, would restart Alpha Panda container
        
        # Verify post-restart state consistency
        # This would check that:
        # - Consumer offsets are properly managed
        # - No duplicate processing occurs
        # - System continues from correct position
        
        assert len(pre_restart_keys) > 0, "Should have cached state before restart"
    
    @pytest.mark.asyncio 
    async def test_performance_under_load(
        self, infrastructure_health_check, kafka_producer
    ):
        """Test system performance under high message load"""
        
        # Generate high-frequency market data
        instrument_tokens = [738561, 2714625, 256265, 779521]  # Multiple instruments
        messages_per_instrument = 1000
        
        start_time = datetime.now()
        
        # Generate high volume of ticks
        for i in range(messages_per_instrument):
            for token in instrument_tokens:
                tick = {
                    "type": "market_tick",
                    "data": {
                        "instrument_token": token,
                        "last_price": 2500.00 + (i * 0.01),
                        "volume": 1000 + i,
                        "timestamp": datetime.now().isoformat()
                    }
                }
                kafka_producer.send('market.ticks', key=str(token), value=tick)
            
            if i % 100 == 0:  # Batch flush every 100 messages
                kafka_producer.flush()
        
        kafka_producer.flush()
        generation_time = (datetime.now() - start_time).total_seconds()
        
        # Wait for processing to complete
        await asyncio.sleep(30)
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        # Verify performance metrics
        total_messages = messages_per_instrument * len(instrument_tokens)
        throughput = total_messages / processing_time
        
        assert throughput > 100, f"Should process >100 msg/sec, got {throughput:.2f}"
        
        # Verify system didn't lose messages under load
        r = redis.Redis(host='localhost', port=6380, db=0)
        portfolio_keys = r.keys("paper:portfolio:*")
        
        # Should have portfolio updates for strategies that were triggered
        assert len(portfolio_keys) > 0, "Should maintain portfolio updates under load"
```

## Testing Infrastructure Setup

### Automated Test Environment Management

```bash
#!/bin/bash
# scripts/test-infrastructure.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Test environment management
setup_test_environment() {
    echo "🚀 Setting up Alpha Panda test environment..."
    
    # Start test infrastructure
    docker-compose -f docker-compose.test.yml up -d
    
    # Wait for services to be healthy
    echo "⏳ Waiting for services to be ready..."
    docker-compose -f docker-compose.test.yml exec -T redpanda-test \
        rpk cluster info --timeout 30s
    
    docker-compose -f docker-compose.test.yml exec -T postgres-test \
        pg_isready -U alpha_panda_test -t 30
    
    docker-compose -f docker-compose.test.yml exec -T redis-test \
        redis-cli ping
    
    # Bootstrap test topics
    echo "📊 Bootstrapping Kafka topics..."
    python scripts/bootstrap_test_topics.py
    
    # Seed test data
    echo "🌱 Seeding test database..."
    python scripts/seed_test_data.py
    
    echo "✅ Test environment ready!"
}

run_unit_tests() {
    echo "🧪 Running unit tests..."
    python -m pytest tests/unit/ -v --cov=. --cov-report=html
}

run_integration_tests() {
    echo "🔗 Running integration tests..."
    python -m pytest tests/integration/ -v --tb=short
}

run_e2e_tests() {
    echo "🌍 Running end-to-end tests..."
    python -m pytest tests/e2e/ -v --tb=short
}

run_performance_tests() {
    echo "⚡ Running performance tests..."
    python -m pytest tests/performance/ -v -m "not slow"
}

run_all_tests() {
    echo "🎯 Running complete test suite..."
    
    run_unit_tests
    run_integration_tests
    run_e2e_tests
    run_performance_tests
    
    echo "🎉 All tests completed!"
}

cleanup_test_environment() {
    echo "🧹 Cleaning up test environment..."
    docker-compose -f docker-compose.test.yml down -v
    docker system prune -f
    echo "✅ Cleanup completed!"
}

# Command line interface
case "${1:-}" in
    "setup")
        setup_test_environment
        ;;
    "unit")
        run_unit_tests
        ;;
    "integration")
        run_integration_tests
        ;;
    "e2e")
        run_e2e_tests
        ;;
    "performance")
        run_performance_tests
        ;;
    "all")
        setup_test_environment
        run_all_tests
        cleanup_test_environment
        ;;
    "cleanup")
        cleanup_test_environment
        ;;
    *)
        echo "Usage: $0 {setup|unit|integration|e2e|performance|all|cleanup}"
        echo ""
        echo "Commands:"
        echo "  setup       - Set up test infrastructure"
        echo "  unit        - Run unit tests"
        echo "  integration - Run integration tests"
        echo "  e2e         - Run end-to-end tests"
        echo "  performance - Run performance tests"
        echo "  all         - Run complete test suite"
        echo "  cleanup     - Clean up test environment"
        exit 1
        ;;
esac
```

### Continuous Integration Pipeline

```yaml
# .github/workflows/comprehensive-testing.yml

name: Comprehensive Testing Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

env:
  PYTHON_VERSION: "3.13"

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ env.PYTHON_VERSION }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    
    - name: Run unit tests
      run: |
        python -m pytest tests/unit/ -v --cov=. --cov-report=xml --cov-report=html
    
    - name: Upload coverage reports
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests

  integration-tests:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: alpha_panda_test
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: alpha_panda_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ env.PYTHON_VERSION }}
    
    - name: Start Redpanda
      run: |
        docker run -d \
          --name redpanda-test \
          -p 9092:9092 \
          -p 8081:8081 \
          -p 8082:8082 \
          docker.redpanda.com/vectorized/redpanda:latest \
          redpanda start \
          --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:19092 \
          --advertise-kafka-addr internal://redpanda-test:9092,external://localhost:9092 \
          --pandaproxy-addr internal://0.0.0.0:8082,external://0.0.0.0:18082 \
          --advertise-pandaproxy-addr internal://redpanda-test:8082,external://localhost:8082 \
          --schema-registry-addr internal://0.0.0.0:8081,external://0.0.0.0:18081 \
          --rpc-addr redpanda-test:33145 \
          --advertise-rpc-addr redpanda-test:33145 \
          --smp 1 \
          --memory 1G \
          --mode dev-container
    
    - name: Wait for Redpanda
      run: |
        timeout 60 bash -c 'until docker exec redpanda-test rpk cluster info; do sleep 2; done'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    
    - name: Bootstrap test environment
      run: |
        python scripts/bootstrap_topics.py
        python scripts/seed_strategies.py
    
    - name: Run integration tests
      run: |
        python -m pytest tests/integration/ -v --tb=short
      env:
        DATABASE__POSTGRES_URL: postgresql+asyncpg://alpha_panda_test:test_password@localhost:5432/alpha_panda_test
        REDPANDA__BOOTSTRAP_SERVERS: localhost:9092
        REDIS__URL: redis://localhost:6379/0

  e2e-tests:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ env.PYTHON_VERSION }}
    
    - name: Start test infrastructure
      run: |
        docker-compose -f docker-compose.test.yml up -d
    
    - name: Wait for services
      run: |
        timeout 120 bash -c 'until docker-compose -f docker-compose.test.yml exec -T redpanda-test rpk cluster info; do sleep 5; done'
        timeout 120 bash -c 'until docker-compose -f docker-compose.test.yml exec -T postgres-test pg_isready -U alpha_panda_test; do sleep 5; done'
        timeout 120 bash -c 'until docker-compose -f docker-compose.test.yml exec -T redis-test redis-cli ping; do sleep 5; done'
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    
    - name: Run E2E tests
      run: |
        python -m pytest tests/e2e/ -v --tb=short
      env:
        ENVIRONMENT: testing
        DATABASE__POSTGRES_URL: postgresql+asyncpg://alpha_panda_test:test_password@localhost:5433/alpha_panda_test
        REDPANDA__BOOTSTRAP_SERVERS: localhost:19092
        REDIS__URL: redis://localhost:6380/0
    
    - name: Cleanup
      if: always()
      run: |
        docker-compose -f docker-compose.test.yml down -v

  performance-tests:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ env.PYTHON_VERSION }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    
    - name: Run performance tests
      run: |
        python -m pytest tests/performance/ -v -m "not slow"
    
    - name: Generate performance report
      run: |
        python scripts/generate_performance_report.py

  security-scan:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: ${{ env.PYTHON_VERSION }}
    
    - name: Install security tools
      run: |
        python -m pip install --upgrade pip
        pip install bandit safety
    
    - name: Run security scan
      run: |
        bandit -r . -x tests/
        safety check
```

## Performance & Load Testing

### Performance Testing Framework

```python
# tests/performance/test_system_performance.py

import pytest
import asyncio
import time
import statistics
from typing import List, Dict
from datetime import datetime, timedelta

from tests.integration.mocks.service_mocks import IntegrationTestEnvironment


@pytest.mark.performance
class TestSystemPerformance:
    """Performance and load testing for the trading system"""
    
    @pytest.fixture
    async def performance_environment(self):
        """Setup high-performance test environment"""
        env = IntegrationTestEnvironment()
        await env.setup()
        yield env
        await env.teardown()
    
    @pytest.mark.asyncio
    async def test_market_data_throughput(self, performance_environment):
        """Test market data processing throughput"""
        
        messages_to_send = 10000
        instruments = [738561, 2714625, 256265, 779521]
        
        start_time = time.time()
        
        # Send high volume of market ticks
        tasks = []
        for i in range(messages_to_send):
            instrument = instruments[i % len(instruments)]
            tick = performance_environment.market_data_generator.generate_tick(instrument)
            
            task = performance_environment.redpanda.publish_message(
                "market.ticks",
                str(instrument),
                {"type": "MARKET_TICK", "data": tick.dict()}
            )
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        end_time = time.time()
        duration = end_time - start_time
        throughput = messages_to_send / duration
        
        print(f"Market data throughput: {throughput:.2f} msg/sec")
        
        # Performance assertion
        assert throughput > 1000, f"Throughput too low: {throughput:.2f} msg/sec"
    
    @pytest.mark.asyncio
    async def test_end_to_end_latency(self, performance_environment):
        """Test end-to-end message processing latency"""
        
        latencies = []
        num_samples = 1000
        
        for i in range(num_samples):
            start_time = time.perf_counter()
            
            # Send market tick
            tick = performance_environment.market_data_generator.generate_tick(738561, 0.01)
            await performance_environment.redpanda.publish_message(
                "market.ticks",
                "738561", 
                {"type": "MARKET_TICK", "data": tick.dict(), "test_timestamp": start_time}
            )
            
            # Wait for processing (simplified - would monitor actual output)
            await asyncio.sleep(0.001)
            
            end_time = time.perf_counter()
            latency = (end_time - start_time) * 1000  # Convert to milliseconds
            latencies.append(latency)
        
        # Calculate statistics
        avg_latency = statistics.mean(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        p99_latency = statistics.quantiles(latencies, n=100)[98]  # 99th percentile
        
        print(f"Average latency: {avg_latency:.2f}ms")
        print(f"P95 latency: {p95_latency:.2f}ms")
        print(f"P99 latency: {p99_latency:.2f}ms")
        
        # Performance assertions
        assert avg_latency < 10.0, f"Average latency too high: {avg_latency:.2f}ms"
        assert p95_latency < 50.0, f"P95 latency too high: {p95_latency:.2f}ms"
        assert p99_latency < 100.0, f"P99 latency too high: {p99_latency:.2f}ms"
    
    @pytest.mark.asyncio
    async def test_concurrent_strategy_processing(self, performance_environment):
        """Test concurrent processing of multiple strategies"""
        
        # Simulate multiple strategies running concurrently
        strategies = ["momentum_1", "momentum_2", "mean_reversion_1", "mean_reversion_2"]
        instruments = [738561, 2714625, 256265, 779521]
        
        concurrent_tasks = []
        
        for strategy in strategies:
            for instrument in instruments:
                task = self._simulate_strategy_processing(
                    performance_environment, strategy, instrument
                )
                concurrent_tasks.append(task)
        
        start_time = time.time()
        results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
        end_time = time.time()
        
        # Analyze results
        successful = sum(1 for r in results if not isinstance(r, Exception))
        failed = len(results) - successful
        duration = end_time - start_time
        
        print(f"Concurrent processing: {successful}/{len(results)} successful in {duration:.2f}s")
        
        # Performance assertions
        assert failed == 0, f"{failed} tasks failed"
        assert duration < 5.0, f"Processing took too long: {duration:.2f}s"
    
    async def _simulate_strategy_processing(self, env, strategy_id: str, instrument: int):
        """Simulate strategy processing workload"""
        
        # Generate market data sequence
        for i in range(100):
            tick = env.market_data_generator.generate_tick(instrument, 0.001)
            await env.redpanda.publish_message(
                "market.ticks",
                str(instrument),
                {"type": "MARKET_TICK", "data": tick.dict(), "strategy": strategy_id}
            )
            await asyncio.sleep(0.001)  # 1ms between ticks
        
        return {"strategy": strategy_id, "instrument": instrument, "processed": 100}
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_sustained_load_stability(self, performance_environment):
        """Test system stability under sustained load"""
        
        duration_minutes = 5
        target_tps = 500  # Transactions per second
        
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        message_count = 0
        error_count = 0
        
        print(f"Starting {duration_minutes}-minute sustained load test at {target_tps} TPS...")
        
        while datetime.now() < end_time:
            batch_start = time.time()
            
            # Send batch of messages
            tasks = []
            for i in range(target_tps):
                tick = performance_environment.market_data_generator.generate_tick(738561)
                task = performance_environment.redpanda.publish_message(
                    "market.ticks",
                    "738561",
                    {"type": "MARKET_TICK", "data": tick.dict()}
                )
                tasks.append(task)
            
            try:
                await asyncio.gather(*tasks)
                message_count += target_tps
            except Exception as e:
                error_count += 1
                print(f"Batch error: {e}")
            
            # Maintain target TPS
            batch_duration = time.time() - batch_start
            sleep_time = max(0, 1.0 - batch_duration)
            await asyncio.sleep(sleep_time)
            
            # Progress update every minute
            elapsed = (datetime.now() - start_time).total_seconds()
            if int(elapsed) % 60 == 0 and elapsed > 0:
                current_tps = message_count / elapsed
                print(f"Progress: {elapsed/60:.1f}min, {current_tps:.1f} TPS, {error_count} errors")
        
        # Final statistics
        total_duration = (datetime.now() - start_time).total_seconds()
        actual_tps = message_count / total_duration
        error_rate = error_count / (message_count / target_tps) * 100
        
        print(f"Load test completed:")
        print(f"  Duration: {total_duration:.1f}s")
        print(f"  Messages: {message_count}")
        print(f"  Actual TPS: {actual_tps:.1f}")
        print(f"  Error rate: {error_rate:.2f}%")
        
        # Stability assertions
        assert actual_tps >= target_tps * 0.95, f"TPS too low: {actual_tps:.1f} < {target_tps * 0.95}"
        assert error_rate < 1.0, f"Error rate too high: {error_rate:.2f}%"
    
    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, performance_environment):
        """Test memory usage remains stable under load"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Generate sustained load
        for batch in range(10):
            tasks = []
            for i in range(1000):
                tick = performance_environment.market_data_generator.generate_tick(738561)
                task = performance_environment.redpanda.publish_message(
                    "market.ticks",
                    "738561",
                    {"type": "MARKET_TICK", "data": tick.dict()}
                )
                tasks.append(task)
            
            await asyncio.gather(*tasks)
            
            # Check memory usage
            current_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = current_memory - initial_memory
            
            print(f"Batch {batch + 1}: Memory usage: {current_memory:.1f}MB (+{memory_increase:.1f}MB)")
            
            # Allow garbage collection
            await asyncio.sleep(0.1)
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        total_increase = final_memory - initial_memory
        
        # Memory stability assertion
        assert total_increase < 100, f"Memory leak suspected: {total_increase:.1f}MB increase"
```

## Testing Best Practices

### Testing Standards & Guidelines

1. **Test Isolation**: Each test should be independent and not affect others
2. **Test Data Management**: Use fixtures and factories for consistent test data
3. **Error Simulation**: Test both happy paths and error conditions
4. **Performance Baselines**: Establish and maintain performance benchmarks
5. **Documentation**: Document test scenarios and expected outcomes

### Test Organization

```
tests/
├── unit/                   # Fast, isolated tests
│   ├── test_events.py
│   ├── test_strategies.py
│   └── test_error_handling.py
├── integration/            # Service interaction tests
│   ├── mocks/
│   └── test_service_flow.py
├── e2e/                    # Full pipeline tests
│   └── test_complete_pipeline.py
├── performance/            # Load and performance tests
│   └── test_system_performance.py
├── chaos/                  # Chaos engineering tests
│   └── test_resilience.py
└── fixtures/               # Shared test data and utilities
```

### Continuous Monitoring

- **Test Execution Time**: Monitor and optimize slow tests
- **Flaky Test Detection**: Identify and fix unreliable tests  
- **Coverage Tracking**: Maintain >90% code coverage
- **Performance Regression**: Alert on performance degradation

This comprehensive testing guide provides the framework for thorough validation of the Alpha Panda trading system across all levels, from unit tests to full end-to-end pipeline testing with real infrastructure.