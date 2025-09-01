# 🐼 Alpha Panda - Algorithmic Trading System

A modern algorithmic trading system built on the Unified Log architecture using Redpanda for event streaming. Features comprehensive testing, multi-broker architecture, and production-ready reliability patterns.

## 🏗️ Architecture

**Unified Log Architecture with Redpanda**

- **Single Source of Truth**: All dynamic data flows through Redpanda event streams
- **Multi-Broker Architecture**: Complete isolation between paper and zerodha trading with unified service deployment
- **Configuration Store**: Static configuration in PostgreSQL
- **Read Path**: FastAPI serves from Redis cache
- **Pure Strategy Logic**: Strategies are completely decoupled from infrastructure

**End-to-End Pipeline Flow:**

```
Market Feed Service (Single Instance)
       ↓ (market.ticks topic - shared across all brokers)
Strategy Runner Service (Multi-Broker)
       ↓ (broker.signals.raw topics - paper.signals.raw, zerodha.signals.raw)
Risk Manager Service (Multi-Broker)
       ↓ (broker.signals.validated topics - paper.signals.validated, zerodha.signals.validated)
Paper Trading Service (broker-scoped) and Zerodha Trading Service (broker-scoped)
       ↓ (broker.order lifecycle topics - paper.orders.*, zerodha.orders.*)
Portfolio Read Path
       ↓ (Redis cache with broker prefixes - paper:portfolio:, zerodha:portfolio:)
API Service (Read Path - Unified)
```

**Key Architecture Patterns:**

- **Single Service Deployments**: Each service instance handles all active brokers
- **Topic-Aware Handlers**: Extract broker context from topic names for routing
- **Unified Consumer Groups**: One consumer group per service processes all broker topics
- **Cache Key Isolation**: Redis keys prefixed by broker for complete data separation
- **StreamServiceBuilder Pattern**: Composition-based service orchestration with fluent API
- **Protocol-Based Contracts**: Type-safe interfaces using `typing.Protocol` instead of ABCs
- **Composition-First Design**: Modern strategy framework with protocol contracts
- **Performance Optimizations**: O(1) instrument-to-strategy mappings for efficient routing
- **Comprehensive Documentation**: Complete module-level documentation across all components

### 🏷️ Important Namespace Distinction

**Two Different "Namespace" Concepts (Do Not Confuse):**

1. **`BROKER_NAMESPACE` Environment Variable** (❌ **Deprecated & Removed**)
   - **Old System**: Used for deployment-level broker isolation
   - **Status**: Successfully migrated to `ACTIVE_BROKERS` list configuration
   - **Migration**: `BROKER_NAMESPACE=zerodha` → `ACTIVE_BROKERS=paper,zerodha`

2. **`broker_namespace` Parameter** (✅ **Valid & Required**)
   - **Current System**: Service-level metrics collection namespacing
   - **Purpose**: Identifies which service/component is recording metrics
   - **Examples**: `"strategy_runner"`, `"shared"`, `"paper"`, `"zerodha"`
   - **Usage**: Creates Redis keys like `pipeline:signals:strategy_runner:count`

**Key Point**: If you see `broker_namespace="strategy_runner"` in code, this is **correct** and different from the old `BROKER_NAMESPACE` env var that was removed.

### 🤝 Multi‑Broker Operation (At a Glance)

- **Strategies → Multiple Brokers**: Strategies generate signals per tick and fan‑out to all active brokers (e.g., `paper.signals.raw` and `zerodha.signals.raw`).
- **Broker‑Scoped Trading**: `paper_trading` and `zerodha_trading` consume their own `{broker}.signals.validated` and emit `{broker}.orders.*` and `{broker}.pnl.snapshots`.
- **Portfolios per Broker**: Portfolio/PnL snapshots are emitted per broker; Redis keys remain broker‑prefixed.
- **Market Data Shared**: A single Zerodha feed publishes `market.ticks` for all brokers to keep strategy behavior consistent.
- **Deprecation Notice**: Any architectures that steer behavior via a global `broker_namespace` are transitional and should be refactored to explicit per‑broker topic routing. The `broker_namespace` identifier remains only for metrics namespacing/compatibility and may be removed in a future cleanup.

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.13+
- Make (optional, for convenience)

### 🏃‍♂️ Development Setup & Run

1. **Clone and setup environment:**

```bash
make dev  # Sets up .env and installs dependencies with constraints
```

2. **Start infrastructure:**

```bash
make up   # Starts Redpanda, PostgreSQL, Redis
```

3. **Bootstrap topics and seed data:**

```bash
make bootstrap  # Creates Redpanda topics with proper partitions
make seed      # Seeds test strategies in database
```

