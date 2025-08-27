# Alpha Panda Implementation Fix Plan

## Overview

This document provides a comprehensive implementation plan to address critical gaps and violations identified in the codebase review against CLAUDE.md specifications. Fixes are prioritized into two phases based on urgency and system impact.

**Review Date**: 2025-08-22  
**Status**: Implementation Required  
**Target Architecture**: Unified Log with Redpanda Event Streaming

---

## Phase 1: Critical System-Breaking Issues (URGENT)

### 🚨 Priority P0 - Immediate Implementation Required

These issues prevent the system from functioning correctly and must be fixed before any production deployment.

---

### 1. Fix EventEnvelope Schema Implementation

**Issue**: Missing mandatory fields for event deduplication and tracing  
**Location**: `core/schemas/events.py:21-28`  
**Impact**: Duplicate processing, no event traceability, broken DLQ replay

#### Implementation Steps

**Step 1.1: Update EventEnvelope Schema**
```python
# File: core/schemas/events.py
from uuid import uuid4
from datetime import datetime
import uuid

def generate_uuid7():
    """Generate UUID v7 for time-ordered event IDs"""
    # Simplified UUID v7 implementation
    return str(uuid4())  # Replace with proper UUID v7 library

class EventEnvelope(BaseModel):
    """MANDATORY standardized envelope for ALL events"""
    # CRITICAL: Add missing required fields
    id: str = Field(default_factory=generate_uuid7, description="Globally unique event ID for deduplication")
    correlation_id: str = Field(..., description="Links related events across services for tracing") 
    causation_id: Optional[str] = Field(None, description="ID of event that caused this one")
    broker: str = Field(..., description="Broker namespace (paper|zerodha) - audit only, NOT for routing")
    
    # Existing fields
    type: EventType
    ts: datetime = Field(default_factory=datetime.utcnow)
    key: str = Field(..., description="Partitioning key for ordering")
    source: str = Field(..., description="Service that generated this event")
    version: int = Field(default=1)
    data: Dict[str, Any] = Field(..., description="Actual event payload")
```

**Step 1.2: Install UUID v7 Library**
```bash
# Add to requirements.txt
uuid7==0.1.0
```

**Step 1.3: Update All Event Creation**
```python
# File: core/streaming/clients.py - Update _emit_event method
async def _emit_event(self, topic: str, event_type: EventType, 
                     key: str, data: Dict[str, Any], 
                     correlation_id: str = None, causation_id: str = None):
    """Emit event with standardized envelope"""
    
    # Extract broker from topic (e.g., "paper.market.ticks" -> "paper")
    broker = topic.split('.')[0] if '.' in topic else "unknown"
    
    envelope = EventEnvelope(
        correlation_id=correlation_id or generate_uuid7(),
        causation_id=causation_id,
        broker=broker,
        type=event_type,
        ts=datetime.utcnow(),
        key=key,
        source=self.name,
        version=1,
        data=data
    )
```

**Validation**: All events must contain the 7 required fields before proceeding.

---

### 2. Fix Topic Naming Convention

**Issue**: Uses deprecated "LIVE" instead of "ZERODHA" and lacks broker prefixes  
**Location**: `core/schemas/topics.py`  
**Impact**: Violates broker segregation, confusion in production

#### Implementation Steps

