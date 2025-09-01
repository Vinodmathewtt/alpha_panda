# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Alpha Panda is an algorithmic trading system built on Unified Log architecture using Redpanda for event streaming. It follows a microservices architecture where all dynamic data flows through event streams, with PostgreSQL for configuration storage and Redis for API caching.

**Architecture**: Alpha Panda follows the **Unified Log architecture** with Redpanda as the single source of truth for all dynamic data, PostgreSQL for configuration, and Redis for API caching. Uses aiokafka + Redpanda (NOT NATS JetStream).

## Architecture

**Core Pattern**: Unified Log with Event Streaming using Redpanda. See [Architecture Documentation](docs/architecture/) for detailed implementation.

**🔐 MANDATORY AUTHENTICATION**: Zerodha authentication is **ALWAYS REQUIRED** for the full trading pipeline (`cli.py run`). Mock mode only for testing.

**🏢 CRITICAL: HYBRID MULTI-BROKER ARCHITECTURE**: Alpha Panda uses a **hybrid namespace approach** where a single deployment manages multiple brokers while maintaining complete data isolation:
- **Topic-Level Isolation**: All topics prefixed by broker (`paper.*` vs `zerodha.*`) for hard data segregation
- **Single Service Deployment**: One service instance handles all active brokers simultaneously
- **Unified Consumer Groups**: Single consumer group per service consumes from all broker-specific topics
- **Topic-Aware Handlers**: Services extract broker context from topic names for routing decisions
- **Cache Key Separation**: Redis keys prefixed (`paper:*` vs `zerodha:*`) for state isolation

**📊 Market Data Architecture**: Market data uses a **single-broker feed model** - currently only Zerodha-based market feed (`market.ticks` topic) regardless of active brokers. This ensures strategy consistency between paper and live trading, while all other application components (trading engines, portfolio management, risk management) follow the multi-broker architecture.

**📖 Detailed Documentation**: See [Multi-Broker Architecture](docs/architecture/MULTI_BROKER_ARCHITECTURE.md) for complete implementation details, deployment patterns, and fault isolation benefits.

**✅ DOCUMENTATION UPDATE STATUS**: The architecture has been successfully migrated from environment-specific deployments (`BROKER_NAMESPACE`) to unified multi-broker deployments (`ACTIVE_BROKERS`). **All module-level documentation has been comprehensively updated** to reflect the current architecture, including complete README.md files for all core modules, services, and components.

**🏷️ NAMESPACE DISTINCTION**: Do not confuse `BROKER_NAMESPACE` env var (❌ removed) with `broker_namespace` parameter (✅ valid for metrics). See README.md namespace section for details.

## Service Architecture

All services follow stream processing pattern with complete broker segregation. See [Services Documentation](services/) for detailed execution flow and patterns.

## Development Commands

See [README.md](README.md) for complete setup instructions and testing commands.

### Quick Setup
```bash
make setup          # Complete first-time setup
make run            # Run the complete trading pipeline
```

### Virtual Environment Rule
**🚨 MANDATORY**: Always activate the virtual environment before running any Python commands.

### Environment Configuration Policy
**🔧 .env FILE POLICY**: The project uses `.env` and `.env.example` files for environment configuration and these files are intentionally kept in the repository for operational simplicity. This is a deliberate architectural decision for this project:
- `.env` and `.env.example` files are part of the codebase and should remain
- These files contain configuration templates and development defaults
- Production secrets are handled through deployment-specific environment variables
- **DO NOT** remove or ignore these files unless explicitly requested

## Key Technologies

- **Event Streaming**: aiokafka with Redpanda (NOT confluent-kafka, NOT NATS JetStream)
- **Database**: PostgreSQL with SQLAlchemy async
- **Cache**: Redis with async client  
- **API**: FastAPI with dependency injection
- **Config**: Pydantic Settings with .env support
- **Logging**: structlog for structured logging
- **Authentication**: JWT for API, Zerodha KiteConnect for market data
- **Zerodha SDK**: Reference implementation in `examples/pykiteconnect-zerodha-python-sdk-for-reference/`

## Critical Architecture Patterns

**📁 Code Examples**: All implementation patterns are demonstrated with working code examples in the `examples/` directory. See `examples/README.md` for a complete overview of available patterns and their usage.

### Event Envelope Standard
ALL events MUST use `EventEnvelope` from `core/schemas/events.py`. See example format and implementation in `examples/trading/message_publishing.py`.

**Critical Fields**:
- `id`: Globally unique UUID v7 for event deduplication
- `correlation_id`: Links related events across services for tracing
- `causation_id`: Points to the event that caused this one
- `broker`: Audit field only - NEVER use for routing (use topic namespaces)

