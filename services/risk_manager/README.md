# Risk Manager Service

## Overview

The Risk Manager Service validates trading signals against risk rules and position limits before allowing execution. It acts as a critical gatekeeper between signal generation and order execution.

## Architecture

- **Service Layer**: Main risk validation service with stream processing
- **Rule Engine**: Configurable risk rules and validation logic
- **Position Checker**: Validates against current position limits
- **Multi-Broker Support**: Separate risk validation per broker

## Key Features

- **Signal Validation**: Validates trading signals against risk parameters
- **Position Limits**: Enforces maximum position size and concentration limits
- **Risk Rules Engine**: Configurable risk rules per strategy and broker
- **Multi-Broker Risk**: Separate risk management for paper vs live trading
- **Rejection Handling**: Routes rejected signals with detailed reasons

## Data Flow

1. **Raw Signals**: Consumes `{broker}.signals.raw` from strategy runner
2. **Risk Validation**: Applies risk rules and position limit checks  
3. **Signal Routing**: 
   - Valid signals → `{broker}.signals.validated`
   - Invalid signals → `{broker}.signals.rejected`

## Usage

```python
from services.risk_manager.service import RiskManagerService

# Initialize risk manager
risk_service = RiskManagerService(
    config=settings.redpanda,
    settings=settings,
    redis_client=redis_client
)

# Start service (begins consuming raw signals)
await risk_service.start()
```

## Risk Rules

- **Position Size Limits**: Maximum position size per instrument
- **Portfolio Concentration**: Maximum % of portfolio in single instrument
- **Daily Loss Limits**: Maximum daily loss thresholds
- **Strategy Limits**: Per-strategy risk parameters
- **Market Hours**: Validates signals during trading hours only

## Dependencies

- **core.streaming**: StreamServiceBuilder for signal processing
- **core.schemas**: Signal event schemas and validation
- **Portfolio State**: Uses broker-scoped portfolio updates maintained within trading services; reads cached state via Redis
