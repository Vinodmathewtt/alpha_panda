"""ClickHouse schema migration manager."""

import os
import re
import uuid
import time
from pathlib import Path
from typing import List, Dict, Optional
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from core.config.settings import Settings
from core.logging.logger import get_logger
from storage.clickhouse_manager import ClickHouseManager


@dataclass
class Migration:
    """Represents a database migration."""
    version: str
    filename: str
    description: str
    sql_content: str


class MigrationManager:
    """Manages ClickHouse schema migrations."""
    
    def __init__(self, settings: Settings, clickhouse_manager: ClickHouseManager):
        """Initialize migration manager.
        
        Args:
            settings: Application settings
            clickhouse_manager: ClickHouse manager instance
        """
        self.settings = settings
        self.clickhouse_manager = clickhouse_manager
        self.logger = get_logger("migration_manager", "migrations")
        
        # Migration directory
        self.migrations_dir = Path(__file__).parent / "migrations"
        
    async def get_available_migrations(self) -> List[Migration]:
        """Get all available migration files."""
        migrations = []
        
        if not self.migrations_dir.exists():
            self.logger.warning(f"Migrations directory not found: {self.migrations_dir}")
            return migrations
            
        # Pattern to match migration files: 001_migration_name.sql
        migration_pattern = re.compile(r'^(\d{3})_(.+)\.sql$')
        
        for file_path in sorted(self.migrations_dir.glob("*.sql")):
            match = migration_pattern.match(file_path.name)
            if match:
                version = match.group(1)
                name = match.group(2)
                
                try:
                    sql_content = file_path.read_text(encoding='utf-8')
                    
                    # Extract description from SQL comment
                    description = self._extract_description(sql_content)
                    
                    migrations.append(Migration(
                        version=version,
                        filename=file_path.name,
                        description=description or name,
                        sql_content=sql_content
                    ))
                    
                except Exception as e:
                    self.logger.error(f"Error reading migration file {file_path}: {e}")
                    
        return migrations
    
    async def get_applied_migrations(self) -> List[str]:
        """Get list of applied migration versions."""
        try:
            # Check if migrations table exists
            await self.clickhouse_manager.execute_query(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version String, applied_at DateTime64(3) DEFAULT now64()) "
                "ENGINE = MergeTree() ORDER BY version"
            )
            
            # Get applied migrations
            result = await self.clickhouse_manager.execute_query(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
            
            return [row[0] for row in result] if result else []
            
        except Exception as e:
            self.logger.error(f"Error getting applied migrations: {e}")
            return []
    
    async def apply_migration(self, migration: Migration) -> bool:
        """Apply a single migration with comprehensive correlation tracking.
        
        Args:
            migration: Migration to apply
            
        Returns:
            True if migration applied successfully
        """
        # Generate correlation ID for tracking this migration
        correlation_id = f"migration_{migration.version}_{uuid.uuid4().hex[:8]}"
        migration_start_ns = time.perf_counter_ns()
        
        self.logger.info("Migration application started", extra={
            'correlation_id': correlation_id,
            'event_type': 'migration_start',
            'migration_version': migration.version,
            'migration_description': migration.description,
            'migration_filename': migration.filename
        })
        
        try:
            # Split SQL into individual statements to handle ClickHouse multi-statement limitations
            statements = self._split_sql_statements(migration.sql_content)
            total_statements = len(statements)
            
            self.logger.info("Migration statements prepared", extra={
                'correlation_id': correlation_id,
                'event_type': 'migration_statements_prepared',
                'total_statements': total_statements,
                'non_empty_statements': len([s for s in statements if s.strip()])
            })
            
            # Execute each statement separately with detailed tracking
            executed_statements = 0
            for i, statement in enumerate(statements):
                if statement.strip():  # Skip empty statements
                    statement_start_ns = time.perf_counter_ns()
                    statement_preview = statement[:100].replace('\n', ' ')
                    
                    self.logger.debug("Executing migration statement", extra={
                        'correlation_id': correlation_id,
                        'event_type': 'migration_statement_start',
                        'statement_index': i + 1,
                        'total_statements': total_statements,
                        'statement_preview': statement_preview,
                        'statement_length': len(statement)
                    })
                    
                    try:
                        await self.clickhouse_manager.execute_query(statement)
                        executed_statements += 1
                        
                        statement_time_us = (time.perf_counter_ns() - statement_start_ns) / 1000
                        
                        self.logger.debug("Migration statement executed successfully", extra={
                            'correlation_id': correlation_id,
                            'event_type': 'migration_statement_success',
                            'statement_index': i + 1,
                            'execution_time_us': statement_time_us,
                            'statement_preview': statement_preview
                        })
                        
                    except Exception as e:
                        statement_time_us = (time.perf_counter_ns() - statement_start_ns) / 1000
                        
                        self.logger.error("Migration statement execution failed", extra={
                            'correlation_id': correlation_id,
                            'event_type': 'migration_statement_error',
                            'statement_index': i + 1,
                            'execution_time_us': statement_time_us,
                            'error': str(e),
                            'error_type': type(e).__name__,
                            'statement_preview': statement_preview,
                            'executed_statements': executed_statements
                        })
                        raise
            
            # Record migration as applied with tracking
            record_start_ns = time.perf_counter_ns()
            await self.clickhouse_manager.execute_query(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (migration.version,)
            )
            record_time_us = (time.perf_counter_ns() - record_start_ns) / 1000
            
            # Calculate total migration time
            total_migration_time_ns = time.perf_counter_ns() - migration_start_ns
            total_migration_time_ms = total_migration_time_ns / 1_000_000
            
            self.logger.info("Migration applied successfully", extra={
                'correlation_id': correlation_id,
                'event_type': 'migration_success',
                'migration_version': migration.version,
                'total_execution_time_ms': total_migration_time_ms,
                'record_time_us': record_time_us,
                'statements_executed': executed_statements,
                'total_statements': total_statements
            })
            
            return True
            
        except Exception as e:
            # Calculate error time
            total_error_time_ns = time.perf_counter_ns() - migration_start_ns
            total_error_time_ms = total_error_time_ns / 1_000_000
            
            self.logger.error("Migration application failed", extra={
                'correlation_id': correlation_id,
                'event_type': 'migration_error',
                'migration_version': migration.version,
                'migration_description': migration.description,
                'error': str(e),
                'error_type': type(e).__name__,
                'total_error_time_ms': total_error_time_ms,
                'statements_executed': executed_statements if 'executed_statements' in locals() else 0
            })
            
            return False
    
    async def run_migrations(self) -> bool:
        """Run all pending migrations with comprehensive tracking.
        
        Returns:
            True if all migrations applied successfully
        """
        # Generate session correlation ID
        session_correlation_id = f"migration_session_{uuid.uuid4().hex[:8]}"
        session_start_ns = time.perf_counter_ns()
        
        self.logger.info("Migration session started", extra={
            'correlation_id': session_correlation_id,
            'event_type': 'migration_session_start',
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
        
        try:
            # Get available and applied migrations
            discovery_start_ns = time.perf_counter_ns()
            available_migrations = await self.get_available_migrations()
            applied_migrations = await self.get_applied_migrations()
            discovery_time_ms = (time.perf_counter_ns() - discovery_start_ns) / 1_000_000
            
            self.logger.info("Migration discovery completed", extra={
                'correlation_id': session_correlation_id,
                'event_type': 'migration_discovery_complete',
                'available_migrations': len(available_migrations),
                'applied_migrations': len(applied_migrations),
                'discovery_time_ms': discovery_time_ms
            })
            
            if not available_migrations:
                self.logger.info("No migration files found", extra={
                    'correlation_id': session_correlation_id,
                    'event_type': 'no_migrations_found'
                })
                return True
                
            # Find pending migrations
            pending_migrations = [
                m for m in available_migrations 
                if m.version not in applied_migrations
            ]
            
            if not pending_migrations:
                self.logger.info("All migrations are up to date", extra={
                    'correlation_id': session_correlation_id,
                    'event_type': 'migrations_up_to_date',
                    'total_migrations': len(available_migrations)
                })
                return True
                
            self.logger.info("Pending migrations identified", extra={
                'correlation_id': session_correlation_id,
                'event_type': 'pending_migrations_identified',
                'pending_count': len(pending_migrations),
                'pending_versions': [m.version for m in pending_migrations]
            })
            
            # Apply pending migrations in order
            success_count = 0
            failed_migration = None
            
            for i, migration in enumerate(pending_migrations):
                migration_progress = f"{i + 1}/{len(pending_migrations)}"
                
                self.logger.info("Starting migration application", extra={
                    'correlation_id': session_correlation_id,
                    'event_type': 'migration_application_start',
                    'migration_version': migration.version,
                    'progress': migration_progress
                })
                
                if await self.apply_migration(migration):
                    success_count += 1
                    self.logger.info("Migration application completed", extra={
                        'correlation_id': session_correlation_id,
                        'event_type': 'migration_application_success',
                        'migration_version': migration.version,
                        'progress': migration_progress,
                        'completed_migrations': success_count
                    })
                else:
                    failed_migration = migration
                    self.logger.error("Migration application failed - stopping process", extra={
                        'correlation_id': session_correlation_id,
                        'event_type': 'migration_application_failed',
                        'migration_version': migration.version,
                        'progress': migration_progress,
                        'completed_migrations': success_count
                    })
                    break
            
            # Calculate session results
            session_time_ns = time.perf_counter_ns() - session_start_ns
            session_time_ms = session_time_ns / 1_000_000
            
            if success_count == len(pending_migrations):
                self.logger.info("Migration session completed successfully", extra={
                    'correlation_id': session_correlation_id,
                    'event_type': 'migration_session_success',
                    'migrations_applied': success_count,
                    'total_pending': len(pending_migrations),
                    'session_duration_ms': session_time_ms
                })
                return True
            else:
                self.logger.error("Migration session completed with failures", extra={
                    'correlation_id': session_correlation_id,
                    'event_type': 'migration_session_partial_failure',
                    'migrations_applied': success_count,
                    'total_pending': len(pending_migrations),
                    'failed_migration': failed_migration.version if failed_migration else 'unknown',
                    'session_duration_ms': session_time_ms
                })
                return False
                
        except Exception as e:
            session_time_ns = time.perf_counter_ns() - session_start_ns
            session_time_ms = session_time_ns / 1_000_000
            
            self.logger.error("Migration session failed with exception", extra={
                'correlation_id': session_correlation_id,
                'event_type': 'migration_session_error',
                'error': str(e),
                'error_type': type(e).__name__,
                'session_duration_ms': session_time_ms
            })
            return False
    
    async def get_migration_status(self) -> Dict:
        """Get current migration status.
        
        Returns:
            Dictionary with migration status information
        """
        try:
            available_migrations = await self.get_available_migrations()
            applied_migrations = await self.get_applied_migrations()
            
            pending_migrations = [
                m.version for m in available_migrations 
                if m.version not in applied_migrations
            ]
            
            return {
                "total_available": len(available_migrations),
                "total_applied": len(applied_migrations),
                "pending_count": len(pending_migrations),
                "pending_versions": pending_migrations,
                "applied_versions": applied_migrations,
                "up_to_date": len(pending_migrations) == 0
            }
            
        except Exception as e:
            self.logger.error(f"Error getting migration status: {e}")
            return {
                "error": str(e),
                "up_to_date": False
            }
    
    def _extract_description(self, sql_content: str) -> Optional[str]:
        """Extract description from SQL migration file."""
        lines = sql_content.split('\n')
        for line in lines[:10]:  # Check first 10 lines
            if line.startswith('-- Description:'):
                return line.replace('-- Description:', '').strip()
        return None
    
    def _split_sql_statements(self, sql_content: str) -> List[str]:
        """Split SQL content into individual statements.
        
        Args:
            sql_content: Raw SQL content with multiple statements
            
        Returns:
            List of individual SQL statements
        """
        # Remove comments and empty lines
        lines = []
        for line in sql_content.split('\n'):
            line = line.strip()
            # Skip comment lines and empty lines
            if line and not line.startswith('--'):
                lines.append(line)
        
        # Join lines and split by semicolon (but be careful with semicolons in strings)
        content = ' '.join(lines)
        
        # Simple split by semicolon - works for our migration files
        # For more complex SQL parsing, we'd need a proper SQL parser
        statements = []
        current_statement = []
        
        # Split by semicolon and reconstruct statements
        parts = content.split(';')
        
        for i, part in enumerate(parts):
            part = part.strip()
            if part:
                current_statement.append(part)
                
                # If this is the last part or the next part starts a new statement
                if i == len(parts) - 1 or (i < len(parts) - 1 and parts[i + 1].strip()):
                    if current_statement:
                        statement = ' '.join(current_statement).strip()
                        if statement and not statement.startswith('--'):
                            statements.append(statement)
                        current_statement = []
        
        # Filter out any remaining empty or comment-only statements
        return [stmt.strip() for stmt in statements if stmt.strip() and not stmt.strip().startswith('--')]