# Multi-Broker Architecture (Hybrid Multi-Broker Mode)

## Executive Summary

Alpha Panda implements a **Hybrid Multi-Broker Architecture** where a single deployment manages multiple brokers while maintaining complete data isolation. This architecture uses `ACTIVE_BROKERS` configuration to enable simultaneous paper trading and live trading with guaranteed separation of portfolios, execution, and risk management through topic-level isolation.

## Core Architecture Principles

### 1. Complete Broker Segregation

**🏢 CRITICAL PRINCIPLE**: Paper trading (`paper`) and Zerodha trading (`zerodha`) are **TWO COMPLETELY DISTINCT BROKERS** with complete isolation:

- **Separate Trading Engines**: PaperTrader and ZerodhaTrader are completely independent
- **Separate Data Namespaces**: All topics, cache keys, and data streams are broker-prefixed
- **NO Data Mixing**: Paper and Zerodha data never intersect
- **Parallel Processing**: Both brokers can run simultaneously

### 2. Topic-Based Data Isolation

All event topics are prefixed by broker namespace to ensure hard segregation:

**Topic Naming Convention**: `{broker}.{domain}.{event_type}[.dlq]`

**Examples**:
- **Market Data (shared)**: `market.ticks`
- **Paper Topics**: `paper.signals.raw`, `paper.signals.validated`, `paper.orders.submitted`, `paper.orders.filled`, `paper.pnl.snapshots`
- **Zerodha Topics**: `zerodha.signals.raw`, `zerodha.signals.validated`, `zerodha.orders.submitted`, `zerodha.orders.filled`, `zerodha.pnl.snapshots`
- **Dead Letter Queues**: `paper.orders.filled.dlq`, `zerodha.signals.validated.dlq`

**📊 Market Data Exception**: Market data uses a single shared `market.ticks` topic (single Zerodha feed) for both brokers.

> Note on legacy namespacing: historical references to a single `broker_namespace` driving runtime behavior are deprecated. Routing must be derived from the topic broker prefix. The `broker_namespace` label is retained only for metrics namespacing/compatibility and should be phased out in favor of explicit `broker`/`broker_context` usage.

### 3. Cache Key Isolation

Redis cache keys are prefixed by broker namespace:
- **Paper Cache**: `paper:portfolio:*`, `paper:positions:*`, `paper:orders:*`
- **Zerodha Cache**: `zerodha:portfolio:*`, `zerodha:positions:*`, `zerodha:orders:*`

## Unified Deployment Model

### Single-Instance Multi-Broker Architecture

The system runs as **a single unified application instance** managing multiple brokers:

```bash
# Single deployment managing multiple brokers (default)
ACTIVE_BROKERS=paper,zerodha python cli.py run

# Single broker deployment (if needed)
ACTIVE_BROKERS=paper python cli.py run
```

### Service Architecture

The unified deployment features:
- **Topic-Aware Handlers**: Services extract broker context from topic names for routing
- **Unified Consumer Groups**: Single consumer group per service processes all broker topics
- **Dynamic Topic Subscription**: Services subscribe to topics for all active brokers at startup
- **Broker-Prefixed Cache Keys**: Maintain isolation through `paper:*` vs `zerodha:*` key prefixes

## Signal Flow Architecture

### 1. Strategy Configuration (Broker-Aware)

Strategies are configured with explicit broker lists:

```yaml
# momentum_strategy.yaml
brokers: ['paper', 'zerodha']  # Trades on both brokers

# conservative_strategy.yaml  
brokers: ['paper']             # Paper trading only
```

### 2. Signal Duplication (Fan-Out Pattern)

**StrategyRunnerService** implements the critical fan-out mechanism:

1. **Single Strategy Runner**: One `StrategyRunnerService` processes all market data
2. **Signal Generation**: Strategy generates trading signal based on market conditions
3. **Active Brokers Fan-Out**: For each broker in `settings.active_brokers`, publishes identical signal to broker-specific topic:
   - Signal → `paper.signals.raw` 
   - Same signal → `zerodha.signals.raw`

### 3. Unified Processing with Topic-Aware Routing

Single service instances handle all active brokers with topic-aware message routing:

**Unified Services Process All Brokers**:
- **Risk Manager**: Consumes from all `{broker}.signals.raw` topics → publishes to appropriate `{broker}.signals.validated`
- **Paper Trading (broker-scoped)**: Consumes `paper.signals.validated` → emits paper order lifecycle `paper.orders.*` and `paper.pnl.snapshots`
- **Zerodha Trading (broker-scoped)**: Consumes `zerodha.signals.validated` → emits zerodha order lifecycle `zerodha.orders.*` and `zerodha.pnl.snapshots`

