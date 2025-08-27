# Alpha Panda Implementation Plan

## Overview

Simple implementation plan following the exact design from the docs folder. Build the Unified Log architecture with Redpanda exactly as specified in ALPHA_PANDA_PLAN.md.

## Architecture (From ALPHA_PANDA_PLAN.md)

**Data Flow:**
1. Configuration Loading: Services query PostgreSQL for configuration
2. Event Ingestion: Market Feed writes ticks to `market.ticks` topic
3. Stream Processing: Strategy Runner → Risk Manager → Trading Engine
4. State Materialization: Portfolio Manager updates Redis cache
5. API Serving: FastAPI reads from Redis cache

**Folder Structure (Exact from docs):**
```
alpha_panda/
├── app/                  # Core application orchestration
├── core/                 # Shared libraries and utilities
│   ├── config/           # Pydantic settings models  
│   ├── database/         # PostgreSQL models and connection
│   └── streaming/        # Redpanda client utilities
├── services/             # Independent stream processing services
│   ├── market_feed/      # Ingests market data into Redpanda
│   ├── strategy_runner/  # Hosts and runs trading strategies
│   ├── risk_manager/     # Validates trading signals
│   ├── trading_engine/   # Executes orders with broker
│   └── portfolio_manager/ # Builds and caches portfolio view
├── api/                  # Read-only API and WebSocket service
├── strategies/           # Pure, decoupled strategy logic
└── docker-compose.yml    # Redpanda, Postgres, Redis
```

## Phase 1: Core Infrastructure (WITH FIXES)

### 1.1 Event Schemas & Contracts FIRST (CRITICAL)
- `core/schemas/events.py`: **MANDATORY** standardized event envelope
  - `EventEnvelope` with fields: `type`, `ts`, `key`, `source`, `version`, `data`
  - Enforce at ALL publish/consume boundaries - no ad-hoc event_type checks
  - Pydantic models for: `MarketTick`, `TradingSignal`, `ValidatedSignal`, `OrderFill`
  - Version all event types starting with `version: 1`
- `core/schemas/topics.py`: **CENTRALIZED** topic names and routing rules
  - Single `market.ticks` topic (partition by instrument_token)  
  - Explicit `orders.filled.paper` and `orders.filled.live` topics
  - NO wildcard subscriptions - route by topic name, not message fields
  - Document partition keys for each topic type

### 1.2 Fixed Streaming Infrastructure (CRITICAL)
- `core/streaming/clients.py`: **COMPLETELY REWRITTEN** with aiokafka
  - **MANDATORY**: Replace blocking confluent-kafka with aiokafka
  - **MANDATORY**: Message keys in EVERY produce() call:
    - `market.ticks`: key = `str(instrument_token)`
    - `trading.signals.*`: key = `f"{strategy_id}:{instrument_token}"`
    - `orders.*`: key = `f"{strategy_id}:{instrument_token}:{timestamp}"`
  - **MANDATORY**: Idempotent producer settings:
    - `enable_idempotence=True`, `acks='all'`, `max_in_flight_requests_per_connection=1`
  - **MANDATORY**: Unique consumer groups per service:
    - `alpha-panda.market-feed`, `alpha-panda.strategy-runner`, `alpha-panda.risk-manager`
    - `alpha-panda.trading-engine`, `alpha-panda.portfolio-manager`
  - **MANDATORY**: Graceful shutdown with `producer.flush()` in all services

### 1.3 Core Configuration
- `core/config/settings.py`: Complete settings with ALL required sections
  - Database, Redpanda, Redis, Auth settings
  - Group ID prefix for unique consumer groups
- `core/database/`: Connection and models (User, StrategyConfiguration)
- `core/logging.py`: Structured logging with structlog

### 1.4 Application Bootstrap (CRITICAL FIXES)
- `app/containers.py`: **COMPLETE** DI container - NO MISSING PROVIDERS
  - **MANDATORY**: Add `PortfolioCache` provider
  - **MANDATORY**: Add `AuthService` provider  
  - **MANDATORY**: Complete `lifespan_services` list with ALL services
  - **MANDATORY**: Unique consumer group IDs per service
- `app/main.py`: Application orchestrator with graceful shutdown
- `app/services.py`: LifespanService protocol with **producer.flush()** in stop()
- `docker-compose.yml`: Redpanda, PostgreSQL, Redis
- `scripts/bootstrap_topics.py`: **CRITICAL** - Create topics with proper partitions