**Step 2.1: Update TopicNames Class**
```python
# File: core/schemas/topics.py
class TopicNames:
    """Centralized topic name definitions with broker segregation"""
    
    # Market data topics (broker-prefixed)
    MARKET_TICKS_PAPER = "paper.market.ticks"
    MARKET_TICKS_ZERODHA = "zerodha.market.ticks"
    
    # Signal topics
    TRADING_SIGNALS_RAW_PAPER = "paper.signals.raw"
    TRADING_SIGNALS_RAW_ZERODHA = "zerodha.signals.raw"
    TRADING_SIGNALS_VALIDATED_PAPER = "paper.signals.validated" 
    TRADING_SIGNALS_VALIDATED_ZERODHA = "zerodha.signals.validated"
    TRADING_SIGNALS_REJECTED_PAPER = "paper.signals.rejected"
    TRADING_SIGNALS_REJECTED_ZERODHA = "zerodha.signals.rejected"
    
    # Order topics (FIXED: zerodha instead of live)
    ORDERS_SUBMITTED_PAPER = "paper.orders.submitted"
    ORDERS_SUBMITTED_ZERODHA = "zerodha.orders.submitted"
    ORDERS_ACK_PAPER = "paper.orders.ack"
    ORDERS_ACK_ZERODHA = "zerodha.orders.ack"
    ORDERS_FILLED_PAPER = "paper.orders.filled"
    ORDERS_FILLED_ZERODHA = "zerodha.orders.filled"  # CRITICAL: Fixed from LIVE
    ORDERS_FAILED_PAPER = "paper.orders.failed"
    ORDERS_FAILED_ZERODHA = "zerodha.orders.failed"  # CRITICAL: Fixed from LIVE
    
    # Portfolio topics
    PNL_SNAPSHOTS_PAPER = "paper.pnl.snapshots"
    PNL_SNAPSHOTS_ZERODHA = "zerodha.pnl.snapshots"
    
    # Dead Letter Queue topics
    @classmethod
    def get_dlq_topic(cls, original_topic: str) -> str:
        """Get DLQ topic for any topic"""
        return f"{original_topic}.dlq"
```

**Step 2.2: Add Topic Map Helper Class**
```python
# File: core/schemas/topics.py
from typing import Literal

Broker = Literal["paper", "zerodha"]

class TopicMap:
    """Helper for dynamic topic name generation"""
    def __init__(self, broker: Broker):
        self.broker = broker
        
    def market_ticks(self) -> str:
        return f"{self.broker}.market.ticks"
        
    def signals_raw(self) -> str:
        return f"{self.broker}.signals.raw"
        
    def signals_validated(self) -> str:
        return f"{self.broker}.signals.validated"
        
    def orders_filled(self) -> str:
        return f"{self.broker}.orders.filled"
        
    def pnl_snapshots(self) -> str:
        return f"{self.broker}.pnl.snapshots"
        
    def dlq(self, base_topic: str) -> str:
        return f"{base_topic}.dlq"

# Usage in services:
# paper_topics = TopicMap("paper")
# zerodha_topics = TopicMap("zerodha")
```

**Step 2.3: Update TopicConfig for All New Topics**
```python
# File: core/schemas/topics.py - Add configurations for all broker-segregated topics
class TopicConfig:
    """Topic configuration with partition counts"""
    CONFIGS = {
        # Paper trading topics
        TopicNames.MARKET_TICKS_PAPER: {
            "partitions": 12,
            "replication_factor": 1,
            "config": {"retention.ms": "3600000"}  # 1 hour
        },
        TopicNames.ORDERS_FILLED_PAPER: {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "604800000"}  # 1 week
        },
        
        # Zerodha trading topics  
        TopicNames.MARKET_TICKS_ZERODHA: {
            "partitions": 12,
            "replication_factor": 1,
            "config": {"retention.ms": "3600000"}  # 1 hour
        },
        TopicNames.ORDERS_FILLED_ZERODHA: {
            "partitions": 3,
            "replication_factor": 1, 
            "config": {"retention.ms": "2592000000"}  # 30 days
        },
        
        # Add all other topic configurations...
    }
```

**Validation**: All topic names must use broker prefixes and "zerodha" instead of "live".

---

### 3. Standardize Service Architecture Pattern

**Issue**: Inconsistent service inheritance (StreamProcessor vs LifespanService)  
**Location**: `services/trading_engine/service.py`, `services/portfolio_manager/service.py`  
**Impact**: Broken lifecycle management, inconsistent patterns

#### Implementation Steps