### Streaming Patterns
- **Producer Keys**: Every message MUST have partition key for ordering
- **Consumer Groups**: Each service has unique consumer group ID  
- **Topic Routing**: Route by topic namespace, NO wildcard subscriptions
- **Idempotent Producers**: acks='all', enable_idempotence=True
- **Manual Offset Commits**: Disable auto-commit, commit only after successful processing
- **Graceful Shutdown**: await consumer.stop() and await producer.stop() (includes flush)
- **Event Deduplication**: Consumer-side dedup using event_id in Redis with TTL
- **DLQ Pattern**: Bounded retries (3-5 attempts) → Dead Letter Queue → Replay tool

### Broker-Namespaced Topic Taxonomy
**CRITICAL**: Topics are namespaced by broker to ensure hard segregation:

#### Topic Naming Convention
**Format**: `{broker}.{domain}.{event_type}[.dlq]`

**Examples**: market.ticks (shared), paper.signals.raw, zerodha.signals.validated, paper.orders.filled, zerodha.orders.filled, paper.orders.filled.dlq (Dead Letter Queue)

#### Complete Topic Map
See complete topic mapping in `examples/architecture/topic_configuration.py`:
- **Market Data (shared)**: market.ticks
- **Paper Trading**: paper.signals.raw, paper.signals.validated, paper.orders.submitted, paper.orders.ack, paper.orders.filled, paper.pnl.snapshots, paper.*.dlq
- **Zerodha Trading**: zerodha.signals.raw, zerodha.signals.validated, zerodha.orders.submitted, zerodha.orders.ack, zerodha.orders.filled, zerodha.pnl.snapshots, zerodha.*.dlq

#### Topic Configuration Class
See implementation example: `examples/architecture/topic_configuration.py`

#### Hard Isolation Guardrails
- **ACLs**: Paper services can only READ/WRITE `paper.*` topics
- **ACLs**: Zerodha services can only READ/WRITE `zerodha.*` topics  
- **Schema Registry**: Separate subjects: `paper.orders.filled-v2`, `zerodha.orders.filled-v2`
- **CI Checks**: Reject builds that reference both `paper.*` and `zerodha.*` in same service
- **Redis Isolation**: Separate key prefixes: `paper:` vs `zerodha:`
- **Database Isolation**: Separate schemas or credential-level separation

### Delivery Semantics & Deduplication
**CRITICAL**: Producer idempotence alone does NOT guarantee exactly-once delivery:

#### Event Deduplication Strategy
See implementation example: `examples/streaming/event_deduplication.py`

#### Offset Commit Strategy
See implementation example: `examples/streaming/offset_commit_strategy.py`

### Service Architecture (From docs/IMPLEMENTATION_PLAN.md)
Services are in `services/` directory, each following the stream processing pattern with **complete broker segregation**:

**🌐 SHARED SERVICES** (Single-broker model):
- **Market Feed Service**: Single service publishing to shared `market.ticks` topic using **Zerodha API only** (single-broker market feed for all active brokers)
- **Auth Service**: Handles JWT authentication and user management

**🏢 MULTI-BROKER SERVICES** (Single instance handling multiple brokers):
- **Strategy Runner Service**: Loads strategies from database, processes ticks, emits signals to all configured broker-specific `{broker}.signals.raw` topics
- **Risk Manager Service**: Validates signals from all brokers, emits to appropriate `{broker}.signals.validated` or `{broker}.signals.rejected` topics
- **Paper Trading Service**: Consumes `paper.signals.validated`, emits `paper.orders.*` and `paper.pnl.snapshots`
- **Zerodha Trading Service**: Consumes `zerodha.signals.validated`, emits `zerodha.orders.*` and `zerodha.pnl.snapshots`

**🔧 HYBRID ARCHITECTURE PATTERNS**:
- **Topic-Aware Handlers**: All message handlers accept `(message, topic)` parameters to extract broker context
- **Active Brokers Configuration**: Services use `settings.active_brokers` list to determine which brokers to handle
- **Unified Consumer Groups**: Single consumer group per service processes all broker-specific topics
- **Dynamic Topic Subscription**: Services generate topic lists based on active brokers at startup

### Strategy Framework
Alpha Panda supports **dual strategy architectures** with orchestration in the services layer:

**Strategy Library** (`strategies/` directory):
- **Legacy**: Inheritance-based strategies (currently active in production)  
- **Modern**: Composition-based framework with protocols (recommended for new strategies)
- **Pure Logic**: No direct infrastructure access (database, Kafka, etc.)

**Strategy Orchestration** (services layer):
- **Entry Point**: `cli.py run` starts all services including strategy runner
- **Main Orchestrator**: `services/strategy_runner/service.py` loads and executes strategies
- **Factory Pattern**: `strategies/core/factory.py` creates strategy executors on demand
- **Database Integration**: Strategies loaded from PostgreSQL with YAML fallback

