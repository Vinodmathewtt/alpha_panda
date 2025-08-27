# Alpha Panda Application Module

This module contains the core application orchestration logic for Alpha Panda, an algorithmic trading system built on Unified Log architecture using Redpanda for event streaming.

## 🏗️ Architecture Overview

Alpha Panda follows a **security-first, health-gated startup pattern** where all systems must pass comprehensive health checks before any trading operations can begin. The application enforces **mandatory Zerodha authentication** to ensure secure broker API access.

### Core Components

- **ApplicationOrchestrator** (`main.py`) - Main application lifecycle manager
- **AppContainer** (`containers.py`) - Dependency injection container
- **Health Checks** (`pre_trading_checks.py`) - Pre-flight system validation
- **Service Management** - Coordinates 7 microservices with proper shutdown handling

## 🚀 Application Startup Flow

### Complete Execution Path

```bash
python cli.py run
    ↓
asyncio.run(run_app())
    ↓
ApplicationOrchestrator()
    ↓
Health Checks (includes AUTH)
    ↓
Database Initialization  
    ↓
Service Startup (7 services)
    ↓
Application Running
```

### Detailed Startup Sequence

#### 1. Container Initialization
```python
# app/main.py:15-30
class ApplicationOrchestrator:
    def __init__(self):
        # Create DI container with all service dependencies
        self.container = AppContainer()
        self._shutdown_event = asyncio.Event()
        
        # Wire dependency injection to modules
        self.container.wire(modules=[__name__, "core.health", "api.dependencies"])
        
        # Load settings and configure logging
        self.settings = self.container.settings()
        configure_logging(self.settings)
        self.logger = get_logger("alpha_panda.main")
        
        # Log current broker namespace for deployment visibility
        self.logger.info(f"🏢 Running in '{self.settings.broker_namespace}' broker namespace")
```

#### 2. Health Check Execution
```python
# app/main.py:34-52
async def startup(self):
    self.logger.info("🚀 Conducting system pre-flight health checks...")
    
    # CRITICAL: All health checks must pass before proceeding
    is_healthy = await self.health_monitor.run_checks()
    
    if not is_healthy:
        self.logger.critical("System health checks failed. Application will not start.")
        await self._cleanup_partial_initialization()
        sys.exit(1)  # Hard exit on health check failure
```

**Health Check Components:**
1. **DatabaseHealthCheck** - PostgreSQL connection validation
2. **RedisHealthCheck** - Redis cache connectivity  
3. **RedpandaHealthCheck** - Kafka broker connectivity
4. **ZerodhaCredentialsCheck** - API key configuration validation
5. **ActiveStrategiesCheck** - Database contains active trading strategies
6. **🔐 BrokerApiHealthCheck** - **AUTHENTICATION ENFORCEMENT POINT**
7. **MarketHoursCheck** - Market status information (warning only)

#### 3. 🔐 Authentication Flow (BLOCKING OPERATION)

The **BrokerApiHealthCheck** triggers the authentication sequence:

```python
# app/pre_trading_checks.py:51-76
async def check(self) -> HealthCheckResult:
    if not self.auth_service.is_authenticated():
        try:
            # This call BLOCKS until user completes OAuth
            auth_initialized = await self.auth_service.auth_manager.initialize()
            
            if not auth_initialized:
                return HealthCheckResult(
                    component="Zerodha API",
                    passed=False,
                    message="CRITICAL: Zerodha authentication required but failed."
                )
        except Exception as e:
            return HealthCheckResult(
                component="Zerodha API", 
                passed=False,
                message=f"CRITICAL: Authentication initialization failed: {e}"
            )
```

**Interactive Authentication Process:**
```python
# services/auth/auth_manager.py:179-228
async def _interactive_authentication(self) -> bool:
    print("\n🔐 ===== ZERODHA AUTHENTICATION REQUIRED =====")
    print("📋 No valid access token found. Please authenticate with Zerodha.")
    print("🛑 SYSTEM WAITING FOR AUTHENTICATION - No other components will start until auth completes")
    
    # Generate and display login URL
    login_url = self.get_login_url()
    print(f"🌐 Please visit this URL to login:\n   {login_url}")
    print("📝 After login, copy the 'request_token' from the redirect URL")
    
    # BLOCKING: Wait for user input with 300-second timeout
    request_token = await self._prompt_for_input("🔑 Enter request_token: ", 300)
    
    # Process token and create session
    session_data = await self._generate_session(request_token.strip())
    
    print("✅ Authentication successful! System will now continue...")
    return True
```

#### 4. Database Initialization
```python
# app/main.py:57-58
# Only executed AFTER successful health checks
db_manager = self.container.db_manager()
await db_manager.init()
```

