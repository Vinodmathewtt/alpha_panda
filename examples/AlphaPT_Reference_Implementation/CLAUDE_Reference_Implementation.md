# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚨 CRITICAL: Keep CLAUDE.md Updated
**MANDATORY**: This CLAUDE.md file MUST be updated whenever there are:
- New implementations or architectural changes
- Technology stack changes or additions
- Module additions, removals, or structural changes
- Configuration or deployment process changes

**The CLAUDE.md file is the single source of truth for development practices and must reflect the current state of the implementation.**

## Project Overview

AlphaPT is a production-ready algorithmic trading platform built with Python, featuring event-driven architecture, comprehensive monitoring, and high-performance data processing.

**Performance Target**: 1000+ market ticks per second processing ✅ ACHIEVED
**Testing Framework**: Production-ready advanced testing with dual-mode capability ✅ COMPLETE

For detailed architecture overview, see [README.md](README.md)

## Technology Stack & Architecture

### Core Technologies
- **Event System**: NATS JetStream with 3 streams (MARKET_DATA, TRADING, SYSTEM)
- **Databases**: PostgreSQL (transactional), ClickHouse (analytics), Redis (caching)  
- **Authentication**: JWT-based with Zerodha KiteConnect and Mock providers
- **Monitoring**: Prometheus metrics with comprehensive health checks and business metrics
- **API Layer**: FastAPI with 9 specialized routers and WebSocket support

### Module Structure Overview
For detailed information about each module, see the respective README.md files:

- `app/` - Application lifecycle and main orchestrator ✅ ACTIVE
- `core/` - Core infrastructure (auth, config, database, events, logging, utils) ✅ ACTIVE
  - [Event System README](core/events/README.md)
  - [Logging README](core/logging/README.md)
- `storage/` - High-performance market data storage ✅ ACTIVE - [README](storage/README.md)
- `api/` - REST API and WebSocket endpoints ✅ ACTIVE
- `strategy_manager/` - Strategy framework with health monitoring ✅ ACTIVE
- `risk_manager/` - Risk management with position and loss controls ✅ ACTIVE
- `paper_trade/` - Paper trading engine ✅ ACTIVE
- `zerodha_trade/` - Live trading with Zerodha KiteConnect ✅ ACTIVE
- `zerodha_market_feed/` - Live market data from Zerodha ✅ ACTIVE
- `mock_market_feed/` - Development market data simulation ✅ ACTIVE (Dev only)
- `instrument_data/` - Instrument registry with Redis caching ✅ ACTIVE
- `monitoring/` - Observability stack ✅ ACTIVE
- `tests/` - Testing infrastructure ✅ ACTIVE - [README](tests/README.md)

**🚨 Important**: `mock_market_feed/` is for development/testing ONLY and will be removed in production deployment

## Implementation Status

**Current Status: Production Ready! 🎉**

For detailed implementation status and deployment guide, see [README.md](README.md)

## Critical Development Rules

### 🚨 MANDATORY: Virtual Environment
**ALWAYS activate the virtual environment before running ANY Python commands:**
```bash
source venv/bin/activate
python -m main
```

### File Organization Rules
1. **ALL test files MUST be created in the `tests/` folder**
2. **Archive documents MUST be moved to the existing `docs/archive/` folder**
3. **🚨 CRITICAL: No Duplicate Folder Names Between Root and Core**:
   - **NEVER create folders with the same name in both root and `core/` module**
   - If a folder exists in root (e.g., `logs/`), do NOT create `core/logs/`
   - If a folder exists in `core/` (e.g., `core/config/`), do NOT create root `config/`
   - This prevents confusion and maintains clear separation of concerns
   - **Folders can be moved from `core/` to project root if they contain runtime data or follow standard practices** (e.g., `core/logs/` → `logs/` for runtime log files)
4. **Configuration Files Organization**:
   - Central config: `core/config/` (used across multiple modules)
   - Module-specific config: `{module}/config/` (dedicated to single module)
   - No root config folder allowed
5. **Never alter application code to match incorrect test files** - always fix test files
6. **🚨 CRITICAL: Application Code vs Testing Code Rules**:
   - **Fix issues in application code when identified during testing** - Testing reveals real problems that need fixing
   - **Do NOT modify application code just to make testing easier or convenient** - Keep application code production-focused
   - **Make necessary changes to testing code or build additional test scripts** to overcome challenges posed by application code design
   - **Respect the application architecture** - If tests fail due to design choices, adapt tests rather than compromise design