## Phase 2: Core Trading Pipeline

### 2.1 Market Feed Service
- Implement exact code from MARKET_FEED.md
- `services/market_feed/auth.py`: BrokerAuthenticator
- `services/market_feed/formatter.py`: Tick formatting
- `services/market_feed/service.py`: MarketFeedService
- Start with mock data, add Zerodha later

### 2.2 Strategy Framework  
- Implement exact code from STRATEGIES.md
- `strategies/base.py`: BaseStrategy, data models
- `strategies/momentum.py`: SimpleMomentumStrategy
- `strategies/mean_reversion.py`: MeanReversionStrategy

### 2.3 Strategy Runner Service
- Implement exact code from STRATEGY_RUNNER.md
- `services/strategy_runner/factory.py`: StrategyFactory for dynamic creation
- `services/strategy_runner/runner.py`: Individual strategy host/container  
- `services/strategy_runner/service.py`: Main orchestrator service
- Loads strategies from database, creates runners, manages lifecycle

### 2.4 Risk Manager Service
- Implement exact code from RISK_MANAGER.md  
- `services/risk_manager/rules.py`: Risk rules
- `services/risk_manager/state.py`: Risk state
- `services/risk_manager/service.py`: Main service

### 2.5 Trading Engine Service
- Implement exact code from TRADING_ENGINE.md
- `services/trading_engine/paper_trader.py`: Paper trading
- `services/trading_engine/zerodha_trader.py`: Live trading
- `services/trading_engine/service.py`: Smart router

## Phase 3: Read Path & API

### 3.1 Portfolio Manager Service
- Implement exact code from PORTFOLIO_MANAGER.md
- `services/portfolio_manager/models.py`: Position and Portfolio data models
- `services/portfolio_manager/cache.py`: Redis cache interface
- `services/portfolio_manager/service.py`: Event stream processor
- Updates Redis from order fills and market ticks

### 3.2 Authentication Service
- Implement exact code from AUTH.md
- `services/auth/security.py`: Password hashing and JWT utilities
- `services/auth/service.py`: User creation and authentication logic
- Required for API security

### 3.3 API Service  
- Implement exact code from API.md
- `api/dependencies.py`: DI and auth dependencies
- `api/routers/portfolios.py`: Portfolio data endpoints
- `api/routers/auth.py`: Authentication endpoints  
- `api/main.py`: FastAPI application setup
- Protected endpoints reading from Redis cache

## Phase 4: Integration

### 4.1 Application Orchestration
- Complete `app/containers.py` with all service definitions
  - Database manager, streaming clients, all services
  - Dependency injection for the entire application
- Service lifecycle management in `app/main.py`
  - Graceful startup/shutdown of all services
  - Signal handling and error recovery

### 4.2 Configuration & Dependencies (UPDATED)
- **MANDATORY**: Add all required dependencies to requirements.txt:
  - `fastapi`, `uvicorn`, `pydantic-settings`
  - `sqlalchemy`, `asyncpg`, `redis`
  - `aiokafka` (**CRITICAL**: replaces confluent-kafka completely)
  - `passlib`, `python-jose[cryptography]` 
  - `dependency-injector`, `structlog`
- Environment variable configuration with .env.example
- Database initialization scripts  
- **CRITICAL**: `scripts/bootstrap_topics.py` with proper partition counts:
  - `market.ticks`: 12 partitions (high throughput)
  - `trading.signals.generated`: 6 partitions 
  - `trading.signals.validated`: 6 partitions
  - `orders.filled.paper`: 3 partitions
  - `orders.filled.live`: 3 partitions
  - **DLQ Topics** (PHASE 4): `{topic}.dlq` with 1 partition each

### 4.3 Testing Framework
- Unit tests for pure strategies (`tests/unit/`)
- Service tests with mocks (`tests/service/`)
- Integration tests with real infrastructure (`tests/integration/`)
- Contract tests for event schemas

## Implementation Order

1. **Infrastructure First**: Get Redpanda, PostgreSQL, Redis running
2. **Core Components**: Build exactly as specified in docs
3. **Services One by One**: Follow the pipeline order
4. **Integration**: Wire everything together
5. **Testing**: End-to-end validation

## Critical Fixes (From PLAN_ISSUES_AND_REVISIONS.md)

### SHOWSTOPPERS - Must Fix Before First Run