#### 5. Service Startup (Parallel Execution)
```python
# app/main.py:60-62
services = self.container.lifespan_services()
# Start all 7 services concurrently
await asyncio.gather(*(service.start() for service in services if service))
self.logger.info("✅ All services started successfully.")
```

**Service Startup Order:**
```python
# app/containers.py:164-172
lifespan_services = providers.List(
    auth_service,           # 1. Already initialized during health checks
    market_feed_service,    # 2. Zerodha WebSocket connection (depends on auth)
    strategy_runner_service,# 3. Load active strategies from database
    risk_manager_service,   # 4. Initialize risk validation rules
    trading_engine_service, # 5. Paper + Zerodha trading engines
    portfolio_manager_service, # 6. Portfolio state management
    pipeline_monitor        # 7. System observability metrics
)
```

## 🔒 Security & Authentication

### Mandatory Authentication Requirements

Alpha Panda enforces **non-negotiable Zerodha authentication** for all operations:

```python
# From CLAUDE.md architecture:
# 🚨 CRITICAL: Zerodha authentication is ALWAYS REQUIRED for the full trading pipeline
# The market feed service depends on Zerodha API for real market data
```

**Authentication States:**
- `UNAUTHENTICATED` - No valid session exists
- `AUTHENTICATING` - Interactive OAuth flow in progress  
- `AUTHENTICATED` - Valid session with API access
- `ERROR` - Configuration or authentication failure

**Session Management:**
- **Storage**: PostgreSQL `trading_sessions` table
- **Validation**: Real-time API calls to verify token validity
- **Expiry**: 24-hour session lifetime matching Zerodha tokens
- **Auto-refresh**: Stored sessions validated on startup

## 🏗️ Infrastructure Dependencies

### Required Services
```yaml
# docker-compose.yml services that MUST be running
services:
  postgres:    # Database for strategies & sessions
    ports: ["5432:5432"]
  
  redis:       # Cache & deduplication 
    ports: ["6379:6379"]
    
  redpanda:    # Event streaming backbone
    ports: ["9092:9092"]
```

### Environment Configuration
```bash
# .env file requirements
ZERODHA__ENABLED=true                    # MANDATORY
ZERODHA__API_KEY=your_api_key           # MANDATORY  
ZERODHA__API_SECRET=your_api_secret     # MANDATORY
BROKER_NAMESPACE=paper                  # paper|zerodha
DATABASE__POSTGRES_URL=postgresql+asyncpg://alpha_panda:alpha_panda@localhost:5432/alpha_panda
REDIS__URL=redis://localhost:6379/0
REDPANDA__BOOTSTRAP_SERVERS=localhost:9092
```

### Database Requirements
```sql
-- Active strategies MUST exist in database
SELECT COUNT(*) FROM strategy_configurations WHERE is_active = true;
-- Must return > 0 or ActiveStrategiesCheck fails
```

## 🎯 Startup Commands

### Complete Setup (First Time)
```bash
# 1. Complete development environment setup
make setup  # Equivalent to: make dev up bootstrap seed

# 2. Run the application  
python cli.py run
```

### Individual Steps
```bash
# Development environment
make dev            # Create .env, install dependencies

# Infrastructure startup
make up             # Start PostgreSQL, Redis, Redpanda

# Topic bootstrapping  
make bootstrap      # Create Kafka topics with proper partitions

# Test data seeding
make seed           # Add sample strategies to database

# Application execution
python cli.py run   # Start full trading pipeline
```

### Service-Specific Commands
```bash
python cli.py api       # API server only (port 8000)
python cli.py bootstrap # Topic creation only
python cli.py seed      # Database seeding only
```

## 🔍 Troubleshooting

### Common Startup Issues

#### 1. Authentication Failures
```bash
# Symptoms: 
❌ CRITICAL: Zerodha authentication required but failed

# Solutions:
✅ Verify ZERODHA__API_KEY and ZERODHA__API_SECRET in .env
✅ Ensure ZERODHA__ENABLED=true
✅ Complete interactive OAuth flow when prompted
✅ Check Zerodha API key permissions and quotas
```

#### 2. Infrastructure Connection Failures
```bash
# Database connection error:
❌ Health check FAILED for Database: Connection refused

# Solution:
docker-compose up -d postgres redis redpanda
# Wait 10-15 seconds for services to initialize
```

#### 3. Missing Active Strategies
```bash
# Symptoms:
❌ Health check FAILED for Strategy Config: No active strategies found

# Solution:
python cli.py seed  # Add sample strategies
# Or manually insert strategies into strategy_configurations table
```

