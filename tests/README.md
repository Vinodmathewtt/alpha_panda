# Alpha Panda Testing Framework

**Status**: ✅ **PRODUCTION-READY TESTING** | 🚀 **Real Infrastructure Integration** | ⚡ **Zero Mock Philosophy**

## Testing Philosophy and Policies

**🎯 CORE PRINCIPLE**: Real infrastructure testing to catch production issues that mocks cannot detect.

### Critical Testing Policies

#### 1. **MANDATORY: Real Infrastructure First**
- **Primary Rule**: Use actual Redis, Kafka, PostgreSQL for all integration tests
- **Mock Usage**: ONLY for external APIs requiring credentials (Zerodha WebSocket during development)
- **Rationale**: Mocks hide critical type conversion, serialization, and connection issues
- **Implementation**: All services must be tested against real infrastructure components

#### 2. **MANDATORY: Fail-Fast Validation**
- **Zero Silent Failures**: Every error must be logged, alerted, or raise an exception
- **Immediate Failure**: System must fail fast when critical dependencies are missing
- **Observable Errors**: All failures must be detectable via logs, metrics, or exceptions
- **No Fallback Data**: Never use hardcoded fallbacks for production data in tests

#### 3. **MANDATORY: Production-Like Test Environment**
- **Infrastructure Isolation**: Test infrastructure on separate ports (Redis 6380, Kafka 19092, PostgreSQL 5433)
- **Real Data Flows**: Events must flow through actual Kafka topics with real serialization
- **Authentic Conditions**: Test with real market data, actual Zerodha API responses, genuine error scenarios
- **State Persistence**: Use real databases for configuration, real Redis for caching

#### 4. **MANDATORY: Comprehensive Error Path Testing**
- **DLQ Scenarios**: Test Dead Letter Queue with actual Kafka topics
- **Connection Failures**: Test Redis/Kafka/PostgreSQL connection loss and recovery
- **Resource Exhaustion**: Test memory limits, connection pool exhaustion
- **Data Corruption**: Test malformed messages, serialization failures

#### 5. **MANDATORY: Service Interface Validation**
- **Method Existence**: Validate all service method calls exist before runtime
- **Signature Compliance**: Verify method parameters match usage patterns
- **Protocol Implementation**: Test that services implement required interfaces
- **Type Safety**: Validate all type hints match actual function calls

## New Testing Architecture

### 3-Layer Testing Strategy

#### Layer 1: Unit Tests (Core Component Validation)
**Purpose**: Test individual components with real infrastructure
- **Event Schema Validation**: EventEnvelope, OrderFilled, MarketData schemas
- **Stream Processing Patterns**: Kafka producer/consumer with real serialization
- **Service Interface Validation**: Method existence, signature compliance
- **Redis Type Handling**: Both decode_responses=True/False modes

#### Layer 2: Integration Tests (Service Interaction Validation) 
**Purpose**: Test service interactions with real infrastructure
- **Multi-Broker Topic Routing**: Real Kafka topics with broker namespacing
- **Cache Isolation**: Redis key prefixing across brokers
- **Database Transactions**: Real PostgreSQL with ACID compliance
- **End-to-End Message Flow**: Events through complete infrastructure stack

#### Layer 3: End-to-End Tests (Complete Pipeline Validation)
**Purpose**: Test complete trading pipeline with real market data
- **Zerodha Authentication**: Real API key/secret authentication
- **Market Data Integration**: Live market feed through WebSocket
- **Trading Pipeline**: Complete flow from market data to portfolio updates
- **Safety Validation**: Paper trading enforcement, risk management

## Test Infrastructure Requirements

### Required Infrastructure Components

| **Component** | **Test Port** | **Purpose** | **Docker Image** |
|---------------|---------------|-------------|------------------|
| Redis | 6380 | Cache testing, type conversion validation | `redis:7-alpine` |
| Kafka | 19092 | Message streaming, serialization testing | `confluentinc/cp-kafka:7.4.0` |
| Zookeeper | 2181 | Kafka coordination | `confluentinc/cp-zookeeper:7.4.0` |
| PostgreSQL | 5433 | Database integration, transaction testing | `postgres:15-alpine` |

### Infrastructure Setup Commands

