# Infrastructure Integration Testing Policy

## Overview

This document establishes a new testing policy designed to catch runtime infrastructure issues that traditional unit/integration tests miss. Based on analysis of critical production failures (bytes/string type errors, missing enum values, undefined method calls), we need tests that verify actual infrastructure integration rather than just business logic.

## Critical Testing Gaps Identified

### 1. Over-Mocking Syndrome
**Problem**: Tests mock infrastructure completely, missing type conversion issues
```python
# ❌ CURRENT: Complete mocking misses real Redis behavior
mock_cache.get = lambda key: {"clean": "python_dict"}

# ✅ NEW: Use real infrastructure components
@pytest.fixture
async def real_redis_client():
    container = await start_redis_container()
    return redis.from_url(container.url, decode_responses=False)  # Test both modes
```

### 2. Missing Contract Validation
**Problem**: Tests don't verify that called methods actually exist on target classes
```python
# ❌ CURRENT: No verification that increment_count() exists
service.metrics_collector.increment_count("signals", "paper")  # Runtime AttributeError

# ✅ NEW: Contract validation tests
def test_metrics_collector_interface_compliance():
    """Verify all methods called by services actually exist"""
    collector = PipelineMetricsCollector(redis_client, settings)
    assert hasattr(collector, 'increment_count')
    assert callable(getattr(collector, 'increment_count'))
```

### 3. Enum/Schema Completeness Gaps
**Problem**: Tests don't verify enum values used in error handling exist
```python
# ❌ CURRENT: No validation of EventType completeness
event_type=EventType.SYSTEM_ERROR  # Runtime AttributeError

# ✅ NEW: Schema completeness tests
def test_event_type_enum_completeness():
    """Verify all EventType values referenced in code exist"""
    # Scan codebase for EventType.XXX usage
    # Verify each XXX exists in enum
```

## New Testing Architecture

### Layer 1: Infrastructure Contract Tests
**Purpose**: Verify service interfaces match actual implementations

```python
class TestServiceContracts:
    """Test that service method calls match actual implementations"""
    
    def test_risk_manager_state_interface(self):
        """Verify RiskManagerState methods called by service exist"""
        state_manager = RiskStateManager(settings, redis_client)
        
        # Verify all methods called by RiskManagerService exist
        assert hasattr(state_manager, 'get_state')
        assert hasattr(state_manager, 'update_position')
        
        # Verify method signatures match usage
        import inspect
        sig = inspect.signature(state_manager.get_state)
        assert len(sig.parameters) == 0  # Called with no params
    
    def test_metrics_collector_interface(self):
        """Verify PipelineMetricsCollector methods exist"""
        collector = PipelineMetricsCollector(redis_client, settings)
        
        # Methods called by StrategyRunnerService
        assert hasattr(collector, 'increment_count')
        assert hasattr(collector, 'set_last_activity_timestamp')
        
        # Verify signatures
        sig = inspect.signature(collector.increment_count)
        params = list(sig.parameters.keys())
        assert 'metric_name' in params
        assert 'broker' in params
```

### Layer 2: Real Infrastructure Integration Tests
**Purpose**: Test with actual Redis, Kafka, database connections