### Documentation Priority Rules
1. **🚨 MANDATORY: Documentation Hierarchy**:
   - **PRIMARY**: Update `README.md` in each module for architecture changes, new functionality, API updates
   - **SECONDARY**: Update this `CLAUDE.md` file for development practices, workflow changes, project-wide updates (keep updates brief, only for major architectural and tech changes)
   - **TERTIARY**: Create files in `docs/` folder ONLY when explicitly requested
2. **🚨 CRITICAL: Documentation Creation Rule**:
   - **DO NOT create documentation in `docs/` folder unless explicitly asked**
   - **All documentation updates should be focused on `README.md` and `CLAUDE.md` (brief updates only)**
   - **If a module doesn't have a `README.md`, please create one and update it**
   - **When user says "update the documentation", follow priority order: module README.md first, then CLAUDE.md only if required**
3. **Exception: Implementation Planning Documents**:
   - Specific implementation plans and guides MAY be created in `docs/` folder prior to implementation
   - Once implementation is completed, mark corresponding documentation as completed and move to `docs/archive/` folder
4. **Living Documentation Principle**:
   - Module `README.md` files are the primary source of truth for that module's functionality
   - Keep documentation close to code - prefer in-module documentation over separate docs
   - Update documentation immediately when implementing changes, not as separate task

5. **🚨 CRITICAL: Lessons Learned Documentation Process**:
   - **MANDATORY**: When resolving critical production issues or implementing major fixes, always extract lessons learned
   - **Process for Critical Issues**:
     1. **Analyze Root Causes**: Document the underlying causes of problems, not just symptoms
     2. **Extract Implementation Patterns**: Identify correct patterns, anti-patterns, and best practices
     3. **Create Guidelines**: Convert solutions into reusable guidelines for future development
     4. **Update Module READMEs**: Add "Critical Lessons Learned" sections to relevant module README.md files
     5. **Organize by Functional Area**: Group lessons by domain (event system, database, application lifecycle, etc.)
   - **Documentation Standards**:
     - Include both **what NOT to do** (❌ WRONG patterns) and **what TO do** (✅ CORRECT patterns)
     - Provide code examples showing correct implementation patterns
     - Add troubleshooting checklists and diagnostic guidelines
     - Include performance considerations and monitoring patterns
   - **Target Modules for Lessons**:
     - `core/events/README.md` - Event system patterns, race conditions, NATS JetStream
     - `storage/README.md` - Database schema patterns, ClickHouse limitations, migration strategies  
     - `app/README.md` - Application lifecycle, shutdown procedures, component initialization
     - `core/logging/README.md` - Logging patterns, structured vs standard logging
     - Module-specific READMEs for domain-specific lessons
   - **Benefits**: Prevents recurring issues, improves development velocity, builds institutional knowledge

### Import and Reference Rules
- Use proper module imports: `from module_name.module_file import ClassName`
- Avoid global imports - use dependency injection and class parameters
- Example fixes applied:
  ```python
  # ❌ Bad
  from core.auth.auth_manager import auth_manager
  
  # ✅ Good  
  from core.auth.auth_manager import AuthManager
  # Then pass instance via constructor or method
  ```

### Event-Driven Architecture Patterns
```python
# Publishers
await event_bus.publish('market.tick.NSE.123456', tick_data)
await event_bus.publish('trading.signal.strategy1.RELIANCE', signal_data)

# Subscribers with correlation tracking
async def handler(event):
    correlation_id = event.correlation_id
    # Process with full logging and error handling
```

### Component Initialization Pattern
All major components follow this pattern:
```python
class ComponentManager:
    def __init__(self, settings=None, event_bus=None):
        self.settings = settings
        self.event_bus = event_bus
        
    def set_dependency(self, dependency):
        """Set required dependencies via methods."""
        self.dependency = dependency
        
    async def initialize(self) -> bool:
        """Initialize the component."""
        # Setup and validation logic
        return True
```

## Development Commands

### Environment Setup
```bash
# Setup virtual environment (MANDATORY first step)
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev,test]"

# Start required services
make start-services
```

### Running the Application
```bash
# ALWAYS activate virtual environment first
source venv/bin/activate

# Production/Development mode with Zerodha feed (DEFAULT - requires authentication)
python -m main

# Testing mode ONLY when Zerodha is unavailable (NOT for regular development)
MOCK_MARKET_FEED=true python -m main

# Enable API server
ENABLE_API_SERVER=true API_SERVER_PORT=8000 python -m main
```