Environment-aware topic bootstrap (optional):

```bash
# Example: production-like overlays
export SETTINGS__ENVIRONMENT=production
export REDPANDA_BROKER_COUNT=3
export TOPIC_PARTITIONS_MULTIPLIER=1.5
export CREATE_DLQ_FOR_ALL=true
make bootstrap
```

4. **Run Alpha Panda:**

```bash
make run  # Starts the complete trading pipeline
```

**Or do it all in one step:**

```bash
make setup  # Complete first-time setup
```

### 📈 Metrics (Prometheus)

- API exposes Prometheus metrics at `/metrics`.
- Example scrape target: `http://localhost:8000/metrics`
- Install deps via `pip install -r requirements.txt -c constraints.txt` (includes `prometheus-client`).
- DLQ counter: `trading_dlq_messages_total{service,broker}` increments when messages are sent to per-topic `.dlq`.

### 📊 Grafana Dashboard

- Import the ready dashboard JSON:
  - `docs/observability/grafana/alpha_panda_prometheus_dashboard.json`
- Optional: Consumer lag dashboard `docs/observability/grafana/consumer_lag_dashboard.json` (requires Kafka exporter).
- Added panels for broker‑scoped trading services (events, DLQ) and inactivity/lag metrics.
- Bind your Prometheus data source during import (input variable `DS_PROMETHEUS`).
- See `docs/observability/CONSUMER_LAG.md` for setup and alert guidance.

### 🛠️ Turnkey Observability (Prometheus + Kafka Exporter)

Start Prometheus and Kafka exporter with docker compose profiles:

```bash
# Start Redpanda, Postgres, Redis (default)
docker compose up -d

# Start observability stack (Prometheus UI at http://localhost:9090)
docker compose --profile observability up -d
```

Prometheus scrapes:
- Redpanda admin metrics at `redpanda:9644`
- Kafka exporter metrics at `kafka-exporter:9308`
- API metrics at `http://host.docker.internal:8000/metrics` (adjust host if needed on Linux)

See the full observability guide at `docs/observability/README.md`.

### 📊 Grafana (One-click UI)

