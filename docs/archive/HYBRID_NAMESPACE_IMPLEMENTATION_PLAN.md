# Comprehensive Hybrid Namespace Implementation Plan (UPDATED)

## Executive Summary

This document outlines a comprehensive plan to refactor Alpha Panda's namespace system from **environment-specific deployments** (`BROKER_NAMESPACE=paper|zerodha`) to a **single deployment managing multiple brokers** while preserving topic-level namespace isolation.

### Key Objectives
- ✅ **Remove `BROKER_NAMESPACE` environment variable dependency**
- ✅ **Enable single service instance to handle multiple brokers**
- ✅ **Preserve topic namespace isolation** (`paper.orders.filled` vs `zerodha.orders.filled`)
- ✅ **Maintain hard data segregation** at infrastructure level
- ✅ **Simplify deployment and operations**

### Critical Updates Based on Codebase Analysis
- 🔧 **Infrastructure-First Approach**: ReliabilityLayer must be updated to pass topic information to handlers
- 🔄 **Clean Pattern Migration**: Standardize all services to use topic-aware handlers (no wrapper patterns)
- 🎯 **Direct Architecture Transition**: Clean implementation without backward compatibility constraints
- ⚖️ **Consumer Group Strategy**: Unified groups for multi-broker processing with ordering guarantees

---

## Architecture Overview

### Current State: Environment-Specific Deployments
```
Deployment 1: BROKER_NAMESPACE=paper
- Topics: paper.signals.validated, paper.orders.filled
- Consumer Group: alpha-panda.trading-engine.paper

Deployment 2: BROKER_NAMESPACE=zerodha  
- Topics: zerodha.signals.validated, zerodha.orders.filled
- Consumer Group: alpha-panda.trading-engine.zerodha
```

### Target State: Unified Multi-Broker Deployment
```
Single Deployment: active_brokers=[paper, zerodha]
- Topics: [paper.signals.validated, zerodha.signals.validated, paper.orders.filled, zerodha.orders.filled]
- Consumer Group: alpha-panda.trading-engine.signals (unified)
- Routing: Extract broker from topic name in handlers
```

---

## Phase 0: Infrastructure Prerequisites (NEW - MANDATORY)

### 0.1 Current Architecture Analysis

**CRITICAL FINDINGS** from codebase review:

1. **Topic Information Available**: MessageConsumer provides topic in raw messages, ServiceOrchestrator passes complete messages
2. **Mixed Implementation Patterns**:
   - **Pattern A**: Wrapper functions (`_handle_message_wrapper`) extract topic from message content
   - **Pattern B**: Direct handlers rely on service configuration, no topic extraction
3. **Complete Broker Infrastructure**: TopicMap, consumer groups, and broker segregation already implemented

### 0.2 Infrastructure Layer Updates

**File**: `core/streaming/reliability/reliability_layer.py`

**CRITICAL CHANGE**: Update ReliabilityLayer to pass topic to handlers:

```python
# Current implementation (line 60):
await self.handler_func(message_value)

# NEW implementation:
async def process_message(self, raw_message: Dict[str, Any]) -> None:
    """Process a message with topic context and all reliability features."""
    message_value = raw_message['value']
    topic = raw_message['topic']  # EXTRACT topic from raw message
    # ... existing code ...
    
    try:
        # UPDATED: Execute business logic with topic context
        await self.handler_func(message_value, topic)
        # ... rest remains same ...
```

**File**: `core/streaming/patterns/stream_service_builder.py`

**CRITICAL CHANGE**: Update handler signature support:

```python
def add_consumer_handler(
    self,
    topics: List[str],
    group_id: str,
    handler_func: Callable[[Dict[str, Any], str], Awaitable[None]]  # UPDATED signature
) -> 'StreamServiceBuilder':
```

## Phase 1: Settings and Configuration Refactoring

### 1.1 Clean Settings Configuration

**File**: `core/config/settings.py`

**CLEAN IMPLEMENTATION**: Replace broker_namespace with active_brokers:

```python
class Settings(BaseSettings):
    # REMOVED: broker_namespace field entirely
    # ADDED: Multi-broker support
    active_brokers: List[str] = Field(
        default=["paper", "zerodha"],
        description="List of active broker namespaces for this deployment instance"
    )
    
    @validator('active_brokers')
    def validate_active_brokers(cls, v):
        """Validate that all brokers are supported"""
        supported_brokers = {"paper", "zerodha"}
        invalid_brokers = set(v) - supported_brokers
        if invalid_brokers:
            raise ValueError(f"Unsupported brokers: {invalid_brokers}")
        if not v:
            raise ValueError("At least one active broker is required")
        return v
    
    # Environment variable support for active_brokers
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        # Support ACTIVE_BROKERS=paper,zerodha environment variable
        field_aliases={"active_brokers": "ACTIVE_BROKERS"}
    )
```

### 1.2 Environment Configuration

**Environment Variable Change**:
```bash
# OLD: BROKER_NAMESPACE=paper
# NEW: ACTIVE_BROKERS=paper,zerodha
```

**Docker Compose Update**:
```yaml
# OLD:
environment:
  BROKER_NAMESPACE: paper

# NEW:
environment:
  ACTIVE_BROKERS: paper,zerodha
```

### 1.2 StreamServiceBuilder Enhancement

**Critical Requirement**: Enable handlers to receive `topic` parameter for broker inference.

**File**: `core/streaming/patterns/stream_service_builder.py`

**Current Handler Signature**:
```python
handler_func: Callable[[Dict[str, Any]], Awaitable[None]]
```

