# Services Documentation

## Service Architecture

Alpha Panda follows a microservices architecture with event streaming, where all services implement the stream processing pattern with complete broker segregation.

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

### 4. Trading Engine Service (`services/trading_engine/`)
- **Input**: Consumes from `{broker}.signals.validated` topic + `market.ticks` for pricing
- **Processing**:
  - Routes validated signals based on execution mode
  - **Paper Trading**: Uses `PaperTrader` for simulation
  - **Zerodha Trading**: Uses `ZerodhaTrader` for real execution (per-strategy config)
- **Output**: Publishes to `{broker}.orders.filled` or `{broker}.orders.failed` topics
- **Events**: `EventType.ORDER_FILLED`, `EventType.ORDER_FAILED`, `EventType.ORDER_PLACED`

### 5. Portfolio Manager Service (`services/portfolio_manager/`)
- **Input**: Consumes from `{broker}.orders.filled` topic
- **Processing**:
  - Updates portfolio positions and P&L
  - Calculates real-time portfolio metrics
  - Maintains position history
- **Output**: Updates Redis cache with broker-prefixed keys (`{broker}:portfolio:*`)
- **Cache Keys**: `{broker}:portfolio:{strategy_id}`, `{broker}:positions:*`

### 6. API Service (`api/`)
- **Input**: HTTP requests for portfolio/position data
- **Processing**: Serves cached data from Redis with broker-specific routing
- **Output**: JSON responses with current portfolio state
- **Read-Only**: Never writes to core trading pipeline

## Common Patterns

All services follow these patterns:
- **StreamProcessor Pattern**: Inherit from base class with producer/consumer and deduplication
- **Broker Namespace**: Each service instance is configured with `BROKER_NAMESPACE=paper|zerodha`
- **Event Deduplication**: Consumer-side dedup using event_id in Redis with TTL
- **Graceful Shutdown**: `await consumer.stop()` and `await producer.stop()`

## Configuration

Services are configured through environment variables and central settings, with broker-specific deployment controlled by the `BROKER_NAMESPACE` variable.