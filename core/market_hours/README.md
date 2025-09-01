# Core Market Hours Module

## Overview

The `core/market_hours/` module provides comprehensive market hours validation and checking functionality for the Indian stock market (NSE/BSE). It handles market session detection, holiday checking, and real-time market status monitoring with timezone awareness.

## Components

### `market_hours_checker.py`
Main market hours checker implementation:

- **MarketHoursChecker**: Primary class for market hours validation
- **Real-time Status**: Current market status checking (open, closed, pre-open, lunch break)
- **Session Detection**: Pre-market and regular trading session identification
- **Holiday Support**: Integration with Indian stock market holidays
- **Development Mode**: 24x7 trading mode for development/testing
- **Event Callbacks**: Status change notifications for applications

### `models.py`
Pydantic models for market hours configuration:

- **MarketStatus**: Enumeration of market states (open, closed, pre_open, lunch_break, weekend, holiday)
- **MarketSession**: Session configuration with start/end times
- **MarketHoursConfig**: Complete market hours configuration model
- **Holiday Models**: Holiday calendar configuration and validation

### `__init__.py`
Module exports and convenience functions for market hours checking.

## Key Features

- **Real-time Market Status**: Live market status checking with timezone awareness
- **Session Management**: Pre-market, regular, and post-market session detection
- **Holiday Calendar**: Indian stock market holiday support with calendar integration
- **Lunch Break Handling**: NSE lunch break detection and enforcement
- **Development Mode**: Override for 24x7 development/testing environments
- **Timezone Support**: Full timezone awareness for Indian markets (Asia/Kolkata)
- **Event Notifications**: Callbacks for market open/close events

## Usage

### Basic Market Hours Checking
```python
from core.market_hours.market_hours_checker import MarketHoursChecker
from core.market_hours.models import MarketStatus

# Initialize market hours checker
market_checker = MarketHoursChecker()

# Check current market status
status = await market_checker.get_current_status()
if status == MarketStatus.OPEN:
    print("Market is currently open")

# Check if market is open
is_open = await market_checker.is_market_open()
if is_open:
    # Execute trading logic
    pass
```

### Advanced Market Hours Usage
```python
from datetime import datetime
import pytz

# Check market status at specific time
ist = pytz.timezone('Asia/Kolkata')
check_time = datetime.now(ist)
status = await market_checker.get_market_status(check_time)

# Get next market open/close times
next_open = await market_checker.get_next_market_open()
next_close = await market_checker.get_next_market_close()

print(f"Next market open: {next_open}")
print(f"Next market close: {next_close}")
```

### Market Session Detection
```python
# Check specific market sessions
is_pre_market = await market_checker.is_pre_market_session()
is_regular_session = await market_checker.is_regular_session()
is_lunch_break = await market_checker.is_lunch_break()

# Get current session information
current_session = await market_checker.get_current_session()
print(f"Current session: {current_session}")
```

### Event Callbacks
```python
async def on_market_open():
    print("Market has opened!")

async def on_market_close():
    print("Market has closed!")

# Register event callbacks
market_checker.register_callback("market_open", on_market_open)
market_checker.register_callback("market_close", on_market_close)

# Start monitoring
await market_checker.start_monitoring()
```

## Market Sessions

### Indian Stock Market Schedule (NSE/BSE)
- **Pre-Market Session**: 9:00 AM - 9:15 AM IST
- **Regular Session**: 9:15 AM - 3:30 PM IST
- **Lunch Break**: 12:00 PM - 1:00 PM IST (configurable)
- **Post-Market**: 3:30 PM - 4:00 PM IST (limited trading)

### Weekend and Holiday Handling
- **Weekends**: Saturday and Sunday are non-trading days
- **Public Holidays**: Indian stock market holidays (Diwali, Holi, etc.)
- **Special Days**: Muhurat trading and other special market sessions

## Configuration

Market hours configuration through models:

```python
from core.market_hours.models import MarketHoursConfig, MarketSession
from datetime import time

# Custom market hours configuration
config = MarketHoursConfig(
    pre_market_session=MarketSession(
        start=time(9, 0),   # 9:00 AM
        end=time(9, 15)     # 9:15 AM
    ),
    regular_session=MarketSession(
        start=time(9, 15),  # 9:15 AM
        end=time(15, 30)    # 3:30 PM
    ),
    lunch_break=MarketSession(
        start=time(12, 0),  # 12:00 PM
        end=time(13, 0)     # 1:00 PM
    ),
    timezone="Asia/Kolkata",
    development_mode=False
)

market_checker = MarketHoursChecker(config)
```

## Market Status Types

### Status Enumeration
- **OPEN**: Regular trading session is active
- **CLOSED**: Market is closed (after hours, weekends)
- **PRE_OPEN**: Pre-market session is active
- **LUNCH_BREAK**: Market is in lunch break (if configured)
- **WEEKEND**: Weekend non-trading period
- **HOLIDAY**: Market holiday (public holiday)

### Status Priority
The market status follows a priority order for overlapping conditions:
1. HOLIDAY (highest priority)
2. WEEKEND
3. LUNCH_BREAK
4. PRE_OPEN
5. OPEN
6. CLOSED (default)

## Development Features

### Development Mode
For development and testing, market hours checking can be overridden:

```python
# Enable 24x7 mode for development
config = MarketHoursConfig(development_mode=True)
market_checker = MarketHoursChecker(config)

# Market will always be "open" in development mode
status = await market_checker.get_current_status()  # Always returns OPEN
```

### Testing Support
```python
# Test market status at specific times
test_time = datetime(2024, 8, 30, 10, 30)  # 10:30 AM
status = await market_checker.get_market_status(test_time)
```

## Architecture Patterns

- **Strategy Pattern**: Different market checking strategies for different markets
- **Observer Pattern**: Event callbacks for market status changes
- **Configuration Pattern**: Configurable market hours and sessions
- **Timezone Awareness**: Proper timezone handling for market operations
- **Async Support**: Non-blocking market status checking
- **Caching**: Efficient caching of market status and session information

## Best Practices

1. **Use Timezone Awareness**: Always work with timezone-aware datetime objects
2. **Cache Market Status**: Cache market status to avoid repeated calculations
3. **Handle Edge Cases**: Account for holidays, special sessions, and transitions
4. **Event-Driven**: Use callbacks for market open/close events
5. **Configuration**: Use configuration for different market requirements
6. **Testing**: Test with various market conditions and edge cases

## Dependencies

- **pytz**: Timezone support for accurate market hours
- **pydantic**: Data validation and settings management
- **datetime**: Date and time operations
- **asyncio**: Async market status checking