**Enhanced Handler Signature**:
```python
handler_func: Callable[[Dict[str, Any], str], Awaitable[None]]  # Added topic parameter
```

**Implementation Changes**:

1. **Update `add_consumer_handler` method**:
```python
def add_consumer_handler(
    self,
    topics: List[str],
    group_id: str,
    handler_func: Callable[[Dict[str, Any], str], Awaitable[None]]  # Topic-aware handler
) -> 'StreamServiceBuilder':
    """Add a consumer with topic-aware handler function."""
    
    # Create consumer
    consumer = MessageConsumer(self.config, topics, group_id)
    
    # Create enhanced reliability layer
    reliability_layer = EnhancedReliabilityLayer(
        service_name=self.service_name,
        handler_func=handler_func,  # Now topic-aware
        consumer=consumer,
        deduplicator=self._deduplicator,
        error_handler=self._error_handler,
        metrics_collector=self._metrics_collector
    )
    
    # Add to orchestrator
    self.orchestrator.add_consumer_flow(consumer, reliability_layer)
    return self
```

### 1.3 Enhanced Reliability Layer

**File**: `core/streaming/reliability/enhanced_reliability_layer.py` (NEW)

```python
import logging
from typing import Callable, Awaitable, Dict, Any, Optional
from datetime import datetime, timezone

from .deduplication_manager import DeduplicationManager
from .error_handler import ErrorHandler  
from .metrics_collector import MetricsCollector
from ..correlation import CorrelationContext, CorrelationLogger

logger = logging.getLogger(__name__)

class EnhancedReliabilityLayer:
    """Enhanced reliability layer with topic-aware message processing."""
    
    def __init__(
        self,
        service_name: str,
        handler_func: Callable[[Dict[str, Any], str], Awaitable[None]],  # Topic-aware
        consumer,
        deduplicator: Optional[DeduplicationManager] = None,
        error_handler: Optional[ErrorHandler] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        self.service_name = service_name
        self.handler_func = handler_func
        self.consumer = consumer
        self.deduplicator = deduplicator
        self.error_handler = error_handler
        self.metrics_collector = metrics_collector or MetricsCollector(service_name)
        self.correlation_logger = CorrelationLogger(service_name)
    
    async def process_message(self, raw_message: Dict[str, Any]) -> None:
        """Process a message with topic context and all reliability features."""
        message_value = raw_message['value']
        topic = raw_message['topic']  # Extract topic from raw message
        event_id = message_value.get('id')
        correlation_id = message_value.get('correlation_id')
        
        # Extract broker from topic for enhanced logging
        broker = topic.split('.')[0] if '.' in topic else 'unknown'
        
        # 1. Set up correlation context with broker information
        if correlation_id:
            CorrelationContext.continue_trace(
                correlation_id, event_id, self.service_name, 
                f"process_{topic}", extra_context={"broker": broker}
            )
        else:
            correlation_id = CorrelationContext.start_new_trace(
                self.service_name, f"process_{topic}", 
                extra_context={"broker": broker}
            )
        
        # 2. Check for duplicates (broker-aware caching)
        if (self.deduplicator and event_id and 
            await self.deduplicator.is_duplicate(event_id, broker_context=broker)):
            self.correlation_logger.debug("Skipping duplicate event", 
                                        event_id=event_id, broker=broker, topic=topic)
            await self.consumer.commit(raw_message)
            return
        
        # 3. Process with error handling and metrics
        start_time = datetime.now(timezone.utc)
        try:
            # Execute business logic with topic context
            await self.handler_func(message_value, topic)
            
            # Commit and mark as processed
            await self.consumer.commit(raw_message)
            if self.deduplicator and event_id:
                await self.deduplicator.mark_processed(event_id, broker_context=broker)
            
            # Record success metrics with broker context
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            self.correlation_logger.debug("Message processed successfully", 
                                        duration_ms=duration * 1000,
                                        broker=broker, topic=topic)
            
            if self.metrics_collector:
                await self.metrics_collector.record_success(duration, broker_context=broker)
        
        except Exception as e:
            self.correlation_logger.error("Failed to process message", 
                                        error=str(e), broker=broker, topic=topic)
            
            if self.error_handler:
                # Error handler manages retries, DLQ, and commits
                await self.error_handler.handle_processing_error_async(
                    raw_message, e, 
                    processing_func=lambda: self.handler_func(message_value, topic),
                    commit_func=lambda: self.consumer.commit(raw_message),
                    broker_context=broker
                )
            else:
                # Simple error handling - log and commit to avoid reprocessing
                logger.error(f"Unhandled processing error for {broker}: {e}")
                await self.consumer.commit(raw_message)
            
            if self.metrics_collector:
                await self.metrics_collector.record_failure(str(e), broker_context=broker)
```

### 1.4 Broker-Aware Deduplication Manager

**File**: `core/streaming/reliability/deduplication_manager.py`

**Enhancement to support broker context**:
```python
async def is_duplicate(self, event_id: str, broker_context: str = None) -> bool:
    """Check if event is duplicate with optional broker context."""
    cache_key = f"event_dedup:{event_id}"
    if broker_context:
        cache_key = f"event_dedup:{broker_context}:{event_id}"
    
    return await self.redis_client.exists(cache_key)

async def mark_processed(self, event_id: str, broker_context: str = None, ttl: int = 3600) -> None:
    """Mark event as processed with optional broker context."""
    cache_key = f"event_dedup:{event_id}"
    if broker_context:
        cache_key = f"event_dedup:{broker_context}:{event_id}"
    
    await self.redis_client.setex(cache_key, ttl, "processed")
```