1. **Event Schema Standardization**
   - Standardize event envelope across all services:
   ```json
   {
     "type": "market_tick|trading_signal|validated_signal|order_fill",
     "ts": "ISO8601",
     "key": "partitioning_key",
     "source": "service_name", 
     "version": 1,
     "data": { ...actual_payload... }
   }
   ```

2. **Topic Naming Consistency**
   - Use `market.ticks` (single topic, partition by instrument_token)
   - Use `orders.filled.paper` and `orders.filled.live` (explicit topics)
   - Fix wildcard subscription issues

3. **Kafka Keys & Ordering**
   - Add message keys: `instrument_token` for ticks, `strategy_id:instrument_token` for signals
   - Enable idempotent producer with `acks=all`

4. **Async/Blocking Issue**
   - Fix blocking `consumer.poll()` in async loops
   - Use `aiokafka` or run poll in thread executor

5. **Consumer Groups**
   - Unique group.id per service (e.g., `alpha-panda.risk-manager`, `alpha-panda.strategy-runner`)

6. **DI Container Gaps**
   - Add missing providers: `PortfolioCache`, `AuthService`
   - Complete `lifespan_services` list

7. **Portfolio P&L Bug**
   - Fix cash calculation: SELL should increase cash, not decrease

### MANDATORY Event Flow Patterns (ENFORCE EVERYWHERE)

**Market Feed Service:**
```python
# CORRECT: Single topic, proper key, standardized envelope
await self.producer.send(
  topic="market.ticks",
  key=str(instrument_token),  # MANDATORY for ordering
  value={
    "type": "market_tick",
    "ts": datetime.utcnow().isoformat(),
    "source": "market_feed", 
    "version": 1,
    "data": formatted_tick  # MarketTick model
  }
)
```

**Strategy Runner:**
```python
# CORRECT: Route by topic, standardized envelope, proper key
await self.producer.send(
  topic="trading.signals.generated",
  key=f"{strategy_id}:{instrument_token}",  # MANDATORY for ordering
  value={
    "type": "trading_signal",
    "ts": datetime.utcnow().isoformat(),
    "source": "strategy_runner",
    "version": 1,
    "data": signal.model_dump()  # TradingSignal model
  }
)
```

**Risk Manager:**
```python
# CORRECT: Subscribe ONLY to topic, route by topic name
consumer = AIOKafkaConsumer(
  "trading.signals.generated",  # NO wildcards, NO event_type filtering
  group_id="alpha-panda.risk-manager"  # UNIQUE group
)

# Emit with standardized envelope
await self.producer.send(
  topic="trading.signals.validated",  # or "trading.signals.rejected"
  key=original_key,  # PRESERVE ordering
  value={
    "type": "validated_signal",  # or "rejected_signal"
    "ts": datetime.utcnow().isoformat(),
    "source": "risk_manager",
    "version": 1,
    "data": validated_signal
  }
)
```

**Trading Engine:**
```python
# CORRECT: Multiple explicit topics, route by topic name
consumer = AIOKafkaConsumer(
  "trading.signals.validated", 
  "market.ticks",  # NO wildcards
  group_id="alpha-panda.trading-engine"
)

# Route by msg.topic, NOT by message content
if msg.topic == "trading.signals.validated":
    handle_signal(msg.value["data"])
elif msg.topic == "market.ticks":  
    update_price_cache(msg.value["data"])
```

**Portfolio Manager:**
```python
# CORRECT: Explicit topics, NO wildcards
consumer = AIOKafkaConsumer(
  "orders.filled.paper",
  "orders.filled.live",  # NO "orders.filled.*" wildcards
  "market.ticks",
  group_id="alpha-panda.portfolio-manager"
)

# FIX: Correct cash flow calculation
if signal['signal_type'] == 'BUY':
    portfolio.cash -= trade_value  # Decrease cash when buying
else:  # SELL
    portfolio.cash += trade_value  # INCREASE cash when selling (FIXED)
```

## MANDATORY Implementation Sequence

### PHASE 0: Schema & Infrastructure Foundation (MUST BE FIRST)
1. **Build schemas first, NOT services**:
   - Create `core/schemas/events.py` with EventEnvelope and all data models
   - Create `core/schemas/topics.py` with centralized topic names and keys
   - Create `scripts/bootstrap_topics.py` for topic creation with proper partitions