```bash
# Start test infrastructure
docker compose -f docker-compose.test.yml up -d

# Verify infrastructure health
docker compose -f docker-compose.test.yml ps

# Check service logs
docker compose -f docker-compose.test.yml logs

# Stop and cleanup
docker compose -f docker-compose.test.yml down -v
```

### Infrastructure Health Validation

```bash
# Quick health check
python -c "
import asyncio
from tests.fixtures.infrastructure_fixtures import InfrastructureHealthChecker

async def main():
    health = await InfrastructureHealthChecker.check_all_services()
    print('Infrastructure Health:', health)
    
asyncio.run(main())
"
```

## Test Execution Strategy

### Development Testing Commands

```bash
# 1. Unit Tests - Core component validation
python -m pytest tests/unit/ -v --tb=short

# 2. Integration Tests - Service interaction validation  
python -m pytest tests/integration/ -v --tb=short

# 3. End-to-End Tests - Complete pipeline validation
# ⚠️  REQUIRES: ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_ACCESS_TOKEN
python -m pytest tests/e2e/ -v -s --tb=short

# 4. Complete Test Suite
python -m pytest tests/ -v --tb=short

# 5. Fast Critical Path Tests (< 30 seconds)
python -m pytest tests/unit/test_event_envelope_validation.py tests/unit/test_service_interfaces.py -v
```

### Production Validation Commands

```bash
# Critical issue prevention (run before deployment)
python -m pytest tests/unit/test_event_envelope_validation.py::TestEventTypeEnumCompleteness -v
python -m pytest tests/unit/test_service_interfaces.py::TestServiceMethodValidation -v
python -m pytest tests/integration/test_real_infrastructure_integration.py::TestRedisIntegrationPatterns -v

# Infrastructure integration validation
python -m pytest tests/integration/ -k "redis or kafka or postgres" -v

# End-to-end safety validation
python -m pytest tests/e2e/test_zerodha_real_trading_pipeline.py::TestRealTradingPipelineValidation::test_end_to_end_pipeline_safety_validation -v
```

## Critical Testing Patterns

### 1. **Event Envelope Validation Pattern**
```python
def test_event_envelope_required_fields(self):
    """Test that EventEnvelope enforces all required fields"""
    envelope = EventEnvelope(
        id=str(uuid4()),
        type=EventType.ORDER_FILLED,
        timestamp=datetime.now(),
        source="trading_engine",
        version="1.0",
        correlation_id=str(uuid4()),
        causation_id=str(uuid4()),
        broker="zerodha",  # MANDATORY for routing
        key="12345",       # MANDATORY for partitioning
        data={"test": "data"}
    )
    assert envelope.broker in ["paper", "zerodha"]
    assert envelope.type == EventType.ORDER_FILLED
```

### 2. **Real Infrastructure Integration Pattern**
```python
@pytest.mark.asyncio
async def test_redis_cache_operations(self, redis_test_client):
    """Test portfolio caching with real Redis client"""
    broker = "zerodha"
    balance_key = f"{broker}:portfolio:balance"
    
    # Test actual Redis operations
    await redis_test_client.set(balance_key, "150000.50")
    balance = await redis_test_client.get(balance_key)
    
    assert balance == "150000.50"
    assert isinstance(balance, str)  # Validates decode_responses=True
```

### 3. **Kafka Message Flow Pattern**
```python
async def test_multi_broker_topic_routing(self, kafka_producer, kafka_consumer):
    """Test broker-specific topic routing with real Kafka"""
    paper_topic = "paper.signals.validated"
    zerodha_topic = "zerodha.signals.validated"
    
    await kafka_consumer.subscribe([paper_topic, zerodha_topic])
    
    # Send to different broker topics
    await kafka_producer.send(topic=paper_topic, value=paper_signal, key=b"12345")
    await kafka_producer.send(topic=zerodha_topic, value=zerodha_signal, key=b"12345")
    
    # Verify routing works correctly
    messages = await consume_messages(kafka_consumer, expected_count=2)
    assert any(msg.topic == paper_topic for msg in messages)
    assert any(msg.topic == zerodha_topic for msg in messages)
```