## Project Structure

See [README.md](README.md) for complete project structure. **All key modules have comprehensive documentation**:

### Core Modules (📁 Complete Documentation)
- [Core Module](core/README.md) - Shared libraries, utilities, and architectural patterns
- [Core Config](core/config/README.md) - Pydantic settings and configuration management
- [Core Database](core/database/README.md) - PostgreSQL integration with async SQLAlchemy
- [Core Health](core/health/README.md) - Health checking and monitoring systems
- [Core Logging](core/logging/README.md) - Enhanced structured logging with correlation tracking
- [Core Market Hours](core/market_hours/README.md) - Indian stock market hours validation
- [Core Schemas](core/schemas/README.md) - Event contracts and topic definitions
- [Core Services](core/services/README.md) - Base service classes and patterns
- [Core Utils](core/utils/README.md) - Utilities, exceptions, and state management

### Service Modules (🚀 Complete Documentation)
- [Services](services/README.md) - Stream processing microservices overview
- [Auth Service](services/auth/README.md) - Authentication with multi-provider support
- [Instrument Data](services/instrument_data/README.md) - Financial instrument management
- Broker-scoped trading services replace legacy trading engine and portfolio manager:
  - `services/paper_trading/` - Paper execution and portfolio updates
  - `services/zerodha_trading/` - Zerodha execution and portfolio updates
- [Risk Manager](services/risk_manager/README.md) - Risk validation and signal filtering
- [Strategy Runner](services/strategy_runner/README.md) - Strategy execution and signal generation

### Strategy Framework (🧠 Complete Documentation)  
- [Strategies](strategies/README.md) - Dual architecture: composition + legacy patterns
- [Architecture Docs](docs/architecture/README.md) - Multi-broker architecture details

### Application Layer (⚡ Updated Documentation)
- [Application](app/README.md) - Application orchestration and lifecycle management
- [API Layer](api/README.md) - FastAPI REST endpoints and services

## Testing

**Comprehensive Testing Framework**: Production-ready 4-layer testing. See [README.md](README.md) for complete testing setup and commands.

### Key Testing Patterns
- **Unit Tests**: 67 passing tests, no infrastructure required
- **Integration Tests**: Service interactions with isolated test environment
- **E2E Tests**: Full pipeline validation
- **Performance Tests**: Load testing with >100 msg/sec throughput targets

### Critical Testing Infrastructure
- **Health-Gated Startup**: `docker compose -f docker-compose.test.yml wait`
- **Complete Isolation**: Separate test ports (19092, 5433, 6380)
- **Example Patterns**: See `examples/testing/` for implementation patterns

## Configuration

Settings via `core/config/settings.py` with .env file support. Key configuration areas:

**🚨 CRITICAL**: Zerodha authentication is **MANDATORY** for `cli.py run`. Application will fail fast if authentication unavailable.

### Hybrid Multi-Broker Deployment Configuration

**ACTIVE_BROKERS Environment Variable**: Core configuration for multi-broker support:

```bash
# Single deployment managing multiple brokers (default)
ACTIVE_BROKERS=paper,zerodha python cli.py run

# Single broker deployment (if needed)
ACTIVE_BROKERS=paper python cli.py run
```

**Unified Service Architecture**:
- Single service instance handles all configured active brokers
- Unified consumer groups process all broker-specific topics: `alpha-panda.trading-engine.signals`
- Topic-aware handlers extract broker context from topic names: `paper.signals.raw` vs `zerodha.signals.raw`
- Redis cache keys remain broker-prefixed for isolation: `paper:portfolio:` vs `zerodha:portfolio:`
- Services dynamically subscribe to topics for all active brokers at startup

## Important Files

- `cli.py`: Main CLI interface
- `app/main.py`: Application entry point with graceful shutdown
- `core/schemas/events.py`: Standardized event contracts
- `docker-compose.yml`: Development infrastructure
- `Makefile`: Development automation
- `docs/improvements/`: Long-term system improvement guidelines and monitoring enhancements

## Critical Development Rules

**🚨 MANDATORY RULES**: These rules MUST be followed in all development work.

### Event-Driven Architecture Rules (MANDATORY)
1. **Standardized Event Envelopes** - ALL events must use EventEnvelope format with type, ts, key, source, version, data
2. **Message Keys & Ordering** - MANDATORY partition keys for all topics to guarantee ordering
3. **Topic Routing** - Route by topic name only, NO wildcard subscriptions
4. **Unique Consumer Groups** - Each service has its own group ID (alpha-panda.service-name)
5. **Producer Idempotence** - acks='all', enable_idempotence=True for all producers
6. **Graceful Shutdown** - Always call producer.flush() before stopping services