---

## Phase 2: Service Refactoring - Clean Multi-Broker Implementation

### 2.1 Standardized Topic-Aware Handler Pattern

**TARGET ARCHITECTURE**: All services use direct topic-aware handlers (no wrapper functions):

```python
# NEW STANDARD PATTERN for all services
async def _handle_validated_signal(self, message: Dict[str, Any], topic: str) -> None:
    """Handle validated signal with broker context from topic"""
    # Extract broker from topic name (e.g., "paper.signals.validated" -> "paper")
    broker = topic.split('.')[0]
    
    # Use broker for context-aware processing
    self.logger.info("Processing validated signal", broker=broker, topic=topic)
```

### 2.2 Trading Engine Service Refactoring

**File**: `services/trading_engine/service.py`

**CLEAN MULTI-BROKER IMPLEMENTATION**:
```python
class TradingEngineService:
    def __init__(self, config, settings, redis_client, trader_factory, execution_router, market_hours_checker):
        self.settings = settings
        self.trader_factory = trader_factory
        self.execution_router = execution_router
        self.market_hours_checker = market_hours_checker
        
        # State management
        self.last_prices: Dict[int, float] = {}
        self.pending_signals: Dict[int, list] = defaultdict(list)
        self.warmed_up_instruments: set[int] = set()
        
        # Enhanced logging setup
        self.logger = get_trading_logger_safe("trading_engine")
        self.perf_logger = get_performance_logger_safe("trading_engine_performance")
        self.error_logger = get_error_logger_safe("trading_engine_errors")
        
        # --- REFACTORED: Multi-broker topic subscription ---
        # Generate list of topics for all active brokers
        validated_signal_topics = []
        for broker in settings.active_brokers:
            topic_map = TopicMap(broker)
            validated_signal_topics.append(topic_map.signals_validated())
        
        # Build orchestrator with topic-aware handlers
        self.orchestrator = (StreamServiceBuilder("trading_engine", config, settings)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                topics=validated_signal_topics,  # Multiple broker topics
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.signals",  # Unified group
                handler_func=self._handle_validated_signal  # Now topic-aware
            )
            .add_consumer_handler(
                topics=[TopicNames.MARKET_TICKS],  # Market data is shared
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.ticks",
                handler_func=self._handle_market_tick
            )
            .build()
        )

    # --- ENHANCED: Topic-aware message handlers ---
    async def _handle_validated_signal(self, message: Dict[str, Any], topic: str) -> None:
        """Handle validated signal with broker context from topic."""
        # Extract broker from topic name (e.g., "paper.signals.validated" -> "paper")
        broker = topic.split('.')[0]
        
        self.logger.info("Processing validated signal", 
                        broker=broker, 
                        topic=topic,
                        strategy_id=message.get('data', {}).get('original_signal', {}).get('strategy_id'))
        
        if message.get('type') != EventType.VALIDATED_SIGNAL:
            return
        
        if not self.market_hours_checker.is_market_open():
            self.logger.debug("Ignoring validated signal - market is closed", broker=broker)
            return
        
        # ... existing validation logic ...
        
        # Route to appropriate trader based on broker
        signal = TradingSignal(**original_signal)
        await self._execute_on_trader(signal, broker)
        
        self.processed_count += 1

    async def _execute_on_trader(self, signal: TradingSignal, broker: str) -> None:
        """Execute signal on the trader for the specified broker."""
        try:
            # Get broker-specific trader
            trader = self.trader_factory.get_trader(broker)
            last_price = self.last_prices.get(signal.instrument_token)
            
            result_data = await trader.execute_order(signal, last_price)
            
            # Emit result to broker-specific topic
            await self._emit_execution_result(signal, result_data, broker)
            
        except Exception as e:
            self.error_count += 1
            self.error_logger.error(f"Execution failed on {broker}",
                                  strategy_id=signal.strategy_id,
                                  broker=broker,
                                  error=str(e))

    async def _emit_execution_result(self, signal: TradingSignal, result_data: Dict[str, Any], broker: str):
        """Emit appropriate event to broker-specific topic."""
        if not self.orchestrator.producers:
            self.error_logger.error("No producers available for emitting events")
            return
        
        producer = self.orchestrator.producers[0]
        
        # Dynamically construct broker-specific topic
        topic_map = TopicMap(broker)
        
        if "error_message" in result_data:
            event_type = EventType.ORDER_FAILED
            topic = topic_map.orders_failed()
        elif broker == "paper":
            event_type = EventType.ORDER_FILLED
            topic = topic_map.orders_filled()
        else:  # zerodha or other live trading
            event_type = EventType.ORDER_PLACED
            topic = topic_map.orders_submitted()
        
        key = f"{signal.strategy_id}:{signal.instrument_token}"
        
        await producer.send(
            topic=topic,
            key=key,
            data=result_data,
            event_type=event_type,
        )
        
        self.logger.info("Execution result emitted", 
                        broker=broker, 
                        topic=topic, 
                        event_type=event_type.value)
```
        
        # --- ENHANCED: Multi-broker topic subscription ---
        # Generate list of topics for all active brokers
        validated_signal_topics = []
        for broker in settings.active_brokers:
            topic_map = TopicMap(broker)
            validated_signal_topics.append(topic_map.signals_validated())
        
        # Build orchestrator with topic-aware handlers
        self.orchestrator = (StreamServiceBuilder("trading_engine", config, settings)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                topics=validated_signal_topics,  # Multiple broker topics
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.signals",  # Unified group
                handler_func=self._handle_validated_signal  # Now topic-aware
            )
            .add_consumer_handler(
                topics=[TopicNames.MARKET_TICKS],  # Market data is shared
                group_id=f"{settings.redpanda.group_id_prefix}.trading_engine.ticks",
                handler_func=self._handle_market_tick
            )
            .build()
        )

    # --- ENHANCED: Topic-aware message handlers ---
    async def _handle_validated_signal(self, message: Dict[str, Any], topic: str) -> None:
        """Handle validated signal with broker context from topic."""
        # Extract broker from topic name (e.g., "paper.signals.validated" -> "paper")
        broker = topic.split('.')[0]
        
        self.logger.info("Processing validated signal", 
                        broker=broker, 
                        topic=topic,
                        strategy_id=message.get('data', {}).get('original_signal', {}).get('strategy_id'))
        
        if message.get('type') != EventType.VALIDATED_SIGNAL:
            return
        
        if not self.market_hours_checker.is_market_open():
            self.logger.debug("Ignoring validated signal - market is closed", broker=broker)
            return
        
        # ... existing validation logic ...
        
        # Route to appropriate trader based on broker
        signal = TradingSignal(**original_signal)
        await self._execute_on_trader(signal, broker)
        
        self.processed_count += 1

    async def _execute_on_trader(self, signal: TradingSignal, broker: str) -> None:
        """Execute signal on the trader for the specified broker."""
        try:
            # Get broker-specific trader
            trader = self.trader_factory.get_trader(broker)
            last_price = self.last_prices.get(signal.instrument_token)
            
            result_data = await trader.execute_order(signal, last_price)
            
            # Emit result to broker-specific topic
            await self._emit_execution_result(signal, result_data, broker)
            
        except Exception as e:
            self.error_count += 1
            self.error_logger.error(f"Execution failed on {broker}",
                                  strategy_id=signal.strategy_id,
                                  broker=broker,
                                  error=str(e))

    async def _emit_execution_result(self, signal: TradingSignal, result_data: Dict[str, Any], broker: str):
        """Emit appropriate event to broker-specific topic."""
        if not self.orchestrator.producers:
            self.error_logger.error("No producers available for emitting events")
            return
        
        producer = self.orchestrator.producers[0]
        
        # Dynamically construct broker-specific topic
        topic_map = TopicMap(broker)
        
        if "error_message" in result_data:
            event_type = EventType.ORDER_FAILED
            topic = topic_map.orders_failed()
        elif broker == "paper":
            event_type = EventType.ORDER_FILLED
            topic = topic_map.orders_filled()
        else:  # zerodha or other live trading
            event_type = EventType.ORDER_PLACED
            topic = topic_map.orders_submitted()
        
        key = f"{signal.strategy_id}:{signal.instrument_token}"
        
        await producer.send(
            topic=topic,
            key=key,
            data=result_data,
            event_type=event_type,
        )
        
        self.logger.info("Execution result emitted", 
                        broker=broker, 
                        topic=topic, 
                        event_type=event_type.value)