### Testing
```bash
# ALWAYS activate virtual environment first
source venv/bin/activate

# 🚨 MANDATORY: Default testing with real Zerodha integration
# Run all tests with environment isolation (MOCK_MARKET_FEED=false by default)
TESTING=true python -m pytest tests/ -v

# Run specific test categories using markers
TESTING=true python -m pytest tests/ -m unit -v                    # Unit tests only
TESTING=true python -m pytest tests/ -m integration -v            # Integration tests
TESTING=true python -m pytest tests/ -m performance -v            # Performance tests
TESTING=true python -m pytest tests/ -m "not slow" -v             # Exclude slow tests

# Run specific test modules
TESTING=true python -m pytest tests/unit/test_strategy_framework.py -v
TESTING=true python -m pytest tests/integration/test_complete_trading_workflow.py -v
TESTING=true python -m pytest tests/load_testing/test_high_throughput_scenarios.py -v

# Run comprehensive test suite
python tests/run_sophisticated_tests.py

# 🚨 EXCEPTION: Mock feed testing ONLY for mock functionality
TESTING=true MOCK_MARKET_FEED=true python -m pytest tests/unit/test_mock_market_feed.py -v
```

### Configuration Options

#### Standard Testing Environment (DEFAULT)
```bash
# 🚨 MANDATORY: Use these settings for all testing unless specific exception applies
MOCK_MARKET_FEED=false                    # Use real Zerodha integration (DEFAULT)
PAPER_TRADING_ENABLED=true               # Enable paper trading
ZERODHA_TRADING_ENABLED=false            # Disable live trading (safety)
```

#### Exception: Mock Feed Testing (ONLY when Zerodha unavailable)
```bash
# 🚨 EXCEPTION: Use ONLY when facing Zerodha authentication issues
MOCK_MARKET_FEED=true                     # Enable mock feed when Zerodha unavailable
PAPER_TRADING_ENABLED=true               # Enable paper trading  
ZERODHA_TRADING_ENABLED=false            # Disable live trading (safety)
MOCK_TICK_INTERVAL_MS=1000               # Control tick frequency in mock mode
```

#### Development Controls
```bash
JSON_LOGS=false                          # Control JSON formatting
DEBUG=true                               # Enable debug mode with detailed logging
ENVIRONMENT=development                  # Set environment (development/staging/production)
ENABLE_API_SERVER=true                   # Enable FastAPI server
API_SERVER_PORT=8000                     # API server port
```

## Implementation Status

**Current Status: Production Ready! 🎉**

✅ **All Core Components Implemented**:
- Application lifecycle management with proper cleanup
- Event-driven architecture with NATS JetStream
- Multi-database architecture (PostgreSQL, ClickHouse, Redis)
- Authentication system with multiple providers
- Comprehensive monitoring and health checks
- Market data pipeline with quality monitoring
- Trading infrastructure (paper + live trading)
- Strategy framework with built-in strategies
- REST API and WebSocket integration
- Enhanced instrument data management

## Testing Framework

**Testing Infrastructure**: ✅ **COMPLETE** - Production-ready comprehensive testing with 5-tier architecture

For detailed testing information, see [tests/README.md](tests/README.md)

### Testing Quick Reference
```bash
# 🚨 MANDATORY: Default testing with real Zerodha integration (MOCK_MARKET_FEED=false)
# Run all tests
TESTING=true python -m pytest tests/ -v

# Run by category  
TESTING=true python -m pytest tests/ -m unit -v           # Unit tests
TESTING=true python -m pytest tests/ -m integration -v   # Integration tests  
TESTING=true python -m pytest tests/ -m contract -v      # Contract tests
TESTING=true python -m pytest tests/ -m e2e -v           # End-to-end tests
TESTING=true python -m pytest tests/ -m smoke -v         # Smoke tests

# 🚨 EXCEPTION: Mock feed testing ONLY for mock functionality
TESTING=true MOCK_MARKET_FEED=true python -m pytest tests/ -k "mock" -v
```

## Key Application Files

For detailed architecture and component information, see module-specific README.md files:

#### Main Entry Points
- `main.py` - Main application entry point  
- `app/application.py` - Application orchestrator and lifecycle manager