### Trading Engine Segregation Rules (CRITICAL ENHANCEMENT)
7. **NEVER mix trading modes** - Paper and zerodha trading data must be completely separate
8. **Topic segregation by mode** - Use separate topics for paper vs zerodha (e.g., orders.filled.paper vs orders.filled.zerodha)
9. **Source identification** - Always include trading_mode field in event data
10. **Configuration-driven routing** - Use database configuration to determine zerodha trading eligibility per strategy
11. **Safety defaults** - All signals go to paper trading by default, zerodha trading is explicit opt-in
12. **Separate trader classes** - PaperTrader and ZerodhaTrader must remain completely independent

### Critical Error Handling Rules (UPDATED)
13. **Structured Retry Pattern** - Classify errors, retry transient failures with exponential backoff
14. **Authentication Error Flow** - For broker auth failures, gracefully degrade to mock data and alert operations
15. **Structured exception hierarchy** - Use defined exceptions in core/utils/exceptions.py
16. **Graceful degradation** - Critical: Portfolio state rebuilding, cache warm-up from events
17. **Correlation IDs** - Include for request tracking and debugging across service boundaries
18. **DLQ Monitoring** - Alert on DLQ accumulation, provide replay tooling for operations team

### **🚨 CRITICAL: Fail-Fast Policy (MANDATORY)**
**The system must fail fast and fail hard - errors should surface immediately and stop execution rather than being ignored. Silent failures are prohibited; every failure must be observable.**

19. **No Silent Failures** - Every error must be logged, alerted, or raise an exception. Silent failures are prohibited
20. **Fail-Fast on Missing Dependencies** - If critical files (CSV, config files) are missing, system must fail immediately with clear error messages
21. **No Fallback Data in Production** - Never use hardcoded fallbacks for production data (instruments, configurations, etc.)
22. **Explicit Error Propagation** - Errors must bubble up through service layers with clear context
23. **Observable Failures** - All failures must be observable via logs, metrics, alerts, or exceptions
24. **Graceful Shutdown on Critical Errors** - When critical dependencies fail, perform graceful shutdown rather than continue with degraded functionality
25. **Clear Error Messages** - Error messages must be actionable and specify exactly what needs to be fixed

### CRITICAL FIX PREVENTION GUIDELINES (2025 Update)
**🚨 MANDATORY**: These guidelines prevent critical integration breakages that can cause 500 errors and system failures.

### Event Schema Validation Rules (MANDATORY - Updated 2025-08-29)
**🚨 CRITICAL**: Prevent Pydantic validation errors at runtime by ensuring schema compliance at development time.

1. **Always Include Required Fields**: All event models must be created with ALL required fields specified in their Pydantic schema
   - `OrderFilled` MUST include: `broker`, `order_id`, `instrument_token`, `quantity`, `fill_price`, `timestamp`
   - `OrderPlaced` MUST include: `broker`, `status`, `order_id`, `instrument_token`, `signal_type`, `quantity`, `price`, `timestamp`
   - `OrderFailed` MUST include: `broker`, `strategy_id`, `instrument_token`, `signal_type`, `quantity`, `order_id`, `execution_mode`, `error_message`, `timestamp`

2. **Broker Field Mandatory**: ALL order events must specify the broker field explicitly (`"paper"` or `"zerodha"`)

3. **Schema Validation Testing**: Implement unit tests that validate event model creation for all traders and services

4. **Interface Method Consistency**: Service method calls must match interface definitions
   - Portfolio managers must implement both `handle_*` and `process_*` method families
   - Service calls must use methods that exist in the interface

5. **Message Producer Envelope Compliance**: ALL producer.send() calls must include `broker` parameter for proper event envelope generation

#### API Dependencies and Imports
1. **Always verify imports exist** - Before importing functions like `get_settings`, `get_redis_client`, ensure they exist in the target module
2. **Use dependency injection consistently** - All API dependencies must use `@inject` decorator with `Provide[AppContainer.resource]` pattern  
3. **Test endpoint imports** - After adding new API endpoints, verify all imported functions exist and are properly configured

#### Service Integration Patterns
4. **Event loop management** - Always capture the running event loop in async service `start()` methods: `self.loop = asyncio.get_running_loop()`
5. **Schema field consistency** - Use consistent field names across schemas and services (e.g., `execution_mode` not `trading_mode`)
6. **Topic naming consistency** - Market data always uses shared topics (`TopicNames.MARKET_TICKS`), not broker-specific topics
7. **EventType enum usage** - Always use `EventType.ORDER_FILLED` instead of string literals like `'order_filled'`

#### Configuration and Portability
8. **Dynamic path resolution** - Never hardcode absolute paths in settings; use `Path(__file__).resolve().parents[N]` for project root
9. **Environment-agnostic design** - Ensure settings work across different development environments and operating systems

