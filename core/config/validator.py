"""
Configuration validation at application startup.

Validates that all critical configuration values are properly set before 
services start, providing clear error messages for missing or invalid settings.
"""

import os
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    import redis.asyncio as redis
except ImportError:
    # Fallback for older redis versions or different installations
    try:
        import aioredis as redis
    except ImportError:
        redis = None

try:
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    sqlalchemy_available = True
except ImportError:
    sqlalchemy_available = False
    create_async_engine = None
    text = None

from .settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of a configuration validation check"""
    is_valid: bool
    component: str
    message: str
    severity: str = "error"  # "error", "warning", "info"


class ConfigurationValidator:
    """
    Comprehensive configuration validator for startup checks.
    
    Validates all critical configuration values and dependencies before
    services start, providing clear feedback on what needs to be fixed.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.validation_results: List[ValidationResult] = []
    
    async def validate_all(self) -> bool:
        """
        Run all validation checks.
        
        Returns:
            bool: True if all critical validations pass
        """
        logger.info("🔍 Starting comprehensive configuration validation...")
        
        # Run all validation checks
        self._validate_environment_variables()
        self._validate_file_paths()
        await self._validate_database_connection()
        await self._validate_redis_connection()
        self._validate_broker_settings()
        self._validate_auth_settings()
        self._validate_logging_settings()
        self._validate_portfolio_manager_settings()
        
        # Analyze results
        errors = [r for r in self.validation_results if r.severity == "error"]
        warnings = [r for r in self.validation_results if r.severity == "warning"]
        
        # Log summary
        if errors:
            logger.error(f"❌ Configuration validation failed: {len(errors)} errors, {len(warnings)} warnings")
            for result in errors:
                logger.error(f"   ERROR [{result.component}]: {result.message}")
        
        if warnings:
            for result in warnings:
                logger.warning(f"   WARNING [{result.component}]: {result.message}")
        
        if not errors and not warnings:
            logger.info("✅ All configuration validation checks passed")
        elif not errors:
            logger.info(f"✅ Configuration validation passed with {len(warnings)} warnings")
        
        return len(errors) == 0
    
    def _validate_environment_variables(self):
        """Validate critical environment variables"""
        # Validate active brokers configuration
        if not self.settings.active_brokers:
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Environment",
                message="ACTIVE_BROKERS must contain at least one broker",
                severity="error"
            ))
        else:
            supported_brokers = {"paper", "zerodha"}
            invalid_brokers = set(self.settings.active_brokers) - supported_brokers
            if invalid_brokers:
                self.validation_results.append(ValidationResult(
                    is_valid=False,
                    component="Environment",
                    message=f"Unsupported brokers in ACTIVE_BROKERS: {invalid_brokers}. Supported: {supported_brokers}",
                    severity="error"
                ))
    
    def _validate_file_paths(self):
        """Validate that required directories and files exist"""
        # Validate logs directory
        logs_dir = Path(self.settings.logs_dir)
        if not logs_dir.parent.exists():
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="File System",
                message=f"Parent directory for logs does not exist: {logs_dir.parent}",
                severity="error"
            ))
        
        # Validate migrations directory
        migrations_dir = Path(self.settings.base_dir) / "migrations"
        if not migrations_dir.exists():
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="File System", 
                message=f"Migrations directory not found: {migrations_dir}",
                severity="warning"
            ))
    
    async def _validate_database_connection(self):
        """Validate database connection"""
        if not sqlalchemy_available:
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Database",
                message="SQLAlchemy not available - cannot test database connection",
                severity="warning"
            ))
            return
            
        try:
            # Test database connectivity
            engine = create_async_engine(
                self.settings.database.postgres_url,
                pool_timeout=self.settings.health_checks.database_connection_timeout_seconds
            )
            
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            
            await engine.dispose()
            
            self.validation_results.append(ValidationResult(
                is_valid=True,
                component="Database",
                message="Database connection successful",
                severity="info"
            ))
            
        except Exception as e:
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Database",
                message=f"Cannot connect to database: {e}",
                severity="error"
            ))
    
    async def _validate_redis_connection(self):
        """Validate Redis connection"""
        if redis is None:
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Redis",
                message="Redis client library not available",
                severity="warning"
            ))
            return
            
        try:
            redis_client = redis.from_url(
                self.settings.redis.url,
                socket_connect_timeout=self.settings.health_checks.redis_connection_timeout_seconds
            )
            
            await redis_client.ping()
            await redis_client.aclose()
            
            self.validation_results.append(ValidationResult(
                is_valid=True,
                component="Redis",
                message="Redis connection successful",
                severity="info"
            ))
            
        except Exception as e:
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Redis",
                message=f"Cannot connect to Redis: {e}",
                severity="error"
            ))
    
    def _validate_broker_settings(self):
        """Validate broker configuration"""
        # Validate Redpanda/Kafka settings
        if not self.settings.redpanda.bootstrap_servers:
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Broker",
                message="Redpanda bootstrap_servers not configured",
                severity="error"
            ))
        
        # For zerodha broker, validate API credentials are set if zerodha is active
        if "zerodha" in self.settings.active_brokers:
            if not self.settings.zerodha.api_key or not self.settings.zerodha.api_secret:
                self.validation_results.append(ValidationResult(
                    is_valid=False,
                    component="Broker",
                    message="Zerodha API credentials not configured but zerodha broker is active",
                    severity="error"
                ))
    
    def _validate_auth_settings(self):
        """Validate authentication settings"""
        if len(self.settings.auth.secret_key) < 32:
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Authentication",
                message="JWT secret key should be at least 32 characters long",
                severity="warning"
            ))
        
        if self.settings.auth.secret_key == "your-secret-key-change-in-production":
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Authentication",
                message="Using default JWT secret key - change in production!",
                severity="error"
            ))
    
    def _validate_logging_settings(self):
        """Validate logging configuration"""
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        
        if self.settings.logging.level.upper() not in valid_log_levels:
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Logging",
                message=f"Invalid log level: {self.settings.logging.level}",
                severity="error"
            ))
    
    def _validate_portfolio_manager_settings(self):
        """Validate portfolio manager configuration"""
        if self.settings.portfolio_manager.snapshot_interval_seconds < 60:
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Portfolio Manager",
                message="Snapshot interval less than 60 seconds may cause performance issues",
                severity="warning"
            ))
        
        if self.settings.portfolio_manager.max_portfolio_locks < 100:
            self.validation_results.append(ValidationResult(
                is_valid=False,
                component="Portfolio Manager",
                message="Max portfolio locks setting too low, may cause lock cleanup thrashing",
                severity="warning"
            ))
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """Get a summary of validation results"""
        errors = [r for r in self.validation_results if r.severity == "error"]
        warnings = [r for r in self.validation_results if r.severity == "warning"]
        
        return {
            "total_checks": len(self.validation_results),
            "errors": len(errors),
            "warnings": len(warnings),
            "is_valid": len(errors) == 0,
            "error_details": [{"component": r.component, "message": r.message} for r in errors],
            "warning_details": [{"component": r.component, "message": r.message} for r in warnings]
        }


async def validate_startup_configuration(settings: Settings) -> bool:
    """
    Convenience function to run startup configuration validation.
    
    Args:
        settings: Application settings to validate
        
    Returns:
        bool: True if validation passes (no critical errors)
    """
    validator = ConfigurationValidator(settings)
    return await validator.validate_all()