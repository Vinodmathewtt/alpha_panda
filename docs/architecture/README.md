# Architecture Documentation

## Hybrid Multi-Broker Architecture

Alpha Panda implements a **hybrid multi-broker architecture** where a single deployment manages multiple brokers with complete data isolation through topic namespacing.

### Broker Isolation

- **Topic Namespacing**: `paper.*` vs `zerodha.*` topic isolation
- **Cache Key Prefixing**: Redis keys prefixed by broker (`paper:*` vs `zerodha:*`)
- **Single Service Instances**: Topic-aware handlers route messages by broker context
- **Complete Data Separation**: Paper and Zerodha data never intersect

### Topic Taxonomy

```
# Paper Trading
paper.signals.raw → paper.signals.validated → paper.orders.filled

# Zerodha Trading  
zerodha.signals.raw → zerodha.signals.validated → zerodha.orders.filled

# Shared Market Data
market.ticks (consumed by both brokers)
```

### Deployment Configuration

```bash
# Multi-Broker Deployment (Recommended)
ACTIVE_BROKERS=paper,zerodha python cli.py run

# Single Broker Deployments
ACTIVE_BROKERS=paper python cli.py run
ACTIVE_BROKERS=zerodha python cli.py run
```

### Service Architecture

**SHARED SERVICES** (Single-broker model):
- **Market Feed Service**: Single service publishing to shared `market.ticks` topic using Zerodha API
- **Auth Service**: Handles JWT authentication and user management

**MULTI-BROKER SERVICES** (Single instance handling multiple brokers):
- **Strategy Runner Service**: Fans out signals to all active broker topics
- **Risk Manager Service**: Topic-aware validation for all active brokers

**BROKER-SCOPED SERVICES** (Per-broker trading):
- **Paper Trading Service**: Consumes `paper.signals.validated`, emits `paper.orders.*` and `paper.pnl.snapshots`
- **Zerodha Trading Service**: Consumes `zerodha.signals.validated`, emits `zerodha.orders.*` and `zerodha.pnl.snapshots`

### Message Flow with Topic-Aware Routing

1. **Market Ticks Generated**: `market.ticks` → All strategies (shared topic)
2. **Signals Fan-Out**: Strategy Runner → publishes to all active broker topics: `{broker}.signals.raw`
3. **Signals Validated**: Risk Manager (unified instance) → processes all `{broker}.signals.raw` → publishes `{broker}.signals.validated`
4. **Trading Execution**: Broker-scoped services process `{broker}.signals.validated` and publish `{broker}.orders.*`
5. **PnL Snapshots**: Broker-scoped services publish `{broker}.pnl.snapshots`; API reads broker-specific Redis keys
6. **API Responses**: API reads from all broker namespaces in Redis

## Implementation Patterns

### Modern Service Architecture Patterns

**StreamServiceBuilder Pattern**: All services use composition-based service orchestration:
```python
self.orchestrator = (StreamServiceBuilder("service_name", config, settings)
    .with_redis(redis_client)
    .with_error_handling()
    .with_metrics()
    .add_producer()
    .add_consumer_handler(topics=topic_list, group_id=group_id, handler_func=handler)
    .build()
)
```

**Topic-Aware Message Handlers**: Services extract broker context from topic names:
```python
async def _handle_message(self, message: Dict[str, Any], topic: str) -> None:
    broker = topic.split('.')[0]  # "paper.signals.raw" -> "paper"
    # Route based on extracted broker context
```

### Code Examples and Documentation

**Implementation Examples** in `examples/architecture/`:
- `topic_configuration.py` - Topic naming and partitioning
- `partitioning_strategy.py` - Partition key strategies

**Comprehensive Module Documentation**:
- [Core Architecture Patterns](../../core/README.md) - StreamServiceBuilder and composition patterns
- [Service Implementation Patterns](../../services/README.md) - Multi-broker service architecture
- [Strategy Framework Architecture](../../strategies/README.md) - Composition vs inheritance patterns

- **Detailed Service Documentation**
  - Broker-scoped trading services (migration completed):
    - Paper Trading: see `services/paper_trading/`
    - Zerodha Trading: see `services/zerodha_trading/`
  - Other services:
    - [Risk Manager](../../services/risk_manager/README.md) - Risk validation and signal filtering
    - [Strategy Runner](../../services/strategy_runner/README.md) - Strategy execution and signal generation
- [Risk Manager](../../services/risk_manager/README.md) - Multi-broker risk validation
- [Strategy Runner](../../services/strategy_runner/README.md) - Strategy execution and signal generation

## Configuration

Services use the `ACTIVE_BROKERS=paper,zerodha` environment variable to determine which broker topics to subscribe to and process, enabling unified multi-broker management.

See [Configuration Documentation](../../core/config/README.md) for detailed configuration management patterns.
### Migration Completed
- Legacy domain-scoped `trading_engine` and `portfolio_manager` have been removed.
- Trading paths are now broker-scoped with strict topic isolation and service-specific consumer groups.
