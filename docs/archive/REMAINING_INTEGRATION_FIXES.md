# Remaining Integration Fixes

**Date**: 2025-01-23  
**Status**: Critical Integration Gaps  
**Priority**: High - Blocking end-to-end functionality

## Overview

This document addresses remaining integration issues not covered in previous fix documents. These are post-implementation gaps that prevent the application from running end-to-end.

## Critical Integration Fixes

### 1. API Dependencies Missing ❌ BLOCKER

**Issue**: `api/routers/monitoring.py:12` imports functions that don't exist
```python
from api.dependencies import get_settings, get_redis_client
```

**Root Cause**: Functions referenced in dependency injection but not implemented

**Fix**: Add missing functions to `api/dependencies.py`

```python
# ADD to api/dependencies.py

@inject
def get_settings(
    settings: Settings = Depends(Provide[AppContainer.settings])
) -> Settings:
    """Get application settings for API endpoints"""
    return settings


@inject
def get_redis_client(
    redis_client: redis.Redis = Depends(Provide[AppContainer.redis_client])
) -> redis.Redis:
    """Get Redis client for API endpoints"""
    return redis_client
```

**Files**: 
- `api/dependencies.py` (add functions)
- `api/routers/monitoring.py` (already importing correctly)

### 2. Terminology Inconsistency ❌ CRITICAL

**Issue**: Portfolio router uses "live_" instead of "zerodha_" terminology

**Location**: `api/routers/portfolios.py:82-83`
```python
elif portfolio_id.startswith("live_"):
    live_portfolios += 1
```

**Root Cause**: Violates architectural principle of using "zerodha" terminology

**Fix**: Replace with consistent "zerodha_" terminology

```python
# REPLACE in api/routers/portfolios.py lines 70, 82-83, 88

# OLD
live_portfolios = 0
elif portfolio_id.startswith("live_"):
    live_portfolios += 1
"live_portfolios": live_portfolios,

# NEW  
zerodha_portfolios = 0
elif portfolio_id.startswith("zerodha_"):
    zerodha_portfolios += 1
"zerodha_portfolios": zerodha_portfolios,
```

**Files**:
- `api/routers/portfolios.py:70, 82-83, 88`

### 3. Event Loop Missing in MarketFeedService ⚠️ RUNTIME ISSUE

**Issue**: `services/market_feed/service.py` references `self.loop` but never initializes it

**Root Cause**: KiteTicker callbacks use `asyncio.run_coroutine_threadsafe(..., self.loop)` but `self.loop` is undefined

**Fix**: Initialize event loop in service start method

```python
# ADD to services/market_feed/service.py in start() method

async def start(self):
    """Start the market feed service"""
    await super().start()
    
    # CRITICAL: Capture running event loop for KiteTicker callbacks
    self.loop = asyncio.get_running_loop()
    
    # Initialize authenticator and start feed
    await self._start_market_feed()
    # ... rest of method
```

**Files**:
- `services/market_feed/service.py` (add `self.loop = asyncio.get_running_loop()`)

### 4. Schema Field Consistency ⚠️ DATA INTEGRITY

**Issue**: Mixed usage of `trading_mode` vs `execution_mode` across services

**Locations**:
- `services/portfolio_manager/service.py` uses `trading_mode`
- `core/schemas/events.py` uses `execution_mode` in OrderFilled

**Root Cause**: Causes portfolio ID mismatches and data segregation failures

**Fix**: Standardize on `execution_mode` throughout

```python
# REPLACE in services/portfolio_manager/service.py

# OLD
def _build_portfolio_id(self, strategy_id: str, trading_mode: str) -> str:
    return f"{trading_mode}_{strategy_id}"

# NEW
def _build_portfolio_id(self, strategy_id: str, execution_mode: str) -> str:
    return f"{execution_mode}_{strategy_id}"

# Update all references from trading_mode to execution_mode
```

**Files**:
- `services/portfolio_manager/service.py` (standardize field names)
- Any other services using `trading_mode` instead of `execution_mode`

## Implementation Steps

### Step 1: Fix API Dependencies (BLOCKER)
```bash
# Add missing functions to api/dependencies.py
# Test with: curl http://localhost:8000/api/v1/monitoring/health
```

### Step 2: Fix Terminology Consistency 
```bash
# Update portfolio router terminology
# Test with: curl http://localhost:8000/api/v1/portfolios/summary/stats
```

### Step 3: Fix Event Loop Initialization
```bash
# Add event loop capture in MarketFeedService.start()
# Test by running full pipeline: make run
```

### Step 4: Standardize Schema Fields
```bash
# Update all services to use execution_mode consistently  
# Run tests to verify portfolio ID generation: make test-unit
```

## Validation Steps

### API Endpoints Test
```bash
# Start API server
python cli.py api

# Test monitoring endpoints
curl http://localhost:8000/api/v1/monitoring/health
curl http://localhost:8000/api/v1/monitoring/pipeline
```

### Portfolio Terminology Test
```bash
# Test portfolio summary
curl http://localhost:8000/api/v1/portfolios/summary/stats

# Should return zerodha_portfolios, not live_portfolios
```

### End-to-End Pipeline Test
```bash
# Full pipeline test
make setup
make run

# Verify no event loop errors in logs
tail -f logs/market_data.log
```

## Risk Assessment

### High Risk (Must Fix)
- **API Dependencies**: Causes 500 errors on monitoring endpoints
- **Event Loop**: Causes runtime crashes on market data

### Medium Risk (Should Fix) 
- **Terminology**: Causes confusion and violates architecture
- **Schema Fields**: Causes data segregation issues

### Low Risk (Nice to Fix)
- Documentation updates to reflect current state

## Post-Implementation Verification

After implementing these fixes:

1. **API Health Check**: All monitoring endpoints should return 200
2. **Portfolio Stats**: Should show `zerodha_portfolios` not `live_portfolios` 
3. **Market Feed**: Should start without event loop errors
4. **Portfolio IDs**: Should generate consistent IDs using `execution_mode`

## Notes

- These fixes address integration gaps not covered in previous documentation
- All fixes maintain backward compatibility where possible  
- Terminology fixes align with established architectural principles
- Event loop fix prevents runtime crashes in production

**Priority Order**: API Dependencies → Event Loop → Terminology → Schema Consistency