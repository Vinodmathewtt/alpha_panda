# MARKET FEED RELIABILITY IMPLEMENTATION PLAN

## Overview

This document provides a detailed implementation plan to address critical reliability issues identified in the market feed service review. These changes will transform the market feed from a proof-of-concept to a production-ready, fault-tolerant component.

## Critical Issues Summary

Based on codebase analysis, the following critical issues require immediate attention:

1. **Unobserved Async Failures** - Silent message drops when producer/Redis operations fail
2. **No Backpressure Protection** - Unbounded coroutine scheduling leading to memory growth
3. **Authentication Boundary Leakage** - Direct access to protected auth manager attributes
4. **Reconnection Race Conditions** - Multiple concurrent reconnection attempts
5. **Timezone Inconsistencies** - Naive datetime fallbacks causing downstream issues

## Implementation Phases

### Phase 1: Critical Reliability (Week 1)

#### 1.1 Fix Async Failure Monitoring

**File**: `services/market_feed/service.py`
**Lines**: 275-276
**Priority**: CRITICAL

```python
# Add to class __init__:
self._failed_sends = 0
self._failed_metrics = 0

# Add callback method:
def _handle_task_exception(self, future):
    """Handle exceptions from background tasks."""
    try:
        future.result()  # This will raise if the task failed
    except Exception as e:
        self.error_logger.error(f"Background task failed: {e}", exc_info=True)
        # Increment failure counters for monitoring
        if "emit" in str(e) or "producer" in str(e):
            self._failed_sends += 1
        elif "metrics" in str(e) or "redis" in str(e):
            self._failed_metrics += 1

# Replace in _on_ticks method:
# OLD:
asyncio.run_coroutine_threadsafe(emit_coro, self.loop)
asyncio.run_coroutine_threadsafe(metrics_coro, self.loop)

# NEW:
future_emit = asyncio.run_coroutine_threadsafe(emit_coro, self.loop)
future_metrics = asyncio.run_coroutine_threadsafe(metrics_coro, self.loop)
future_emit.add_done_callback(self._handle_task_exception)
future_metrics.add_done_callback(self._handle_task_exception)
```

#### 1.2 Implement Backpressure Protection

**File**: `services/market_feed/service.py`
**Priority**: CRITICAL

```python
# Add to class __init__:
self._tick_queue = asyncio.Queue(maxsize=10000)  # Bounded queue
self._processor_task = None
self._dropped_ticks = 0

# Add new method:
async def _tick_processor(self):
    """Worker task that consumes ticks from queue and processes them."""
    self.logger.info("Tick processor worker started")
    while self._running:
        try:
            # Wait for tick with timeout to allow graceful shutdown
            tick = await asyncio.wait_for(self._tick_queue.get(), timeout=1.0)
            
            # Process tick
            await self._process_tick_async(tick)
            self._tick_queue.task_done()
            
        except asyncio.TimeoutError:
            continue  # Normal timeout, check if still running
        except asyncio.CancelledError:
            self.logger.info("Tick processor cancelled")
            break
        except Exception as e:
            self.error_logger.error(f"Tick processor error: {e}", exc_info=True)

async def _process_tick_async(self, formatted_tick):
    """Process a single tick asynchronously."""
    try:
        market_tick = MarketTick(**formatted_tick)
        key = PartitioningKeys.market_tick_key(market_tick.instrument_token)

        # Emit to Kafka
        if self.orchestrator.producers and len(self.orchestrator.producers) > 0:
            producer = self.orchestrator.producers[0]
            await producer.send(
                topic=TopicNames.MARKET_TICKS,
                key=key,
                data=market_tick.model_dump(mode='json'),
                event_type=EventType.MARKET_TICK,
                broker="shared"
            )

        # Update metrics
        await self.metrics_collector.record_market_tick(market_tick.model_dump(mode='json'))
        
        self.ticks_processed += 1
        
    except Exception as e:
        self.error_logger.error(f"Failed to process tick: {e}", exc_info=True)
        raise

# Update start method:
async def start(self):
    # ... existing code ...
    
    # Start tick processor
    self._processor_task = asyncio.create_task(self._tick_processor())
    
    # ... rest of existing code ...

# Update stop method:
async def stop(self):
    self._running = False
    
    # Cancel processor task
    if self._processor_task:
        self._processor_task.cancel()
        try:
            await self._processor_task
        except asyncio.CancelledError:
            pass
    
    # ... rest of existing code ...

# Update _on_ticks method:
def _on_ticks(self, ws, ticks: List[Dict[str, Any]]):
    """Main callback - now uses bounded queue."""
    if not self._running:
        return

    for tick in ticks:
        try:
            formatted_tick = self.formatter.format_tick(tick)
            
            # Use bounded queue with drop policy
            try:
                self._tick_queue.put_nowait(formatted_tick)
            except asyncio.QueueFull:
                self._dropped_ticks += 1
                self.logger.warning(f"Tick queue full - dropped tick (total dropped: {self._dropped_ticks})")
                
        except Exception as e:
            self.error_logger.error(f"Error formatting tick: {e}", extra={"tick_data": tick})
```

