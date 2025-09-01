# Database Migrations

## Overview

The migrations directory contains Alembic database migration scripts for Alpha Panda's PostgreSQL schema management. This follows a structured approach to database versioning, schema evolution, and data migrations.

## Components

### Core Migration Files

#### `env.py`
Alembic environment configuration:

- **Async Migration Support**: Supports async database operations for modern SQLAlchemy patterns
- **Model Auto-Discovery**: Automatically imports all database models for metadata generation
- **Settings Integration**: Uses Alpha Panda's configuration system for database connections
- **Offline/Online Modes**: Supports both offline SQL generation and online database execution

#### `script.py.mako`
Template for generating new migration scripts:

- **Revision Tracking**: Automatic revision ID generation and dependency tracking
- **Standardized Format**: Consistent migration script structure
- **Upgrade/Downgrade**: Bidirectional migration support

### Migration Versions

#### `versions/` Directory
Contains versioned migration scripts:

- **`cc6a84f0b6f1_add_use_composition_column_to_strategy_.py`** - Adds composition pattern support to strategy configurations

## Migration Architecture

### Async Migration Pattern
```python
async def run_async_migrations() -> None:
    """Run migrations with async engine support"""
    connectable = AsyncEngine(engine_from_config(...))
    
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
```

### Model Integration
```python
# Auto-discovery of all models
from core.database.models import *
from services.instrument_data.instrument import *

target_metadata = Base.metadata
```

### Configuration Integration
```python
def get_url():
    """Get database URL from settings"""
    return settings.database.postgres_url
```

## Usage

### Creating New Migrations
```bash
# Generate migration from model changes
python scripts/create_migration.py "Add new table"

# Or use Alembic directly
alembic revision --autogenerate -m "Add new column"
```

### Running Migrations
```bash
# Upgrade to latest
alembic upgrade head

# Upgrade to specific revision
alembic upgrade cc6a84f0b6f1

# Downgrade one revision
alembic downgrade -1

# Check current revision
alembic current
```

### Migration History
```bash
# Show migration history
alembic history

# Show current status
alembic show current
```

## Migration Best Practices

### Schema Changes
- **Backward Compatibility**: New columns should be nullable or have defaults
- **Index Management**: Create indexes with appropriate naming conventions
- **Data Preservation**: Always preserve existing data during schema changes
- **Performance**: Consider impact of large table alterations

### Data Migrations
```python
def upgrade() -> None:
    # Schema changes first
    op.add_column('table_name', sa.Column('new_column', sa.String(255)))
    
    # Data migration after schema changes
    connection = op.get_bind()
    connection.execute(sa.text("""
        UPDATE table_name 
        SET new_column = 'default_value'
        WHERE condition = true
    """))
```

### Rollback Safety
```python
def downgrade() -> None:
    # Reverse data changes first
    connection = op.get_bind()
    connection.execute(sa.text("DELETE FROM table WHERE ..."))
    
    # Then reverse schema changes
    op.drop_column('table_name', 'new_column')
```

## Migration Strategy

### Development Workflow
1. **Model Changes**: Modify SQLAlchemy models in application code
2. **Generate Migration**: Use auto-generation to create migration script
3. **Review Script**: Manually review and adjust generated migration
4. **Test Migration**: Test upgrade and downgrade paths
5. **Apply Migration**: Run migration in development environment

### Production Deployment
1. **Backup Database**: Always backup before production migrations
2. **Dry Run**: Test migration on production copy
3. **Maintenance Window**: Schedule migration during low-traffic periods
4. **Monitoring**: Monitor migration progress and database performance
5. **Rollback Plan**: Have tested rollback procedure ready

## Architecture Integration

### Multi-Broker Schema Design
- **Broker Isolation**: Tables support multi-broker data isolation
- **Partitioning Strategy**: Consider table partitioning for broker-specific data
- **Index Optimization**: Indexes optimized for multi-broker queries
- **Foreign Key Constraints**: Maintain referential integrity across brokers

### Strategy Framework Evolution
- **Composition Support**: Schema supports both inheritance and composition strategies
- **Configuration Migration**: Smooth migration from YAML to database configuration
- **Version Management**: Strategy version tracking and rollback support
- **Performance Optimization**: Optimized queries for strategy execution

## Version Control Integration

### Migration Naming
- **Descriptive Names**: Clear, descriptive migration names
- **Revision IDs**: Alembic-generated revision identifiers
- **Dependencies**: Proper revision dependency tracking
- **Branch Merging**: Handle migration conflicts during branch merges

### Code Reviews
- **Migration Review**: All migrations reviewed before merge
- **Performance Impact**: Review potential performance implications
- **Data Safety**: Verify data preservation and integrity
- **Rollback Testing**: Confirm rollback procedures work correctly

## Monitoring and Alerting

### Migration Execution
- **Progress Tracking**: Monitor long-running migration progress
- **Error Detection**: Immediate alerts on migration failures
- **Performance Monitoring**: Track migration execution time and resource usage
- **Rollback Alerts**: Alert on automatic or manual rollback events

### Schema Health
- **Constraint Validation**: Regular constraint and index validation
- **Performance Monitoring**: Track query performance after schema changes
- **Storage Monitoring**: Monitor database storage growth
- **Integrity Checks**: Regular data integrity validation

## Dependencies

- **Alembic**: Database migration framework
- **SQLAlchemy**: ORM and database abstraction
- **PostgreSQL**: Target database system
- **Core Configuration**: Settings and database connection management
- **Model Definitions**: All application database models

## Troubleshooting

### Common Issues
- **Revision Conflicts**: Handle merge conflicts in migration history
- **Failed Migrations**: Recovery procedures for failed migrations
- **Data Consistency**: Resolve data inconsistencies during migrations
- **Performance Issues**: Address slow migrations and locking issues

### Recovery Procedures
- **Manual Rollback**: Procedures for manual migration rollback
- **Data Recovery**: Restore data from backups if needed
- **Schema Repair**: Fix schema inconsistencies manually
- **History Repair**: Resolve Alembic revision history issues