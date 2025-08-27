"""
Production Alerting System for AlphaPT
Provides advanced alerting capabilities with smart routing and escalation.
"""

import asyncio
import json
import logging
import smtplib
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.multipart import MimeMultipart
from email.mime.text import MimeText
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import aiohttp
import redis.asyncio as redis

from core.config.settings import get_settings


class AlertSeverity(Enum):
    """Alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


class AlertComponent(Enum):
    """System components for alert classification"""

    MARKET_DATA = "market_data"
    TRADING = "trading"
    RISK_MANAGEMENT = "risk_management"
    STRATEGY = "strategy"
    DATABASE = "database"
    EVENT_SYSTEM = "event_system"
    SYSTEM = "system"
    BUSINESS = "business"


@dataclass
class Alert:
    """Alert data structure"""

    alert_id: str
    name: str
    component: AlertComponent
    severity: AlertSeverity
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    escalation_level: int = 0
    last_notification: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary"""
        return {
            "alert_id": self.alert_id,
            "name": self.name,
            "component": self.component.value,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "escalation_level": self.escalation_level,
            "last_notification": self.last_notification.isoformat() if self.last_notification else None,
        }


@dataclass
class AlertRule:
    """Alert rule configuration"""

    name: str
    condition: Callable[[Dict[str, Any]], bool]
    severity: AlertSeverity
    component: AlertComponent
    cooldown_minutes: int = 5
    escalation_minutes: int = 15
    max_escalations: int = 3
    enabled: bool = True


class NotificationChannel:
    """Base class for notification channels"""

    async def send(self, alert: Alert) -> bool:
        """Send notification for alert"""
        raise NotImplementedError


class SlackNotificationChannel(NotificationChannel):
    """Slack notification channel"""

    def __init__(self, webhook_url: str, channel_mapping: Dict[AlertComponent, str]):
        self.webhook_url = webhook_url
        self.channel_mapping = channel_mapping

    async def send(self, alert: Alert) -> bool:
        """Send Slack notification"""
        try:
            channel = self.channel_mapping.get(alert.component, "#alphapt-monitoring")

            # Format message based on severity
            emoji = {
                AlertSeverity.INFO: "ℹ️",
                AlertSeverity.WARNING: "⚠️",
                AlertSeverity.CRITICAL: "🚨",
                AlertSeverity.FATAL: "💀",
            }

            message = {
                "channel": channel,
                "text": f"{emoji[alert.severity]} AlphaPT Alert",
                "attachments": [
                    {
                        "color": self._get_color(alert.severity),
                        "fields": [
                            {"title": "Alert", "value": alert.name, "short": True},
                            {"title": "Component", "value": alert.component.value, "short": True},
                            {"title": "Severity", "value": alert.severity.value.upper(), "short": True},
                            {
                                "title": "Time",
                                "value": alert.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
                                "short": True,
                            },
                            {"title": "Message", "value": alert.message, "short": False},
                        ],
                        "footer": f"Alert ID: {alert.alert_id}",
                    }
                ],
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=message) as response:
                    return response.status == 200

        except Exception as e:
            logging.error(f"Failed to send Slack notification: {e}")
            return False

    def _get_color(self, severity: AlertSeverity) -> str:
        """Get color based on severity"""
        colors = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ff9500",
            AlertSeverity.CRITICAL: "#ff0000",
            AlertSeverity.FATAL: "#8b0000",
        }
        return colors[severity]


class EmailNotificationChannel(NotificationChannel):
    """Email notification channel"""

    def __init__(self, smtp_host: str, smtp_port: int, username: str, password: str):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password

    async def send(self, alert: Alert) -> bool:
        """Send email notification"""
        try:
            # Determine recipients based on severity and component
            recipients = self._get_recipients(alert)

            for recipient in recipients:
                msg = MimeMultipart()
                msg["From"] = self.username
                msg["To"] = recipient
                msg["Subject"] = f"AlphaPT Alert: {alert.name} ({alert.severity.value.upper()})"

                body = self._format_email_body(alert)
                msg.attach(MimeText(body, "html"))

                # Send email in executor to avoid blocking
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._send_email, msg, recipient)

            return True

        except Exception as e:
            logging.error(f"Failed to send email notification: {e}")
            return False

    def _send_email(self, msg: MimeMultipart, recipient: str):
        """Send email synchronously"""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)

    def _get_recipients(self, alert: Alert) -> List[str]:
        """Get email recipients based on alert properties"""
        # Default recipients
        recipients = ["trading-team@company.com"]

        # Add specific recipients based on component and severity
        if alert.component == AlertComponent.RISK_MANAGEMENT:
            recipients.append("risk-team@company.com")

        if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.FATAL]:
            recipients.extend(["management@company.com", "oncall@company.com"])

        return list(set(recipients))  # Remove duplicates

    def _format_email_body(self, alert: Alert) -> str:
        """Format email body"""
        return f"""
        <html>
        <body>
            <h2>AlphaPT Trading System Alert</h2>
            
            <table border="1" cellpadding="5" cellspacing="0">
                <tr><td><strong>Alert Name:</strong></td><td>{alert.name}</td></tr>
                <tr><td><strong>Component:</strong></td><td>{alert.component.value}</td></tr>
                <tr><td><strong>Severity:</strong></td><td style="color: red;">{alert.severity.value.upper()}</td></tr>
                <tr><td><strong>Time:</strong></td><td>{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</td></tr>
                <tr><td><strong>Message:</strong></td><td>{alert.message}</td></tr>
                <tr><td><strong>Alert ID:</strong></td><td>{alert.alert_id}</td></tr>
            </table>
            
            <h3>Additional Details:</h3>
            <pre>{json.dumps(alert.details, indent=2)}</pre>
            
            <p><em>This is an automated alert from the AlphaPT trading system.</em></p>
        </body>
        </html>
        """