**Step 3.1: Convert Trading Engine to StreamProcessor**
```python
# File: services/trading_engine/service.py
from core.streaming.clients import StreamProcessor
from core.schemas.events import EventType
from core.schemas.topics import TopicNames, ConsumerGroups, TopicMap

class TradingEngineService(StreamProcessor):
    """Trading engine service using StreamProcessor pattern"""
    
    def __init__(self, config: RedpandaSettings, settings: Settings, db_manager: DatabaseManager):
        # CRITICAL: Use broker-aware topics
        broker = settings.broker_namespace  # Add this to settings
        topics = TopicMap(broker)
        
        consume_topics = [
            topics.signals_validated(),  # e.g., "paper.signals.validated"
            topics.market_ticks()        # e.g., "paper.market.ticks"
        ]
        
        super().__init__(
            name="trading_engine",
            config=config,
            consume_topics=consume_topics,
            group_id=ConsumerGroups.TRADING_ENGINE
        )
        
        self.settings = settings
        self.db_manager = db_manager
        self.paper_trader = PaperTrader(self.producer, settings)
        self.zerodha_trader = ZerodhaTrader(self.producer, db_manager, settings)
        self.last_prices = {}
        self.topics = topics  # Store for publishing
    
    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Handle incoming messages using StreamProcessor pattern"""
        try:
            event_type = message.get('type')
            
            if topic == self.topics.signals_validated():
                if event_type == 'validated_signal':
                    await self._handle_signal(message.get('data', {}))
            elif topic == self.topics.market_ticks():
                if event_type == 'market_tick':
                    tick_data = message.get('data', {})
                    self.last_prices[tick_data.get('instrument_token')] = tick_data.get('last_price')
        
        except Exception as e:
            await self._handle_processing_error(message, e)
```

**Step 3.2: Convert Portfolio Manager to StreamProcessor**
```python
# File: services/portfolio_manager/service.py  
from core.streaming.clients import StreamProcessor

class PortfolioManagerService(StreamProcessor):
    """Portfolio manager using StreamProcessor pattern"""
    
    def __init__(self, config: RedpandaSettings, settings: Settings, redis_client, db_manager: DatabaseManager):
        broker = settings.broker_namespace
        topics = TopicMap(broker)
        
        consume_topics = [
            topics.orders_filled(),  # e.g., "paper.orders.filled"
            topics.pnl_snapshots()   # e.g., "paper.pnl.snapshots"
        ]
        
        super().__init__(
            name="portfolio_manager",
            config=config,
            consume_topics=consume_topics,
            group_id=ConsumerGroups.PORTFOLIO_MANAGER
        )
        
        self.settings = settings
        self.redis_client = redis_client
        self.db_manager = db_manager
        self.cache = PortfolioCache(redis_client)
        self.topics = topics
    
    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Handle portfolio events"""
        try:
            if topic == self.topics.orders_filled():
                await self._handle_order_filled(message.get('data', {}))
            elif topic == self.topics.pnl_snapshots():
                await self._handle_pnl_snapshot(message.get('data', {}))
        except Exception as e:
            await self._handle_processing_error(message, e)
```

**Step 3.3: Update App Container**
```python
# File: app/containers.py
# Update service registrations to use consistent StreamProcessor pattern
```

**Validation**: All services must inherit from StreamProcessor and use standardized lifecycle.

---

### 4. Update Database Schema and Terminology

**Issue**: Database uses "live" instead of "zerodha"  
**Location**: `core/database/models.py:40`  
**Impact**: Configuration inconsistency, violates naming rules

#### Implementation Steps