2. **Fix streaming infrastructure**:
   - Replace confluent-kafka with aiokafka completely  
   - Implement producer with mandatory keys and idempotence
   - Implement consumer with unique groups per service
3. **Complete DI container**:
   - Add ALL missing providers (PortfolioCache, AuthService)
   - Wire unique consumer groups per service
   - Complete lifespan_services list

### PHASE 1-4: Services (ONLY AFTER PHASE 0)
- Build services using the standardized patterns above
- ENFORCE envelope format at every publish/consume boundary
- NO ad-hoc event_type checks - route by topic only
- ALL services must flush() producer on shutdown

## Essential Operability (Foundation Only)

### Basic Observability (PHASE 4)
- **Structured Logging**: JSON logs via structlog (already planned)
- **Essential Metrics** (Prometheus format):
  - Producer: messages sent, send errors per topic
  - Consumer: messages processed, processing errors per service
  - API: request count, response times
- **Simple Health Checks**: `/health` endpoint per service
- **No complex tracing initially** - add OpenTelemetry later

### Basic Error Handling (PHASE 4)
- **Dead Letter Queues** (DLQ): Simple approach
  - `{topic}.dlq` for poison pills (e.g., `trading.signals.generated.dlq`)
  - Send to DLQ after 3 failed attempts
  - Manual review/replay process (no auto-retry initially)
- **Schema Validation**: Reject invalid events at consume boundary
- **Circuit Breaker**: Simple fail-fast for downstream service errors

### Basic Recovery Procedures (PHASE 4)
- **State Rebuild**: Simple Redis cache rebuild from Redpanda
  - Read from earliest offset on `orders.filled.*` and `market.ticks`
  - Deterministic portfolio calculation (same events = same state)
  - Manual trigger only (no automated rebuild initially)
- **Event Replay**: Manual offset reset for service recovery
  - Document consumer group reset procedures
  - Simple runbook for common failure scenarios

### Delivery Semantics (Keep Simple)
- **At-least-once delivery**: Default for all topics
- **Idempotent consumers**: Portfolio manager handles duplicate events gracefully
- **No exactly-once complexity**: Use event deduplication by timestamp/key
- **Manual intervention**: For data consistency issues (keep simple)

## Critical Testing Requirements

### Contract Tests (MANDATORY)
- Test event envelope compliance for every message type
- Validate schema versions and backward compatibility
- Test topic routing without wildcard subscriptions

### Integration Tests (MANDATORY)  
- End-to-end flow with real Redpanda/Redis/Postgres
- Verify message ordering within partitions
- Test consumer group isolation between services
- **Basic failure scenarios**: DLQ handling, service restart

## Key Principles

- **SCHEMAS FIRST**: Never start services without event contracts
- **NO WILDCARDS**: Route by explicit topic names only
- **MANDATORY KEYS**: Every message must have proper partition key
- **ENVELOPE EVERYWHERE**: No ad-hoc message formats
- **UNIQUE GROUPS**: No sharing consumer groups between services

## Success Criteria

### Phase 0-3: Core System
- All critical fixes from PLAN_ISSUES_AND_REVISIONS.md implemented
- Standardized event schema used throughout
- All services start with unique consumer groups
- Mock market data flows through entire pipeline with correct event types
- Paper trades execute successfully with proper P&L calculation
- API serves data from Redis cache
- System runs end-to-end without blocking or ordering issues

### Phase 4: Basic Operations
- Basic metrics collection working (Prometheus format)
- DLQ handling for poison pill events
- Simple state rebuild from Redpanda events
- Health checks respond correctly
- Manual runbook procedures documented

## Implementation Notes

1. **Start with event schemas** in `core/schemas/` first
2. **Fix producer/consumer patterns** before building services
3. **Use exact code samples** but apply the critical fixes
4. **Add proper error handling** and graceful shutdown with `producer.flush()`
5. **Mock data first**, Zerodha integration after core pipeline works
6. **Keep operability simple**: Manual procedures over automation initially
7. **Defer complexity**: OpenTelemetry, auto-scaling, complex retry logic for later phases

## Future Enhancements (Post-Foundation)

**After Phase 4 success, consider:**
- OpenTelemetry distributed tracing
- Automated DLQ replay mechanisms
- Advanced circuit breakers and retry policies
- Horizontal auto-scaling of services
- Real-time dashboards and alerting (Grafana)
- Automated state reconciliation
- Performance optimization and caching strategies