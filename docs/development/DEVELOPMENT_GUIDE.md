# Development Guide

## Infrastructure Management Commands

### Development Environment
```bash
# Check what's currently running
docker ps

# Stop any running environment
make down           # Stop infrastructure
docker compose down # Alternative command

# Clean containers and volumes
make clean          

# Start default development environment
make up

# Start Redpanda Console (http://localhost:8080)
docker compose --profile console up -d
```

### Test Environment Management
```bash
docker compose -f docker-compose.yml up -d    # Start environment
docker compose -f docker-compose.yml down     # Stop environment
docker compose -f docker-compose.yml down -v  # Stop and remove volumes
```

### Development Tools
```bash
# MANDATORY: Always use virtual environment
python3 -m venv venv
source venv/bin/activate         # Activate virtual environment (Linux/Mac)
# OR: venv\Scripts\activate      # Activate virtual environment (Windows)

pip install -r requirements.txt  # Install dependencies
python cli.py bootstrap          # Bootstrap topics manually
python cli.py seed              # Seed data manually
```

## Development Environment Requirements

### Critical Rules

1. **Virtual Environment**: Always activate the virtual environment before running any Python commands or operations
2. **Docker Compose Command**: Always use `docker compose` (with space) instead of `docker-compose` (deprecated)

### Adding New Features (Following Modern Architecture Patterns)
1. **Event Schema First**: Define new events in `core/schemas/events.py` with EventEnvelope
2. **Topic Definition**: Add new topics to `core/schemas/topics.py` with broker-prefixed naming
3. **Modern Service Implementation**: Use StreamServiceBuilder pattern for composition-based services
4. **Protocol Contracts**: Use `typing.Protocol` for interfaces instead of inheritance
5. **Broker Authentication**: Use `AuthService` for Zerodha KiteConnect integration
6. **User Authentication**: Use JWT for API endpoints
7. **Composition-Based Strategies**: Prefer composition + protocols over inheritance in `strategies/`
8. **Configuration Management**: Use `core/config/` patterns with Pydantic settings
9. **Multi-Broker Support**: Design with `ACTIVE_BROKERS` configuration from the start
10. **API Integration**: Read-only endpoints serving from broker-segregated Redis cache
11. **Comprehensive Testing**: Unit tests + integration tests with real infrastructure

## Development Philosophy

- **Unified Log Pattern** - Single source of truth for all dynamic data through Redpanda
- **Read Path Isolation** - API reads only from Redis cache, never from core trading pipeline
- **Pure Strategy Logic** - Strategies are generator functions with Pydantic models
- **Broker Authentication** - Separate machine-to-machine auth for market feed (Zerodha KiteConnect)
- **User Authentication** - JWT-based auth service for API access
- **Multi-Broker Trading** - Single deployment handles multiple brokers with `ACTIVE_BROKERS` configuration
- **Configuration over Code** - Dynamic strategy configuration in PostgreSQL
- **Graceful Degradation** - System continues operating even if individual services fail

### Critical Development Philosophy
- **Real Trading Focus** - Alpha Panda is designed for REAL trading with Zerodha APIs
- **Zerodha Integration Priority** - Always prioritize Zerodha KiteConnect integration and real market data
- **🚨 NO MOCK DATA ALLOWED** - Mock data ONLY permitted in unit tests
- **Authentication Required** - Expect real Zerodha authentication for all development and testing
- **🚨 NO BACKWARD COMPATIBILITY WRAPPERS** - Modify all related components when refactoring

## Market Feed Implementation

**Single Market Feed Service**: 
- Market feed service (`services/market_feed/`) handles both mock and real data generation
- Mock data generation via `MockMarketDataGenerator` class in `mock_data.py`
- Zerodha integration via `BrokerAuthenticator` and KiteConnect
- Service publishes standardized events to `market.ticks` topic regardless of data source
- Production deployment uses real Zerodha data, development uses mock data

### Broker Context Boundary (Important)
- Market data is a single shared stream on `market.ticks` for the entire application. Do not attach a per‑broker context to market tick logs, envelopes, or pipeline metrics.
- For envelopes, set `broker="shared"` when emitting `market.ticks`. This prevents duplication and keeps the feed unified.
- For pipeline metrics, always pass `broker_context="shared"` for market tick updates. Normalized keys should follow `pipeline:market_ticks:shared:{last|count}` (legacy aliases may exist during transition).
- Brokerization starts at strategy signal generation. The Strategy Runner emits `{broker}.signals.raw`, and all downstream services (risk manager, trading engines, portfolios) use strictly broker‑scoped topics and metrics.
- Keep market feed channel logs unbrokered (no `broker` field); add broker context only after signals are generated.

## Terminology Rules

**🚨 MANDATORY**: Use "zerodha" instead of "live" throughout documentation and implementation:
- ❌ **WRONG**: "live trading", "live_trading_enabled", "orders.filled.live"
- ✅ **CORRECT**: "zerodha trading", "zerodha_trading_enabled", "orders.filled.zerodha"

## Development Commands Priority

- Use `make` commands for common operations (setup, run, up, down, clean)
- Always check infrastructure status with `docker-compose logs redpanda postgres redis`
- Bootstrap Redpanda topics before running services (`make bootstrap`)
- Seed test data for development (`make seed`)
- Start Redpanda Console for debugging: `docker compose --profile console up -d`

## Documentation References

### Module Documentation
**Comprehensive Documentation**: All modules now have complete README.md files:
- [Core Modules](../core/README.md) - Shared libraries and architectural patterns
- [Services](../services/README.md) - Stream processing microservices
- [Strategies](../strategies/README.md) - Strategy framework and composition patterns
- [Authentication](../services/auth/README.md) - Multi-provider authentication
- [Configuration](../core/config/README.md) - Settings and environment management

### Architecture Patterns
- [Multi-Broker Architecture](../docs/architecture/MULTI_BROKER_ARCHITECTURE.md) - Unified deployment patterns
- [Python Development Policies](../docs/development/PYTHON_DEVELOPMENT_POLICIES.md) - Composition-first guidelines

### Zerodha KiteConnect SDK Reference
**CRITICAL**: For all Zerodha KiteConnect API integrations, refer to the PyKiteConnect SDK copy located at `examples/pykiteconnect-zerodha-python-sdk-for-reference/`. Consult whenever:
- Implementing new Zerodha API integration components
- Reviewing existing KiteConnect integration code  
- Understanding API patterns, authentication flows, and data structures
- Troubleshooting Zerodha-specific implementation issues
