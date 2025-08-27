"""Alert management system for AlphaPT."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from core.utils.exceptions import AlphaPTException


class AlertSeverity(Enum):
    """Alert severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertChannel(Enum):
    """Alert delivery channels."""

    LOG = "log"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SLACK = "slack"


@dataclass
class Alert:
    """Alert data structure."""

    id: str
    title: str
    message: str
    severity: AlertSeverity
    component: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertRule:
    """Alert rule configuration."""

    id: str
    name: str
    condition: Callable[[Dict[str, Any]], bool]
    severity: AlertSeverity
    channels: List[AlertChannel]
    cooldown_minutes: int = 5
    enabled: bool = True


class AlertManager:
    """Manages alerts and notifications for the trading system."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.alerts: Dict[str, Alert] = {}
        self.rules: Dict[str, AlertRule] = {}
        self.active_cooldowns: Dict[str, datetime] = {}
        self.alert_handlers: Dict[AlertChannel, Callable] = {}
        self._setup_default_handlers()

    def _setup_default_handlers(self):
        """Setup default alert handlers."""
        self.alert_handlers[AlertChannel.LOG] = self._log_alert

    async def initialize(self) -> bool:
        """Initialize the alert manager."""
        try:
            self.logger.info("🚨 Initializing Alert Manager")
            self._setup_default_rules()
            self.logger.info("✅ Alert Manager initialized successfully")
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Alert Manager: {e}")
            return False

    def _setup_default_rules(self):
        """Setup default alert rules."""
        # High memory usage alert
        self.add_rule(
            AlertRule(
                id="high_memory_usage",
                name="High Memory Usage",
                condition=lambda metrics: metrics.get("memory_usage_percent", 0) > 85,
                severity=AlertSeverity.HIGH,
                channels=[AlertChannel.LOG],
            )
        )

        # Database connection failure
        self.add_rule(
            AlertRule(
                id="database_connection_failure",
                name="Database Connection Failure",
                condition=lambda metrics: not metrics.get("database_healthy", True),
                severity=AlertSeverity.CRITICAL,
                channels=[AlertChannel.LOG],
            )
        )

        # High latency alert
        self.add_rule(
            AlertRule(
                id="high_latency",
                name="High Processing Latency",
                condition=lambda metrics: metrics.get("avg_processing_latency_ms", 0) > 1000,
                severity=AlertSeverity.MEDIUM,
                channels=[AlertChannel.LOG],
            )
        )

        # Market feed disconnection
        self.add_rule(
            AlertRule(
                id="market_feed_disconnected",
                name="Market Feed Disconnected",
                condition=lambda metrics: not metrics.get("market_feed_connected", True),
                severity=AlertSeverity.CRITICAL,
                channels=[AlertChannel.LOG],
            )
        )

    def add_rule(self, rule: AlertRule):
        """Add an alert rule."""
        self.rules[rule.id] = rule
        self.logger.info(f"Added alert rule: {rule.name}")

    def remove_rule(self, rule_id: str):
        """Remove an alert rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            self.logger.info(f"Removed alert rule: {rule_id}")

    async def check_metrics(self, metrics: Dict[str, Any]):
        """Check metrics against alert rules and trigger alerts if needed."""
        for rule_id, rule in self.rules.items():
            if not rule.enabled:
                continue

            # Check cooldown
            if rule_id in self.active_cooldowns:
                if datetime.utcnow() < self.active_cooldowns[rule_id]:
                    continue

            try:
                if rule.condition(metrics):
                    await self._trigger_alert(rule, metrics)
            except Exception as e:
                self.logger.error(f"Error checking rule {rule_id}: {e}")

    async def _trigger_alert(self, rule: AlertRule, metrics: Dict[str, Any]):
        """Trigger an alert."""
        alert_id = f"{rule.id}_{int(datetime.utcnow().timestamp())}"

        alert = Alert(
            id=alert_id,
            title=rule.name,
            message=f"Alert triggered: {rule.name}",
            severity=rule.severity,
            component="system",
            metadata={"metrics": metrics, "rule_id": rule.id},
        )

        self.alerts[alert_id] = alert

        # Send notifications
        for channel in rule.channels:
            if channel in self.alert_handlers:
                try:
                    await self.alert_handlers[channel](alert)
                except Exception as e:
                    self.logger.error(f"Failed to send alert via {channel}: {e}")

        # Set cooldown
        cooldown_until = datetime.utcnow() + timedelta(minutes=rule.cooldown_minutes)
        self.active_cooldowns[rule.id] = cooldown_until

        self.logger.warning(f"🚨 Alert triggered: {alert.title}")

    async def _log_alert(self, alert: Alert):
        """Log alert handler."""
        severity_emoji = {
            AlertSeverity.LOW: "ℹ️",
            AlertSeverity.MEDIUM: "⚠️",
            AlertSeverity.HIGH: "🔴",
            AlertSeverity.CRITICAL: "🚨",
        }

        emoji = severity_emoji.get(alert.severity, "🔔")
        self.logger.warning(f"{emoji} ALERT [{alert.severity.value.upper()}] {alert.title}: {alert.message}")

    async def resolve_alert(self, alert_id: str):
        """Resolve an alert."""
        if alert_id in self.alerts:
            self.alerts[alert_id].resolved = True
            self.logger.info(f"✅ Alert resolved: {alert_id}")

    def get_active_alerts(self) -> List[Alert]:
        """Get all active (unresolved) alerts."""
        return [alert for alert in self.alerts.values() if not alert.resolved]

    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """Get alert history for the specified time period."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return [alert for alert in self.alerts.values() if alert.timestamp >= cutoff]

    async def cleanup_old_alerts(self, days: int = 7):
        """Clean up old alerts."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        old_alerts = [alert_id for alert_id, alert in self.alerts.items() if alert.timestamp < cutoff]

        for alert_id in old_alerts:
            del self.alerts[alert_id]

        if old_alerts:
            self.logger.info(f"🧹 Cleaned up {len(old_alerts)} old alerts")

    def register_handler(self, channel: AlertChannel, handler: Callable):
        """Register a custom alert handler."""
        self.alert_handlers[channel] = handler
        self.logger.info(f"Registered handler for {channel}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get alert statistics."""
        active_alerts = self.get_active_alerts()
        total_alerts = len(self.alerts)

        severity_counts = {}
        for severity in AlertSeverity:
            severity_counts[severity.value] = len([alert for alert in active_alerts if alert.severity == severity])

        return {
            "total_alerts": total_alerts,
            "active_alerts": len(active_alerts),
            "resolved_alerts": total_alerts - len(active_alerts),
            "active_rules": len([rule for rule in self.rules.values() if rule.enabled]),
            "severity_breakdown": severity_counts,
            "active_cooldowns": len(self.active_cooldowns),
        }

    async def shutdown(self):
        """Shutdown the alert manager."""
        self.logger.info("🔄 Shutting down Alert Manager")
        await self.cleanup_old_alerts()
        self.logger.info("✅ Alert Manager shutdown complete")