### 4. **Service Interface Validation Pattern**
```python
def test_service_method_exists(self):
    """Test that called service methods actually exist"""
    assert hasattr(TradingEngineService, 'execute_signal')
    execute_signal = getattr(TradingEngineService, 'execute_signal')
    assert callable(execute_signal)
    assert inspect.iscoroutinefunction(execute_signal)
```

### 5. **Zerodha Real Data Integration Pattern**
```python
async def test_strategy_with_real_market_data(self, kite_client):
    """Test strategy processing with real Zerodha market data"""
    # Get real historical data
    historical_data = kite_client.historical_data(
        instrument_token=12345,
        from_date=start_date,
        to_date=end_date,
        interval='5minute'
    )
    
    # Process with real strategy logic
    prices = [Decimal(str(candle['close'])) for candle in historical_data[-10:]]
    signal = generate_momentum_signal(prices)
    
    # Validate signal with real market conditions
    assert signal.price > 0
    assert isinstance(signal.price, Decimal)
    assert signal.confidence <= 1.0
```

## Safety Enforcement Policies

### 1. **MANDATORY: Paper Trading Enforcement**
- **Default Mode**: All tests run in paper trading mode
- **Live Trading Block**: Tests must validate that live trading is disabled
- **Credential Isolation**: Market data credentials separate from trading credentials
- **Safety Checks**: Multiple validation layers prevent accidental live trading

### 2. **MANDATORY: Infrastructure Isolation**
- **Port Separation**: Test infrastructure on different ports than production
- **Database Isolation**: Test database completely separate from production
- **Network Isolation**: Test containers in isolated Docker networks
- **State Cleanup**: All test data cleaned up after each test run

### 3. **MANDATORY: Error Handling Validation**
- **Exception Propagation**: Test that errors bubble up correctly
- **DLQ Processing**: Test dead letter queue with real poison messages
- **Circuit Breaker**: Test service degradation under failure conditions
- **Recovery Testing**: Test system recovery after infrastructure restarts

## Performance and Monitoring

### Performance Targets
- **Unit Tests**: Complete execution < 60 seconds
- **Integration Tests**: Complete execution < 180 seconds  
- **E2E Tests**: Complete execution < 300 seconds (including infrastructure)
- **Infrastructure Startup**: < 30 seconds to healthy state
- **Test Isolation**: Parallel test execution without interference

### Critical Metrics Monitoring
- **Message Throughput**: >100 messages/second through Kafka
- **Cache Performance**: <5ms Redis operations
- **Database Performance**: <20ms query execution
- **Memory Usage**: <500MB total for test infrastructure
- **Error Recovery**: <5 seconds to recover from infrastructure restart

## Test Environment Setup

### Prerequisites
- Docker and Docker Compose installed
- Python 3.11+ with virtual environment
- Minimum 4GB RAM for test infrastructure
- Ports 6380, 19092, 5433, 2181 available

### Environment Variables (Required for E2E tests)

#### **🔐 Zerodha Authentication Requirements**

**CRITICAL**: End-to-end tests require **real Zerodha credentials** for authentic market data validation.

```bash
export ZERODHA_API_KEY="your_api_key"
export ZERODHA_API_SECRET="your_api_secret"  
export ZERODHA_ACCESS_TOKEN="your_access_token"
```

#### **Authentication Failure Policy**
- **Test Behavior**: If Zerodha authentication fails, tests will **immediately stop** and display clear error message
- **User Responsibility**: It is the **user's responsibility** to provide valid, working Zerodha credentials
- **No Fallbacks**: Tests will **not** fall back to mock data - authentication must work for real market feed testing
- **Clear Error Messages**: Authentication failures will show specific error details to help user resolve issues

#### **Authentication Error Examples**
```bash
# Missing credentials error:
"Zerodha credentials not available - set ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_ACCESS_TOKEN"

# Invalid credentials error:
"Zerodha authentication failed: Invalid access token. Please regenerate your access token."

# API connection error:
"Zerodha API connection failed: Unable to connect to Kite API. Check your internet connection."
```

#### **Safety Enforcement**
- **Paper Trading Mode**: All tests run in **paper trading mode only** for safety
- **No Live Trading**: Tests validate that live trading is **disabled** even with real credentials
- **Market Data Only**: Real credentials used **only** for market data access, not order placement
- **Multiple Validation Layers**: Tests ensure no accidental live trading can occur