```

### 2.3 Strategy Runner Service Refactoring

**File**: `services/strategy_runner/service.py`

**CLEAN MULTI-BROKER IMPLEMENTATION**:
```python
class StrategyRunnerService:
    def __init__(self, config, settings, db_manager, redis_client=None, market_hours_checker=None):
        self.settings = settings
        self.db_manager = db_manager
        self.logger = get_trading_logger_safe("strategy_runner")
        
        # Store active brokers for signal generation
        self.active_brokers = settings.active_brokers
        self.strategy_runners: Dict[str, StrategyRunner] = {}
        self.strategy_instruments: Dict[str, List[int]] = {}
        
        # Build streaming service - CLEANED: Remove wrapper pattern
        self.orchestrator = (StreamServiceBuilder("strategy_runner", config, settings)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                topics=[TopicNames.MARKET_TICKS],  # Shared market data
                group_id=f"{settings.redpanda.group_id_prefix}.strategy_runner.ticks",
                handler_func=self._handle_market_tick  # Direct topic-aware handler
            )
            .build()
        )
    
    async def _handle_market_tick(self, message: Dict[str, Any], topic: str) -> None:
        """Process market tick and generate signals for all active brokers."""
        if message.get('type') != EventType.MARKET_TICK:
            return
        
        if not self.market_hours_checker.is_market_open():
            self.logger.debug("Ignoring market tick - market is closed")
            return
            
        tick_data = message.get("data", {})
        instrument_token = tick_data.get("instrument_token")
        
        if not instrument_token:
            return
        
        # Find strategies interested in this instrument
        interested_strategies = []
        for strategy_id, runner in self.strategy_runners.items():
            strategy_instruments = self.strategy_instruments.get(strategy_id, [])
            if instrument_token in strategy_instruments:
                interested_strategies.append((strategy_id, runner))
        
        # Process tick through each interested strategy
        for strategy_id, runner in interested_strategies:
            try:
                # Get strategy configuration for broker routing
                strategy_config = await self._get_strategy_config(strategy_id)
                
                # Generate signals for each active broker
                for broker in self.active_brokers:
                    if self._should_process_strategy_for_broker(strategy_config, broker):
                        signal = await runner.process_market_data(tick_data)
                        if signal:
                            await self._emit_signal(signal, broker, strategy_id)
                            
            except Exception as e:
                self.error_logger.error("Error executing strategy",
                                      strategy_id=strategy_id,
                                      instrument_token=instrument_token,
                                      error=str(e))
    
    def _should_process_strategy_for_broker(self, strategy_config: Dict, broker: str) -> bool:
        """Determine if strategy should generate signals for specific broker."""
        if broker == "paper":
            return True  # Always generate paper signals
        elif broker == "zerodha":
            return strategy_config.get('zerodha_trading_enabled', False)
        return False
    
    async def _emit_signal(self, signal: TradingSignal, broker: str, strategy_id: str):
        """Emit signal to broker-specific topic."""
        topic_map = TopicMap(broker)
        topic = topic_map.signals_raw()
        
        producer = self.orchestrator.producers[0]
        key = f"{strategy_id}:{signal.instrument_token}"
        
        await producer.send(
            topic=topic,
            key=key,
            data=signal.dict(),
            event_type=EventType.TRADING_SIGNAL
        )
        
        self.logger.info("Signal generated", 
                        broker=broker,
                        strategy_id=strategy_id,
                        signal_type=signal.signal_type,
                        topic=topic)