#### 1.3 Add Reconnection Lock Protection

**File**: `services/market_feed/service.py`
**Priority**: HIGH

```python
# Add to class __init__:
self._reconnection_lock = asyncio.Lock()

# Update _attempt_reconnection method:
async def _attempt_reconnection(self):
    """Attempt reconnection with concurrency protection."""
    async with self._reconnection_lock:
        if not self._running:
            return

        # ... rest of existing reconnection logic ...
```

### Phase 2: Clean Architecture (Week 2)

#### 2.1 Fix Authentication Boundary Leakage

**File**: `services/auth/service.py`
**Priority**: HIGH

```python
# Add new public method:
async def get_access_token(self) -> Optional[str]:
    """
    Public method to get access token for authenticated services.
    Returns None if not authenticated.
    """
    if not self.is_authenticated():
        return None
    
    try:
        return await self.auth_manager.get_access_token()
    except Exception as e:
        logger.error(f"Failed to retrieve access token: {e}")
        return None
```

**File**: `services/market_feed/auth.py`
**Priority**: HIGH

```python
# Update get_ticker method:
async def get_ticker(self) -> KiteTicker:
    """Performs authentication using public AuthService API."""
    if not self._auth_service.is_authenticated():
        raise ConnectionError("Cannot start market feed: No authenticated Zerodha session found.")

    try:
        # Use public API instead of reaching into protected attributes
        access_token = await self._auth_service.get_access_token()
        api_key = self._settings.zerodha.api_key

        if not all([api_key, access_token]):
            raise ValueError("Zerodha API key or access token is missing.")

        ticker = KiteTicker(api_key, access_token)
        logger.info("BrokerAuthenticator successfully created KiteTicker instance")
        return ticker

    except Exception as e:
        logger.error(f"Broker authentication failed: {e}")
        raise
```

#### 2.2 Normalize Timezone Handling

**File**: `services/market_feed/formatter.py`
**Priority**: MEDIUM

```python
from datetime import datetime, timezone

# Update _format_timestamp method:
def _format_timestamp(self, raw_tick: Dict[str, Any]) -> datetime:
    """Format timestamp with UTC normalization."""
    timestamp = raw_tick.get("exchange_timestamp") or raw_tick.get("last_trade_time")
    
    if timestamp is None:
        # Always return timezone-aware UTC datetime
        return datetime.now(timezone.utc)
    
    return self._normalize_to_utc(timestamp)

def _normalize_to_utc(self, dt_value: Any) -> datetime:
    """Normalize any datetime value to UTC."""
    if dt_value is None:
        return datetime.now(timezone.utc)
    
    if isinstance(dt_value, datetime):
        # If naive, assume UTC
        if dt_value.tzinfo is None:
            return dt_value.replace(tzinfo=timezone.utc)
        # If timezone-aware, convert to UTC
        return dt_value.astimezone(timezone.utc)
    
    elif isinstance(dt_value, str):
        try:
            parsed = datetime.fromisoformat(dt_value)
            return self._normalize_to_utc(parsed)
        except ValueError:
            try:
                parsed = datetime.strptime(dt_value, "%Y-%m-%d %H:%M:%S")
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return datetime.now(timezone.utc)
    
    return datetime.now(timezone.utc)
```

### Phase 3: Enhanced Observability (Week 3)

#### 3.1 Add Comprehensive Metrics

**File**: `services/market_feed/service.py`
**Priority**: MEDIUM

```python
# Add to class __init__:
self._metrics = {
    'ticks_received': 0,
    'ticks_processed': 0,
    'ticks_dropped': 0,
    'send_failures': 0,
    'metrics_failures': 0,
    'reconnection_attempts': 0,
    'last_tick_timestamp': None,
    'queue_size': 0
}

# Add metrics reporting method:
async def get_metrics(self) -> Dict[str, Any]:
    """Get comprehensive service metrics."""
    current_queue_size = self._tick_queue.qsize() if hasattr(self, '_tick_queue') else 0
    
    return {
        **self._metrics,
        'queue_size': current_queue_size,
        'connection_status': 'connected' if (self.kws and self.kws.is_connected()) else 'disconnected',
        'is_running': self._running,
        'processing_rate': self._calculate_processing_rate()
    }

def _calculate_processing_rate(self) -> float:
    """Calculate ticks per second processing rate."""
    if not hasattr(self, '_start_time') or self._metrics['ticks_processed'] == 0:
        return 0.0
    
    elapsed = (datetime.now() - self._start_time).total_seconds()
    return self._metrics['ticks_processed'] / elapsed if elapsed > 0 else 0.0

# Update metrics in various methods:
def _on_ticks(self, ws, ticks: List[Dict[str, Any]]):
    self._metrics['ticks_received'] += len(ticks)
    # ... rest of method

async def _process_tick_async(self, formatted_tick):
    # ... processing logic ...
    self._metrics['ticks_processed'] += 1
    self._metrics['last_tick_timestamp'] = datetime.now(timezone.utc)
```

