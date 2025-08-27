# Alpha Panda Testing Framework - Multi-Broker Architecture

**Status**: 🔄 **Rebuilding for Updated Architecture** | 📋 **Phased Implementation Plan** | ⚡ **Focus on End-to-End Validation**

## 🚀 Quick Start (New Architecture)

```bash
# 1. Setup virtual environment and dependencies
source venv/bin/activate
pip install -r requirements.txt -c constraints.txt

# 2. Phase 1: Core Infrastructure Tests
python -m pytest tests/unit/phase1/ -v

# 3. Phase 2: Service Integration Tests  
make test-setup
python -m pytest tests/integration/phase2/ -v

# 4. Phase 3: End-to-End Pipeline Tests
python -m pytest tests/e2e/phase3/ -v

# 5. Performance and Load Tests
python -m pytest tests/performance/ -v

# 6. Clean up test infrastructure
make test-clean
```

## Testing Strategy Overview

Alpha Panda's testing framework has been **completely redesigned** to validate the new **Unified Log Architecture** with **Multi-Broker Support** and **Real Market Data Integration**. The testing approach focuses on:

1. **Real System Validation** - Testing actual trading pipeline with authentic data flows
2. **Multi-Broker Architecture** - Validating paper/zerodha broker segregation and integration
3. **Event Streaming Core** - Comprehensive Redpanda/aiokafka integration testing  
4. **End-to-End Trading Flow** - Complete market data → strategy → risk → execution → portfolio pipeline
5. **Performance & Resilience** - High-frequency data processing and error recovery testing

## Testing Philosophy

**🎯 Primary Goal**: Validate that the complete trading system works correctly with real market data and can execute trades safely across multiple brokers with proper isolation.

**⚠️ Critical Principle**: Mock data is used ONLY for testing infrastructure - all trading logic validation uses realistic market data patterns to prevent discrepancies with live trading.

## Phased Testing Architecture

### Phase 1: Core Infrastructure Tests (Unit Level)
- **Event System** - EventEnvelope, topic routing, message serialization
- **Broker Segregation** - Topic namespace isolation, cache key prefixing
- **Strategy Framework** - Pure strategy logic without external dependencies
- **Configuration** - Multi-broker settings, active broker configuration
- **Error Handling** - DLQ patterns, retry mechanisms, graceful degradation

### Phase 2: Service Integration Tests  
- **Market Feed Service** - Zerodha API integration, tick formatting, event publishing
- **Strategy Runner** - Strategy execution, signal generation, multi-broker routing
- **Risk Manager** - Signal validation, risk rules, broker-aware risk checks
- **Trading Engine** - Order execution, paper/zerodha trader routing
- **Portfolio Manager** - Position tracking, PnL calculation, broker segregation

### Phase 3: End-to-End Pipeline Tests
- **Complete Trading Flow** - Market data → Strategy → Risk → Execution → Portfolio
- **Multi-Broker Operation** - Simultaneous paper/zerodha trading with isolation
- **Market Data Integration** - Real Zerodha feed processing and distribution
- **System Resilience** - Service restart recovery, infrastructure failover
- **Performance Validation** - High-frequency processing, latency requirements

## New Test Structure (Updated Architecture)

```
tests/
├── unit/
│   └── phase1/                    # Core infrastructure tests
│       ├── test_event_system.py              # EventEnvelope, serialization
│       ├── test_broker_segregation.py        # Topic/cache isolation
│       ├── test_strategy_framework.py        # Pure strategy logic
│       ├── test_configuration.py             # Multi-broker settings
│       └── test_error_handling.py            # DLQ, retry patterns
├── integration/
│   └── phase2/                    # Service integration tests
│       ├── test_market_feed.py               # Market data ingestion
│       ├── test_strategy_runner.py           # Strategy execution
│       ├── test_risk_manager.py              # Risk validation
│       ├── test_trading_engine.py            # Order execution
│       └── test_portfolio_manager.py         # Portfolio tracking
├── e2e/
│   └── phase3/                    # End-to-end pipeline tests
│       ├── test_trading_pipeline.py          # Complete trading flow
│       ├── test_multi_broker.py              # Dual broker operation
│       └── test_system_resilience.py         # Recovery and failover
├── performance/                   # Load and latency tests
│   ├── test_market_data_throughput.py
│   ├── test_trading_latency.py
│   └── test_sustained_load.py
├── mocks/                         # Mock data infrastructure (tests only)
│   ├── mock_market_server.py                # Market data simulation
│   ├── mock_zerodha_api.py                  # Zerodha API simulation
│   └── realistic_data_generator.py          # Market-realistic test data
└── fixtures/                      # Shared utilities and data
    ├── test_instruments.py
    ├── test_portfolios.py
    └── redis_cache_helpers.py
```

## Implementation Plan

### Phase 1: Core Infrastructure Tests (Week 1)
**Goal**: Validate foundational architecture components work correctly

1. **Event System Testing** (`test_event_system.py`)
   - EventEnvelope serialization/deserialization
   - UUID v7 event ID generation and validation
   - Correlation ID and causation ID linking
   - Topic routing by broker namespace

2. **Broker Segregation Testing** (`test_broker_segregation.py`)
   - Topic namespace isolation (paper.* vs zerodha.*)
   - Redis cache key prefixing (paper: vs zerodha:)
   - Configuration-based broker activation
   - Topic subscription patterns

3. **Strategy Framework Testing** (`test_strategy_framework.py`)
   - BaseStrategy inheritance and interface
   - MarketTick → TradingSignal pure function processing
   - Strategy configuration and parameter validation
   - Multi-strategy execution isolation