#### Type Safety and Signatures
10. **Match function signatures with calls** - Ensure type hints match actual function calls (e.g., handler functions)
11. **Validate method implementations** - When routers call service methods, ensure those methods exist with correct signatures

#### Service Architecture Validation
12. **End-to-end flow validation** - Before deployment, validate complete message flow from market data to portfolio updates
13. **Cross-service schema alignment** - Regularly validate that event schemas match across all services that produce/consume them

#### Implementation Verification Checklist
Before marking any feature complete, verify:

**Basic Integration Requirements:**
- [ ] All imported functions exist in their modules
- [ ] All service methods called by routers are implemented  
- [ ] Event loops are properly captured in threaded operations
- [ ] Schema fields match between producers and consumers
- [ ] Paths are dynamic and environment-agnostic
- [ ] Type hints match actual function signatures
- [ ] EventType enums are used instead of string literals

**Enhanced Architecture Compliance (2025 Update):**
- [ ] Services use StreamServiceBuilder pattern for stream processing setup
- [ ] Message handlers accept (message, topic) parameters for broker context extraction
- [ ] Protocol contracts defined for service interfaces where applicable
- [ ] Composition preferred over inheritance in strategy and service design
- [ ] Instrument-to-strategy mappings use O(1) lookup patterns for performance
- [ ] Topic-aware handlers properly extract broker context from topic names
- [ ] Service protocols implemented for dependency injection contracts
- [ ] Performance optimization patterns implemented (reverse mappings, efficient lookups)

### CRITICAL: Trading Engine Segregation (Current Implementation Enhancement)
**🎯 FUNDAMENTAL PRINCIPLE**: Paper and Zerodha are treated as **DISTINCT BROKERS**, each with complete isolation:

#### Topic Segregation by Trading Mode
- **Paper Trading Topics**: `orders.placed.paper`, `orders.filled.paper`, `orders.failed.paper`
- **Zerodha Trading Topics**: `orders.placed.zerodha`, `orders.filled.zerodha`, `orders.failed.zerodha`
- **NEVER mix paper and zerodha data** in the same topics

#### Service-Level Segregation
- **PaperTrader**: Completely separate class handling only simulated execution
- **ZerodhaTrader**: Completely separate class handling only zerodha broker integration
- **TradingEngineService**: Routes validated signals to appropriate trader based on configuration

#### Configuration-Based Routing
- **Global Settings**: `settings.paper_trading.enabled`, `settings.zerodha.enabled`
- **Per-Strategy Configuration**: Database-driven `zerodha_trading_enabled` flag per strategy
- **Default Behavior**: ALL signals go to paper trading, opt-in for zerodha trading per strategy

#### Data Isolation Patterns
See implementation example: `examples/trading/trading_engine_routing.py`

### Redpanda/aiokafka Integration Rules (CRITICAL)
**Critical Fixes SUCCESSFULLY APPLIED**:
- ✅ EventEnvelope standardization across all services
- ✅ Message keys for ordering guarantees
- ✅ Unique consumer groups per service
- ✅ Topic routing by name, not message content
- ✅ Producer idempotence settings

## File Organization Rules (CRITICAL)

**🚨 MANDATORY FILE PLACEMENT RULES**:
1. **ALL test files MUST be created in the `tests/` folder** (if created)
2. **ALL standalone scripts MUST be created in the `scripts/` folder**
3. **ALL documents MUST be created in the `docs/` folder** in application root (README.md are exceptions; documents can also be created in dedicated `docs/` folders inside modules or application folders)
4. **Archive documents to `docs/` folder if needed**
5. **Avoid duplicate folder names between root and core modules**
6. **Configuration organization**:
   - Central config: `core/config/` (used across modules)
   - Module-specific config: `{module}/config/` (single module)
7. **Fix application code when issues identified during testing**
8. **Do NOT modify application code just to make testing convenient**

## Documentation Standards (Updated 2025-08-30)

**✅ COMPREHENSIVE DOCUMENTATION COMPLETE**: All core modules, services, and components now have complete README.md files that accurately reflect the current architecture and implementation patterns.

### Documentation Maintenance Rules
- **Module-Level Documentation**: Each module has comprehensive README.md with usage examples, architecture patterns, and best practices
- **Current State Compliance**: All documentation reflects modern StreamServiceBuilder patterns, multi-broker architecture, and composition-first design
- **No Outdated References**: Documentation updated to remove deprecated `BROKER_NAMESPACE` references and include current `ACTIVE_BROKERS` configuration
- **Consistent Architecture**: All documentation aligns with the unified log architecture and topic-aware handler patterns

### Future Documentation Updates
- **Incremental Updates**: Update relevant module README.md when making implementation changes
- **CLAUDE.md Updates**: Only for major architectural changes, keep updates minimal and concise
- **New Components**: Follow established documentation patterns when creating new modules or services