**Step 4.1: Create Database Migration**
```python
# File: scripts/migrate_live_to_zerodha.py
"""
Migration script to rename 'live' to 'zerodha' in database schema
"""
import asyncio
from core.database.connection import DatabaseManager
from core.config.settings import settings

async def migrate_terminology():
    """Migrate live_trading_enabled to zerodha_trading_enabled"""
    db_manager = DatabaseManager(settings.database.postgres_url)
    await db_manager.init()
    
    async with db_manager.get_session() as session:
        # Add new column
        await session.execute("""
            ALTER TABLE strategy_configurations 
            ADD COLUMN IF NOT EXISTS zerodha_trading_enabled BOOLEAN DEFAULT FALSE NOT NULL;
        """)
        
        # Copy data from old column
        await session.execute("""
            UPDATE strategy_configurations 
            SET zerodha_trading_enabled = live_trading_enabled;
        """)
        
        # Remove old column (do this carefully in production)
        # await session.execute("ALTER TABLE strategy_configurations DROP COLUMN live_trading_enabled;")
        
        await session.commit()
    
    print("✅ Migration completed: live -> zerodha")

if __name__ == "__main__":
    asyncio.run(migrate_terminology())
```

**Step 4.2: Update Model Definition**
```python
# File: core/database/models.py
class StrategyConfiguration(Base):
    __tablename__ = 'strategy_configurations'
    
    id = Column(String, primary_key=True)
    strategy_type = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    parameters = Column(JSON, default={})
    
    # CRITICAL: Fixed from live_trading_enabled
    zerodha_trading_enabled = Column(Boolean, default=False, nullable=False)  # Enable zerodha trading
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

**Step 4.3: Update Service Code**
```python
# File: services/trading_engine/service.py
async def _get_strategy_config(self, strategy_id: str) -> Dict[str, Any]:
    """Fetch strategy configuration with correct field name"""
    try:
        async with self.db_manager.get_session() as session:
            result = await session.execute(
                select(StrategyConfiguration).where(StrategyConfiguration.id == strategy_id)
            )
            config = result.scalar_one_or_none()
            
            if config:
                return {
                    "zerodha_trading_enabled": config.zerodha_trading_enabled,  # FIXED
                    "is_active": config.is_active,
                    "strategy_type": config.strategy_type,
                    "parameters": config.parameters
                }
```

**Validation**: All database fields and service code must use "zerodha" terminology.

---

### 5. Add Broker Namespace Configuration

**Issue**: Services don't know which broker namespace they belong to  
**Location**: `core/config/settings.py`  
**Impact**: Cannot determine topic prefixes at runtime

#### Implementation Steps

**Step 5.1: Add Broker Configuration**
```python
# File: core/config/settings.py
class Settings(BaseSettings):
    """Main application settings"""
    
    # Add broker namespace configuration
    broker_namespace: Literal["paper", "zerodha"] = Field(
        default="paper", 
        description="Broker namespace for this deployment instance"
    )
    
    # Existing settings...
    app_name: str = "Alpha Panda"
    environment: Environment = Environment.DEVELOPMENT
    # ... rest of settings
```

**Step 5.2: Update Environment Variables**
```bash
# File: .env
BROKER_NAMESPACE=paper  # or zerodha for production deployment
```

**Step 5.3: Update Services to Use Broker Namespace**
```python
# File: services/market_feed/service.py
class MarketFeedService(StreamProcessor):
    def __init__(self, config: RedpandaSettings, settings: Settings):
        # Use broker namespace from settings
        self.topics = TopicMap(settings.broker_namespace)
        
        super().__init__(
            name="market_feed",
            config=config,
            consume_topics=[],  # Market feed doesn't consume
            group_id=ConsumerGroups.MARKET_FEED
        )
        
    async def _run_feed(self):
        """Publish to broker-specific topic"""
        # Emit to paper.market.ticks or zerodha.market.ticks
        await self._emit_event(
            topic=self.topics.market_ticks(),  # Broker-aware topic
            event_type=EventType.MARKET_TICK,
            key=key,
            data=market_tick.model_dump(mode='json')
        )
