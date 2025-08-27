"""Monitoring and observability configuration."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MonitoringConfig(BaseModel):
    """Monitoring configuration settings."""

    # Prometheus settings
    prometheus_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    prometheus_port: int = Field(default=8001, description="Prometheus metrics port")
    prometheus_path: str = Field(default="/metrics", description="Prometheus metrics path")
    prometheus_pushgateway_url: Optional[str] = Field(default=None, description="Prometheus pushgateway URL")
    prometheus_job_name: str = Field(default="alphapt", description="Prometheus job name")

    # Health check settings
    health_check_enabled: bool = Field(default=True, description="Enable health checks")
    health_check_interval: float = Field(default=30.0, description="Health check interval in seconds")
    health_check_timeout: float = Field(default=5.0, description="Health check timeout in seconds")
    health_check_endpoint: str = Field(default="/health", description="Health check endpoint")

    # Alerting settings
    alerting_enabled: bool = Field(default=True, description="Enable alerting")
    alert_channels: List[str] = Field(default=["log"], description="Alert channels (log, email, slack, webhook)")
    alert_webhook_url: Optional[str] = Field(default=None, description="Alert webhook URL")
    alert_email_smtp_host: Optional[str] = Field(default=None, description="SMTP host for email alerts")
    alert_email_smtp_port: int = Field(default=587, description="SMTP port for email alerts")
    alert_email_username: Optional[str] = Field(default=None, description="SMTP username for email alerts")
    alert_email_password: Optional[str] = Field(default=None, description="SMTP password for email alerts")
    alert_email_from: Optional[str] = Field(default=None, description="From email address for alerts")
    alert_email_to: List[str] = Field(default_factory=list, description="To email addresses for alerts")

    # Logging settings
    log_structured: bool = Field(default=True, description="Enable structured logging")
    log_json_format: bool = Field(default=True, description="Use JSON log format")
    log_file_enabled: bool = Field(default=True, description="Enable file logging")
    log_file_path: str = Field(default="alphapt.log", description="Log file path (legacy single file)")
    log_file_max_size: str = Field(default="100MB", description="Maximum log file size")
    log_file_backup_count: int = Field(default=5, description="Log file backup count")
    log_console_enabled: bool = Field(default=True, description="Enable console logging")
    
    # Multi-channel logging settings
    log_multi_channel_enabled: bool = Field(default=True, description="Enable multi-channel logging")
    log_audit_retention_days: int = Field(default=365, description="Audit log retention in days")
    log_performance_retention_days: int = Field(default=30, description="Performance log retention in days")
    log_database_level: str = Field(default="WARNING", description="Database log level to reduce SQL noise")
    log_trading_level: str = Field(default="INFO", description="Trading operations log level")
    log_api_level: str = Field(default="INFO", description="API operations log level")
    log_auto_cleanup_enabled: bool = Field(default=True, description="Enable automatic log cleanup")
    log_compression_enabled: bool = Field(default=True, description="Enable log compression for old files")
    log_compression_age_days: int = Field(default=7, description="Compress logs older than this many days")

    # Performance monitoring
    performance_monitoring_enabled: bool = Field(default=True, description="Enable performance monitoring")
    performance_metrics_interval: float = Field(default=10.0, description="Performance metrics collection interval")
    slow_query_threshold: float = Field(default=1.0, description="Slow query threshold in seconds")

    # Business metrics
    business_metrics_enabled: bool = Field(default=True, description="Enable business metrics")
    pnl_calculation_interval: float = Field(default=60.0, description="PnL calculation interval")
    position_monitoring_interval: float = Field(default=30.0, description="Position monitoring interval")

    # System metrics
    system_metrics_enabled: bool = Field(default=True, description="Enable system metrics")
    system_metrics_interval: float = Field(default=15.0, description="System metrics collection interval")
    memory_alert_threshold: float = Field(default=0.9, description="Memory usage alert threshold")
    cpu_alert_threshold: float = Field(default=0.8, description="CPU usage alert threshold")
    disk_alert_threshold: float = Field(default=0.9, description="Disk usage alert threshold")

    # Event monitoring
    event_monitoring_enabled: bool = Field(default=True, description="Enable event monitoring")
    event_queue_size_threshold: int = Field(default=1000, description="Event queue size alert threshold")
    event_processing_lag_threshold: float = Field(default=5.0, description="Event processing lag threshold in seconds")

    # Market data monitoring
    market_data_monitoring_enabled: bool = Field(default=True, description="Enable market data monitoring")
    market_data_latency_threshold: float = Field(default=1.0, description="Market data latency threshold in seconds")
    market_data_gap_threshold: float = Field(default=10.0, description="Market data gap threshold in seconds")

    def get_prometheus_config(self) -> dict:
        """Get Prometheus configuration."""
        return {
            "enabled": self.prometheus_enabled,
            "port": self.prometheus_port,
            "path": self.prometheus_path,
            "pushgateway_url": self.prometheus_pushgateway_url,
            "job_name": self.prometheus_job_name,
        }

    def get_alerting_config(self) -> dict:
        """Get alerting configuration."""
        return {
            "enabled": self.alerting_enabled,
            "channels": self.alert_channels,
            "webhook_url": self.alert_webhook_url,
            "email_config": {
                "smtp_host": self.alert_email_smtp_host,
                "smtp_port": self.alert_email_smtp_port,
                "username": self.alert_email_username,
                "password": self.alert_email_password,
                "from_email": self.alert_email_from,
                "to_emails": self.alert_email_to,
            },
        }

    def get_logging_config(self) -> dict:
        """Get logging configuration."""
        return {
            "structured": self.log_structured,
            "json_format": self.log_json_format,
            "file_enabled": self.log_file_enabled,
            "file_path": self.log_file_path,
            "file_max_size": self.log_file_max_size,
            "file_backup_count": self.log_file_backup_count,
            "console_enabled": self.log_console_enabled,
            # Multi-channel settings
            "multi_channel_enabled": self.log_multi_channel_enabled,
            "audit_retention_days": self.log_audit_retention_days,
            "performance_retention_days": self.log_performance_retention_days,
            "database_level": self.log_database_level,
            "trading_level": self.log_trading_level,
            "api_level": self.log_api_level,
            "auto_cleanup_enabled": self.log_auto_cleanup_enabled,
            "compression_enabled": self.log_compression_enabled,
            "compression_age_days": self.log_compression_age_days,
        }