4. **Configuration Testing** (`test_configuration.py`)
   - ACTIVE_BROKERS environment variable parsing
   - Multi-broker settings validation
   - Topic name generation for active brokers
   - Redis and database connection configuration per broker

5. **Error Handling Testing** (`test_error_handling.py`)
   - DLQ pattern implementation
   - Exponential backoff with jitter
   - Poison message detection and routing
   - Graceful degradation scenarios

### Phase 2: Service Integration Tests (Week 2)
**Goal**: Validate service interactions and event flow integration

1. **Market Feed Service Testing** (`test_market_feed.py`)
   - Zerodha API connection and authentication
   - Market tick formatting and validation
   - Event publishing to market.ticks topic
   - Connection recovery and error handling

2. **Strategy Runner Service Testing** (`test_strategy_runner.py`)
   - Strategy loading from database configuration
   - Market tick processing and signal generation
   - Multi-broker signal routing (paper.* vs zerodha.* topics)
   - Strategy execution isolation and error containment

3. **Risk Manager Service Testing** (`test_risk_manager.py`)
   - Signal validation against risk rules
   - Position size and exposure limits
   - Broker-aware risk rule application
   - Signal approval/rejection flow

4. **Trading Engine Service Testing** (`test_trading_engine.py`)
   - Topic-aware message handling with broker extraction
   - PaperTrader vs ZerodhaTrader routing
   - Order execution and acknowledgment flow
   - Error handling and retry mechanisms

5. **Portfolio Manager Service Testing** (`test_portfolio_manager.py`)
   - Multi-broker position tracking with cache isolation
   - Real-time PnL calculation
   - Portfolio state consistency across service restarts
   - Event-driven portfolio updates

### Phase 3: End-to-End Pipeline Tests (Week 3)
**Goal**: Validate complete trading system with realistic market conditions

1. **Complete Trading Pipeline** (`test_trading_pipeline.py`)
   - Market data → Strategy → Risk → Execution → Portfolio flow
   - Message ordering and correlation ID tracking
   - Event deduplication across the pipeline
   - System latency and performance validation

2. **Multi-Broker Operation** (`test_multi_broker.py`)
   - Simultaneous paper and zerodha trading
   - Complete data isolation between brokers
   - Independent portfolio tracking
   - Configuration-driven broker activation

3. **System Resilience** (`test_system_resilience.py`)
   - Service restart and state recovery
   - Infrastructure failover scenarios
   - Message replay and gap detection
   - Graceful degradation under load

## Mock Data Infrastructure (Tests Only)

### Mock Market Data Server
**Purpose**: Provide realistic market data patterns for testing without depending on live market feeds

1. **Realistic Data Generation** (`realistic_data_generator.py`)
   - Historical price movement patterns
   - Volume and volatility simulation
   - Multiple instrument support (NIFTY, BANKNIFTY, etc.)
   - Configurable market hours and trading sessions

2. **Mock Zerodha API** (`mock_zerodha_api.py`)
   - WebSocket tick stream simulation
   - Order placement and status responses
   - Portfolio and position data
   - Authentication flow simulation

3. **Mock Market Server** (`mock_market_server.py`)
   - HTTP/WebSocket server for market data distribution
   - Configurable latency and throughput
   - Error injection for resilience testing
   - Market event simulation (circuit breakers, halts)

**⚠️ Critical Note**: Mock data servers exist ONLY in the tests module and are never part of the main application. All trading logic must be validated with realistic patterns to prevent live trading discrepancies.

## Performance Targets & Monitoring

### Target Metrics
- **Market Data Throughput**: >500 ticks/second sustained processing
- **End-to-End Latency**: <20ms average, <50ms P95 (market tick → order placed)
- **Memory Usage**: <100MB per service under normal load
- **Error Recovery**: System operational within 30 seconds of infrastructure restart
- **Multi-Strategy Processing**: Handle 10+ strategies simultaneously without degradation

### Monitoring Points
- Event processing latency per service
- Message queue depth and throughput
- Database connection pool utilization
- Redis cache hit rates and memory usage
- Service health check response times

## Development Commands

### Phase 1 Development
```bash
# Create Phase 1 test structure
mkdir -p tests/unit/phase1
mkdir -p tests/mocks
mkdir -p tests/fixtures

# Run Phase 1 tests
source venv/bin/activate
python -m pytest tests/unit/phase1/ -v --tb=short

# Run with coverage
python -m pytest tests/unit/phase1/ --cov=core --cov=strategies --cov-report=term-missing
```

### Infrastructure Management
```bash
# Start test infrastructure
make test-setup

# Check infrastructure health
docker compose -f docker-compose.test.yml ps
docker compose -f docker-compose.test.yml logs

# Clean up test environment
make test-clean
```

## Critical Success Criteria

### Phase 1 Completion
- [ ] All event system tests passing
- [ ] Broker segregation validated
- [ ] Strategy framework functional
- [ ] Configuration handling robust
- [ ] Error handling patterns working

### Phase 2 Completion  
- [ ] All services can start and process messages
- [ ] Multi-broker routing working correctly
- [ ] Service integration tests passing
- [ ] Infrastructure dependencies healthy

### Phase 3 Completion
- [ ] Complete end-to-end trading pipeline working
- [ ] Multi-broker isolation verified
- [ ] System resilience validated
- [ ] Performance targets met

**Overall Goal**: Demonstrate that the complete Alpha Panda trading system works reliably with real market data patterns and can execute trades safely across multiple brokers.

---

**Last Updated**: 2025-08-27 | **Status**: Ready for Phase 1 Implementation