```

### 2.3 Portfolio Manager Service Refactoring

**File**: `services/portfolio_manager/service.py`

**Key Changes**:
```python
class PortfolioManagerService:
    def __init__(self, config, settings, db_manager, redis_client, portfolio_cache):
        # ... existing initialization ...
        
        # --- ENHANCED: Multi-broker order topic subscription ---
        order_topics = []
        for broker in settings.active_brokers:
            topic_map = TopicMap(broker)
            order_topics.extend([
                topic_map.orders_filled(),
                topic_map.orders_failed(),
                topic_map.orders_submitted()
            ])
        
        # Build orchestrator
        self.orchestrator = (StreamServiceBuilder("portfolio_manager", config, settings)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                topics=order_topics,  # All broker order topics
                group_id=f"{settings.redpanda.group_id_prefix}.portfolio_manager.orders",
                handler_func=self._handle_order_event  # Topic-aware
            )
            .build()
        )
        
        # --- ENHANCED: Broker-specific portfolio managers ---
        self.portfolio_managers = {}
        for broker in settings.active_brokers:
            if broker == "paper":
                self.portfolio_managers[broker] = PaperPortfolioManager(portfolio_cache, broker)
            elif broker == "zerodha":
                self.portfolio_managers[broker] = ZerodhaPortfolioManager(portfolio_cache, broker)
    
    async def _handle_order_event(self, message: Dict[str, Any], topic: str) -> None:
        """Handle order events with broker context."""
        # Extract broker from topic
        broker = topic.split('.')[0]
        
        self.logger.info("Processing order event", 
                        broker=broker, 
                        topic=topic,
                        event_type=message.get('type'))
        
        # Get broker-specific portfolio manager
        manager = self.portfolio_managers.get(broker)
        if not manager:
            self.error_logger.error(f"No portfolio manager for broker: {broker}")
            return
        
        # Route to appropriate handler based on topic suffix
        if topic.endswith(".filled"):
            await manager.process_fill(message.get('data'))
        elif topic.endswith(".failed"):
            await manager.process_failure(message.get('data'))
        elif topic.endswith(".submitted"):
            await manager.process_submission(message.get('data'))
        
        # Emit PnL snapshot to broker-specific topic
        await self._emit_pnl_snapshot(broker, manager.get_current_portfolio())
    
    async def _emit_pnl_snapshot(self, broker: str, portfolio_data: Dict[str, Any]):
        """Emit PnL snapshot to broker-specific topic."""
        topic_map = TopicMap(broker)
        topic = topic_map.pnl_snapshots()
        
        producer = self.orchestrator.producers[0]
        
        await producer.send(
            topic=topic,
            key=f"portfolio_snapshot_{broker}",
            data=portfolio_data,
            event_type=EventType.PNL_SNAPSHOT
        )
```

---

## Phase 3: Application Bootstrap and Container Updates

### 3.1 Application Main Updates

**File**: `app/main.py`

**Enhanced startup logging**:
```python
class ApplicationOrchestrator:
    def __init__(self):
        # ... existing initialization ...
        
        # --- ENHANCED: Multi-broker startup logging ---
        self.logger.info(f"🏢 Alpha Panda initializing with active brokers: {self.settings.active_brokers}")
        
        # Validate broker configuration
        self._validate_broker_configuration()
    
    def _validate_broker_configuration(self):
        """Validate that all active brokers are properly configured."""
        for broker in self.settings.active_brokers:
            if broker == "zerodha":
                if not self.settings.zerodha.api_key or not self.settings.zerodha.api_secret:
                    self.logger.warning(f"Zerodha broker active but credentials not configured")
            
            self.logger.info(f"✅ Broker '{broker}' configuration validated")