#### Configuration & Deployment  
- `pyproject.toml` - Python package configuration with dependencies and build settings
- `pytest.ini` - Testing configuration with markers and environment settings
- `docker-compose.yml` - Multi-service Docker setup for development
- `k8s/` - Kubernetes deployment manifests
- `.env.example` - Environment configuration template

## Development Guidelines

### Adding New Features
1. Follow async/await pattern throughout
2. Add appropriate monitoring and health checks
3. Include structured logging with correlation IDs
4. Write tests in `tests/` folder (unit, integration, performance)
5. **Always activate virtual environment**: `source venv/bin/activate`
6. **Use TESTING=true for all test execution**
7. Use dependency injection - avoid global imports
8. Implement all three monitoring aspects (anti-silent failure, business validation, debugging)
9. Add Prometheus metrics for new functionality
10. Include business context in technical monitoring

### Development Philosophy
- **Real Trading Focus**: AlphaPT is designed for REAL trading with Zerodha APIs - not a simulation system
- **Zerodha Integration Priority**: Always prioritize Zerodha KiteConnect integration and real market data
- **Mock Mode Usage**: Use `MOCK_MARKET_FEED=true` ONLY when testing mock market feed functionality
- **Authentication Required**: Expect real Zerodha authentication for all development and testing
- **Avoid Over Engineering**: Retail trading system with selective enterprise patterns
- **Avoid Early Optimization**: Implement correctly first, optimize using monitoring data
- **Market Feed Segregation**: Mock follows Zerodha exactly, never reverse
- **🚨 NO BACKWARD COMPATIBILITY WRAPPERS**: Do not create backward compatibility wrappers in the application. When refactoring components significantly, modify all related application components to align with the changes and maintain original integration patterns. This ensures continuous improvement and modernization of the application architecture.

### Market Feed Segregation Rules (CRITICAL)
**🚨 MANDATORY SEGREGATION**: 
- `zerodha_market_feed/` and `mock_market_feed/` are completely separate
- `mock_market_feed` must follow `zerodha_market_feed` structure exactly
- **NEVER** modify `zerodha_market_feed` to accommodate `mock_market_feed`
- During production, `mock_market_feed` will be completely removed

### Error Handling
- Use structured exception hierarchy in `core/utils/exceptions.py`
- Implement graceful degradation for non-critical failures
- **Never raise exceptions in event handlers** - log errors gracefully
- Include correlation IDs for request tracking

### Performance Considerations
- Target: 1000+ market ticks per second ✅ ACHIEVED
- Use connection pooling for database operations
- Implement Redis caching strategies
- Monitor performance with Prometheus metrics
- Use NATS JetStream for high-throughput event streaming

## Common Troubleshooting

### Import Errors
- Ensure virtual environment is activated
- Check module structure matches import statements
- Use proper class names in imports
- Verify dependencies are properly injected

### Authentication Issues
- **🚨 STOP TESTING if authentication fails** - Ask user to login, then continue after confirmation
- For production: Verify Zerodha credentials in `.env`
- Check authentication manager initialization
- **Use `MOCK_MARKET_FEED=true` ONLY for testing mock market feed functionality**

### Advanced Testing Commands

For comprehensive testing guide, see [tests/README.md](tests/README.md)

**Quick Testing Commands**
```bash
# ALWAYS activate virtual environment first
source venv/bin/activate

# 🚨 MANDATORY: Default testing with real Zerodha integration (MOCK_MARKET_FEED=false)
# Test specific components by keyword
TESTING=true python -m pytest tests/ -k "risk" -v         # Risk management tests
TESTING=true python -m pytest tests/ -k "strategy" -v     # Strategy framework tests
TESTING=true python -m pytest tests/ -k "storage" -v      # Storage and database tests

# 🚨 EXCEPTION: Mock feed testing ONLY for mock functionality
TESTING=true MOCK_MARKET_FEED=true python -m pytest tests/ -k "mock" -v
```

### Database Connection Problems
- Ensure services are running: `docker compose up -d`
- Verify connection settings in configuration
- Check database initialization status

### Event System Issues
- Verify NATS JetStream is running
- Check event handler registration
- Monitor correlation ID tracking
- Review connection quality metrics

## File Naming Conventions

- `*_manager.py`: Component orchestrators
- `*_factory.py`: Factory pattern implementations  
- `*_config.py`: Configuration modules
- `test_*.py`: Test suites (in `tests/` folder only)