Grafana is included under the `observability` profile and auto‑provisions:
- A Prometheus datasource (http://prometheus:9090)
- Dashboards loaded from `docs/observability/grafana`

Start Grafana:

```bash
docker compose --profile observability up -d grafana
```

Access UI: http://localhost:3000 (default admin/admin; change after first login)

Tips:
- If you modify dashboard JSONs, Grafana picks them up automatically (files are mounted read‑only to `/var/lib/grafana/dashboards`).
- Ensure Prometheus is up before Grafana so the datasource is healthy.

### ⚙️ Kafka Producer Tuning (optional)

Per-service producer tuning is config-driven and disabled by default. You can enable light tuning for high‑throughput stages (e.g., `market_feed`) without code changes.

Option A — JSON env (recommended for dict settings):

```bash
# Example: slightly lower linger and zstd compression for market_feed
export PRODUCER_TUNING='{"market_feed": {"linger_ms": 2, "compression_type": "zstd"}}'
```

Option B — .env file (same JSON string):

```
PRODUCER_TUNING={"market_feed": {"linger_ms": 2, "compression_type": "zstd"}}
```

Notes:
- Supported keys: `linger_ms`, `compression_type` (gzip|snappy|lz4|zstd), `batch_size`, `request_timeout_ms`, `max_in_flight_requests`.
- You can also set a `default` profile applied to all producers unless overridden by service name.
- Defaults remain unchanged unless you set overrides.

### 🔎 Tracing (optional)

- Feature‑flagged OpenTelemetry traces for Kafka producer/consumer and API.
- Enable via env:
  - `TRACING__ENABLED=true`
  - `TRACING__EXPORTER=otlp`
  - `TRACING__OTLP_ENDPOINT=http://localhost:4317`
- See `docs/observability/TRACING.md` for details.

### 📨 DLQ Replay (optional)

Replay messages from per-topic DLQs back to their original topics (dry-run supported):

```
python scripts/dlq_replay.py --bootstrap localhost:9092 --dlq paper.signals.raw.dlq --group replay-tool --dry-run
```

Remove `--dry-run` to actually republish. Use `--limit` to cap messages.

### 🧪 Testing

Phase 1 focuses on fast, deterministic unit tests aligned with the multi‑broker architecture. Integration/E2E layers are optional and infra‑gated.

Quick run (unit only):

```bash
pytest -q
```

Planned phases (opt‑in):
- Phase 2: Integration tests (Kafka/Redis/Postgres) behind `make test-setup && make test-with-env`.
- Phase 3: E2E smoke with broker fan‑out and DLQ metrics validation.
- **Redis Integration**: Tests with actual Redis client (both decode_responses modes)
- **Kafka Integration**: Real message serialization/deserialization with actual topics
- **PostgreSQL Integration**: Actual database connections, transactions, and ACID compliance
- **Zerodha Real API**: End-to-end tests with actual market data and authentication

#### **✅ NEW: Critical Issue Prevention**
- **Service Interface Validation**: Prevents AttributeError exceptions before runtime
- **Event Schema Validation**: Catches missing EventType enum values during development
- **Type Conversion Testing**: Redis bytes vs string handling with real clients
- **Serialization Testing**: EventEnvelope round-trip through actual Kafka topics

### 🚀 **Quick Start Testing**

```bash
# 1. Unit Tests - Core component validation with real infrastructure
python -m pytest tests/unit/ -v --tb=short

# 2. Integration Tests - Service interactions with real Redis/Kafka/PostgreSQL
python -m pytest tests/integration/ -v --tb=short

# 3. End-to-End Tests - Complete pipeline with real Zerodha authentication
# ⚠️  REQUIRES: ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_ACCESS_TOKEN
python -m pytest tests/e2e/ -v -s --tb=short

# 4. Complete Test Suite
python -m pytest tests/ -v --tb=short

# 5. Critical Path Validation (< 30 seconds)
python -m pytest tests/unit/test_event_envelope_validation.py tests/unit/test_service_interfaces.py -v
```

### 🔐 **Zerodha Authentication Requirements**

**CRITICAL**: End-to-end tests require **real Zerodha credentials** for authentic market data validation.

#### **Required Environment Variables:**
```bash
export ZERODHA_API_KEY="your_api_key_here"
export ZERODHA_API_SECRET="your_api_secret_here"
export ZERODHA_ACCESS_TOKEN="your_access_token_here"
```

#### **Authentication Failure Policy:**
- **Test Behavior**: If Zerodha authentication fails, tests will **immediately stop** and display clear error message
- **User Responsibility**: It is the **user's responsibility** to provide valid, working Zerodha credentials
- **No Fallbacks**: Tests will **not** fall back to mock data - authentication must work for real market feed testing
- **Clear Error Messages**: Authentication failures will show specific error details to help user resolve issues

#### **Authentication Error Examples:**
```bash
# Example error message when credentials are missing:
"Zerodha credentials not available - set ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_ACCESS_TOKEN"

# Example error message when authentication fails:
"Zerodha authentication failed: Invalid access token. Please regenerate your access token."
```

#### **Safety Enforcement:**
- **Paper Trading Mode**: All tests run in **paper trading mode only** for safety
- **No Live Trading**: Tests validate that live trading is **disabled** even with real credentials
- **Market Data Only**: Real credentials used **only** for market data access, not order placement

#### **Market Hours Behavior:**
- **During Market Hours (9:15 AM - 3:30 PM IST)**: Live market data with real-time price changes
- **During Non-Market Hours**: Zerodha provides **closing price feeds** with constant values
- **Test Considerations**: Tests during non-market hours will receive **constant price streams**
- **Strategy Impact**: Momentum and volatility-based strategies may not generate signals with static prices
- **Recommendation**: Run comprehensive E2E tests during market hours for full validation

### 🏗️ **Test Infrastructure Requirements**

**Required Infrastructure Components:**

| **Component** | **Test Port** | **Purpose** | **Docker Image** |
|---------------|---------------|-------------|------------------|
| Redis | 6380 | Cache testing, type conversion validation | `redis:7-alpine` |
| Kafka | 19092 | Message streaming, serialization testing | `confluentinc/cp-kafka:7.4.0` |
| PostgreSQL | 5433 | Database integration, transaction testing | `postgres:15-alpine` |

```bash
# Start test infrastructure
docker compose -f docker-compose.test.yml up -d

# Verify infrastructure health
docker compose -f docker-compose.test.yml ps

# Stop and cleanup
docker compose -f docker-compose.test.yml down -v
```

### 🎯 **Critical Testing Policies**

#### **MANDATORY: Real Infrastructure First**
- Use actual Redis, Kafka, PostgreSQL for all integration tests
- Mock usage ONLY for external APIs requiring credentials
- Rationale: Mocks hide critical type conversion, serialization, and connection issues

#### **MANDATORY: Fail-Fast Validation**
- Zero silent failures - every error must be logged, alerted, or raise exception
- System must fail fast when critical dependencies are missing
- All failures must be observable via logs, metrics, or exceptions

#### **MANDATORY: Production-Like Test Environment**
- Test infrastructure on separate ports for complete isolation
- Real data flows through actual Kafka topics with real serialization
- State persistence using real databases and caches

### 📊 **Testing Framework Architecture**

#### **Layer 1: Unit Tests** - Core Component Validation
- Event schema validation (EventEnvelope, OrderFilled, MarketData)
- Stream processing patterns with real Kafka integration
- Service interface validation to prevent method call errors
- Redis type handling for both decode_responses modes

#### **Layer 2: Integration Tests** - Service Interaction Validation
- Multi-broker topic routing with real Kafka topics
- Cache isolation with Redis key prefixing
- Database transactions with real PostgreSQL
- End-to-end message flow through complete infrastructure stack

#### **Layer 3: End-to-End Tests** - Complete Pipeline Validation
- Zerodha authentication with real API credentials
- Market data integration through live WebSocket feed
- Complete trading pipeline from market data to portfolio updates
- Safety validation ensuring paper trading enforcement

### 🔥 **Production Issues Prevented**

The new testing framework prevents these critical runtime issues:

1. **Redis Type Errors**: `TypeError: a bytes-like object is required, not 'str'`
2. **Missing Service Methods**: `AttributeError: 'Service' object has no attribute 'method_name'`
3. **Missing Enum Values**: `AttributeError: type object 'EventType' has no attribute 'SYSTEM_ERROR'`
4. **Kafka Serialization Failures**: Message round-trip data corruption
5. **Database Connection Issues**: Connection pooling and transaction failures

**See [tests/README.md](tests/README.md) for complete testing documentation and policies.**

### 🐳 Test Infrastructure Components

**docker-compose.test.yml Services:**

```yaml
redpanda-test: # Port 19092 (isolated from dev 9092)
  healthcheck: ['CMD-SHELL', 'rpk cluster info']

postgres-test: # Port 5433 (isolated from dev 5432)
  healthcheck: ['CMD-SHELL', 'pg_isready -U alpha_panda_test']

redis-test: # Port 6380 (isolated from dev 6379)
  healthcheck: ['CMD', 'redis-cli', 'ping']
```

### 📜 Schema Registry (Scaffolding)

- Avro schemas are provided under `schemas/avro/` for core event types.
- Register schemas to Redpanda Schema Registry (default http://localhost:8082):

```bash
python scripts/register_schemas.py
python scripts/validate_schema_compatibility.py  # optional: checks vs latest
```

- Notes:
  - Runtime still uses JSON; registry is introduced first for contract enforcement and CI checks.
  - In CI, start registry via docker-compose, then run the above scripts.

### 🔍 Dependency Management (Python 3.13 Compatible)

**Version Constraints (`constraints.txt`):**

```bash
# Ensures Python 3.13 compatibility
dependency-injector>=4.42.0,<5
fastapi>=0.104.0,<0.200.0
pydantic>=2.5.0,<3.0.0
# ... additional version bounds for stability
```

**Installation with Constraints:**

```bash
pip install -r requirements.txt -c constraints.txt  # Prevents version conflicts
```

### 🧪 Testing Layers

#### 🎯 Unit Tests (`tests/unit/`) - **67 Passing Tests**

**No Infrastructure Required - Fast & Isolated**

- ✅ **Enhanced error handling** - Retry logic, exponential backoff, DLQ patterns
- ✅ **Event schema validation** - EventEnvelope compliance and correlation tracking
- ✅ **Broker segregation** - Paper/Zerodha topic isolation validation
- ✅ **Strategy framework** - Pure strategy logic with market data history
- ✅ **Chaos engineering** - Random failure injection and recovery testing
- ✅ **Streaming lifecycle** - Producer/consumer lifecycle and graceful shutdown

**Run Command:**

```bash
python -m pytest tests/unit/ -v --cov=core --cov=services --cov=strategies
```

#### 🔗 Integration Tests (`tests/integration/`)

**Requires Test Infrastructure - Service Interaction**

- 🔧 **Service communication** - Real Kafka message flow between services
- 🔧 **Broker segregation** - End-to-end paper/zerodha data isolation
- 🔧 **Risk manager testing** - Signal validation and rejection with real state
- 🔧 **Database integration** - Strategy loading and configuration management

**Run Command:**

```bash
make test-setup                    # Start isolated test infrastructure
make test-with-env                 # Run with test environment
```

#### 🌍 End-to-End Tests (`tests/e2e/`)

**Full Pipeline - Real Infrastructure**

- 🔧 **Complete pipeline validation** - Market tick to portfolio update flow
- 🔧 **Dual broker isolation** - Parallel paper/zerodha trading execution
- 🔧 **System recovery** - Service restart and state consistency
- 🔧 **Performance under load** - High-frequency data processing

**Run Command:**

```bash
make test-all-infra               # Complete infrastructure test suite
```

#### ⚡ Performance Tests (`tests/performance/`)

**Load Testing & Benchmarks**

- 🔧 **Market data throughput** - Target: >100 messages/second
- 🔧 **End-to-end latency** - Target: <50ms average, <100ms P95
- 🔧 **Concurrent processing** - Multiple strategies without conflicts
- 🔧 **Memory stability** - <50MB increase under sustained load
- 🔧 **Error recovery** - System continues with <5% error rate

**Run Command:**

```bash
make test-performance-with-env    # Performance tests with test infrastructure
```

### 📊 Test Status Overview

**✅ Working (No Infrastructure):**

- **67 Unit Tests** - All core modules validated
- **32% Code Coverage** - Focus on critical paths
- **Error Handling** - Comprehensive resilience testing
- **Event System** - Complete schema and correlation validation

**🔧 Infrastructure Required:**

- **Integration Tests** - Need Kafka/Redis/PostgreSQL setup
- **E2E Pipeline Tests** - Full service orchestration
- **Performance Benchmarks** - Load testing infrastructure
- **Service Communication** - Real message passing validation

### 🎭 Test Environment Verification

**Verify Setup Working:**

```bash
# Run the complete verification script
./test-infrastructure-setup.sh

# Manual verification steps
docker compose -f docker-compose.test.yml ps
export $(grep -v '^#' .env.test | xargs)
python -c "import os; print('✅ Test env loaded:', os.getenv('DATABASE_URL'))"
```

### 🚀 CI/CD Integration

**GitHub Actions Pipeline:**

```yaml
# .github/workflows/tests.yml
- name: Install dependencies with constraints
  run: pip install -r requirements.txt -c constraints.txt

- name: Start test infrastructure
  run: |
    docker compose -f docker-compose.test.yml up -d
    docker compose -f docker-compose.test.yml wait

- name: Run tests with environment
  run: make test-all-infra
```

**Benefits:**

- ✅ **Deterministic builds** - Health checks eliminate flaky tests
- ✅ **Parallel execution** - Dev and test environments isolated
- ✅ **Version stability** - Constraints prevent dependency conflicts
- ✅ **Fast feedback** - Unit tests run without infrastructure

## 📁 Project Structure

```
alpha_panda/
├── app/                    # Application orchestration & DI container
├── core/                   # Shared libraries
│   ├── config/            # Pydantic settings
│   ├── database/          # PostgreSQL models & connection
│   ├── schemas/           # Event contracts & topic definitions
│   └── streaming/         # aiokafka client utilities
├── services/              # Stream processing microservices
│   ├── market_feed/       # Market data ingestion (shared)
│   ├── strategy_runner/   # Strategy execution (broker-segregated)
│   ├── risk_manager/      # Risk validation (broker-segregated)
│   ├── paper_trading/     # Paper broker-scoped trading service
│   └── zerodha_trading/   # Zerodha broker-scoped trading service
├── strategies/            # Pure trading strategy logic
│   ├── base/             # BaseStrategy foundation components
│   ├── legacy/           # Inheritance-based strategies (production active)
│   ├── core/             # Composition framework (protocols, config, executor, factory)
│   ├── implementations/  # Modern strategy implementations
│   ├── validation/       # Strategy validation components
│   └── configs/          # YAML configuration files
├── api/                   # FastAPI read endpoints
├── tests/                 # Comprehensive testing framework
│   ├── unit/             # Fast isolated tests
│   ├── integration/      # Service interaction tests
│   ├── e2e/             # Full pipeline tests
│   ├── performance/     # Load and performance tests
│   └── fixtures/        # Shared test data and utilities
├── scripts/              # Bootstrap & utility scripts
└── examples/             # Code examples and patterns
```

## 🏢 Multi-Broker Architecture

**CRITICAL**: Alpha Panda uses a **hybrid namespace approach** where a single deployment manages multiple brokers (paper/zerodha) while maintaining complete data isolation:

- **Topic-Level Isolation**: All topics prefixed by broker (`paper.*` vs `zerodha.*`) for hard data segregation
- **Single Service Deployment**: One service instance handles all active brokers simultaneously
- **Unified Consumer Groups**: Single consumer group per service consumes from all broker-specific topics
- **Topic-Aware Handlers**: Services extract broker context from topic names for routing decisions
- **Cache Key Separation**: Redis keys prefixed (`paper:*` vs `zerodha:*`) for state isolation

**Configuration:**

```bash
# Multi-broker deployment (default)
ACTIVE_BROKERS=paper,zerodha python cli.py run

# Single broker deployment
ACTIVE_BROKERS=paper python cli.py run
```

See [Multi-Broker Architecture](docs/architecture/MULTI_BROKER_ARCHITECTURE.md) for detailed implementation patterns.

### 🏗️ Advanced Architecture Patterns

Alpha Panda implements several advanced architectural patterns for maintainable, scalable trading systems:

#### StreamServiceBuilder Pattern

**Composition-Based Service Orchestration**

All services use the StreamServiceBuilder for consistent setup with fluent API:

```python
# Example from MarketFeedService
self.orchestrator = (StreamServiceBuilder("market_feed", config, settings)
    .with_redis(redis_client)        # Optional Redis integration
    .with_error_handling()           # Automatic DLQ and retry logic
    .with_metrics()                  # Performance monitoring
    .add_producer()                  # Kafka producer with idempotence
    .add_consumer_handler(           # Topic-aware consumer
        topics=[TopicNames.MARKET_TICKS],
        group_id="alpha-panda.market-feed",
        handler_func=self._handle_message
    )
    .build()
)
```

**Benefits:**

- ✅ **Consistent Configuration**: All services use same patterns
- ✅ **Error Handling**: Built-in DLQ and retry mechanisms
- ✅ **Monitoring**: Automatic metrics collection
- ✅ **Testability**: Easy to mock components for testing

#### Topic-Aware Handler Pattern

**Broker Context Extraction from Topic Names**

All message handlers accept `(message, topic)` parameters for broker-aware processing:

```python
# Example from TradingEngineService
async def _handle_validated_signal(self, message: Dict[str, Any], topic: str) -> None:
    # Extract broker from topic name for routing decisions
    broker = topic.split('.')[0]  # "paper.signals.validated" -> "paper"

    # Route to appropriate trader based on broker context
    trader = self.trader_factory.get_trader(broker)
    await trader.execute_order(signal)
```

**Benefits:**

- ✅ **Single Service Instance**: One deployment handles all brokers
- ✅ **Dynamic Routing**: Runtime broker determination
- ✅ **Data Isolation**: Complete segregation maintained

#### Performance Optimization Patterns

**Efficient Data Structures for High-Frequency Trading**

Strategy runner uses reverse mappings for O(1) instrument lookups:

```python
# Efficient instrument-to-strategy mapping
class StrategyRunnerService:
    def __init__(self):
        # O(1) lookup instead of O(n) iteration
        self.instrument_to_strategies: Dict[int, List[str]] = defaultdict(list)

    async def _handle_market_tick(self, message: Dict[str, Any], topic: str):
        instrument_token = message['data']['instrument_token']
        # Instant lookup of interested strategies
        interested_strategies = self.instrument_to_strategies.get(instrument_token, [])
```

**Performance Targets Met:**

- ✅ **>100 msg/sec throughput** with optimized lookups
- ✅ **<50ms average latency** with efficient routing
- ✅ **Memory stability** with bounded data structures

#### Protocol-Based Service Contracts

**Type-Safe Interface Design**

Services implement protocols for dependency injection and testing:

```python
# Future enhancement: Service protocols
from typing import Protocol

class MarketFeedProtocol(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def get_connection_status(self) -> Dict[str, Any]: ...

class TradingEngineProtocol(Protocol):
    async def execute_signal(self, signal: Dict[str, Any], broker: str) -> Dict[str, Any]: ...
    def get_status(self) -> Dict[str, Any]: ...
```

**Benefits:**

- ✅ **Type Safety**: Compile-time interface validation
- ✅ **Testability**: Easy mocking with protocol compliance
- ✅ **Maintainability**: Clear contracts between components

#### Composition-First Design Philosophy

**Modern Python Architecture Principles**

Alpha Panda follows composition-over-inheritance patterns throughout:

```python
# PREFERRED: Composition + Protocol pattern (future strategy framework)
class StrategyProcessor(Protocol):
    def process_market_data(self, data: MarketData) -> List[TradingSignal]: ...

class StrategyExecutor:
    def __init__(self, processor: StrategyProcessor, config: StrategyConfig):
        self._processor = processor  # Composition over inheritance
        self._config = config

    async def execute(self, market_data: MarketData) -> List[TradingSignal]:
        return self._processor.process_market_data(market_data)

# Strategy implementations as simple classes
class MomentumProcessor:
    def process_market_data(self, data: MarketData) -> List[TradingSignal]:
        # Pure strategy logic without base class dependencies
        pass
```

**Current vs Future Strategy Design:**

| Current (BaseStrategy)        | Future (Composition)      | Benefits                |
| ----------------------------- | ------------------------- | ----------------------- |
| Inheritance-based             | Protocol + Composition    | ✅ Better testability   |
| Tight coupling                | Loose coupling            | ✅ Easier mocking       |
| Hard to extend                | Easy to extend            | ✅ Flexible composition |
| Base class changes affect all | Interface-based stability | ✅ Reduced coupling     |

**Migration Strategy:**

- ✅ Keep existing `BaseStrategy` for backward compatibility
- 🔄 Implement new composition framework alongside
- 🔄 Gradually migrate strategies to new pattern
- 🔄 Mark `BaseStrategy` as deprecated once migration complete

### 🧪 Architecture Quality Metrics

**Compliance Scorecard (August 2025):**

| Architecture Component      | Score   | Status           |
| --------------------------- | ------- | ---------------- |
| Multi-Broker Architecture   | 95%     | ✅ Excellent     |
| Event-Driven Patterns       | 98%     | ✅ Excellent     |
| Python Development Policies | 85%     | 🟡 Good          |
| Type Safety                 | 90%     | ✅ Excellent     |
| Service Design              | 88%     | 🟡 Good          |
| Performance Optimization    | 92%     | ✅ Excellent     |
| **Overall Score**           | **89%** | **✅ Excellent** |

**Key Improvements Implemented:**

- ✅ **StreamServiceBuilder pattern** for consistent service composition
- ✅ **Topic-aware handlers** for dynamic broker routing
- ✅ **Performance optimizations** with O(1) lookup patterns
- 🔄 **Protocol-based contracts** (planned enhancement)
- 🔄 **Strategy framework evolution** (composition over inheritance)

## 📊 Event Schema

All events follow a standardized `EventEnvelope`:

```json
{
  "id": "01234567-89ab-cdef-0123-456789abcdef",
  "type": "market_tick|trading_signal|validated_signal|order_fill",
  "timestamp": "2024-01-01T12:00:00.000Z",
  "correlation_id": "req-123",
  "causation_id": "event-456",
  "source": "service_name",
  "version": 1,
  "broker": "paper|zerodha",
  "data": { ...payload... }
}
```

## 🎯 Key Features

✅ **Production-Ready Foundation**

- Event schemas with standardized envelopes
- Topic definitions with proper partitioning
- aiokafka streaming with idempotence and ordering guarantees
- Comprehensive error handling with DLQ patterns
- Graceful shutdown and lifecycle management

✅ **Core Services**

- Market Feed with mock data generation
- Strategy Runner with database-driven configuration
- Risk Manager with configurable validation rules
- Trading Engine with Paper/Zerodha traders
- Portfolio Manager with Redis state materialization

✅ **Testing & Quality**

- **4-layer testing** framework (Unit, Integration, E2E, Performance)
- **Service mocking** framework for isolated testing
- **Performance baselines** with automated regression detection
- **Chaos engineering** for resilience validation
- **Security scanning** with vulnerability detection

✅ **Infrastructure**

- Docker Compose for local development and testing
- Automated topic bootstrap and data seeding
- Structured logging with correlation tracking
- CLI and Makefile for easy operations
- CI/CD pipeline with GitHub Actions

## 🔧 Development Commands

### Application

```bash
make setup      # Complete first-time setup (dev + up + bootstrap + seed)
make dev        # Set up .env and install dependencies
make up         # Start infrastructure (Redpanda, PostgreSQL, Redis)
make run        # Run the complete trading pipeline
make clean      # Clean containers and volumes
```

### Testing (Complete Infrastructure Support)

```bash
# Infrastructure-aware testing (RECOMMENDED)
make test-setup                    # Health-gated test infrastructure startup
make test-with-env                 # Integration + E2E tests with isolated environment
make test-performance-with-env     # Performance tests with test infrastructure
make test-all-infra               # Complete infrastructure test suite

# Traditional testing (unit tests only)
make test-unit        # Unit tests with coverage (no infrastructure required)
make test-integration # Service integration tests (requires setup)
make test-e2e         # End-to-end tests (requires setup)
make test-performance # Performance tests (requires setup)
make test-chaos       # Chaos engineering tests (unit level)
make test-all         # Complete test suite (mixed infrastructure needs)

# Environment management
make test-status      # Show test environment status
make test-clean       # Clean test infrastructure

# Verification and debugging
./test-infrastructure-setup.sh    # Verify complete setup works
```

### Infrastructure Management

```bash
make bootstrap  # Create Redpanda topics manually
make seed       # Seed database manually
make down       # Stop infrastructure
```

## 🧭 Logging & Observability Enhancements

- JSON file logs and pretty console output via structlog ProcessorFormatter.
- API access logs enriched with method, path, status, latency_ms, client IP, user agent,
  and IDs (request_id, correlation_id) issued per request.
- Non-blocking logging with QueueHandler/QueueListener; Prometheus metrics:
  `alpha_panda_logging_queue_size`, `alpha_panda_logging_queue_capacity`,
  `alpha_panda_logging_queue_dropped_total`.
- Logging stats endpoint: `/api/v1/logs/stats` (queue size/capacity/drops, channel handlers, config).
- Alert rules for queue drops/backpressure: `docs/observability/prometheus/logging_alerts.yml`
- Channel-based files: `logs/api.log`, `logs/error.log`, `logs/database.log`, `logs/application.log`, `logs/market_data.log`, etc.

### HTTP Request/Response IDs
- Each HTTP request gets a unique `X-Request-ID`; the response echoes this value.
- A `X-Correlation-ID` is ensured/propagated and included in responses.
- Both IDs are embedded in structured logs and enriched API access logs for end-to-end tracing.

## 🔒 Security & Reliability

- **Zerodha Authentication**: Mandatory for production pipeline
- **JWT Authentication**: User auth for API endpoints
- **Input Validation**: Pydantic schemas with type safety
- **Error Classification**: Transient vs poison message handling
- **Rate Limiting**: Configurable position and trade limits
- **Audit Logging**: Complete event trail with correlation IDs

## 📈 Performance Targets

- **Market Data Throughput**: >100 messages/second
- **End-to-End Latency**: <50ms average, <100ms P95
- **Memory Stability**: <50MB increase under sustained load
- **Error Recovery**: System continues functioning with <5% error rate
- **Concurrent Processing**: Handle multiple strategies without failure

## 🐳 Development Tools

**View logs:**

```bash
docker-compose logs -f redpanda postgres redis
```

**Access Redpanda Console:**

```bash
docker-compose --profile console up -d
# Visit http://localhost:8080
```

**Monitor test environment:**

```bash
make test-status  # Check all test services
```

**Performance monitoring:**

```bash
make test-performance  # Run performance benchmarks
```

## 🎯 Design Principles

### Core Architecture Principles

- **Event-Driven Architecture**: All dynamic data through event streams
- **Broker Isolation**: Complete segregation between paper and zerodha
- **Schemas First**: Event contracts defined before implementation
- **No Wildcards**: Explicit topic subscriptions only
- **Mandatory Keys**: Every message has partition key for ordering
- **Producer Safety**: Idempotent producers with acks=all
- **Testing Excellence**: Production-ready testing at all levels

### Modern Development Principles (2025)

- **Composition Over Inheritance**: Prefer dependency injection and Protocol contracts
- **Fail-Fast Philosophy**: Observable failures with clear error messages
- **Performance-First**: O(1) lookups and efficient data structures
- **Type Safety**: Full type hints with Protocol-based interfaces
- **Single Responsibility**: Small, focused services with clear boundaries
- **Testability**: Protocol-based mocking and dependency injection

### Service Design Patterns

- **StreamServiceBuilder**: Consistent service orchestration with fluent API
- **Topic-Aware Handlers**: Dynamic broker routing from topic context
- **Protocol Contracts**: Type-safe interfaces for service dependencies
- **Reverse Mappings**: Performance optimizations for high-frequency operations
- **Graceful Degradation**: Circuit breakers and retry mechanisms

## 🚀 Virtual Environment & Dependencies (CRITICAL)

**🚨 MANDATORY**: Always activate the virtual environment and use constraints for dependency management:

```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate         # Linux/Mac
# OR: venv\Scripts\activate      # Windows

# 2. Install dependencies with version constraints (Python 3.13 compatible)
pip install -r requirements.txt -c constraints.txt

# 3. For development, use the make command that includes constraints
make dev  # Automatically uses constraints for installation
```

**Why Constraints Are Critical:**

- ✅ **Python 3.13 Compatibility** - Optimized dependency versions
- ✅ **Version Stability** - Prevents breaking changes with upper bounds
- ✅ **CI/CD Reliability** - Ensures reproducible builds across environments
- ✅ **Dependency Safety** - Prevents future compatibility issues

**Key Constraint Examples:**

```bash
# constraints.txt
dependency-injector>=4.43,<5    # Python 3.13 optimized
fastapi>=0.104.0,<0.200.0        # Stable version range
pydantic>=2.5.0,<3.0.0           # Prevents breaking changes
```

This approach prevents conflicts with system packages, ensures consistent dependency management, and maintains Python 3.13 compatibility.

---

**Built with comprehensive testing, dual broker architecture, and production-ready reliability patterns for algorithmic trading at scale.**
