# Services Documentation

## Service Architecture

Alpha Panda follows a microservices architecture with unified log streaming, where services implement the modern StreamServiceBuilder pattern with multi-broker support. Services use composition-first design with protocol contracts and topic-aware message handling.

## Service Execution Flow

### 1. Market Feed Service (`services/market_feed/`)
- **Input**: Zerodha WebSocket market data (live) or Mock data (development)
- **Processing**: Formats ticks to standardized `MarketTick` events
- **Output**: Publishes to `market.ticks` topic (shared by all brokers)
- **Key**: Partitioned by `instrument_token` for ordering

### 2. Strategy Runner Service (`services/strategy_runner/`)
- **Input**: Consumes from `market.ticks` topic
- **Processing**: 
  - Loads active strategies from database
  - Filters ticks by strategy instrument configuration
  - Executes pure strategy logic (`BaseStrategy.on_market_data()`)
- **Output**: Publishes to `{broker}.signals.raw` topic (e.g., `paper.signals.raw`)
- **Key**: Partitioned by `strategy_id:instrument_token` for ordering
- **Events**: `EventType.TRADING_SIGNAL`

### 3. Risk Manager Service (`services/risk_manager/`)
- **Input**: Consumes from `{broker}.signals.raw` topic
- **Processing**:
  - Validates signals against risk rules (position limits, exposure, etc.)
  - Checks portfolio state and current positions
  - Applies risk constraints and filters
- **Output**: 
  - **Approved**: Publishes to `{broker}.signals.validated` topic
  - **Rejected**: Publishes to `{broker}.signals.rejected` topic
- **Events**: `EventType.VALIDATED_SIGNAL` or `EventType.REJECTED_SIGNAL`

### 4. Broker‑Scoped Trading Services
- Paper Trading (`services/paper_trading/`)
  - Input: `paper.signals.validated`
  - Output: broker‑scoped order lifecycle topics (`paper.orders.*`)
  - Notes: Purely simulated execution path
- Zerodha Trading (`services/zerodha_trading/`)
  - Input: `zerodha.signals.validated`
  - Output: broker‑scoped order lifecycle topics (`zerodha.orders.*`)
  - Notes: Real broker integration path

Migration completed: legacy `services/trading_engine/` and `services/portfolio_manager/` have been removed. Trading is now handled by `services/paper_trading/` and `services/zerodha_trading/`.

### 6. API Service (`api/`)
- **Input**: HTTP requests for portfolio/position data
- **Processing**: Serves cached data from Redis with broker-specific routing
- **Output**: JSON responses with current portfolio state
- **Read-Only**: Never writes to core trading pipeline

## Modern Service Patterns

### StreamServiceBuilder Pattern
All services use the modern StreamServiceBuilder for composition-based architecture:

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

### Topic-Aware Handlers
Message handlers accept (message, topic) parameters for broker context extraction:

```python
async def _handle_message(self, message: Dict[str, Any], topic: str) -> None:
    broker = topic.split('.')[0]  # Extract broker: "paper.signals.raw" -> "paper"
    # Route based on broker context
```

### Multi-Broker Architecture
- **Unified Deployment**: Single service instance handles multiple brokers (`ACTIVE_BROKERS=paper,zerodha`)
- **Topic Segregation**: Broker-prefixed topics for hard isolation (paper.*, zerodha.*)
- **Unified Consumer Groups**: Single consumer group processes all broker topics
- **Cache Segregation**: Redis keys prefixed by broker for state isolation

> Deprecation note: any design that centralizes behavior around a global `broker_namespace` should be considered transitional. Services must derive broker routing from topic names and pass explicit broker context to metrics. The `broker_namespace` label is maintained for metrics compatibility only and should be refactored out over time.

## Service Types

### Shared Services (Single-Broker Model)
- **Market Feed Service**: Single Zerodha feed publishing to shared `market.ticks` topic
- **Auth Service**: Unified authentication for all brokers

### Multi-Broker Services (Unified Instance Model)  
- **Strategy Runner**: Processes ticks, generates signals for all active brokers
- **Risk Manager**: Validates signals from all brokers with separate risk rules

### Broker-Scoped Services  
- **Paper Trading**: Simulated execution for paper broker; emits orders and PnL snapshots
- **Zerodha Trading**: Live execution path for zerodha broker; emits orders and PnL snapshots

## Migration Completed
- DI now starts `paper_trading_service` and `zerodha_trading_service` only.
- Monitoring and dashboards include dedicated panels for both services (events, DLQ, inactivity, lag).
- Topic bootstrap scripts include `{broker}.pnl.snapshots` topics.

## Configuration

Services use multi-broker configuration with `ACTIVE_BROKERS` environment variable:

```bash
# Multi-broker deployment (default)
ACTIVE_BROKERS=paper,zerodha

# Single broker deployment  
ACTIVE_BROKERS=paper
```