#### 3.2 Add Health Check Endpoint Support

**File**: `services/market_feed/service.py`
**Priority**: LOW

```python
async def health_check(self) -> Dict[str, Any]:
    """Comprehensive health check for monitoring systems."""
    metrics = await self.get_metrics()
    
    # Calculate health score
    is_healthy = (
        self._running and
        (self.kws and self.kws.is_connected()) and
        metrics['queue_size'] < 8000 and  # Queue not near full
        metrics['send_failures'] / max(metrics['ticks_processed'], 1) < 0.01  # < 1% failure rate
    )
    
    return {
        'status': 'healthy' if is_healthy else 'unhealthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'metrics': metrics,
        'issues': self._identify_health_issues(metrics)
    }

def _identify_health_issues(self, metrics: Dict[str, Any]) -> List[str]:
    """Identify specific health issues."""
    issues = []
    
    if not self._running:
        issues.append("Service not running")
    if not (self.kws and self.kws.is_connected()):
        issues.append("WebSocket disconnected")
    if metrics['queue_size'] > 8000:
        issues.append("Queue near capacity")
    if metrics['send_failures'] / max(metrics['ticks_processed'], 1) > 0.01:
        issues.append("High failure rate")
    if metrics['ticks_dropped'] > 0:
        issues.append("Dropped ticks detected")
    
    return issues
```

## Testing Strategy

### Unit Tests
```python
# tests/unit/services/market_feed/test_service.py

async def test_backpressure_protection():
    """Test that full queue drops ticks gracefully."""
    service = MarketFeedService(...)
    
    # Fill queue to capacity
    for i in range(10001):  # Over capacity
        service._tick_queue.put_nowait({'test': i})
    
    # Should drop additional ticks
    service._on_ticks(None, [{'instrument_token': 123, 'last_price': 100}])
    assert service._dropped_ticks > 0

async def test_async_failure_handling():
    """Test that async failures are captured."""
    service = MarketFeedService(...)
    
    # Mock failing producer
    service.orchestrator.producers[0].send.side_effect = Exception("Send failed")
    
    # Process tick should increment failure counter
    await service._process_tick_async({'instrument_token': 123, 'last_price': 100})
    assert service._failed_sends > 0
```

### Integration Tests
```python
async def test_full_pipeline_reliability():
    """Test complete pipeline under load."""
    # Send 1000 ticks rapidly
    # Verify all are processed or dropped gracefully
    # Verify no silent failures
```

## Deployment Strategy

### Rolling Deployment
1. **Deploy to staging** with full test suite
2. **Performance testing** with simulated market load
3. **Canary deployment** to 10% of production traffic
4. **Full production deployment** after validation

### Monitoring Setup
1. **Add alerts** for queue size > 8000
2. **Add alerts** for drop rate > 1%
3. **Add alerts** for send failure rate > 1%
4. **Dashboard** showing processing rates and health metrics

## Success Criteria

### Reliability Metrics
- [ ] Zero silent failures (all exceptions logged/handled)
- [ ] Queue never grows unbounded under normal load
- [ ] Reconnection race conditions eliminated
- [ ] Memory usage stable under 24-hour load test

### Performance Metrics  
- [ ] Process > 100 ticks/second consistently
- [ ] < 1% message drop rate under peak load
- [ ] < 50ms average processing latency per tick
- [ ] Graceful degradation when queue approaches capacity

### Observability Metrics
- [ ] All failure modes have dedicated metrics
- [ ] Health check provides actionable status
- [ ] Monitoring alerts fire before system failure
- [ ] Complete audit trail for all processed ticks

## Risk Mitigation

### Rollback Plan
- Keep current service.py as `service.py.backup`
- Feature flags for new backpressure system
- Gradual queue size increase (1000 → 5000 → 10000)

### Circuit Breaker
- Automatic service restart if > 5% failure rate
- Graceful degradation to mock data if Zerodha unavailable
- Alert operations team for manual intervention

This implementation plan addresses all critical reliability issues while maintaining backwards compatibility and providing comprehensive testing and monitoring capabilities.