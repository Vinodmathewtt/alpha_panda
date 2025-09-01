"""
Alerting integration framework for Alpha Panda.
Provides hooks for external alerting systems (email, Slack, PagerDuty, etc.)
"""

import asyncio
from core.logging import get_monitoring_logger_safe
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

logger = get_monitoring_logger_safe("alerting")


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    CRITICAL = "critical"      # System failure, trading disrupted
    HIGH = "high"             # Degraded performance, manual intervention needed  
    MEDIUM = "medium"         # Warning condition, monitoring required
    LOW = "low"               # Informational, for tracking trends
    INFO = "info"             # General information


class AlertCategory(str, Enum):
    """Alert categories for routing and filtering"""
    AUTHENTICATION = "authentication"     # Zerodha auth issues
    MARKET_DATA = "market_data"          # Market feed problems
    TRADING = "trading"                  # Order execution issues  
    SYSTEM = "system"                    # Infrastructure problems
    PIPELINE = "pipeline"                # Data flow issues
    PERFORMANCE = "performance"          # Performance degradation


@dataclass
class Alert:
    """Alert message structure"""
    
    title: str
    message: str
    severity: AlertSeverity
    category: AlertCategory
    component: str
    broker_namespace: str = "unknown"
    
    # Alert metadata
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    alert_id: str = field(default_factory=lambda: f"alert_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    correlation_id: Optional[str] = None
    
    # Context information
    details: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Alert behavior
    suppress_duration_minutes: int = 60  # Suppress similar alerts
    retry_attempts: int = 3
    auto_resolve: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary for serialization"""
        return {
            "alert_id": self.alert_id,
            "title": self.title,
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "component": self.component,
            "broker_namespace": self.broker_namespace,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "details": self.details,
            "metrics": self.metrics,
            "suppress_duration_minutes": self.suppress_duration_minutes,
            "auto_resolve": self.auto_resolve
        }


class AlertChannel(ABC):
    """Abstract base class for alert delivery channels"""
    
    @abstractmethod
    async def send_alert(self, alert: Alert) -> bool:
        """
        Send alert through this channel.
        
        Returns:
            True if alert was sent successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def supports_severity(self, severity: AlertSeverity) -> bool:
        """Check if this channel supports the given severity level"""
        pass


class LoggingChannel(AlertChannel):
    """Simple logging-based alert channel"""
    
    def __init__(self, logger_name: str = "alerts"):
        self.logger = get_monitoring_logger_safe(logger_name)
    
    async def send_alert(self, alert: Alert) -> bool:
        """Log alert message"""
        try:
            log_method = {
                AlertSeverity.CRITICAL: self.logger.critical,
                AlertSeverity.HIGH: self.logger.error,
                AlertSeverity.MEDIUM: self.logger.warning,
                AlertSeverity.LOW: self.logger.info,
                AlertSeverity.INFO: self.logger.info
            }.get(alert.severity, self.logger.info)
            
            log_method(
                f"ALERT [{alert.category.value.upper()}]: {alert.title} - {alert.message}",
                extra={
                    "alert_id": alert.alert_id,
                    "component": alert.component,
                    "broker": alert.broker_namespace,
                    "severity": alert.severity.value,
                    "details": alert.details,
                    "metrics": alert.metrics
                }
            )
            return True
        except Exception as e:
            logger.error(f"Failed to log alert: {e}")
            return False
    
    def supports_severity(self, severity: AlertSeverity) -> bool:
        """Supports all severities"""
        return True


class EmailChannel(AlertChannel):
    """Email alert channel (placeholder implementation)"""
    
    def __init__(self, smtp_config: Dict[str, Any], recipients: List[str]):
        self.smtp_config = smtp_config
        self.recipients = recipients
        self.min_severity = AlertSeverity.MEDIUM
    
    async def send_alert(self, alert: Alert) -> bool:
        """Send email alert (placeholder - implement with actual SMTP)"""
        try:
            # Placeholder implementation
            logger.info(f"EMAIL ALERT would be sent to {self.recipients}: {alert.title}")
            
            # Real implementation would:
            # 1. Format email template
            # 2. Connect to SMTP server
            # 3. Send email to recipients
            # 4. Handle bounces and delivery failures
            
            return True
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            return False
    
    def supports_severity(self, severity: AlertSeverity) -> bool:
        """Only send emails for medium+ severity"""
        severity_order = [AlertSeverity.INFO, AlertSeverity.LOW, AlertSeverity.MEDIUM, AlertSeverity.HIGH, AlertSeverity.CRITICAL]
        return severity_order.index(severity) >= severity_order.index(self.min_severity)


class SlackChannel(AlertChannel):
    """Slack alert channel (placeholder implementation)"""
    
    def __init__(self, webhook_url: str, channels: Dict[AlertSeverity, str]):
        self.webhook_url = webhook_url
        self.channels = channels  # Map severity to channel
    
    async def send_alert(self, alert: Alert) -> bool:
        """Send Slack alert (placeholder - implement with actual webhook)"""
        try:
            channel = self.channels.get(alert.severity, "#alerts")
            
            # Placeholder implementation
            logger.info(f"SLACK ALERT would be sent to {channel}: {alert.title}")
            
            # Real implementation would:
            # 1. Format Slack message with blocks/attachments
            # 2. Send HTTP POST to webhook URL
            # 3. Handle rate limiting and retries
            
            return True
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False
    
    def supports_severity(self, severity: AlertSeverity) -> bool:
        """Supports all severities"""
        return True


class PagerDutyChannel(AlertChannel):
    """PagerDuty alert channel (placeholder implementation)"""
    
    def __init__(self, integration_key: str, routing_key: str):
        self.integration_key = integration_key
        self.routing_key = routing_key
    
    async def send_alert(self, alert: Alert) -> bool:
        """Send PagerDuty alert (placeholder - implement with Events API)"""
        try:
            # Only send critical alerts to PagerDuty
            if alert.severity != AlertSeverity.CRITICAL:
                return True
            
            # Placeholder implementation
            logger.critical(f"PAGERDUTY ALERT would be triggered: {alert.title}")
            
            # Real implementation would:
            # 1. Use PagerDuty Events API v2
            # 2. Send trigger/acknowledge/resolve events
            # 3. Handle deduplication keys
            
            return True
        except Exception as e:
            logger.error(f"Failed to send PagerDuty alert: {e}")
            return False
    
    def supports_severity(self, severity: AlertSeverity) -> bool:
        """Only send critical alerts to PagerDuty"""
        return severity == AlertSeverity.CRITICAL


class AlertManager:
    """Central alert management and routing"""
    
    def __init__(self, settings=None):
        self.settings = settings
        self.channels: List[AlertChannel] = []
        self.alert_history: List[Alert] = []
        self.suppressed_alerts: Dict[str, datetime] = {}
        self.alert_hooks: List[Callable[[Alert], None]] = []
        
        # Default to logging channel
        self._setup_default_channels()
        
        # Alert statistics
        self._stats = {
            "alerts_sent": 0,
            "alerts_suppressed": 0,
            "alerts_failed": 0,
            "last_alert_time": None
        }
    
    def _setup_default_channels(self):
        """Setup default alert channels"""
        # Always have logging channel
        self.add_channel(LoggingChannel("alpha_panda.alerts"))
    
    def add_channel(self, channel: AlertChannel):
        """Add an alert delivery channel"""
        self.channels.append(channel)
        logger.info(f"Added alert channel: {type(channel).__name__}")
    
    def add_alert_hook(self, hook: Callable[[Alert], None]):
        """Add custom alert processing hook"""
        self.alert_hooks.append(hook)
    
    async def send_alert(
        self, 
        title: str,
        message: str,
        severity: AlertSeverity,
        category: AlertCategory,
        component: str,
        broker_namespace: str = "unknown",
        **kwargs
    ) -> bool:
        """
        Send alert through all appropriate channels.
        
        Returns:
            True if alert was sent through at least one channel
        """
        alert = Alert(
            title=title,
            message=message,
            severity=severity,
            category=category,
            component=component,
            broker_namespace=broker_namespace,
            **kwargs
        )
        
        return await self.send_alert_object(alert)
    
    async def send_alert_object(self, alert: Alert) -> bool:
        """Send alert object through all appropriate channels"""
        
        # Check for suppression
        if self._is_suppressed(alert):
            self._stats["alerts_suppressed"] += 1
            logger.debug(f"Alert suppressed: {alert.alert_id}")
            return False
        
        # Execute custom hooks
        for hook in self.alert_hooks:
            try:
                hook(alert)
            except Exception as e:
                logger.error(f"Alert hook failed: {e}")
        
        # Send through all supporting channels
        success_count = 0
        for channel in self.channels:
            if channel.supports_severity(alert.severity):
                try:
                    if await channel.send_alert(alert):
                        success_count += 1
                except Exception as e:
                    logger.error(f"Alert channel {type(channel).__name__} failed: {e}")
        
        # Update statistics and history
        if success_count > 0:
            self._stats["alerts_sent"] += 1
            self._stats["last_alert_time"] = alert.timestamp.isoformat()
            self.alert_history.append(alert)
            
            # Add to suppression cache
            self._add_to_suppression_cache(alert)
            
            # Limit history size
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-1000:]
                
            logger.info(f"Alert sent through {success_count} channels: {alert.alert_id}")
            return True
        else:
            self._stats["alerts_failed"] += 1
            logger.error(f"Failed to send alert through any channel: {alert.alert_id}")
            return False
    
    def _is_suppressed(self, alert: Alert) -> bool:
        """Check if alert should be suppressed"""
        suppression_key = f"{alert.component}:{alert.category.value}:{alert.title}"
        
        if suppression_key in self.suppressed_alerts:
            last_alert_time = self.suppressed_alerts[suppression_key]
            time_diff = (alert.timestamp - last_alert_time).total_seconds() / 60
            return time_diff < alert.suppress_duration_minutes
        
        return False
    
    def _add_to_suppression_cache(self, alert: Alert):
        """Add alert to suppression cache"""
        suppression_key = f"{alert.component}:{alert.category.value}:{alert.title}"
        self.suppressed_alerts[suppression_key] = alert.timestamp
    
    def get_recent_alerts(self, minutes: int = 60) -> List[Alert]:
        """Get alerts from the last N minutes"""
        cutoff_time = datetime.now(timezone.utc).timestamp() - (minutes * 60)
        return [
            alert for alert in self.alert_history 
            if alert.timestamp.timestamp() > cutoff_time
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get alerting statistics"""
        return {
            **self._stats,
            "active_channels": len(self.channels),
            "alert_hooks": len(self.alert_hooks),
            "suppressed_keys": len(self.suppressed_alerts),
            "history_size": len(self.alert_history)
        }
    
    # Convenience methods for common alert types
    async def critical_alert(self, title: str, message: str, component: str, **kwargs):
        """Send critical alert"""
        return await self.send_alert(
            title=title,
            message=message,
            severity=AlertSeverity.CRITICAL,
            category=kwargs.get('category', AlertCategory.SYSTEM),
            component=component,
            **kwargs
        )
    
    async def authentication_alert(self, title: str, message: str, component: str, **kwargs):
        """Send authentication-related alert"""
        return await self.send_alert(
            title=title,
            message=message,
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.AUTHENTICATION,
            component=component,
            **kwargs
        )
    
    async def performance_alert(self, title: str, message: str, component: str, **kwargs):
        """Send performance-related alert"""
        return await self.send_alert(
            title=title,
            message=message,
            severity=kwargs.get('severity', AlertSeverity.MEDIUM),
            category=AlertCategory.PERFORMANCE,
            component=component,
            **kwargs
        )


# Global alert manager instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager(settings=None) -> AlertManager:
    """Get or create global alert manager instance"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager(settings)
    return _alert_manager


def configure_alerting(settings) -> AlertManager:
    """Configure alerting system with settings"""
    global _alert_manager
    _alert_manager = AlertManager(settings)
    
    # Setup channels based on settings
    if hasattr(settings, 'alerting') and settings.alerting:
        alerting_config = settings.alerting
        
        # Email channel
        if alerting_config.get('email', {}).get('enabled', False):
            email_config = alerting_config['email']
            email_channel = EmailChannel(
                smtp_config=email_config.get('smtp', {}),
                recipients=email_config.get('recipients', [])
            )
            _alert_manager.add_channel(email_channel)
        
        # Slack channel  
        if alerting_config.get('slack', {}).get('enabled', False):
            slack_config = alerting_config['slack']
            slack_channel = SlackChannel(
                webhook_url=slack_config.get('webhook_url'),
                channels=slack_config.get('channels', {})
            )
            _alert_manager.add_channel(slack_channel)
        
        # PagerDuty channel
        if alerting_config.get('pagerduty', {}).get('enabled', False):
            pd_config = alerting_config['pagerduty']
            pd_channel = PagerDutyChannel(
                integration_key=pd_config.get('integration_key'),
                routing_key=pd_config.get('routing_key')
            )
            _alert_manager.add_channel(pd_channel)
    
    return _alert_manager


# Convenience functions for common alerting patterns
async def send_critical_alert(title: str, message: str, component: str, **kwargs):
    """Send critical alert using global manager"""
    manager = get_alert_manager()
    return await manager.critical_alert(title, message, component, **kwargs)


async def send_auth_failure_alert(component: str, error: str, **kwargs):
    """Send authentication failure alert"""
    manager = get_alert_manager()
    return await manager.authentication_alert(
        title="Authentication Failure",
        message=f"Authentication failed in {component}: {error}",
        component=component,
        **kwargs
    )


async def send_performance_degradation_alert(component: str, metric: str, value: float, threshold: float, **kwargs):
    """Send performance degradation alert"""
    manager = get_alert_manager()
    return await manager.performance_alert(
        title="Performance Degradation",
        message=f"{component}: {metric} is {value:.2f} (threshold: {threshold:.2f})",
        component=component,
        details={"metric": metric, "current_value": value, "threshold": threshold},
        **kwargs
    )