```python
@pytest.fixture(scope="session")
async def infrastructure_stack():
    """Start real infrastructure components for testing"""
    containers = {
        'redis': await start_redis_container(),
        'kafka': await start_kafka_container(), 
        'postgres': await start_postgres_container()
    }
    yield containers
    await cleanup_containers(containers)

class TestRealInfrastructure:
    """Test services with real infrastructure components"""
    
    @pytest.mark.asyncio
    async def test_redis_key_type_handling(self, infrastructure_stack):
        """Test Redis bytes vs string handling"""
        redis_client = redis.from_url(
            infrastructure_stack['redis'].url, 
            decode_responses=False  # Force bytes mode
        )
        
        state_manager = RiskStateManager(settings, redis_client)
        await state_manager.initialize("test_broker")
        
        # Set up test data that will return bytes keys
        await redis_client.set("test_broker:risk:counter:daily_trades_strategy_1", "5")
        
        # This should NOT fail with TypeError
        result = await state_manager.get_state()
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio 
    async def test_kafka_message_serialization(self, infrastructure_stack):
        """Test actual Kafka message serialization/deserialization"""
        producer = AIOKafkaProducer(
            bootstrap_servers=infrastructure_stack['kafka'].url,
            value_serializer=lambda v: json.dumps(v).encode()
        )
        
        consumer = AIOKafkaConsumer(
            'test_topic',
            bootstrap_servers=infrastructure_stack['kafka'].url,
            value_deserializer=lambda m: json.loads(m.decode())
        )
        
        await producer.start()
        await consumer.start()
        
        # Test EventEnvelope serialization
        envelope = EventEnvelope(
            type=EventType.TRADING_SIGNAL,
            data={"test": "data"},
            source="test_service",
            key="test_key",
            broker="paper",
            correlation_id="test_correlation"
        )
        
        # This should serialize/deserialize without errors
        await producer.send('test_topic', envelope.model_dump())
        message = await anext(consumer)
        
        # Verify round-trip integrity
        assert message.value['type'] == 'trading_signal'
        
        await producer.stop()
        await consumer.stop()
```

### Layer 3: Schema and Enum Validation Tests
**Purpose**: Verify all referenced enums/schemas are complete

```python
import ast
import os
from pathlib import Path

class TestSchemaCompleteness:
    """Validate schema and enum completeness across codebase"""
    
    def test_event_type_enum_completeness(self):
        """Verify all EventType references exist in enum"""
        # Scan codebase for EventType.XXX patterns
        event_types_used = self._find_event_type_usage()
        
        # Get actual enum values
        actual_values = set(EventType.__members__.keys())
        
        # Verify all used values exist
        missing = event_types_used - actual_values
        assert not missing, f"Missing EventType values: {missing}"
    
    def test_signal_type_enum_completeness(self):
        """Verify all SignalType references exist"""
        signal_types_used = self._find_signal_type_usage()
        actual_values = set(SignalType.__members__.keys())
        
        missing = signal_types_used - actual_values
        assert not missing, f"Missing SignalType values: {missing}"
    
    def _find_event_type_usage(self) -> set:
        """Scan codebase for EventType.XXX usage patterns"""
        project_root = Path(__file__).parent.parent.parent
        event_types = set()
        
        for py_file in project_root.rglob("*.py"):
            if "test" in str(py_file):
                continue
                
            try:
                with open(py_file) as f:
                    tree = ast.parse(f.read())
                
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Attribute) and 
                        isinstance(node.value, ast.Name) and 
                        node.value.id == "EventType"):
                        event_types.add(node.attr)
            except:
                continue  # Skip files that can't be parsed
        
        return event_types
```

### Layer 4: Error Path Integration Tests
**Purpose**: Test error scenarios that trigger DLQ and error handling

```python
class TestErrorPathIntegration:
    """Test error scenarios and recovery mechanisms"""
    
    @pytest.mark.asyncio
    async def test_dlq_error_handling(self, infrastructure_stack):
        """Test Dead Letter Queue error handling uses correct EventType"""
        # Set up service that will trigger DLQ
        service = RiskManagerService(settings, database, redis_client)
        
        # Create poison message that will cause processing error
        poison_signal = EventEnvelope(
            type=EventType.TRADING_SIGNAL,
            data={"invalid": "signal_data"},  # Missing required fields
            source="test_service", 
            key="poison_key",
            broker="paper",
            correlation_id="test_correlation"
        )
        
        # Process should fail and send to DLQ
        with patch('core.streaming.error_handling.send_to_dlq') as mock_dlq:
            await service._handle_message(poison_signal.model_dump(), "paper.signals.raw")
            
            # Verify DLQ was called with valid EventType
            mock_dlq.assert_called_once()
            call_args = mock_dlq.call_args
            assert call_args[1]['event_type'] == EventType.SYSTEM_ERROR
    
    @pytest.mark.asyncio
    async def test_redis_connection_failure_recovery(self, infrastructure_stack):
        """Test Redis connection failure and recovery"""
        redis_client = redis.from_url(infrastructure_stack['redis'].url)
        state_manager = RiskStateManager(settings, redis_client)
        
        # Simulate Redis connection failure
        await infrastructure_stack['redis'].stop()
        
        # Operations should fail gracefully, not crash
        try:
            result = await state_manager.get_state()
            assert result == {}  # Default empty state on error
        except Exception as e:
            assert isinstance(e, RedisError)  # Should be wrapped properly
        
        # Recovery after Redis comes back
        await infrastructure_stack['redis'].start()
        result = await state_manager.get_state()
        assert isinstance(result, dict)
```

