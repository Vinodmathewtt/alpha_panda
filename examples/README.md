# Alpha Panda Code Examples

This directory contains code examples extracted from CLAUDE.md to demonstrate key architectural patterns and implementation approaches for the Alpha Panda algorithmic trading system.

## Directory Structure

### Architecture Patterns
- `architecture/topic_configuration.py` - Broker-namespaced topic taxonomy for hard isolation
- `architecture/partitioning_strategy.py` - Partitioning strategies and hot key management

### Streaming Patterns  
- `streaming/event_deduplication.py` - Event deduplication using Redis for exactly-once semantics
- `streaming/offset_commit_strategy.py` - Manual offset commit patterns for data safety
- `streaming/lifecycle_management.py` - Consumer lifecycle and graceful shutdown patterns
- `streaming/producer_consumer_config.py` - Optimized aiokafka configuration

### Error Handling & Reliability
- `patterns/error_handling.py` - Structured retry patterns with error classification
- `patterns/dlq_replay_tool.py` - Dead Letter Queue replay tool implementation
- `patterns/cache_management.py` - Redis cache management with TTL strategies
- `patterns/async_broker_adapter.py` - Async wrapper for synchronous broker APIs

### Monitoring & Observability
- `monitoring/health_checks.py` - Service health checks and readiness probes
- `monitoring/service_metrics.py` - OpenTelemetry metrics and distributed tracing
- `monitoring/partition_metrics.py` - Hot partition detection and monitoring

### Trading Patterns
- `trading/broker_authentication.py` - Zerodha KiteConnect authentication pattern
- `trading/pure_strategy_pattern.py` - Pure strategy implementation (infrastructure-free)
- `trading/message_publishing.py` - Standardized EventEnvelope message publishing
- `trading/trading_engine_routing.py` - Configuration-based trading engine routing

### Testing Infrastructure
- `testing/testing_infrastructure.py` - Shared test infrastructure with testcontainers
- `testing/test_examples.py` - Examples for different test categories

## Usage

These examples serve as reference implementations for the patterns described in the main CLAUDE.md documentation. Each file contains:

1. **Focused Implementation** - Single responsibility per file
2. **Production Patterns** - Real-world production-ready code
3. **Comprehensive Documentation** - Docstrings explaining the pattern
4. **Usage Examples** - How to integrate the pattern

## Key Principles Demonstrated

- **Event-Driven Architecture** - All dynamic data flows through Redpanda streams
- **Unified Log Pattern** - Single source of truth for system state
- **Hard Isolation** - Complete segregation between paper and zerodha trading
- **Exactly-Once Semantics** - Event deduplication and manual offset commits
- **Graceful Degradation** - Error handling and recovery patterns
- **Production Observability** - Health checks, metrics, and distributed tracing

Refer to the main CLAUDE.md file for complete architectural context and implementation guidelines.