**Remember**: Never use descriptive prefixes like `enhanced_*`, `simple_*`, `new_*` in file or class names.

## Production Considerations

### Environment Configuration
- Use `.env` files for environment-specific settings
- Set proper logging levels (INFO for production, DEBUG for development)
- Configure monitoring and alerting thresholds
- **Environment Variables**: `ENVIRONMENT`, `MOCK_MARKET_FEED`, `TESTING`, `DEBUG`

### Deployment
- Docker Compose provided for multi-service deployment
- Kubernetes manifests available (`k8s/` folder)
- Health check endpoints available
- Graceful shutdown handling implemented
- **Always use virtual environment**: `source venv/bin/activate`
- **Production Notes**: Set `MOCK_MARKET_FEED=false`, remove `mock_market_feed/` module completely

### Integration Points
- **External Dependencies**: Zerodha KiteConnect, ClickHouse, PostgreSQL, Redis, NATS JetStream, Prometheus
- **Cross-Component Communication**: Market Feed → Event Bus → Strategy Manager → Risk Manager → Trading Engine
- **Zerodha API Integration**: **ALWAYS review examples/ folder** for official SDK patterns before implementation

---

**Current Status: Production Ready! 🎉**

All phases complete - AlphaPT is a production-ready algorithmic trading platform:
- ✅ **Core Infrastructure**: NATS, databases, auth, monitoring
- ✅ **Market Data Pipeline**: Zerodha integration, caching, quality monitoring
- ✅ **Trading Infrastructure**: Paper + live trading, risk management
- ✅ **Strategy Framework**: Built-in strategies, parallel execution
- ✅ **API Integration**: REST API, WebSocket, comprehensive endpoints
- ✅ **Production Readiness**: Performance optimization, deployment automation, monitoring
- ✅ **Enhanced Instrument Data**: Smart scheduling, Redis caching, target management

## Recent Status & Recommendations

### System Status ✅ PRODUCTION-READY
- **Overall Rating**: ✅ EXCELLENT (9.2/10)  
- **Performance Target**: ✅ ACHIEVED (1000+ ticks/second)
- **Code Quality**: ✅ HIGH STANDARD

### Implementation Recommendations
For detailed recommendations and implementation roadmap, see:
- [docs/FUTURE_IMPROVEMENTS.md](docs/FUTURE_IMPROVEMENTS.md)
- [docs/PRIORITY_IMPLEMENTATION_PLAN.md](docs/PRIORITY_IMPLEMENTATION_PLAN.md)

## Critical Integration Patterns & Troubleshooting

### Important Integration Patterns

#### Event System Rules (MANDATORY)
```python
# ✅ CORRECT - Always use proper BaseEvent subclasses
from core.events.event_types import SystemEvent, EventType
event = SystemEvent(
    event_id=str(uuid.uuid4()),
    event_type=EventType.STRATEGY_STARTED,
    timestamp=datetime.now(timezone.utc),
    source="component_name",
    details={"data": "value"}  # Use correct field name
)

# ❌ WRONG - Never publish plain dictionaries
await event_bus.publish("subject", {"key": "value"})  # Will fail
```

#### Component Lifecycle Pattern
```python
class ComponentManager:
    async def initialize(self) -> bool:
        # Setup and validation logic
        return True
        
    async def cleanup(self):
        # Cleanup resources
        await self.stop()
```

### Common Troubleshooting

For comprehensive troubleshooting guide, see:
- [docs/ISSUES_TO_BE_RESOLVED.md](docs/ISSUES_TO_BE_RESOLVED.md)  
- [Event System Documentation](core/events/README.md)

#### Quick Fixes
- **Event System Errors**: Always use Event objects, never plain dictionaries
- **Database Errors**: Ensure services running with `docker compose up -d`
- **Import Errors**: Activate virtual environment: `source venv/bin/activate`

---

**File Last Updated**: August 2025
**Review Status**: ✅ COMPLETE - Comprehensive end-to-end analysis completed with troubleshooting guidelines
**Implementation Status**: 📋 RECOMMENDATIONS READY - Detailed implementation plan and troubleshooting guide available

This file represents the current state of AlphaPT as of August 2025. The system is production-ready with 1000+ ticks/sec processing, comprehensive monitoring, automated deployment, thorough architectural review, and battle-tested troubleshooting procedures from production issue resolution.