## Implementation Strategy

### Phase 1: Critical Infrastructure Tests (Week 1)
1. **Contract Validation Tests**: Verify all service method calls exist
2. **Real Redis Integration**: Test bytes/string handling with actual Redis
3. **Schema Completeness**: Validate all EventType/SignalType references exist

### Phase 2: Error Path Coverage (Week 2)  
1. **DLQ Testing**: Test all error scenarios that use Dead Letter Queue
2. **Connection Failure**: Test database/Redis/Kafka connection failures
3. **Message Serialization**: Test with real Kafka serialization/deserialization

### Phase 3: Performance Integration (Week 3)
1. **Load Testing**: Test infrastructure under realistic load
2. **Memory Leak Detection**: Long-running tests with real connections
3. **Concurrent Access**: Test Redis/database concurrent access patterns

## Test Configuration

### Docker Test Infrastructure
```yaml
# docker-compose.test-infrastructure.yml
version: '3.8'
services:
  test-redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    command: redis-server --appendonly yes
    
  test-kafka:
    image: confluentinc/cp-kafka:7.4.0
    ports:
      - "19092:19092"
    environment:
      KAFKA_ZOOKEEPER_CONNECT: test-zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:19092
      
  test-postgres:
    image: postgres:15-alpine
    ports:
      - "5433:5432"
    environment:
      POSTGRES_DB: alpha_panda_test
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
```

### Test Execution Commands
```bash
# Run infrastructure integration tests
make test-infrastructure

# Run contract validation tests  
make test-contracts

# Run schema completeness tests
make test-schemas

# Run all new testing layers
make test-complete
```

## Continuous Integration Integration

### Pre-commit Hooks
```bash
#!/bin/bash
# .git/hooks/pre-commit
echo "Running contract validation tests..."
python -m pytest tests/contracts/ -v

echo "Running schema completeness tests..."
python -m pytest tests/schemas/ -v

if [ $? -ne 0 ]; then
  echo "❌ Infrastructure tests failed - commit blocked"
  exit 1
fi
```

### CI Pipeline Updates
```yaml
# .github/workflows/test.yml
- name: Run Infrastructure Integration Tests
  run: |
    docker compose -f docker-compose.test-infrastructure.yml up -d
    sleep 10  # Wait for services to start
    python -m pytest tests/infrastructure/ -v --tb=short
    docker compose -f docker-compose.test-infrastructure.yml down
```

## Monitoring and Maintenance

### Test Health Metrics
- **Infrastructure test pass rate**: Should be >95%
- **Contract validation coverage**: All service method calls verified
- **Schema completeness**: 100% enum usage validated
- **Error path coverage**: All DLQ scenarios tested

### Regular Maintenance
- **Weekly**: Review failed infrastructure tests
- **Monthly**: Update test containers to match production versions
- **Quarterly**: Review and expand error path test coverage

## Success Metrics

### Immediate Goals (30 days)
- ✅ Zero `AttributeError` exceptions in production
- ✅ Zero `TypeError` exceptions from type conversion
- ✅ 100% enum completeness validation
- ✅ All service method calls verified to exist

### Long-term Goals (90 days)  
- ✅ 95%+ infrastructure test pass rate
- ✅ All critical error paths tested
- ✅ Real infrastructure integration in CI/CD
- ✅ Proactive detection of integration issues

This testing policy shift moves from "business logic correctness" to "infrastructure integration reliability" - catching the runtime issues that pure unit tests miss.