**Topic-Aware Message Handlers**:
All handlers receive `(message, topic)` parameters and extract broker context from topic names for proper routing.

## Service Architecture

### Shared Services (Single-broker model)
- **Market Feed Service**: Single service publishing to shared `market.ticks` topic using **Zerodha API only**
- **Auth Service**: Handles JWT authentication and user management

### Multi-Broker Services (Single instance handling multiple brokers)
- **Strategy Runner Service**: Fans out signals to all `settings.active_brokers` topics
- **Risk Manager Service**: Topic-aware handlers validate signals for all active brokers
- **Paper Trading Service**: Broker-scoped trading for `paper.*` topics
- **Zerodha Trading Service**: Broker-scoped trading for `zerodha.*` topics

## Configuration Management

### Environment Variables

**Core Configuration**:
```bash
ACTIVE_BROKERS=paper,zerodha    # Comma-separated list of active brokers
TRADING__PAPER__ENABLED=true
TRADING__ZERODHA__ENABLED=false # Enable to activate live order placement
# Zerodha auth/feed are always-on; ensure API key/secret are configured
```

### Deployment Patterns

**Unified Multi-Broker Deployment (Recommended)**:
```bash
# Single deployment managing multiple brokers
ACTIVE_BROKERS=paper,zerodha python cli.py run
```

**Single Broker Deployment**:
```bash
# Paper trading only
ACTIVE_BROKERS=paper python cli.py run

# Zerodha trading only
ACTIVE_BROKERS=zerodha python cli.py run
```

## Fault Isolation Benefits

### 1. Topic-Level Isolation
- **Zerodha API failure**: Only affects zerodha message processing, paper trading continues
- **Paper trader bug**: Only affects paper topic handlers, live trading unaffected  
- **Message processing errors**: Isolated by topic namespace with DLQ support

### 2. Simplified Operations
- **Single deployment**: Easier to manage than multiple processes
- **Unified monitoring**: Single service instance to monitor
- **Resource efficiency**: Shared infrastructure for both brokers

### 3. Flexible Configuration
- **Runtime broker selection**: Change active brokers via configuration
- **Feature rollouts**: Test features with paper broker first
- **Gradual rollouts**: Enable brokers incrementally

## Dashboard Integration

### Unified Read Layer

Dashboard connects through **single FastAPI service** that:
- **Reads from all broker namespaces**: Queries both `paper:*` and `zerodha:*` Redis keys
- **Provides unified API**: Single endpoint aggregates data from multiple brokers
- **Maintains separation**: Clear distinction between paper and live data

### API Patterns

```http
GET /api/v1/portfolios/paper/summary     # Paper trading data
GET /api/v1/portfolios/zerodha/summary   # Live trading data
GET /api/v1/portfolios/all/summary       # Aggregated view
```

## Adding New Brokers

The architecture scales easily to support additional brokers:

1. **Add Broker Support**: Add `'alpaca'` to supported brokers in settings validation
2. **Implement Trading Service**: Create broker-scoped trading service for the new broker
3. **Update Configuration**: Set `ACTIVE_BROKERS=paper,zerodha,alpaca`
4. **Topic Routing**: Services automatically handle `alpaca.*` topics
5. **Update Dashboard**: Add alpaca-specific API endpoints

## Implementation Verification

The hybrid multi-broker architecture has been thoroughly verified:

✅ **Topic Isolation**: Dynamic topic subscription based on active brokers
✅ **Unified Consumer Groups**: Single consumer group per service handles all broker topics  
✅ **Cache Key Prefixing**: Redis keys properly namespaced by broker
✅ **Signal Fan-Out**: Strategies publish to all active broker topics
✅ **Topic-Aware Routing**: Services extract broker context from topic names
✅ **Configuration Management**: `ACTIVE_BROKERS` environment variable works
✅ **Message Isolation**: Broker-specific message processing with shared infrastructure

## Summary

The Hybrid Multi-Broker Architecture provides:
- **Complete Data Isolation** between brokers through topic namespacing
- **Unified Service Management** with single deployment handling multiple brokers
- **Topic-Aware Processing** enabling intelligent message routing
- **Simplified Operations** compared to separate process architectures
- **Scalable Broker Support** through configuration-driven activation
- **Production-Ready Reliability** with fault isolation at the topic level

This architecture ensures that multiple brokers operate with complete data separation while sharing infrastructure, strategy logic, and market data sources through a single, unified deployment.
