"""Database configuration settings."""

import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator


class DatabaseConfig(BaseModel):
    """Database configuration settings."""

    # PostgreSQL settings
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_user: str = Field(default="alphapt", description="PostgreSQL user")
    postgres_password: str = Field(default="alphapt", description="PostgreSQL password")
    postgres_database: str = Field(default="alphapt", description="PostgreSQL database")
    postgres_pool_size: int = Field(default=30, description="PostgreSQL pool size")
    postgres_max_overflow: int = Field(default=50, description="PostgreSQL max overflow")
    postgres_pool_timeout: int = Field(default=20, description="PostgreSQL pool timeout")
    postgres_pool_pre_ping: bool = Field(default=True, description="PostgreSQL pool pre-ping")
    postgres_pool_recycle: int = Field(default=3600, description="PostgreSQL pool recycle time")
    postgres_ssl_mode: str = Field(default="prefer", description="PostgreSQL SSL mode")

    # ClickHouse settings
    clickhouse_host: str = Field(default="localhost", description="ClickHouse host")
    clickhouse_port: int = Field(default=8123, description="ClickHouse HTTP port")
    clickhouse_user: str = Field(default="default", description="ClickHouse user")
    clickhouse_password: str = Field(default="", description="ClickHouse password")
    clickhouse_database: str = Field(default="alphapt", description="ClickHouse database")
    clickhouse_connect_timeout: int = Field(default=10, description="ClickHouse connect timeout")
    clickhouse_send_receive_timeout: int = Field(default=300, description="ClickHouse send/receive timeout")
    clickhouse_compression: str = Field(default="lz4", description="ClickHouse compression")
    clickhouse_pool_size: int = Field(default=15, description="ClickHouse connection pool size")
    clickhouse_insert_block_size: int = Field(default=1048576, description="ClickHouse insert block size")
    clickhouse_settings: dict = Field(
        default_factory=lambda: {
            "max_memory_usage": "4000000000",  # 4GB
            "max_threads": 8,
            "max_execution_time": 60,
            "join_use_nulls": 1,
            "compress": 1,
        },
        description="ClickHouse custom settings",
    )

    # Connection pool settings
    connection_retry_attempts: int = Field(default=3, description="Connection retry attempts")
    connection_retry_delay: float = Field(default=1.0, description="Connection retry delay")
    connection_health_check_interval: float = Field(default=30.0, description="Connection health check interval")

    @property
    def postgres_url(self) -> str:
        """Get PostgreSQL connection URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
        )

    @property
    def postgres_async_url(self) -> str:
        """Get async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_database}"
        )

    @property
    def clickhouse_url(self) -> str:
        """Get ClickHouse connection URL."""
        auth = (
            f"{self.clickhouse_user}:{self.clickhouse_password}@"
            if self.clickhouse_password
            else f"{self.clickhouse_user}@"
        )
        return f"clickhouse://{auth}{self.clickhouse_host}:{self.clickhouse_port}/{self.clickhouse_database}"

    def get_postgres_connection_params(self) -> dict:
        """Get PostgreSQL connection parameters."""
        return {
            "host": self.postgres_host,
            "port": self.postgres_port,
            "user": self.postgres_user,
            "password": self.postgres_password,
            "database": self.postgres_database,
            "pool_size": self.postgres_pool_size,
            "max_overflow": self.postgres_max_overflow,
            "pool_timeout": self.postgres_pool_timeout,
            "pool_pre_ping": self.postgres_pool_pre_ping,
            "pool_recycle": self.postgres_pool_recycle,
        }

    def get_clickhouse_connection_params(self) -> dict:
        """Get ClickHouse connection parameters."""
        return {
            "host": self.clickhouse_host,
            "port": self.clickhouse_port,
            "username": self.clickhouse_user,
            "password": self.clickhouse_password,
            "database": self.clickhouse_database,
            "connect_timeout": self.clickhouse_connect_timeout,
            "send_receive_timeout": self.clickhouse_send_receive_timeout,
            "compression": self.clickhouse_compression,
            # Note: Removed settings parameter as it was causing connection issues
            # Settings can be applied per-query instead
        }

    @field_validator("postgres_host")
    @classmethod
    def validate_postgres_host(cls, v: str) -> str:
        """Validate PostgreSQL host."""
        if not v or not v.strip():
            raise ValueError("PostgreSQL host cannot be empty")

        # Check for valid hostname/IP format
        host = v.strip()
        if not re.match(r"^[a-zA-Z0-9.-]+$", host):
            raise ValueError("Invalid PostgreSQL host format")

        return host

    @field_validator("postgres_port")
    @classmethod
    def validate_postgres_port(cls, v: int) -> int:
        """Validate PostgreSQL port."""
        if not 1 <= v <= 65535:
            raise ValueError("PostgreSQL port must be between 1 and 65535")
        return v

    @field_validator("postgres_user")
    @classmethod
    def validate_postgres_user(cls, v: str) -> str:
        """Validate PostgreSQL user."""
        if not v or not v.strip():
            raise ValueError("PostgreSQL user cannot be empty")

        user = v.strip()
        if len(user) > 63:  # PostgreSQL username limit
            raise ValueError("PostgreSQL username cannot exceed 63 characters")

        # Check for valid username characters
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_$]*$", user):
            raise ValueError("Invalid PostgreSQL username format")

        return user

    @field_validator("postgres_password")
    @classmethod
    def validate_postgres_password(cls, v: str) -> str:
        """Validate PostgreSQL password."""
        if not v:
            raise ValueError("PostgreSQL password cannot be empty")

        # Check password strength in production
        import os

        if os.getenv("ENVIRONMENT") == "production":
            if len(v) < 12:
                raise ValueError("PostgreSQL password must be at least 12 characters in production")

            # Check for basic complexity
            if not any(c.isupper() for c in v):
                raise ValueError("PostgreSQL password must contain uppercase letters")
            if not any(c.islower() for c in v):
                raise ValueError("PostgreSQL password must contain lowercase letters")
            if not any(c.isdigit() for c in v):
                raise ValueError("PostgreSQL password must contain digits")
            if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v):
                raise ValueError("PostgreSQL password must contain special characters")

        return v

    @field_validator("postgres_database")
    @classmethod
    def validate_postgres_database(cls, v: str) -> str:
        """Validate PostgreSQL database name."""
        if not v or not v.strip():
            raise ValueError("PostgreSQL database name cannot be empty")

        db_name = v.strip()
        if len(db_name) > 63:  # PostgreSQL identifier limit
            raise ValueError("PostgreSQL database name cannot exceed 63 characters")

        # Check for valid database name
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_$]*$", db_name):
            raise ValueError("Invalid PostgreSQL database name format")

        return db_name

    @field_validator("clickhouse_host")
    @classmethod
    def validate_clickhouse_host(cls, v: str) -> str:
        """Validate ClickHouse host."""
        if not v or not v.strip():
            raise ValueError("ClickHouse host cannot be empty")

        host = v.strip()
        if not re.match(r"^[a-zA-Z0-9.-]+$", host):
            raise ValueError("Invalid ClickHouse host format")

        return host

    @field_validator("clickhouse_port")
    @classmethod
    def validate_clickhouse_port(cls, v: int) -> int:
        """Validate ClickHouse port."""
        if not 1 <= v <= 65535:
            raise ValueError("ClickHouse port must be between 1 and 65535")
        return v

    @field_validator("clickhouse_database")
    @classmethod
    def validate_clickhouse_database(cls, v: str) -> str:
        """Validate ClickHouse database name."""
        if not v or not v.strip():
            raise ValueError("ClickHouse database name cannot be empty")

        db_name = v.strip()
        # ClickHouse database names are more flexible than PostgreSQL
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", db_name):
            raise ValueError("Invalid ClickHouse database name format")

        return db_name

    @field_validator("postgres_pool_size")
    @classmethod
    def validate_postgres_pool_size(cls, v: int) -> int:
        """Validate PostgreSQL pool size."""
        if not 1 <= v <= 100:
            raise ValueError("PostgreSQL pool size must be between 1 and 100")
        return v

    @field_validator("clickhouse_pool_size")
    @classmethod
    def validate_clickhouse_pool_size(cls, v: int) -> int:
        """Validate ClickHouse pool size."""
        if not 1 <= v <= 50:
            raise ValueError("ClickHouse pool size must be between 1 and 50")
        return v

    @field_validator("clickhouse_compression")
    @classmethod
    def validate_clickhouse_compression(cls, v: str) -> str:
        """Validate ClickHouse compression method."""
        valid_compressions = {"none", "lz4", "lz4hc", "zstd", "gzip"}
        if v.lower() not in valid_compressions:
            raise ValueError(f"ClickHouse compression must be one of: {valid_compressions}")
        return v.lower()

    def validate_connection_urls(self) -> Dict[str, bool]:
        """Validate all connection URLs are properly formatted.

        Returns:
            Dict[str, bool]: Validation results for each connection type
        """
        results = {}

        try:
            # Validate PostgreSQL URL
            postgres_url = self.postgres_url
            parsed = urlparse(postgres_url)

            if not all([parsed.scheme, parsed.hostname, parsed.username, parsed.password]):
                results["postgres"] = False
            else:
                results["postgres"] = True

        except Exception:
            results["postgres"] = False

        try:
            # Validate ClickHouse URL
            clickhouse_url = self.clickhouse_url
            parsed = urlparse(clickhouse_url)

            if not all([parsed.scheme, parsed.hostname]):
                results["clickhouse"] = False
            else:
                results["clickhouse"] = True

        except Exception:
            results["clickhouse"] = False

        return results

    def get_security_recommendations(self) -> Dict[str, Any]:
        """Get security recommendations for database configuration.

        Returns:
            Dict[str, Any]: Security recommendations and warnings
        """
        recommendations = {"warnings": [], "recommendations": [], "critical_issues": []}

        # Check for default/weak passwords
        if self.postgres_password in ["postgres", "password", "123456", "alphapt"]:
            recommendations["critical_issues"].append("PostgreSQL using default/weak password - change immediately")

        if self.clickhouse_password in ["", "password", "123456", "clickhouse"]:
            recommendations["warnings"].append("ClickHouse using weak/empty password - consider strengthening")

        # Check SSL configuration
        if self.postgres_ssl_mode == "disable":
            recommendations["warnings"].append("PostgreSQL SSL is disabled - enable for production")

        # Check connection limits
        if self.postgres_pool_size > 50:
            recommendations["warnings"].append("PostgreSQL pool size is quite large - monitor connection usage")

        # Environment-specific checks
        import os

        if os.getenv("ENVIRONMENT") == "production":
            if self.postgres_host in ["localhost", "127.0.0.1"]:
                recommendations["warnings"].append(
                    "Using localhost for PostgreSQL in production - ensure this is intended"
                )

            if self.clickhouse_host in ["localhost", "127.0.0.1"]:
                recommendations["warnings"].append(
                    "Using localhost for ClickHouse in production - ensure this is intended"
                )

        return recommendations