```

### 3.2 Dependency Injection Container Updates

**File**: `app/containers.py`

**Enhanced health checks for multiple brokers**:
```python
class AppContainer(containers.DeclarativeContainer):
    # ... existing providers ...
    
    @providers.provider
    def dynamic_health_checks(settings, auth_service, db_manager):
        """Generate health checks for all active brokers."""
        checks = [
            # Core infrastructure checks (broker-agnostic)
            DatabaseHealthCheck(db_manager=db_manager),
            RedisHealthCheck(redis_client=redis.from_url(settings.redis.url)),
            RedpandaHealthCheck(settings=settings),
            MarketHoursCheck(),
            ActiveStrategiesCheck(db_manager=db_manager),
        ]
        
        # Add broker-specific health checks
        for broker in settings.active_brokers:
            if broker != "paper":  # No external API for paper trading
                checks.extend([
                    BrokerApiHealthCheck(auth_service=auth_service, broker_name=broker),
                    ZerodhaAuthenticationCheck(auth_service=auth_service, broker_name=broker)
                ])
        
        return checks
    
    # Enhanced health monitor with dynamic checks
    system_health_monitor = providers.Singleton(
        SystemHealthMonitor,
        checks=dynamic_health_checks
    )
    
    # --- ENHANCED: Service providers with multi-broker support ---
    trading_engine_service = providers.Singleton(
        TradingEngineService,
        config=settings.provided.redpanda,
        settings=settings,
        redis_client=redis_client,
        trader_factory=trader_factory,
        execution_router=execution_router,
        market_hours_checker=market_hours_checker
    )
    
    strategy_runner_service = providers.Singleton(
        StrategyRunnerService,
        config=settings.provided.redpanda,
        settings=settings,  # Now uses active_brokers instead of broker_namespace
        db_manager=db_manager,
        redis_client=redis_client,
        market_hours_checker=market_hours_checker
    )
    
    portfolio_manager_service = providers.Singleton(
        PortfolioManagerService,
        config=settings.provided.redpanda,
        settings=settings,
        db_manager=db_manager,
        redis_client=redis_client,
        portfolio_cache=portfolio_cache
    )
```

---

## Phase 4: Enhanced Health Checks and Monitoring

### 4.1 Multi-Broker Health Check Enhancements

**File**: `core/health/multi_broker_health_checks.py` (NEW)

```python
from typing import Dict, List, Any
from .base import BaseHealthCheck, HealthCheckResult
from core.config.settings import Settings

class MultiBrokerHealthCheck(BaseHealthCheck):
    """Base class for broker-aware health checks."""
    
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
    
    async def check_all_brokers(self) -> List[HealthCheckResult]:
        """Check health for all active brokers."""
        results = []
        
        for broker in self.settings.active_brokers:
            try:
                result = await self.check_broker_health(broker)
                results.append(result)
            except Exception as e:
                results.append(HealthCheckResult(
                    component=f"{self.component_name}_{broker}",
                    passed=False,
                    message=f"Health check failed for {broker}: {str(e)}",
                    details={"broker": broker, "error": str(e)}
                ))
        
        return results
    
    async def check_broker_health(self, broker: str) -> HealthCheckResult:
        """Override this method in subclasses."""
        raise NotImplementedError

class BrokerTopicHealthCheck(MultiBrokerHealthCheck):
    """Verify that all broker-specific topics exist."""
    
    component_name = "broker_topics"
    
    async def check_broker_health(self, broker: str) -> HealthCheckResult:
        """Check if all required topics exist for a broker."""
        from core.schemas.topics import TopicMap
        
        topic_map = TopicMap(broker)
        required_topics = [
            topic_map.signals_raw(),
            topic_map.signals_validated(),
            topic_map.orders_submitted(),
            topic_map.orders_filled(),
            topic_map.pnl_snapshots()
        ]
        
        # Check topic existence using admin client
        # Implementation depends on your Kafka/Redpanda admin setup
        missing_topics = await self._check_topics_exist(required_topics)
        
        if missing_topics:
            return HealthCheckResult(
                component=f"broker_topics_{broker}",
                passed=False,
                message=f"Missing topics for {broker}: {', '.join(missing_topics)}",
                details={"broker": broker, "missing_topics": missing_topics}
            )
        
        return HealthCheckResult(
            component=f"broker_topics_{broker}",
            passed=True,
            message=f"All required topics exist for {broker}",
            details={"broker": broker, "topic_count": len(required_topics)}
        )

class BrokerStateHealthCheck(MultiBrokerHealthCheck):
    """Check broker-specific state and configuration."""
    
    component_name = "broker_state"
    
    async def check_broker_health(self, broker: str) -> HealthCheckResult:
        """Check broker state consistency."""
        checks = []
        
        # Check Redis cache keys are properly namespaced
        cache_health = await self._check_cache_namespace(broker)
        checks.append(cache_health)
        
        # Check database configuration for broker
        db_health = await self._check_database_config(broker)
        checks.append(db_health)
        
        # Aggregate results
        passed = all(check["passed"] for check in checks)
        message = f"Broker state check for {broker}: {'PASSED' if passed else 'FAILED'}"
        
        return HealthCheckResult(
            component=f"broker_state_{broker}",
            passed=passed,
            message=message,
            details={"broker": broker, "checks": checks}
        )
```

### 4.2 Enhanced Service Health Checker

**File**: `core/health/health_checker.py`

**Updates for multi-broker support**:
```python
class ServiceHealthChecker:
    def __init__(self, settings: Settings, redis_client):
        self.settings = settings
        self.redis_client = redis_client
    
    async def check_service_health(self) -> Dict[str, Any]:
        """Enhanced health check with multi-broker support."""
        health_status = {
            "service_name": "alpha_panda",
            "active_brokers": self.settings.active_brokers,  # Enhanced
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "broker_health": {}  # New: per-broker health
        }
        
        # Check health for each active broker
        for broker in self.settings.active_brokers:
            broker_health = await self._check_broker_health(broker)
            health_status["broker_health"][broker] = broker_health
        
        # Aggregate health status
        all_brokers_healthy = all(
            health["healthy"] for health in health_status["broker_health"].values()
        )
        health_status["overall_healthy"] = all_brokers_healthy
        
        return health_status
    
    async def _check_broker_health(self, broker: str) -> Dict[str, Any]:
        """Check health metrics for a specific broker."""
        return {
            "broker": broker,
            "healthy": True,  # Implement actual health logic
            "signal_generation": await self._check_signal_generation(broker),
            "order_processing": await self._check_order_processing(broker),
            "portfolio_updates": await self._check_portfolio_updates(broker)
        }
    
    async def _check_signal_generation(self, broker: str) -> Dict[str, Any]:
        """Check signal generation health for specific broker."""
        signals_key = f"alpha_panda:metrics:{broker}:signals:last_generated"
        signal_count_key = f"alpha_panda:metrics:{broker}:signals:count_last_5min"
        
        last_signal_time = await self.redis_client.get(signals_key)
        signal_count = await self.redis_client.get(signal_count_key)
        
        # Implement health logic...
        return {
            "healthy": True,
            "last_signal_time": last_signal_time,
            "signals_last_5min": signal_count or 0,
            "broker": broker
        }