```

**Validation**: All services must use broker_namespace for topic determination.

---

## Phase 2: Production Readiness (Future Implementation)

### 🔧 Priority P1 - Critical for Production

These features are required for production deployment but don't break basic functionality.

---

### 6. Implement Event Deduplication Pattern

**Issue**: No event deduplication despite examples existing  
**Location**: All services lack deduplication  
**Impact**: Duplicate processing, data inconsistency

#### Implementation Steps

**Step 6.1: Add Redis-based Deduplication Service**
```python
# File: core/streaming/deduplication.py
import redis.asyncio as redis
from typing import Optional
import json

class EventDeduplicator:
    """Redis-based event deduplication with TTL"""
    
    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 3600):
        self.redis = redis_client
        self.ttl = ttl_seconds
    
    async def is_duplicate(self, event_id: str) -> bool:
        """Check if event was already processed"""
        key = f"event_processed:{event_id}"
        exists = await self.redis.exists(key)
        return bool(exists)
    
    async def mark_processed(self, event_id: str, metadata: dict = None) -> None:
        """Mark event as processed with TTL"""
        key = f"event_processed:{event_id}"
        value = json.dumps({
            "processed_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        })
        await self.redis.setex(key, self.ttl, value)
    
    async def get_processing_info(self, event_id: str) -> Optional[dict]:
        """Get processing information for event"""
        key = f"event_processed:{event_id}"
        value = await self.redis.get(key)
        return json.loads(value) if value else None
```

**Step 6.2: Update StreamProcessor with Deduplication**
```python
# File: core/streaming/clients.py
class StreamProcessor:
    """Base class with deduplication support"""
    
    def __init__(self, name: str, config: RedpandaSettings, 
                 consume_topics: List[str], group_id: str, redis_client=None):
        # ... existing initialization ...
        
        # Add deduplicator if Redis available
        if redis_client:
            self.deduplicator = EventDeduplicator(redis_client)
        else:
            self.deduplicator = None
    
    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Handle message with deduplication check"""
        
        # Check for deduplication
        if self.deduplicator:
            event_id = message.get('id')
            if event_id and await self.deduplicator.is_duplicate(event_id):
                # Skip duplicate event
                return
        
        try:
            # Process message
            await self._process_message(topic, key, message)
            
            # Mark as processed
            if self.deduplicator and event_id:
                await self.deduplicator.mark_processed(event_id, {
                    "service": self.name,
                    "topic": topic
                })
                
        except Exception as e:
            await self._handle_processing_error(message, e)
    
    async def _process_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Override this in subclasses - replaces old _handle_message"""
        raise NotImplementedError
```

---

### 7. Implement DLQ Pattern with Retry Logic

**Issue**: All error handling shows TODO for DLQ  
**Location**: Multiple files with TODO comments  
**Impact**: No production error handling

#### Implementation Steps

**Step 7.1: Create Error Classification System**
```python
# File: core/streaming/error_handling.py
from enum import Enum
import asyncio
import random

class ErrorType(Enum):
    TRANSIENT = "transient"      # Network issues, temporary unavailability
    POISON = "poison"            # Malformed data, schema violations
    BUSINESS = "business"        # Strategy logic errors, risk violations
    INFRASTRUCTURE = "infrastructure"  # Database, Redis unavailability

class RetryConfig:
    def __init__(self, max_attempts: int = 5, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    def get_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter"""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        return delay * (0.5 + 0.5 * random.random())

class ErrorClassifier:
    """Classify errors for appropriate handling"""
    
    @staticmethod
    def classify_error(error: Exception) -> ErrorType:
        """Classify error based on exception type"""
        error_name = type(error).__name__
        
        # Network and timeout errors
        if error_name in ['ConnectionError', 'TimeoutError', 'KafkaTimeoutError']:
            return ErrorType.TRANSIENT
        
        # Data validation errors
        if error_name in ['ValidationError', 'ValueError', 'KeyError', 'JSONDecodeError']:
            return ErrorType.POISON
        
        # Database connection issues
        if error_name in ['SQLAlchemyError', 'RedisConnectionError']:
            return ErrorType.INFRASTRUCTURE
        
        # Default to business logic error
        return ErrorType.BUSINESS
```

**Step 7.2: Add DLQ Publisher**
```python
# File: core/streaming/error_handling.py
class DLQPublisher:
    """Dead Letter Queue message publisher"""
    
    def __init__(self, producer, service_name: str):
        self.producer = producer
        self.service_name = service_name
    
    async def send_to_dlq(self, original_message, error: Exception, reason: str, retry_count: int = 0):
        """Send failed message to Dead Letter Queue"""
        
        # Determine DLQ topic
        original_topic = getattr(original_message, 'topic', 'unknown')
        dlq_topic = f"{original_topic}.dlq"
        
        # Create DLQ event
        dlq_event = {
            "original_topic": original_topic,
            "original_partition": getattr(original_message, 'partition', -1),
            "original_offset": getattr(original_message, 'offset', -1),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "failure_reason": reason,
            "retry_count": retry_count,
            "failed_at": datetime.utcnow().isoformat(),
            "original_event": getattr(original_message, 'value', {}),
            "replay_metadata": {
                "consumer_group": f"alpha-panda.{self.service_name}",
                "service_name": self.service_name,
                "dlq_version": "1.0"
            }
        }
        
        # Send to DLQ topic
        await self.producer.send(
            topic=dlq_topic,
            key=getattr(original_message, 'key', '').decode() if hasattr(getattr(original_message, 'key', ''), 'decode') else str(getattr(original_message, 'key', '')),
            value=dlq_event
        )
```

**Step 7.3: Update StreamProcessor with DLQ Support**
```python
# File: core/streaming/clients.py
class StreamProcessor:
    """Base class with DLQ and retry support"""
    
    def __init__(self, name: str, config: RedpandaSettings, 
                 consume_topics: List[str], group_id: str, redis_client=None):
        # ... existing initialization ...
        
        self.retry_config = RetryConfig()
        self.error_classifier = ErrorClassifier()
        self.dlq_publisher = DLQPublisher(self.producer, name)
        self._message_retry_count = {}  # Track retry attempts per message
    
    async def _handle_processing_error(self, message, error: Exception):
        """Handle processing errors with retry and DLQ logic"""
        error_type = self.error_classifier.classify_error(error)
        message_key = f"{message.topic}:{message.partition}:{message.offset}"
        retry_count = self._message_retry_count.get(message_key, 0)
        
        # Poison messages go straight to DLQ
        if error_type == ErrorType.POISON:
            await self.dlq_publisher.send_to_dlq(message, error, "poison_message")
            await self._commit_offset(message)
            return
        
        # Max retries exceeded - send to DLQ
        if retry_count >= self.retry_config.max_attempts:
            await self.dlq_publisher.send_to_dlq(message, error, "max_retries_exceeded", retry_count)
            await self._commit_offset(message)
            del self._message_retry_count[message_key]
            return
        
        # Retry with exponential backoff
        self._message_retry_count[message_key] = retry_count + 1
        delay = self.retry_config.get_delay(retry_count)
        await asyncio.sleep(delay)
        
        # Do NOT commit offset - message will be retried
        print(f"Retrying message (attempt {retry_count + 1}/{self.retry_config.max_attempts}): {error}")
```

---

### 8. Fix Offset Commit Strategy

**Issue**: Auto-commit enabled, should be manual after successful processing  
**Location**: `core/streaming/clients.py:95`  
**Impact**: Message loss risk, no processing guarantees

#### Implementation Steps

**Step 8.1: Update Consumer Configuration**
```python
# File: core/streaming/clients.py
class RedpandaConsumer:
    def __init__(self, config: RedpandaSettings, topics: List[str], group_id: str):
        self.config = config
        self.topics = topics
        
        # CRITICAL: Disable auto-commit for manual control
        self._consumer = AIOKafkaConsumer(
            *topics,
            bootstrap_servers=config.bootstrap_servers,
            client_id=f"{config.client_id}-consumer",
            group_id=group_id,
            auto_offset_reset='earliest',
            enable_auto_commit=False,  # CRITICAL: Manual commits only
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )
        self._started = False
    
    async def commit_offset(self, message):
        """Manually commit offset after successful processing"""
        try:
            await self._consumer.commit()
        except Exception as e:
            print(f"Failed to commit offset: {e}")
            raise
```

**Step 8.2: Update Message Processing with Manual Commits**
```python
# File: core/streaming/clients.py
class StreamProcessor:
    async def consume(self, handler: Callable[[str, str, Dict[str, Any]], None]) -> None:
        """Consume with manual offset management"""
        if not self._started:
            await self.start()
        
        try:
            async for message in self._consumer:
                try:
                    # Process message
                    topic = message.topic
                    key = message.key.decode('utf-8') if message.key else None
                    value = message.value
                    
                    # Validate EventEnvelope format
                    if not isinstance(value, dict) or 'type' not in value:
                        await self.dlq_publisher.send_to_dlq(message, ValueError("Invalid message format"), "schema_validation_failed")
                        await self._consumer.commit()  # Commit to skip poison message
                        continue
                    
                    # Process message with deduplication and error handling
                    await self._handle_message(topic, key, value)
                    
                    # CRITICAL: Only commit after successful processing
                    await self._consumer.commit()
                    
                except Exception as e:
                    # Error handling with retry/DLQ logic
                    await self._handle_processing_error(message, e)
                    # Note: Do NOT commit on error - will retry or go to DLQ
        
        except Exception as e:
            print(f"Consumer error: {e}")
            raise
```

---

### 9. Add Correlation ID Propagation

**Issue**: No correlation ID tracking across service boundaries  
**Location**: All services  
**Impact**: Cannot trace requests across services

#### Implementation Steps

**Step 9.1: Add Correlation Context Manager**
```python
# File: core/streaming/correlation.py
from contextvars import ContextVar
from typing import Optional
import uuid

# Context variable to store correlation ID
correlation_context: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

class CorrelationContext:
    """Manage correlation ID across async calls"""
    
    @staticmethod
    def set_correlation_id(correlation_id: str):
        """Set correlation ID in current context"""
        correlation_context.set(correlation_id)
    
    @staticmethod
    def get_correlation_id() -> Optional[str]:
        """Get correlation ID from current context"""
        return correlation_context.get()
    
    @staticmethod
    def generate_correlation_id() -> str:
        """Generate new correlation ID"""
        return str(uuid.uuid4())
    
    @staticmethod 
    def ensure_correlation_id() -> str:
        """Get existing or generate new correlation ID"""
        correlation_id = correlation_context.get()
        if not correlation_id:
            correlation_id = CorrelationContext.generate_correlation_id()
            correlation_context.set(correlation_id)
        return correlation_id
```

**Step 9.2: Update StreamProcessor to Use Correlation Context**
```python
# File: core/streaming/clients.py
from core.streaming.correlation import CorrelationContext

class StreamProcessor:
    async def _handle_message(self, topic: str, key: str, message: Dict[str, Any]):
        """Handle message with correlation tracking"""
        
        # Extract correlation ID from incoming message
        correlation_id = message.get('correlation_id')
        if correlation_id:
            CorrelationContext.set_correlation_id(correlation_id)
        else:
            # Generate new correlation ID if missing
            correlation_id = CorrelationContext.generate_correlation_id()
            CorrelationContext.set_correlation_id(correlation_id)
        
        # Process message (correlation ID available in context)
        await self._process_message(topic, key, message)
    
    async def _emit_event(self, topic: str, event_type: EventType, 
                         key: str, data: Dict[str, Any], causation_id: str = None):
        """Emit event with correlation propagation"""
        
        # Get correlation ID from context
        correlation_id = CorrelationContext.ensure_correlation_id()
        
        broker = topic.split('.')[0] if '.' in topic else "unknown"
        
        envelope = EventEnvelope(
            correlation_id=correlation_id,  # Propagate correlation ID
            causation_id=causation_id,
            broker=broker,
            type=event_type,
            ts=datetime.utcnow(),
            key=key,
            source=self.name,
            version=1,
            data=data
        )
        
        await self.producer.send(
            topic=topic,
            key=key,
            value=envelope.model_dump()
        )
```

---

### 10. Add Comprehensive Monitoring & Metrics

**Issue**: Limited observability for production deployment  
**Impact**: Cannot monitor system health or performance

#### Implementation Steps

**Step 10.1: Add Service Metrics Collection**
```python
# File: core/monitoring/metrics.py
from typing import Dict, Any
from datetime import datetime
import json

class ServiceMetrics:
    """Collect and expose service metrics"""
    
    def __init__(self, service_name: str, redis_client=None):
        self.service_name = service_name
        self.redis_client = redis_client
        self._counters = {}
        self._timers = {}
    
    def increment_counter(self, metric_name: str, tags: Dict[str, str] = None):
        """Increment a counter metric"""
        key = self._make_metric_key(metric_name, tags)
        self._counters[key] = self._counters.get(key, 0) + 1
        
        # Persist to Redis if available
        if self.redis_client:
            redis_key = f"metrics:{self.service_name}:{key}"
            asyncio.create_task(self.redis_client.incr(redis_key))
    
    def record_timer(self, metric_name: str, duration_ms: float, tags: Dict[str, str] = None):
        """Record a timing metric"""
        key = self._make_metric_key(metric_name, tags)
        if key not in self._timers:
            self._timers[key] = []
        self._timers[key].append(duration_ms)
        
        # Keep only last 1000 measurements
        if len(self._timers[key]) > 1000:
            self._timers[key] = self._timers[key][-1000:]
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics"""
        return {
            "service": self.service_name,
            "timestamp": datetime.utcnow().isoformat(),
            "counters": self._counters.copy(),
            "timers": {
                k: {
                    "count": len(v),
                    "avg": sum(v) / len(v) if v else 0,
                    "min": min(v) if v else 0,
                    "max": max(v) if v else 0
                } for k, v in self._timers.items()
            }
        }
```

---

## Implementation Timeline

### Phase 1 (Weeks 1-2): Critical Fixes
- **Week 1**: EventEnvelope schema, topic naming, database migration
- **Week 2**: Service architecture standardization, broker configuration

### Phase 2 (Weeks 3-6): Production Readiness  
- **Week 3**: Event deduplication implementation
- **Week 4**: DLQ pattern and retry logic
- **Week 5**: Manual offset commits and correlation tracking
- **Week 6**: Monitoring, metrics, and final testing

## Validation Checklist

### Phase 1 Completion Criteria
- [ ] All events contain 7 required EventEnvelope fields
- [ ] All topic names use "zerodha" instead of "live"
- [ ] All topics use broker prefix format (e.g., "paper.orders.filled")
- [ ] All services inherit from StreamProcessor
- [ ] Database schema uses "zerodha_trading_enabled"
- [ ] All services use settings.broker_namespace for topics

### Phase 2 Completion Criteria
- [ ] Event deduplication working with Redis TTL
- [ ] DLQ pattern implemented with error classification
- [ ] Manual offset commits after successful processing
- [ ] Correlation ID propagated across all services
- [ ] Service metrics collected and exposed
- [ ] All TODO comments for DLQ removed

## Deployment Strategy

### Development Environment
```bash
# Use paper trading namespace
BROKER_NAMESPACE=paper

# Start with Phase 1 fixes
make setup
python cli.py run
```

### Production Environment
```bash
# Use zerodha trading namespace
BROKER_NAMESPACE=zerodha

# Deploy with all Phase 2 features
make setup
python cli.py run
```

This implementation plan addresses all critical gaps identified in the codebase review and provides a clear path to full compliance with CLAUDE.md specifications.