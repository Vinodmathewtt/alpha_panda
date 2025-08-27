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
- **Trading Engine Service**: Topic-aware routing to PaperTrader/ZerodhaTrader
- **Portfolio Manager Service**: Maintains broker-specific state with prefixed cache keys

### Message Flow with Topic-Aware Routing

1. **Market Ticks Generated**: `market.ticks` → All strategies (shared topic)
2. **Signals Fan-Out**: Strategy Runner → publishes to all active broker topics: `{broker}.signals.raw`
3. **Signals Validated**: Risk Manager (unified instance) → processes all `{broker}.signals.raw` → publishes `{broker}.signals.validated`
4. **Trading Execution**: Trading Engine (unified instance) → routes by topic to appropriate trader → publishes `{broker}.orders.filled`
5. **Portfolio Updates**: Portfolio Manager (unified instance) → updates broker-specific Redis keys (`{broker}:portfolio:*`)
6. **API Responses**: API reads from all broker namespaces in Redis

## Implementation Patterns

See example implementations in `examples/architecture/`:
- `topic_configuration.py` - Topic naming and partitioning
- `partitioning_strategy.py` - Partition key strategies

## Configuration

Services use the `ACTIVE_BROKERS=paper,zerodha` environment variable to determine which broker topics to subscribe to and process, enabling unified multi-broker management.