```

---

## Phase 4: Migration and Deployment Strategy

### 4.1 Clean Migration Steps (No Backward Compatibility)

**Step 1: Infrastructure Update**
```bash
# 1. Update ReliabilityLayer to pass topic to handlers
# 2. Update StreamServiceBuilder signature 
# 3. Deploy infrastructure changes
# 4. Restart all services to pickup new infrastructure
```

**Step 2: Environment Configuration**
```bash
# Update environment variables
# OLD: BROKER_NAMESPACE=paper
# NEW: ACTIVE_BROKERS=paper,zerodha

# Update docker-compose.yml
# Remove BROKER_NAMESPACE environment variable
# Add ACTIVE_BROKERS=paper,zerodha
```

**Step 3: Service Refactoring (Coordinated Deployment)**
```bash
# Deploy all service changes simultaneously
# Services must be updated together due to handler signature change
1. Deploy TradingEngineService (critical path)
2. Deploy StrategyRunnerService 
3. Deploy PortfolioManagerService (remove wrapper pattern)
4. Deploy RiskManagerService (remove wrapper pattern)
5. Deploy all remaining services
```

**Step 4: Validation**
```bash
# Verify unified multi-broker operation
python -m core.health.broker_health_checker --check-all-brokers

# Verify topic-level isolation maintained
python scripts/validate_broker_isolation.py --brokers=paper,zerodha

# Verify unified consumer groups working
rpk group list | grep alpha-panda
```

### 4.2 Rollback Strategy

**If critical issues occur:**
1. **Emergency Stop**: Stop all services immediately
2. **Quick Revert**: Deploy previous version (keep old infrastructure available)
3. **Root Cause**: Fix issues in development environment  
4. **Clean Retry**: Re-attempt with fixes

### 4.3 Updated Testing Strategy

**Infrastructure Tests**:
```python
# Test ReliabilityLayer passes topic correctly
async def test_reliability_layer_topic_passing():
    handler_calls = []
    
    async def mock_handler(message, topic):
        handler_calls.append((message, topic))
    
    reliability_layer = ReliabilityLayer("test", mock_handler, mock_consumer)
    raw_message = {"topic": "paper.signals.validated", "value": {"data": "test"}}
    
    await reliability_layer.process_message(raw_message)
    
    assert len(handler_calls) == 1
    assert handler_calls[0][1] == "paper.signals.validated"
```

**Service Handler Tests**:
```python
# Test topic-aware handlers extract broker correctly
@pytest.mark.parametrize("topic,expected_broker", [
    ("paper.signals.validated", "paper"),
    ("zerodha.signals.validated", "zerodha")
])
async def test_topic_aware_handler(topic, expected_broker):
    service = TradingEngineService(...)
    
    message = {"type": "validated_signal", "data": {"original_signal": {...}}}
    await service._handle_validated_signal(message, topic)
    
    # Verify broker was correctly extracted and used
    assert service.last_processed_broker == expected_broker
```

**Multi-Broker Integration Tests**:
```python
async def test_unified_consumer_group_processing():
    # Test single service processes multiple broker topics
    settings = Settings(active_brokers=["paper", "zerodha"])
    service = TradingEngineService(config, settings, ...)
    
    # Publish signals to both broker topics
    await publish_signal("paper.signals.validated", paper_signal)
    await publish_signal("zerodha.signals.validated", zerodha_signal)
    
    # Verify both are processed by same service instance
    await wait_for_processing()
    
    # Verify outputs go to correct broker-specific topics
    paper_order = await consume_message("paper.orders.filled")
    zerodha_order = await consume_message("zerodha.orders.placed")
    
    assert paper_order is not None
    assert zerodha_order is not None
    
    # Verify no cross-contamination
    paper_zerodha_order = await try_consume_message("zerodha.orders.filled", timeout=1)
    zerodha_paper_order = await try_consume_message("paper.orders.placed", timeout=1)
    
    assert paper_zerodha_order is None
    assert zerodha_paper_order is None
```

**Load Testing**:
```python
async def test_unified_consumer_group_ordering():
    # Verify message ordering maintained with unified consumer groups
    service = TradingEngineService(config, settings, ...)
    
    # Send sequence of signals with same partition key
    signals = [create_signal(strategy="test", instrument=12345, seq=i) for i in range(100)]
    
    for i, signal in enumerate(signals):
        broker = "paper" if i % 2 == 0 else "zerodha"
        topic = f"{broker}.signals.validated"
        await publish_signal(topic, signal)
    
    # Verify processing order maintained
    await verify_processing_order(signals)