#### 4. Permission/File Descriptor Errors
```bash
# Symptoms (in non-interactive environments):
PermissionError: [Errno 1] Operation not permitted

# Solutions:
✅ Run in proper terminal environment (not headless)
✅ Ensure proper TTY access for Docker containers
✅ Use interactive session: docker exec -it container bash
```

### Health Check Debugging
```bash
# Enable detailed logging
export LOG_LEVEL=DEBUG
python cli.py run

# Check specific health components
python -c "
from app.containers import AppContainer
container = AppContainer()
health_monitor = container.system_health_monitor()
import asyncio
asyncio.run(health_monitor.run_checks())
"
```

### Authentication Debugging
```bash
# Test authentication separately
python -c "
from services.auth.service import AuthService
from core.config.settings import Settings
from core.database.connection import DatabaseManager

settings = Settings()
db_manager = DatabaseManager(settings.database.postgres_url)
auth_service = AuthService(settings, db_manager)

import asyncio
asyncio.run(auth_service.auth_manager.initialize())
"
```

## 🏢 Broker Segregation

Alpha Panda treats **paper trading** and **zerodha trading** as completely separate brokers:

### Configuration
```bash
# Paper trading deployment
export BROKER_NAMESPACE=paper
python cli.py run

# Zerodha trading deployment  
export BROKER_NAMESPACE=zerodha
python cli.py run

# Both can run simultaneously in separate processes
```

### Topic Segregation
```python
# Paper trading topics
paper.signals.raw
paper.signals.validated  
paper.orders.filled

# Zerodha trading topics
zerodha.signals.raw
zerodha.signals.validated
zerodha.orders.filled

# Shared market data
market.ticks  # Same Zerodha market feed for both brokers
```

### Service Isolation
Each broker namespace creates separate:
- **Consumer groups**: `alpha-panda.paper.strategy-runner` vs `alpha-panda.zerodha.strategy-runner`
- **Redis keys**: `paper:portfolio:*` vs `zerodha:portfolio:*`  
- **Service instances**: Complete isolation of trading engines and portfolio managers

## 🔧 Development & Testing

### Mock Mode (Development Only)
```bash
# Disable Zerodha requirements for testing
export ZERODHA__ENABLED=false
export AUTH__ENABLE_USER_AUTH=false

# This bypasses authentication but limits functionality
# Market feed will use mock data instead of real Zerodha data
```

### API Testing
```bash
# Start API server separately
python cli.py api

# Test endpoints
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/portfolios/summary
```

### Integration Testing
```bash
# Run with test infrastructure
make test-setup    # Start test environment
make test-integration
```

## 📊 Monitoring & Observability

### Application Logs
```bash
# Multi-channel logging (when running)
tail -f logs/application.log    # General application events
tail -f logs/trading.log       # Trading-specific events  
tail -f logs/market_data.log   # Market data processing
tail -f logs/error.log         # Error tracking
```

### Service Health
```python
# Runtime service status
from app.containers import AppContainer
container = AppContainer()
services = container.lifespan_services()

# Check individual service health
for service in services:
    print(f"{service.__class__.__name__}: {getattr(service, '_running', 'unknown')}")
```

### Metrics Collection
- **Pipeline metrics**: Message throughput, latency, error rates
- **Authentication status**: Session validity, API call success rates
- **Market data quality**: Tick processing rates, data completeness
- **Trading performance**: Signal generation, execution latency

## 🚨 Production Deployment Notes

### Security Considerations
1. **Environment Variables**: Use secure secret management for API keys
2. **Database Security**: Encrypt sensitive session data
3. **Network Security**: Restrict API access to authorized IPs
4. **Audit Logging**: Enable comprehensive audit trail for all trading operations

### Scalability Patterns  
1. **Horizontal Scaling**: Multiple instances per broker namespace
2. **Geographic Distribution**: Regional deployments for latency optimization
3. **Load Balancing**: API layer scaling with session affinity
4. **Resource Isolation**: Dedicated infrastructure per trading environment

### Disaster Recovery
1. **Session Backup**: Replicated session storage across regions  
2. **Market Data Resilience**: Alternative data feed integration
3. **Graceful Degradation**: Fallback to paper trading on API failures
4. **Fast Recovery**: Automated restart with session restoration

---

## 📚 Additional Resources

- **Core Documentation**: `../CLAUDE.md` - Complete system architecture
- **API Documentation**: `../api/README.md` - API endpoints and usage
- **Testing Guide**: `../tests/README.md` - Comprehensive testing strategies  
- **Examples**: `../examples/` - Code patterns and implementation examples

For support and troubleshooting, refer to the main project documentation and ensure all infrastructure dependencies are properly configured before attempting to run the application.