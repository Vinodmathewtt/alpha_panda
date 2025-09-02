# Alpha Panda Testing

This repository uses a pragmatic, lightweight test strategy focused on high‑signal unit tests. Integration/E2E tests are deferred or infra‑gated and not collected by default.

## Scope

- Unit tests: Validate schemas, routing helpers, formatters, and critical producer semantics.
- Integration/E2E: Optional and infra‑gated; directories are placeholders. Not collected by default.

## Running Tests

```bash
pytest -q
```

Defaults are configured in `pytest.ini` to only collect tests under `tests/` and standard `test_*.py` patterns.

## Covered Areas

- Event schemas and enums (`tests/unit/test_event_schemas_v2.py`)
- Event envelope child creation and trace inheritance (`tests/unit/test_event_envelope_child.py`)
- Metrics keys and registry (`tests/unit/test_metrics_registry_v2.py`, `tests/unit/test_metrics_registry_keys.py`)
- Market tick formatter (`tests/unit/test_market_tick_formatter.py`)
- Topic routing and DLQ suffix helper (`tests/unit/test_topic_routing.py`)
- Topic helpers and asset-class mapping (`tests/unit/test_topics_mapping_extras.py`)
- Producer semantics (requires event_type for non‑market topics; defaults on market ticks) (`tests/unit/test_message_producer_semantics.py`)
- Producer serialization of datetime/Decimal (`tests/unit/test_message_producer_serialization.py`)
- Order event defaults and enum coercion (`tests/unit/test_order_event_defaults.py`)

## Notes on Multi‑Broker

- Unit tests assert topic mapping and broker extraction, consistent with the multi‑broker architecture (`paper.*`, `zerodha.*`) and shared `market.ticks`.

## Deferred Layers (Optional)

- `tests/integration/`, `tests/e2e/`, `tests/performance/`, `tests/resilience/`, `tests/property_based/` are present as placeholders and may be populated when infra is available. Do not assume infra is running during unit tests.
  - Note: these folders are intentionally omitted from source control until populated to keep the repo lean.

## Contributing Tests

- Prefer asserting on Enums or `.value` explicitly when dealing with serialization.
- Avoid network, external services, or file system side effects in unit tests.
- If you add integration tests, gate them behind environment flags and mark them accordingly to keep unit test runs fast and deterministic.

## Roadmap (Progressive Plan)

- Phase 1 (complete)
  - Core schemas, topics, formatter, producer semantics, serialization, envelope lineage
- Phase 2 (optional)
  - Pipeline metrics Redis integration using a local fake client
  - DLQ emission path unit tests with in-memory producer fakes
  - Validator latency threshold paths (market_data/signal/risk/order/portfolio)
  - Market feed enqueue blocking path (queue full with block-with-timeout instrumentation)
  - StreamServiceBuilder DLQ metrics callback (simulate publish and assert Prometheus counter increments)
- Phase 3 (optional/infra)
  - Kafka/Redis integration: topic fan-out and per-broker processing
  - E2E smoke: strategy → risk → trading → portfolio with metrics assertions
  - Performance smoke: basic throughput and latency sampling
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
