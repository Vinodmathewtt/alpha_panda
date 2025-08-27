# Database Configuration

This directory contains database initialization scripts and configuration files for AlphaPT.

## Files

- `init_postgresql.sql` - PostgreSQL database initialization script
- `init_clickhouse.sql` - ClickHouse database initialization script

## PostgreSQL Setup

The PostgreSQL database stores transactional data including:
- Orders and executions
- Positions and portfolios
- Risk metrics and limits
- User sessions and authentication
- Strategy metadata

### Manual Setup

```bash
# Connect to PostgreSQL as superuser
sudo -u postgres psql

# Run the initialization script
\i /path/to/alphapt/scripts/database/init_postgresql.sql
```

### Docker Setup

```bash
# Start PostgreSQL with Docker Compose
docker compose up -d postgres

# Run initialization script
docker exec -i alphapt_postgres psql -U postgres < scripts/database/init_postgresql.sql
```

## ClickHouse Setup

The ClickHouse database handles high-frequency analytics data:
- Real-time market tick data (1000+ TPS)
- OHLC aggregations with materialized views
- ML features and technical indicators
- Strategy signals and performance metrics

### Manual Setup

```bash
# Connect to ClickHouse
clickhouse-client

# Run the initialization script
SOURCE /path/to/alphapt/scripts/database/init_clickhouse.sql
```

### Docker Setup

```bash
# Start ClickHouse with Docker Compose
docker compose up -d clickhouse

# Run initialization script
docker exec -i alphapt_clickhouse clickhouse-client < scripts/database/init_clickhouse.sql
```

## Database Environments

The scripts create three database environments:

1. **Development** (`alphapt_dev`) - Local development and testing
2. **Test** (`alphapt_test`) - Automated testing and CI/CD
3. **Production** (`alphapt_prod`) - Live trading environment

## Connection Details

### PostgreSQL
- **Host**: localhost (or container name in Docker)
- **Port**: 5432
- **User**: alphapt_user
- **Password**: Set in environment variables

### ClickHouse
- **Host**: localhost (or container name in Docker)
- **Port**: 9000 (native), 8123 (HTTP)
- **User**: default
- **Password**: Set in environment variables

## Security Notes

⚠️ **Important Security Considerations**:

1. **Change Default Passwords**: The initialization scripts use development passwords. Change these in production.

2. **Environment Variables**: Use environment variables for database credentials:
   ```bash
   POSTGRES_PASSWORD=your_secure_password
   CLICKHOUSE_PASSWORD=your_secure_password
   ```

3. **Network Security**: In production, restrict database access to application servers only.

4. **SSL/TLS**: Enable SSL connections for production databases.

## Backup and Recovery

### PostgreSQL Backup
```bash
# Create backup
pg_dump -h localhost -U alphapt_user alphapt_prod > backup.sql

# Restore backup
psql -h localhost -U alphapt_user alphapt_prod < backup.sql
```

### ClickHouse Backup
```bash
# Create backup
clickhouse-client --query "BACKUP DATABASE alphapt_prod TO '/var/lib/clickhouse/backup/'"

# Restore backup
clickhouse-client --query "RESTORE DATABASE alphapt_prod FROM '/var/lib/clickhouse/backup/'"
```

## Performance Tuning

### PostgreSQL
- Configure `shared_buffers` to 25% of available RAM
- Set `effective_cache_size` to 75% of available RAM
- Adjust `work_mem` based on concurrent connections
- Enable `synchronous_commit = off` for high-frequency inserts (with backup strategy)

### ClickHouse
- Configure `max_memory_usage` based on available RAM
- Set appropriate `max_threads` for query processing
- Use `LZ4` compression for hot data, `ZSTD` for cold data
- Partition tables by month for optimal query performance

## Monitoring

- Monitor query performance with `pg_stat_statements` (PostgreSQL)
- Use ClickHouse system tables for performance metrics
- Set up alerts for disk space and connection limits
- Monitor replication lag if using database replicas

## Migration Support

Future versions will include Alembic migration support for PostgreSQL schema changes. ClickHouse schema changes should be handled through versioned SQL scripts.