## Python Development Policies

**🐍 COMPOSITION-FIRST OOP**: Follow composition-first object-oriented programming principles for maintainable, testable code. See [Python Development Policies](docs/development/PYTHON_DEVELOPMENT_POLICIES.md) for detailed guidelines and examples.

### Core Python Principles
- **Prefer composition + protocols over inheritance** - Default to no inheritance; use `typing.Protocol` for contracts
- **Small, explicit objects** - Keep classes focused (≤7 public methods), avoid God objects
- **Dependency injection** - Pass dependencies via constructor, use protocol-typed parameters
- **Immutability preferred** - Use `@dataclass(slots=True, frozen=True)` for value objects
- **Type safety mandatory** - Full type hints on all public APIs, run mypy/pyright in CI

### Architecture Patterns
- **Domain isolation** - Domain must not import adapters; adapters depend on domain only
- **Protocol-based contracts** - Use `typing.Protocol` for interfaces, enable duck typing
- **ABC Reduction Policy** - Minimize abstract base classes; use protocols for contracts, only ABC for framework adapters
- **Factory functions** - Module-level factories for object assembly, avoid global singletons
- **Error handling** - Custom exceptions flat hierarchy, convert external errors at boundaries

### Development Rules
- **No inheritance by default** - Only for framework adapters, stable hierarchies, tiny mixins (one level max)
- **Protocol over ABC** - Use `typing.Protocol` for contracts; minimize abstract base classes to framework adapters only
- **Pure domain logic** - Keep I/O at edges, core domain sync and pure where possible
- **Explicit over implicit** - No metaclass magic, clear naming (nouns for classes, verbs for methods)

### Trading-Specific Rules
- **Concurrency boundaries** - Message passing over shared state; lock wrappers only in adapters
- **Decimal precision** - All monetary values use `Decimal`, never `float`; currency-aware quantization
- **Event sourcing** - Aggregates as state machines; monotonic versioning; optimistic concurrency

### Architecture Improvement Guidelines (2025 Update)

**🚨 PRIORITY IMPROVEMENTS**: Based on comprehensive codebase review, focus on these areas for enhanced compliance:

#### 1. Strategy Framework Enhancement (HIGH PRIORITY)
**Current Issue**: `BaseStrategy` uses inheritance pattern where composition would be preferred.

**RECOMMENDED APPROACH**: Replace inheritance-based strategy framework with composition + Protocol pattern:

```python
# PREFERRED: Protocol-based contracts
from typing import Protocol, List
from core.schemas.events import MarketData, TradingSignal

class StrategyProcessor(Protocol):
    """Protocol defining strategy processing contract"""
    def process_market_data(self, data: MarketData) -> List[TradingSignal]: ...
    def get_required_history(self) -> int: ...
    def supports_instrument(self, token: int) -> bool: ...

class StrategyExecutor:
    """Composition-based strategy executor"""
    def __init__(self, 
                 processor: StrategyProcessor,
                 config: StrategyConfig,
                 brokers: List[str],
                 instruments: List[int]):
        self._processor = processor  # Composition over inheritance
        self._config = config
        self.brokers = brokers
        self.instrument_tokens = instruments
        self._history: List[MarketData] = []
    
    async def execute(self, market_data: MarketData) -> List[TradingSignal]:
        """Execute strategy using composed processor"""
        self._update_history(market_data)
        return self._processor.process_market_data(market_data)

# Strategy implementations as simple classes implementing Protocol
class MomentumProcessor:
    def process_market_data(self, data: MarketData) -> List[TradingSignal]:
        # Pure strategy logic
        pass
```

**ABC REDUCTION MIGRATION STRATEGY**:

**Phase 1: No New ABC Usage**
- New interfaces should use `typing.Protocol`
- Document ABC as legacy pattern
- All new strategy implementations use composition + protocols

**Phase 2: Protocol Migration**
- Create Protocol alternatives for existing ABCs
- Add compatibility bridges (e.g., `CompatibilityAdapter` for `BaseStrategy`)
- Parallel development with both patterns supported

**Phase 3: Legacy ABC Retirement**
- Mark ABC classes as deprecated with migration timelines
- Migrate remaining usage to Protocols
- Remove deprecated ABCs after full transition

**Current State**: Phase 2 implemented - composition framework with Protocol contracts available alongside legacy `BaseStrategy` ABC

#### 2. Service Protocol Definitions (MEDIUM PRIORITY)
**Current Issue**: Missing Protocol definitions for service contracts.

**ADD PROTOCOLS FOR**:

```python
# services/protocols.py - NEW FILE TO CREATE
from typing import Protocol, Dict, Any
from datetime import datetime

class MarketFeedProtocol(Protocol):
    """Contract for market data feed services"""
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def get_connection_status(self) -> Dict[str, Any]: ...
    def get_metrics(self) -> Dict[str, int]: ...

class TradingEngineProtocol(Protocol):
    """Contract for trading engine services"""
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def execute_signal(self, signal: Dict[str, Any], broker: str) -> Dict[str, Any]: ...
    def get_status(self) -> Dict[str, Any]: ...

class PortfolioManagerProtocol(Protocol):
    """Contract for portfolio management services"""
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def update_position(self, order_fill: Dict[str, Any]) -> None: ...
    async def get_portfolio_snapshot(self, broker: str) -> Dict[str, Any]: ...

class RiskManagerProtocol(Protocol):
    """Contract for risk management services"""
    async def validate_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]: ...
    def get_risk_limits(self, strategy_id: str) -> Dict[str, Any]: ...
```

**IMPLEMENTATION STRATEGY**:
- Add Protocol imports to existing service classes: `from services.protocols import MarketFeedProtocol`
- Update service factory methods to accept Protocol types
- Use Protocols in dependency injection containers
- Add runtime Protocol compliance validation in tests

#### 3. Enhanced Architectural Patterns Documentation

**MISSING PATTERNS TO DOCUMENT**:

**StreamServiceBuilder Pattern**:
```python
# Key architectural component for service composition
self.orchestrator = (StreamServiceBuilder("service_name", config, settings)
    .with_redis(redis_client)           # Optional Redis integration
    .with_error_handling()              # Automatic DLQ and retry logic
    .with_metrics()                     # Performance monitoring
    .add_producer()                     # Kafka producer with idempotence
    .add_consumer_handler(              # Topic-aware consumer
        topics=topic_list,
        group_id="alpha-panda.service.group",
        handler_func=self._handle_message
    )
    .build()
)
```

**Topic-Aware Handler Pattern**:
```python
# CRITICAL: Handlers must accept (message, topic) parameters
async def _handle_validated_signal(self, message: Dict[str, Any], topic: str) -> None:
    # Extract broker from topic name for routing decisions
    broker = topic.split('.')[0]  # "paper.signals.validated" -> "paper"
    
    # Route based on extracted broker context
    trader = self.trader_factory.get_trader(broker)
    await trader.execute_order(signal)
```

**Instrument-to-Strategy Mapping Pattern**:
```python
# Performance optimization: O(1) lookups instead of O(n)
class StrategyRunnerService:
    def __init__(self):
        # Reverse mapping for efficient tick routing
        self.instrument_to_strategies: Dict[int, List[str]] = defaultdict(list)
    
    async def _handle_market_tick(self, message: Dict[str, Any], topic: str):
        instrument_token = message['data']['instrument_token']
        # O(1) lookup instead of iterating all strategies
        interested_strategies = self.instrument_to_strategies.get(instrument_token, [])
```

## Development Guidelines

See [Development Guide](docs/development/DEVELOPMENT_GUIDE.md) for complete development environment setup, commands, and philosophy.

### Critical Development Requirements
**🚨 MANDATORY**: 
1. **Virtual Environment**: Always activate venv before ANY Python operations
2. **Docker Compose**: Use `docker compose` (with space), not `docker-compose` (deprecated)
3. **Real Trading Focus**: System designed for REAL Zerodha trading, not simulation
4. **🚨 NO MOCK DATA ALLOWED** - Mock data ONLY in unit tests
5. **Zerodha SDK Reference**: Use `examples/pykiteconnect-zerodha-python-sdk-for-reference/`

### Critical Testing Implementation Rule (2025-08-23 Update)

**🚨 MANDATORY TESTING PRINCIPLE**: When fixing testing issues, the approach must be:

1. **Tests Should Identify Real Issues**: Testing failures should expose legitimate implementation gaps in application code, not test framework shortcomings
2. **Never Modify Application Code to Match Test Expectations**: Do not change application code simply to make poorly designed tests pass  
3. **Fix Tests to Validate Correct Behavior**: If tests are incorrectly implemented, fix the test code to properly validate the intended application behavior
4. **Implementation Gaps Are Implementation Tasks**: Test failures that reveal missing service methods, missing models, or incorrect async patterns indicate legitimate work needed in application services
5. **Maintain Test Integrity**: Tests must validate real-world usage patterns and expose actual implementation needs

**Example**: If tests fail because `MarketFeedService.__init__()` is missing an `auth_service` parameter, this indicates the service implementation is incomplete - implement the missing parameter rather than removing it from tests.

### Implementation Pattern References