#### **Market Hours Behavior**
- **During Market Hours (9:15 AM - 3:30 PM IST)**: Live market data with real-time price changes and volume
- **During Non-Market Hours**: Zerodha provides **closing price feeds** with constant values from previous session
- **Test Considerations**: 
  - Tests during non-market hours will receive **constant price streams** (same price repeated)
  - Momentum strategies may not generate signals due to zero price movement
  - Volatility-based strategies will show minimal activity with static prices
  - Volume data will be zero or minimal during non-market hours
- **Testing Strategy**:
  - **Unit/Integration Tests**: Can run anytime (use real infrastructure, not dependent on live data)
  - **E2E Market Data Tests**: Best run during market hours for authentic data validation
  - **Strategy Signal Tests**: May need market hours for meaningful signal generation
  - **Parameter Testing**: Tests of parameters that don't depend on changing prices can run anytime
- **Non-Price Dependent Tests** (can run during non-market hours):
  - Service interface validation
  - Event schema compliance testing
  - Redis/Kafka/PostgreSQL integration testing
  - Authentication and API connectivity testing
  - Portfolio calculation logic (with fixed prices)
  - Risk management rule validation
  - Configuration and settings validation
- **Recommendation**: Schedule comprehensive E2E tests during IST market hours (9:15 AM - 3:30 PM) for complete validation

### First-Time Setup
```bash
# 1. Setup virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate     # Windows

# 2. Install dependencies
pip install -r requirements.txt -c constraints.txt

# 3. Start test infrastructure
docker compose -f docker-compose.test.yml up -d

# 4. Wait for infrastructure to be ready
sleep 30

# 5. Run tests
python -m pytest tests/unit/ -v
```

## Troubleshooting

### Common Issues

**1. Infrastructure Not Available**
```bash
# Check if containers are running
docker compose -f docker-compose.test.yml ps

# Check container logs
docker compose -f docker-compose.test.yml logs redis
docker compose -f docker-compose.test.yml logs kafka
docker compose -f docker-compose.test.yml logs postgres
```

**2. Port Conflicts**
```bash
# Check if ports are in use
netstat -tulpn | grep ":6380\|:19092\|:5433\|:2181"

# Kill processes using test ports
sudo lsof -ti:6380 | xargs kill -9
```

**3. Permission Issues**
```bash
# Fix Docker permissions
sudo chmod 666 /var/run/docker.sock
sudo usermod -aG docker $USER
```

**4. Test Data Cleanup**
```bash
# Clean up test data
docker compose -f docker-compose.test.yml down -v
docker volume prune -f
docker system prune -f
```

### Test Execution Debugging

**Enable Verbose Logging**
```bash
# Run tests with detailed output
python -m pytest tests/ -v -s --tb=long --log-cli-level=DEBUG

# Run specific test with maximum detail
python -m pytest tests/unit/test_event_envelope_validation.py::TestEventEnvelopeValidation::test_event_envelope_required_fields -v -s --tb=long
```

**Infrastructure Health Check**
```bash
# Quick health validation
python -c "
import asyncio
from tests.fixtures.infrastructure_fixtures import InfrastructureHealthChecker

async def main():
    results = await InfrastructureHealthChecker.check_all_services()
    for service, healthy in results.items():
        status = '✅' if healthy else '❌'
        print(f'{status} {service}: {healthy}')

asyncio.run(main())
"
```

## Migration from Legacy Tests

### What Changed
1. **Removed**: All mock-based tests that hid infrastructure issues
2. **Added**: Real infrastructure integration testing
3. **Enhanced**: Service interface validation to prevent AttributeError
4. **Improved**: Event schema validation to prevent Pydantic errors
5. **Implemented**: Zerodha real API integration for E2E testing

### Benefits
- **Production Issue Prevention**: Catches Redis type errors, Kafka serialization issues
- **Interface Validation**: Prevents method call errors before deployment  
- **Real Data Testing**: Validates system with actual market conditions
- **Infrastructure Resilience**: Tests real failure scenarios and recovery
- **Performance Validation**: Real infrastructure performance measurement

---

**Last Updated**: 2025-08-29 | **Status**: 🚀 **PRODUCTION-READY** | **Priority**: 🎯 **CRITICAL INFRASTRUCTURE VALIDATION**