class ProductionAlertManager:
    """
    Production-grade alert manager with smart routing and escalation
    """

    def __init__(self):
        self.settings = get_settings()
        self.logger = logging.getLogger(__name__)

        # Alert storage
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_rules: List[AlertRule] = []
        self.notification_channels: List[NotificationChannel] = []

        # Redis for persistence
        self.redis_client: Optional[redis.Redis] = None

        # Statistics
        self.stats = {"alerts_triggered": 0, "alerts_resolved": 0, "notifications_sent": 0, "escalations": 0}

        # Background task
        self._monitoring_task: Optional[asyncio.Task] = None

    async def initialize(self):
        """Initialize alert manager"""
        try:
            # Setup Redis connection
            if hasattr(self.settings, "redis_url"):
                self.redis_client = redis.from_url(self.settings.redis_url)
                await self.redis_client.ping()
                self.logger.info("✅ Alert manager Redis connection established")

            # Setup notification channels
            await self._setup_notification_channels()

            # Register default alert rules
            self._register_default_rules()

            # Start monitoring task
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())

            self.logger.info("✅ Production alert manager initialized")

        except Exception as e:
            self.logger.error(f"❌ Failed to initialize alert manager: {e}")
            raise

    async def _setup_notification_channels(self):
        """Setup notification channels"""
        try:
            # Slack notifications
            if hasattr(self.settings, "slack_webhook_url"):
                channel_mapping = {
                    AlertComponent.TRADING: "#alphapt-trading",
                    AlertComponent.RISK_MANAGEMENT: "#alphapt-risk",
                    AlertComponent.MARKET_DATA: "#alphapt-data",
                    AlertComponent.STRATEGY: "#alphapt-strategies",
                }
                slack_channel = SlackNotificationChannel(self.settings.slack_webhook_url, channel_mapping)
                self.notification_channels.append(slack_channel)

            # Email notifications
            if hasattr(self.settings, "smtp_host"):
                email_channel = EmailNotificationChannel(
                    self.settings.smtp_host,
                    self.settings.smtp_port,
                    self.settings.smtp_username,
                    self.settings.smtp_password,
                )
                self.notification_channels.append(email_channel)

            self.logger.info(f"✅ Configured {len(self.notification_channels)} notification channels")

        except Exception as e:
            self.logger.error(f"❌ Failed to setup notification channels: {e}")

    def _register_default_rules(self):
        """Register default alert rules"""
        # High latency rule
        self.register_rule(
            AlertRule(
                name="HighMarketDataLatency",
                condition=lambda metrics: metrics.get("market_data_latency", 0) > 0.1,
                severity=AlertSeverity.WARNING,
                component=AlertComponent.MARKET_DATA,
                cooldown_minutes=2,
            )
        )

        # Low throughput rule
        self.register_rule(
            AlertRule(
                name="LowMarketDataThroughput",
                condition=lambda metrics: metrics.get("market_data_tps", 0) < 500,
                severity=AlertSeverity.CRITICAL,
                component=AlertComponent.MARKET_DATA,
                cooldown_minutes=1,
            )
        )

        # Risk exposure rule
        self.register_rule(
            AlertRule(
                name="HighRiskExposure",
                condition=lambda metrics: metrics.get("risk_exposure_ratio", 0) > 0.8,
                severity=AlertSeverity.CRITICAL,
                component=AlertComponent.RISK_MANAGEMENT,
                cooldown_minutes=0,  # Immediate alerts for risk
            )
        )

        # Database connection rule
        self.register_rule(
            AlertRule(
                name="DatabaseConnectionIssue",
                condition=lambda metrics: metrics.get("db_connection_ratio", 0) > 0.9,
                severity=AlertSeverity.CRITICAL,
                component=AlertComponent.DATABASE,
                cooldown_minutes=1,
            )
        )

        self.logger.info(f"✅ Registered {len(self.alert_rules)} default alert rules")

    def register_rule(self, rule: AlertRule):
        """Register new alert rule"""
        self.alert_rules.append(rule)
        self.logger.info(f"📋 Registered alert rule: {rule.name}")

    async def check_metrics(self, metrics: Dict[str, Any]):
        """Check metrics against alert rules"""
        try:
            for rule in self.alert_rules:
                if not rule.enabled:
                    continue

                # Check if condition is met
                if rule.condition(metrics):
                    await self._trigger_alert(rule, metrics)

        except Exception as e:
            self.logger.error(f"❌ Error checking metrics: {e}")

    async def _trigger_alert(self, rule: AlertRule, metrics: Dict[str, Any]):
        """Trigger alert if conditions are met"""
        alert_id = f"{rule.component.value}_{rule.name}_{int(time.time())}"

        # Check if we have a recent alert with cooldown
        existing_alert = self._find_existing_alert(rule.name, rule.component)
        if existing_alert and not self._is_cooldown_expired(existing_alert, rule.cooldown_minutes):
            return

        # Create new alert
        alert = Alert(
            alert_id=alert_id,
            name=rule.name,
            component=rule.component,
            severity=rule.severity,
            message=f"{rule.name} triggered",
            details=metrics,
        )

        self.active_alerts[alert_id] = alert
        self.stats["alerts_triggered"] += 1

        # Send notifications
        await self._send_notifications(alert)

        # Persist alert
        if self.redis_client:
            await self.redis_client.setex(f"alert:{alert_id}", 3600, json.dumps(alert.to_dict()))  # 1 hour TTL

        self.logger.warning(f"🚨 Alert triggered: {alert.name} ({alert.severity.value})")

    def _find_existing_alert(self, name: str, component: AlertComponent) -> Optional[Alert]:
        """Find existing alert with same name and component"""
        for alert in self.active_alerts.values():
            if alert.name == name and alert.component == component and not alert.resolved:
                return alert
        return None

    def _is_cooldown_expired(self, alert: Alert, cooldown_minutes: int) -> bool:
        """Check if alert cooldown has expired"""
        if alert.last_notification is None:
            return True

        cooldown_delta = timedelta(minutes=cooldown_minutes)
        return datetime.utcnow() - alert.last_notification > cooldown_delta

    async def _send_notifications(self, alert: Alert):
        """Send notifications for alert"""
        try:
            notification_tasks = []

            for channel in self.notification_channels:
                task = asyncio.create_task(channel.send(alert))
                notification_tasks.append(task)

            # Wait for all notifications
            results = await asyncio.gather(*notification_tasks, return_exceptions=True)

            # Count successful notifications
            successful = sum(1 for result in results if result is True)
            self.stats["notifications_sent"] += successful

            # Update alert
            alert.last_notification = datetime.utcnow()

            self.logger.info(f"📢 Sent {successful}/{len(notification_tasks)} notifications for {alert.name}")

        except Exception as e:
            self.logger.error(f"❌ Failed to send notifications: {e}")

    async def resolve_alert(self, alert_id: str):
        """Resolve an active alert"""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.resolved = True
            self.stats["alerts_resolved"] += 1

            self.logger.info(f"✅ Resolved alert: {alert.name}")

            # Remove from active alerts
            del self.active_alerts[alert_id]

    async def _monitoring_loop(self):
        """Background monitoring loop for escalation"""
        while True:
            try:
                await self._check_escalations()
                await asyncio.sleep(60)  # Check every minute

            except Exception as e:
                self.logger.error(f"❌ Error in monitoring loop: {e}")
                await asyncio.sleep(60)

    async def _check_escalations(self):
        """Check for alerts that need escalation"""
        current_time = datetime.utcnow()

        for alert in list(self.active_alerts.values()):
            if alert.resolved:
                continue

            # Find the rule for this alert
            rule = next((r for r in self.alert_rules if r.name == alert.name), None)
            if not rule:
                continue

            # Check if escalation is needed
            escalation_delta = timedelta(minutes=rule.escalation_minutes)
            time_since_last = current_time - (alert.last_notification or alert.timestamp)

            if time_since_last > escalation_delta and alert.escalation_level < rule.max_escalations:

                await self._escalate_alert(alert)

    async def _escalate_alert(self, alert: Alert):
        """Escalate alert to higher severity"""
        alert.escalation_level += 1
        self.stats["escalations"] += 1

        # Increase severity
        if alert.severity == AlertSeverity.WARNING:
            alert.severity = AlertSeverity.CRITICAL
        elif alert.severity == AlertSeverity.CRITICAL:
            alert.severity = AlertSeverity.FATAL

        alert.message = f"ESCALATED: {alert.message} (Level {alert.escalation_level})"

        # Send escalated notifications
        await self._send_notifications(alert)

        self.logger.warning(f"⬆️ Escalated alert: {alert.name} to level {alert.escalation_level}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get alert manager statistics"""
        return {
            **self.stats,
            "active_alerts": len(self.active_alerts),
            "alert_rules": len(self.alert_rules),
            "notification_channels": len(self.notification_channels),
        }

    async def cleanup(self):
        """Cleanup resources"""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        if self.redis_client:
            await self.redis_client.close()

        self.logger.info("🧹 Production alert manager cleanup completed")


# Global instance
alert_manager = ProductionAlertManager()