```

---

## Phase 6: Operations and Monitoring

### 6.1 Enhanced Logging

**Structured logging with broker context**:
```python
# All log messages should include broker context
self.logger.info("Processing validated signal",
                broker=broker,
                topic=topic,
                strategy_id=signal.strategy_id,
                instrument_token=signal.instrument_token)

# JSON output:
{
  "event": "Processing validated signal",
  "broker": "paper",
  "topic": "paper.signals.validated",
  "strategy_id": "momentum_v1",
  "instrument_token": 12345,
  "timestamp": "2025-01-20T10:30:00Z",
  "service": "trading_engine"
}
```

### 6.2 Monitoring and Alerting

**Broker-specific metrics**:
```python
# Metrics collection with broker dimensions
await metrics_collector.increment("signals.processed",
                                 tags={"broker": broker, "strategy": strategy_id})

await metrics_collector.histogram("order.processing_time",
                                 duration_ms,
                                 tags={"broker": broker, "outcome": "success"})
```

**Grafana Dashboard Queries**:
```sql
-- Signals processed by broker
sum(rate(signals_processed_total[5m])) by (broker)

-- Order processing latency by broker
histogram_quantile(0.95, order_processing_time_bucket) by (broker)

-- Broker health status
broker_healthy{broker=~"paper|zerodha"}
```

### 6.3 Troubleshooting Guide

**Common Issues and Solutions**:

1. **Cross-broker data leakage**:
   ```bash
   # Check Redis cache keys are properly prefixed
   redis-cli KEYS "*portfolio*" | grep -E "(paper|zerodha)"
   
   # Verify topic consumer assignments
   rpk group describe alpha-panda.trading-engine.signals
   ```

2. **Service not processing specific broker**:
   ```bash
   # Check if service subscribed to broker topics
   rpk group describe alpha-panda.trading-engine.signals --topics
   
   # Verify handler is receiving topic parameter
   tail -f logs/trading_engine.log | grep "broker="
   ```

3. **Performance degradation**:
   ```bash
   # Check consumer lag by topic
   rpk group lag alpha-panda.trading-engine.signals
   
   # Monitor message processing rates by broker
   grep "Message processed successfully" logs/*.log | grep -c "broker=paper"
   ```

---

## Updated Implementation Timeline

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| **Phase 0**: Infrastructure Prerequisites | 1.5 weeks | ReliabilityLayer update, StreamServiceBuilder signature change |
| **Phase 1**: Settings Configuration | 0.5 weeks | Remove broker_namespace, add active_brokers |
| **Phase 2**: Service Refactoring | 2 weeks | All services updated to topic-aware handlers (coordinated) |
| **Phase 3**: Health & Monitoring | 1 week | Multi-broker health checks, enhanced logging |
| **Phase 4**: Migration & Testing | 1 week | Coordinated deployment, validation, rollback procedures |
| **Phase 5**: Operations | 0.5 weeks | Monitoring setup, troubleshooting guides |

**Total Estimated Duration**: 5.5-6 weeks

### Critical Path Analysis

**CRITICAL**: Phase 0 and Phase 2 are blocking - all services must be updated together due to infrastructure changes.

**Phase Dependencies**:
- Phase 1 depends on Phase 0 completion
- Phase 2 requires Phase 0 + 1 (coordinated deployment)
- Phase 3 can run parallel with Phase 2
- Phase 4 requires all previous phases
- Phase 5 can begin during Phase 4

### Risk Mitigation

**High Risk**: Infrastructure signature changes affect all services simultaneously
**Mitigation**: Extensive testing in development environment before production deployment

**Medium Risk**: Consumer group changes may affect message ordering
**Mitigation**: Validate ordering guarantees with load testing before deployment

---

## Success Criteria

✅ **Single deployment manages both paper and zerodha brokers**  
✅ **No BROKER_NAMESPACE environment variable required**  
✅ **Complete data isolation maintained at topic level**  
✅ **All services process messages for their relevant brokers only**  
✅ **Enhanced logging provides clear broker context**  
✅ **Health checks validate all broker configurations**  
✅ **Zero downtime deployment achieved**  
✅ **Performance equivalent or better than current system**

---

## Conclusion

This **UPDATED** comprehensive plan transforms Alpha Panda from environment-specific broker deployments to a unified multi-broker architecture while preserving the benefits of namespace isolation.

### Key Updates Based on Codebase Analysis

**✅ Infrastructure-First Approach**: The plan now correctly addresses the need to update ReliabilityLayer and StreamServiceBuilder infrastructure before service changes.

**✅ Clean Architecture Transition**: Eliminates the mixed implementation patterns (wrapper vs. direct handlers) in favor of a standardized topic-aware handler approach.

**✅ Realistic Timeline**: Updated to 5.5-6 weeks to account for the infrastructure prerequisites and coordinated service deployment requirements.

**✅ Coordinated Deployment Strategy**: Recognizes that all services must be updated together due to handler signature changes - no backward compatibility required.

**✅ Comprehensive Testing**: Enhanced testing strategy includes infrastructure, service, integration, and load testing to validate the multi-broker processing and ordering guarantees.

### Benefits of Updated Plan

- **Simpler Architecture**: Eliminates wrapper patterns and broker_namespace configuration
- **Better Isolation**: Maintains topic-level namespace isolation while enabling unified processing
- **Operational Excellence**: Single deployment managing multiple brokers with enhanced monitoring
- **Scalability**: Foundation for adding new brokers without deployment complexity
- **Maintainability**: Standardized handler pattern across all services

The enhanced system will be simpler to deploy, easier to monitor, and more scalable while maintaining the robust data segregation that namespaces provide at the infrastructure level.