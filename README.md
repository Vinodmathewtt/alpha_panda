# 🐼 Alpha Panda - Algorithmic Trading System

A modern algorithmic trading system built on the Unified Log architecture using Redpanda for event streaming. Features comprehensive testing, dual broker architecture, and production-ready reliability patterns.

## 🏗️ Architecture

**Unified Log Architecture with Redpanda**
- **Single Source of Truth**: All dynamic data flows through Redpanda event streams
- **Dual Broker System**: Complete isolation between paper and zerodha trading
- **Configuration Store**: Static configuration in PostgreSQL  
- **Read Path**: FastAPI serves from Redis cache
- **Pure Strategy Logic**: Strategies are completely decoupled from infrastructure

**End-to-End Pipeline Flow:**
```
Market Feed Service
       ↓ (market.ticks topic - shared)
Strategy Runner Service  
       ↓ (broker.signals.raw topic - e.g., paper.signals.raw)
Risk Manager Service
       ↓ (broker.signals.validated topic - e.g., paper.signals.validated)
Trading Engine Service
       ↓ (broker.orders.filled topic - e.g., paper.orders.filled) 
Portfolio Manager Service
       ↓ (Redis cache with broker prefix - e.g., paper:portfolio:)
API Service (Read Path)
```

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

4. **Run Alpha Panda:**
```bash
make run  # Starts the complete trading pipeline
```

**Or do it all in one step:**
```bash
make setup  # Complete first-time setup
```

### 🧪 Quick Testing

```bash
# 1. Run unit tests (no infrastructure needed)
python -m pytest tests/unit/ -v

# 2. Set up test infrastructure (health-gated)
make test-setup

# 3. Run infrastructure tests with isolated environment
make test-with-env                 # Integration + E2E tests
make test-performance-with-env     # Performance tests

# 4. Clean up test environment
make test-clean
```

## 🧪 Comprehensive Testing Framework

Alpha Panda includes a **production-ready testing framework** with **complete environment isolation** and health-gated startup for reliable CI/CD execution.

### 🏗️ Test Environment Architecture

**Complete Infrastructure Isolation:**
- **Development Environment**: `localhost:5432`, `:6379`, `:9092`
- **Test Environment**: `localhost:5433`, `:6380`, `:19092` 
- **Zero Conflicts**: Run dev and test environments simultaneously
- **Health-Gated Startup**: All services wait for readiness before testing

### 🚀 Quick Test Setup

```bash
# 1. Install dependencies with version constraints
pip install -r requirements.txt -c constraints.txt

# 2. Start test infrastructure with health checks
make test-setup
# This runs: docker compose -f docker-compose.test.yml up -d && wait

# 3. Run tests with proper environment isolation
make test-with-env                 # Integration + E2E tests
make test-performance-with-env     # Performance tests
make test-all-infra               # Complete infrastructure test suite

# 4. Clean up when done
make test-clean
```

### 🔧 Advanced Test Commands

```bash
# Traditional test commands (unit tests only)
make test-unit        # Unit tests with coverage
make test-integration # Service integration tests  
make test-e2e         # End-to-end pipeline tests
make test-performance # Performance and load tests
make test-chaos       # Chaos engineering tests

# New infrastructure-aware commands
make test-setup                    # Health-gated infrastructure startup
make test-with-env                 # Tests with isolated test environment
make test-performance-with-env     # Performance tests with test env
make test-all-infra               # Complete infrastructure test suite

# Monitoring and cleanup
make test-status      # Check test environment status
make test-clean       # Clean test infrastructure
```

### 🏥 Health-Gated Infrastructure

**Modern Docker Compose Approach:**
```bash
# Start with health checks
docker compose -f docker-compose.test.yml up -d
docker compose -f docker-compose.test.yml wait  # 🔑 CRITICAL

# Health checks ensure services are ready:
# ✅ Redpanda: rpk cluster info
# ✅ PostgreSQL: pg_isready -U alpha_panda_test  
# ✅ Redis: redis-cli ping
```

### 📁 Test Environment Configuration

**Isolated Test Configuration (`.env.test`):**
```bash
# Test-specific ports and databases
DATABASE_URL=postgresql+asyncpg://alpha_panda_test:test_password@localhost:5433/alpha_panda_test
REDIS_URL=redis://localhost:6380
REDPANDA_BOOTSTRAP_SERVERS=localhost:19092

# Test-specific settings
ENVIRONMENT=testing
MOCK_MARKET_FEED_ENABLED=true
MOCK_ZERODHA_ENABLED=true
```

### 🐳 Test Infrastructure Components

**docker-compose.test.yml Services:**
```yaml
redpanda-test:    # Port 19092 (isolated from dev 9092)
  healthcheck: ["CMD-SHELL", "rpk cluster info"]
  
postgres-test:   # Port 5433 (isolated from dev 5432) 
  healthcheck: ["CMD-SHELL", "pg_isready -U alpha_panda_test"]
  
redis-test:      # Port 6380 (isolated from dev 6379)
  healthcheck: ["CMD", "redis-cli", "ping"]
```

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
│   ├── trading_engine/    # Order execution (broker-segregated)
│   └── portfolio_manager/ # Portfolio state (broker-segregated)
├── strategies/            # Pure trading strategy logic
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

## 🏢 Dual Broker Architecture

**CRITICAL**: Alpha Panda treats paper trading and Zerodha trading as **completely separate brokers** with full data isolation and independent execution paths.

See [Architecture Documentation](docs/architecture/) for detailed implementation patterns.

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

- **Event-Driven Architecture**: All dynamic data through event streams
- **Broker Isolation**: Complete segregation between paper and zerodha
- **Schemas First**: Event contracts defined before implementation
- **No Wildcards**: Explicit topic subscriptions only
- **Mandatory Keys**: Every message has partition key for ordering
- **Producer Safety**: Idempotent producers with acks=all
- **Testing Excellence**: Production-ready testing at all levels

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