**Existing Patterns:**
- **Event Publishing**: `examples/trading/message_publishing.py`
- **Broker Authentication**: `examples/trading/broker_authentication.py`
- **Pure Strategy Pattern**: `examples/trading/pure_strategy_pattern.py`
- **Trading Engine Routing**: `examples/trading/trading_engine_routing.py`
- **Lifecycle Management**: `examples/streaming/lifecycle_management.py`

**New Architectural Patterns (2025):**
- **StreamServiceBuilder**: `core/streaming/patterns/stream_service_builder.py` - Service composition pattern
- **Topic-Aware Handlers**: All `services/*/service.py` files - Handler methods with (message, topic) signatures
- **Service Protocols**: Implement `services/protocols.py` for contracts (recommended)
- **Strategy Composition**: Future `strategies/composition/` directory for composition-based strategies
- **Performance Optimization**: `services/strategy_runner/service.py` - Instrument-to-strategy mapping pattern

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.

**Documentation Update Rules:**
- **Do not create documents unless explicitly asked to do so**
- **When there is an instruction to update documentation, that is mostly about updating README.md in the relevant module or application folder**
  - For example, if the details to be updated are related to testing, the document to be updated is README.md in the tests module
  - Update the README.md in root folder or CLAUDE.md only if explicitly asked to do so
- **After new implementation or architectural changes, update the relevant README.md files** (module or application specific README.md files or the one in application root folder)
- **If it is major change, update in CLAUDE.md, but all CLAUDE.md updates should be minimal and concise**
- **Archive documents to `docs/` folder if needed**
- **Fix application code when issues identified during testing**
- **Do NOT modify application code just to make testing convenient**

### Critical Testing Implementation Rule (2025-08-23 Update)

**🚨 MANDATORY TESTING PRINCIPLE**: When fixing testing issues, the approach must be:

1. **Tests Should Identify Real Issues**: Testing failures should expose legitimate implementation gaps in application code, not test framework shortcomings
2. **Never Modify Application Code to Match Test Expectations**: Do not change application code simply to make poorly designed tests pass  
3. **Fix Tests to Validate Correct Behavior**: If tests are incorrectly implemented, fix the test code to properly validate the intended application behavior
4. **Implementation Gaps Are Implementation Tasks**: Test failures that reveal missing service methods, missing models, or incorrect async patterns indicate legitimate work needed in application services
5. **Maintain Test Integrity**: Tests must validate real-world usage patterns and expose actual implementation needs

**Example**: If tests fail because `MarketFeedService.__init__()` is missing an `auth_service` parameter, this indicates the service implementation is incomplete - implement the missing parameter rather than removing it from tests.

### Mandatory Implementation Verification Rule (2025-08-28 Update)

**🚨 MANDATORY VERIFICATION PRINCIPLE**: Every new implementation and change MUST be followed by comprehensive verification:

1. **Run Tests After Every Implementation**: Immediately after implementing any feature or fix, run the full test suite to verify nothing is broken
2. **Validate Integration Points**: Check that all service integrations, API endpoints, and dependencies work correctly
3. **Verify Configuration Changes**: Ensure any configuration updates (settings, environment variables) are properly loaded and used
4. **Check Import Dependencies**: Verify that all imports and dependencies are available and working
5. **Test Critical Paths**: Run specific tests for the implemented functionality to ensure it works as intended
6. **Document Test Results**: Record test outcomes and any issues discovered during verification

**Implementation Workflow**:
1. Implement the feature/fix
2. Run `python -m pytest tests/unit/` to verify unit tests pass
3. Test critical imports and basic functionality with simple Python scripts
4. Run integration tests if changes affect service interactions
5. Document any test failures and fix them before considering implementation complete

**This rule ensures that implementations are verified working before moving to the next task, preventing accumulation of broken code.**

### Clean Architecture Migration Policy (2025-08-29 Update)

**🚨 MANDATORY CLEAN MIGRATION PRINCIPLE**: Alpha Panda follows a strict clean architecture migration policy with NO backward compatibility:

1. **No Compatibility Shims**: Never create compatibility adapters, bridges, or shim layers for legacy code
2. **No Legacy Support**: When architectural changes are introduced, they are clean breaks from the old system
3. **Direct Migration**: All existing code (including tests) must be updated to use the new architecture directly
4. **Clean Codebase**: Remove all legacy code paths completely - no mixed architecture states
5. **Test Migration**: If tests reference old architecture components, update the tests to use new components

**Examples**:
- ❌ Create `BaseStrategy` compatibility shim for legacy tests
- ✅ Update tests to use `StrategyExecutor` and composition patterns directly
- ❌ Keep both legacy and modern streaming clients
- ✅ Migrate all services to `StreamServiceBuilder` and remove legacy clients
- ❌ Support both inheritance and composition strategy patterns
- ✅ Complete migration to composition-only strategy framework

**This policy ensures clean, maintainable architecture without technical debt from compatibility layers.**
