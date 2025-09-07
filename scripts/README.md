# Scripts Directory

## Overview

The scripts directory contains operational scripts, database migrations, testing utilities, and system administration tools for Alpha Panda. These scripts support development, testing, deployment, and maintenance operations.

## Script Categories

### Infrastructure Bootstrap Scripts
- **`bootstrap_topics.py`** - Creates Kafka topics (env-aware overlays for dev/test/prod)
- **`test-infrastructure.sh`** - Comprehensive infrastructure testing and validation script

### Database Management Scripts
- **`create_instrument_tables.py`** - Creates database tables for financial instruments
- **`create_portfolio_tables.py`** - Creates database tables for portfolio management
- **`create_migration.py`** - Generates new Alembic migration files
 

### Migration and Strategy Scripts
- **`migrate_live_to_zerodha.py`** - Migrates live trading configuration to Zerodha broker
- **`migrate_strategies_to_composition.py`** - Migrates legacy inheritance-based strategies to composition pattern
- **`migrate_yaml_configs.py`** - Migrates YAML-based configuration to database storage
- **`seed_composition_strategies.py`** - Seeds database with composition-based strategy configurations
- **`seed_strategies.py`** - Seeds database with strategy definitions and configurations
- **`seed_test_data.py`** - Comprehensive test data seeding for development and testing

### Testing and Integration Scripts
- Moved ad-hoc helpers to `tests/integration/tools/`:
  - `tool_enhanced_market_data_capture.py` – Market data capture checks
  - `tool_instrument_integration.py` – Instrument data integration checks
  - `tool_market_feed_integration.py` – Market feed integration checks
  - `tool_monitoring.py` – Monitoring and alerting checks

### Validation and Quality Assurance Scripts
- **`validate_composition_migration.py`** - Validates composition pattern migration integrity
- **`validate_critical_fixes.py`** - Validates critical architecture fixes
- **`validate_risk_manager_improvements.py`** - Validates risk management improvements
- **`verify_all_issues_resolved.py`** - Comprehensive system validation script

### Emergency Operations
- **`emergency_rollback.sh`** - Emergency rollback script for critical issues
- **`dlq_replay.py`** - Replays messages from per-topic `.dlq` topics to the original topic (supports `--dry-run` and `--limit`)

## Usage Patterns

### Development Setup
```bash
# Bootstrap development environment
python scripts/bootstrap_topics.py
python scripts/seed_test_data.py
python scripts/create_instrument_tables.py
```

### Testing Infrastructure
```bash
# Run comprehensive infrastructure tests
./scripts/test-infrastructure.sh

# Ad-hoc integration checks
python tests/integration/tools/tool_market_feed_integration.py
python tests/integration/tools/tool_instrument_integration.py
```

### Database Operations
```bash
# Create new migration
python scripts/create_migration.py "Add new column"

# Seed strategies
python scripts/seed_strategies.py
python scripts/seed_composition_strategies.py
```

### System Validation
```bash
# Validate system integrity
python scripts/verify_all_issues_resolved.py
python scripts/validate_critical_fixes.py
```

### Emergency Operations
```bash
# Emergency rollback (if needed)
./scripts/emergency_rollback.sh

# Dry run DLQ replay (no publishing)
python scripts/dlq_replay.py --bootstrap localhost:9092 --dlq paper.signals.raw.dlq --group replay-tool --dry-run

# Replay up to 100 messages
python scripts/dlq_replay.py --bootstrap localhost:9092 --dlq paper.signals.raw.dlq --group replay-tool --limit 100
```

## Script Architecture

### Async Script Pattern
```python
#!/usr/bin/env python3
"""Script with async operations"""
import asyncio
from core.config.settings import get_settings

async def main():
    settings = get_settings()
    # Script logic here
    
if __name__ == "__main__":
    asyncio.run(main())
```

### Database Connection Pattern
```python
from core.database.connection import get_database_url
from sqlalchemy.ext.asyncio import create_async_engine

async def setup_database():
    engine = create_async_engine(get_database_url())
    # Database operations
```

### Kafka Integration Pattern
```python
from core.streaming.kafka_client import get_kafka_client

async def setup_topics():
    client = get_kafka_client()
    # Topic operations
```

## Script Development Guidelines

### Error Handling
- **Fail Fast**: Scripts must fail immediately on critical errors
- **Clear Messages**: Error messages must be actionable and specific
- **Rollback Support**: Destructive operations must support rollback
- **Logging**: All operations must be logged with structured logging

### Configuration
- **Environment Aware**: Scripts must work across development/test/production
- **Override Support**: Support environment variable overrides
- **Validation**: Validate configuration before executing operations
- **Documentation**: Each script must document required configuration

### Testing
- **Dry Run Mode**: Support `--dry-run` flag for testing
- **Validation Mode**: Support `--validate` flag for configuration checking
- **Test Coverage**: Critical scripts must have accompanying tests
- **Integration Tests**: Infrastructure scripts tested in CI/CD pipeline

### Operational Safety
- **Confirmation Prompts**: Destructive operations require confirmation
- **Backup Creation**: Database operations create backups before changes
- **Atomic Operations**: Operations must be atomic where possible
- **Monitoring Integration**: Critical operations send metrics/alerts

## Dependencies

- **Core Modules**: Integration with `core/config`, `core/database`, `core/streaming`
- **Database**: PostgreSQL with Alembic migrations
- **Message Queues**: Redpanda/Kafka for topic operations
- **Environment**: Support for development, test, and production environments
- **Monitoring**: Integration with logging and metrics systems

## Maintenance

### Regular Operations
- **Database Migrations**: Regular schema updates via Alembic
- **Topic Management**: Kafka topic configuration and maintenance
- **Data Seeding**: Regular test data refresh and strategy updates
- **System Validation**: Regular integrity checks and validations

### Monitoring
- **Script Execution**: Monitor script execution success/failure
- **Performance**: Track script execution times and resource usage
- **Error Rates**: Monitor script error rates and failure patterns
- **Dependencies**: Monitor script dependency health and availability
### Topic Bootstrap Overlays (env-aware)

`bootstrap_topics.py` supports environment overlays to size topics and DLQs:

- `SETTINGS__ENVIRONMENT`: `development` (default) | `testing` | `production`
- `REDPANDA_BROKER_COUNT`: integer broker count (used to cap RF)
- `TOPIC_PARTITIONS_MULTIPLIER`: float to scale configured partitions
- `CREATE_DLQ_FOR_ALL`: `true|false` (default true) to create per-topic `.dlq`

Examples:

```bash
# Development (default)
python scripts/bootstrap_topics.py

# Production-like
export SETTINGS__ENVIRONMENT=production
export REDPANDA_BROKER_COUNT=3
export TOPIC_PARTITIONS_MULTIPLIER=1.5
export CREATE_DLQ_FOR_ALL=true
python scripts/bootstrap_topics.py
```
