"""Data quality monitoring and validation system.

This module provides comprehensive data quality monitoring for:
- Market tick data validation
- Data completeness checks
- Anomaly detection
- Real-time quality metrics
- Alerting on quality issues
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque

from core.config.settings import Settings
from core.events import EventBusCore, get_event_publisher, subscriber, SystemEvent, EventType
from core.events.event_types import EventFactory, MarketDataEvent
from core.logging.logger import get_logger
from core.utils.exceptions import ValidationError


class QualityLevel(str, Enum):
    """Data quality levels."""
    EXCELLENT = "excellent"  # >98% quality
    GOOD = "good"           # 95-98% quality
    FAIR = "fair"           # 90-95% quality
    POOR = "poor"           # 85-90% quality
    CRITICAL = "critical"   # <85% quality


class IssueType(str, Enum):
    """Data quality issue types."""
    MISSING_DATA = "missing_data"
    INVALID_PRICE = "invalid_price"
    STALE_DATA = "stale_data"
    DUPLICATE_DATA = "duplicate_data"
    INVALID_VOLUME = "invalid_volume"
    MISSING_DEPTH = "missing_depth"
    TIMESTAMP_ISSUE = "timestamp_issue"
    ENCODING_ERROR = "encoding_error"


@dataclass
class QualityIssue:
    """Data quality issue record."""
    issue_type: IssueType
    instrument_token: int
    timestamp: datetime
    description: str
    severity: str
    field: Optional[str] = None
    value: Optional[Any] = None
    expected_value: Optional[Any] = None


@dataclass
class InstrumentQualityMetrics:
    """Quality metrics for individual instrument."""
    instrument_token: int
    total_ticks: int = 0
    valid_ticks: int = 0
    invalid_ticks: int = 0
    missing_data_count: int = 0
    last_tick_time: Optional[datetime] = None
    issues: List[QualityIssue] = field(default_factory=list)
    quality_score: float = 100.0
    quality_level: QualityLevel = QualityLevel.EXCELLENT
    
    def calculate_quality_score(self):
        """Calculate quality score as percentage."""
        if self.total_ticks == 0:
            self.quality_score = 100.0
        else:
            self.quality_score = (self.valid_ticks / self.total_ticks) * 100
        
        # Determine quality level
        if self.quality_score >= 98:
            self.quality_level = QualityLevel.EXCELLENT
        elif self.quality_score >= 95:
            self.quality_level = QualityLevel.GOOD
        elif self.quality_score >= 90:
            self.quality_level = QualityLevel.FAIR
        elif self.quality_score >= 85:
            self.quality_level = QualityLevel.POOR
        else:
            self.quality_level = QualityLevel.CRITICAL


@dataclass
class SystemQualityMetrics:
    """System-wide quality metrics."""
    total_instruments: int = 0
    total_ticks_processed: int = 0
    total_valid_ticks: int = 0
    total_issues: int = 0
    overall_quality_score: float = 100.0
    quality_distribution: Dict[QualityLevel, int] = field(default_factory=dict)
    issue_distribution: Dict[IssueType, int] = field(default_factory=dict)
    last_update: Optional[datetime] = None


# Global data quality monitor instance for decorator handlers
_quality_monitor_instance: Optional['DataQualityMonitor'] = None


@subscriber.on_event("market.tick.*", durable_name="quality-monitor-ticks")
async def handle_market_tick_quality(event: MarketDataEvent) -> None:
    """Handle market tick events for quality monitoring.
    
    This decorator-based handler routes market data events to the quality monitor.
    """
    global _quality_monitor_instance
    if _quality_monitor_instance:
        event_data = {
            'instrument_token': event.instrument_token,
            'last_price': float(event.last_price),
            'ohlc': event.ohlc,
            'volume': event.volume,
            'timestamp': event.timestamp,
            'correlation_id': event.correlation_id,
            'exchange': event.exchange,
            'tradingsymbol': event.tradingsymbol
        }
        await _quality_monitor_instance._handle_market_data_event(event_data)


@subscriber.on_event("market.depth.*", durable_name="quality-monitor-depth")
async def handle_market_depth_quality(event: MarketDataEvent) -> None:
    """Handle market depth events for quality monitoring."""
    global _quality_monitor_instance
    if _quality_monitor_instance and hasattr(event, 'depth') and event.depth:
        event_data = {
            'instrument_token': event.instrument_token,
            'depth': event.depth,
            'timestamp': event.timestamp,
            'correlation_id': event.correlation_id,
            'exchange': event.exchange,
            'tradingsymbol': event.tradingsymbol
        }
        await _quality_monitor_instance._handle_market_data_event(event_data)


class DataQualityMonitor:
    """Comprehensive data quality monitoring system."""
    
    def __init__(self, settings: Settings, event_bus: EventBusCore):
        """Initialize data quality monitor.
        
        Args:
            settings: Application settings
            event_bus: Event bus for monitoring events
        """
        self.settings = settings
        self.event_bus = event_bus
        self.event_publisher = get_event_publisher(settings) if event_bus else None
        self.logger = get_logger("data_quality_monitor")
        
        # Quality tracking
        self.instrument_metrics: Dict[int, InstrumentQualityMetrics] = {}
        self.system_metrics = SystemQualityMetrics()
        
        # Monitoring configuration
        self.validation_rules = self._initialize_validation_rules()
        self.quality_thresholds = {
            'min_price': 0.01,
            'max_price': 100000.0,
            'max_volume': 10000000,
            'max_tick_age_seconds': 300,  # 5 minutes
            'min_quality_score': 90.0,
        }
        
        # Issue tracking
        self.recent_issues: deque = deque(maxlen=1000)
        self.critical_alerts: Set[str] = set()
        
        # Performance tracking
        self.validation_times: deque = deque(maxlen=100)
        
        # Monitoring state
        self.is_running = False
        self._monitoring_task: Optional[asyncio.Task] = None
        
    def _initialize_validation_rules(self) -> Dict[str, Any]:
        """Initialize validation rules for market data."""
        return {
            'required_fields': [
                'instrument_token', 'last_price', 'timestamp', 'exchange'
            ],
            'numeric_fields': [
                'last_price', 'last_quantity', 'volume', 'average_price',
                'buy_quantity', 'sell_quantity', 'oi'
            ],
            'price_fields': [
                'last_price', 'average_price', 'open', 'high', 'low', 'close'
            ],
            'volume_fields': [
                'last_quantity', 'volume', 'buy_quantity', 'sell_quantity'
            ],
            'timestamp_fields': [
                'timestamp', 'exchange_timestamp'
            ]
        }
    
    async def start(self) -> bool:
        """Start the data quality monitoring system.
        
        Returns:
            True if started successfully
        """
        try:
            self.logger.info("Starting data quality monitoring system...")
            
            # Set global instance for decorator handlers
            global _quality_monitor_instance
            _quality_monitor_instance = self
            self.logger.info("✅ Quality monitor registered for event subscriptions")
            
            # Start monitoring task
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            self.is_running = True
            self.logger.info("✅ Data quality monitoring started")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start quality monitoring: {e}")
            return False
    
    async def stop(self) -> None:
        """Stop the data quality monitoring system."""
        try:
            self.logger.info("Stopping data quality monitoring...")
            
            self.is_running = False
            
            # Cancel monitoring task
            if self._monitoring_task and not self._monitoring_task.done():
                self._monitoring_task.cancel()
                try:
                    await self._monitoring_task
                except asyncio.CancelledError:
                    pass
            
            # Clear global instance
            global _quality_monitor_instance
            _quality_monitor_instance = None
            self.logger.info("Quality monitor unregistered from event subscriptions")
            
            self.logger.info("✅ Data quality monitoring stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping quality monitoring: {e}")
    
    
    async def _handle_market_data_event(self, event_data: Dict[str, Any]) -> None:
        """Handle market data event for quality validation.
        
        Args:
            event_data: Market data event data
        """
        try:
            tick_data = event_data.get('data', {})
            if not tick_data:
                return
            
            # Validate tick data quality
            await self.validate_tick_data(tick_data)
            
        except Exception as e:
            self.logger.error(f"Error handling market data event for quality: {e}")
    
    async def validate_tick_data(self, tick_data: Dict[str, Any]) -> Tuple[bool, List[QualityIssue]]:
        """Validate market tick data quality.
        
        Args:
            tick_data: Market tick data dictionary
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        start_time = datetime.utcnow()
        issues = []
        
        try:
            instrument_token = tick_data.get('instrument_token', 0)
            
            # Get or create instrument metrics
            if instrument_token not in self.instrument_metrics:
                self.instrument_metrics[instrument_token] = InstrumentQualityMetrics(
                    instrument_token=instrument_token
                )
            
            metrics = self.instrument_metrics[instrument_token]
            metrics.total_ticks += 1
            
            # Validate required fields
            issues.extend(self._validate_required_fields(tick_data))
            
            # Validate numeric fields
            issues.extend(self._validate_numeric_fields(tick_data))
            
            # Validate price fields
            issues.extend(self._validate_price_fields(tick_data))
            
            # Validate volume fields
            issues.extend(self._validate_volume_fields(tick_data))
            
            # Validate timestamps
            issues.extend(self._validate_timestamps(tick_data))
            
            # Validate market depth
            issues.extend(self._validate_market_depth(tick_data))
            
            # Check for duplicates (simplified)
            issues.extend(self._check_duplicate_data(tick_data))
            
            # Update metrics
            if issues:
                metrics.invalid_ticks += 1
                metrics.issues.extend(issues)
                self.recent_issues.extend(issues)
            else:
                metrics.valid_ticks += 1
            
            metrics.last_tick_time = datetime.utcnow()
            metrics.calculate_quality_score()
            
            # Update system metrics
            self._update_system_metrics()
            
            # Check for critical issues
            await self._check_critical_issues(issues)
            
            # Track validation performance
            validation_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.validation_times.append(validation_time)
            
            return len(issues) == 0, issues
            
        except Exception as e:
            self.logger.error(f"Error validating tick data: {e}")
            return False, [QualityIssue(
                issue_type=IssueType.ENCODING_ERROR,
                instrument_token=tick_data.get('instrument_token', 0),
                timestamp=datetime.utcnow(),
                description=f"Validation error: {e}",
                severity="critical"
            )]
    
    def _validate_required_fields(self, tick_data: Dict[str, Any]) -> List[QualityIssue]:
        """Validate required fields are present."""
        issues = []
        
        for field in self.validation_rules['required_fields']:
            if field not in tick_data or tick_data[field] is None:
                issues.append(QualityIssue(
                    issue_type=IssueType.MISSING_DATA,
                    instrument_token=tick_data.get('instrument_token', 0),
                    timestamp=datetime.utcnow(),
                    description=f"Missing required field: {field}",
                    severity="high",
                    field=field
                ))
        
        return issues
    
    def _validate_numeric_fields(self, tick_data: Dict[str, Any]) -> List[QualityIssue]:
        """Validate numeric fields have valid values."""
        issues = []
        
        for field in self.validation_rules['numeric_fields']:
            if field in tick_data and tick_data[field] is not None:
                try:
                    value = float(tick_data[field])
                    if value < 0:  # Negative values not allowed
                        issues.append(QualityIssue(
                            issue_type=IssueType.INVALID_PRICE if field in self.validation_rules['price_fields'] else IssueType.INVALID_VOLUME,
                            instrument_token=tick_data.get('instrument_token', 0),
                            timestamp=datetime.utcnow(),
                            description=f"Negative value for {field}: {value}",
                            severity="medium",
                            field=field,
                            value=value
                        ))
                except (ValueError, TypeError):
                    issues.append(QualityIssue(
                        issue_type=IssueType.INVALID_PRICE if field in self.validation_rules['price_fields'] else IssueType.INVALID_VOLUME,
                        instrument_token=tick_data.get('instrument_token', 0),
                        timestamp=datetime.utcnow(),
                        description=f"Non-numeric value for {field}: {tick_data[field]}",
                        severity="high",
                        field=field,
                        value=tick_data[field]
                    ))
        
        return issues
    
    def _validate_price_fields(self, tick_data: Dict[str, Any]) -> List[QualityIssue]:
        """Validate price fields are within reasonable ranges."""
        issues = []
        
        for field in self.validation_rules['price_fields']:
            if field in tick_data and tick_data[field] is not None:
                try:
                    price = float(tick_data[field])
                    
                    if price < self.quality_thresholds['min_price']:
                        issues.append(QualityIssue(
                            issue_type=IssueType.INVALID_PRICE,
                            instrument_token=tick_data.get('instrument_token', 0),
                            timestamp=datetime.utcnow(),
                            description=f"Price too low for {field}: {price}",
                            severity="medium",
                            field=field,
                            value=price
                        ))
                    
                    if price > self.quality_thresholds['max_price']:
                        issues.append(QualityIssue(
                            issue_type=IssueType.INVALID_PRICE,
                            instrument_token=tick_data.get('instrument_token', 0),
                            timestamp=datetime.utcnow(),
                            description=f"Price too high for {field}: {price}",
                            severity="medium",
                            field=field,
                            value=price
                        ))
                        
                except (ValueError, TypeError):
                    pass  # Already handled in numeric validation
        
        return issues
    
    def _validate_volume_fields(self, tick_data: Dict[str, Any]) -> List[QualityIssue]:
        """Validate volume fields are reasonable."""
        issues = []
        
        for field in self.validation_rules['volume_fields']:
            if field in tick_data and tick_data[field] is not None:
                try:
                    volume = int(tick_data[field])
                    
                    if volume > self.quality_thresholds['max_volume']:
                        issues.append(QualityIssue(
                            issue_type=IssueType.INVALID_VOLUME,
                            instrument_token=tick_data.get('instrument_token', 0),
                            timestamp=datetime.utcnow(),
                            description=f"Volume too high for {field}: {volume}",
                            severity="low",
                            field=field,
                            value=volume
                        ))
                        
                except (ValueError, TypeError):
                    pass  # Already handled in numeric validation
        
        return issues
    
    def _validate_timestamps(self, tick_data: Dict[str, Any]) -> List[QualityIssue]:
        """Validate timestamp fields."""
        issues = []
        current_time = datetime.utcnow()
        
        for field in self.validation_rules['timestamp_fields']:
            if field in tick_data and tick_data[field] is not None:
                try:
                    if isinstance(tick_data[field], str):
                        timestamp = datetime.fromisoformat(tick_data[field].replace('Z', '+00:00'))
                    elif isinstance(tick_data[field], datetime):
                        timestamp = tick_data[field]
                    else:
                        continue
                    
                    # Check if timestamp is too old
                    age_seconds = (current_time - timestamp).total_seconds()
                    if age_seconds > self.quality_thresholds['max_tick_age_seconds']:
                        issues.append(QualityIssue(
                            issue_type=IssueType.STALE_DATA,
                            instrument_token=tick_data.get('instrument_token', 0),
                            timestamp=datetime.utcnow(),
                            description=f"Stale data - {field} is {age_seconds:.1f}s old",
                            severity="medium",
                            field=field,
                            value=timestamp
                        ))
                    
                    # Check if timestamp is in the future
                    if timestamp > current_time + timedelta(seconds=60):
                        issues.append(QualityIssue(
                            issue_type=IssueType.TIMESTAMP_ISSUE,
                            instrument_token=tick_data.get('instrument_token', 0),
                            timestamp=datetime.utcnow(),
                            description=f"Future timestamp for {field}: {timestamp}",
                            severity="high",
                            field=field,
                            value=timestamp
                        ))
                        
                except (ValueError, TypeError) as e:
                    issues.append(QualityIssue(
                        issue_type=IssueType.TIMESTAMP_ISSUE,
                        instrument_token=tick_data.get('instrument_token', 0),
                        timestamp=datetime.utcnow(),
                        description=f"Invalid timestamp format for {field}: {e}",
                        severity="high",
                        field=field,
                        value=tick_data[field]
                    ))
        
        return issues
    
    def _validate_market_depth(self, tick_data: Dict[str, Any]) -> List[QualityIssue]:
        """Validate market depth data."""
        issues = []
        
        depth = tick_data.get('depth')
        if depth is None:
            return issues  # Depth is optional
        
        # Check buy and sell depth
        for side in ['buy', 'sell']:
            if side in depth and depth[side]:
                for i, level in enumerate(depth[side][:5]):  # Check first 5 levels
                    if not isinstance(level, dict):
                        issues.append(QualityIssue(
                            issue_type=IssueType.MISSING_DEPTH,
                            instrument_token=tick_data.get('instrument_token', 0),
                            timestamp=datetime.utcnow(),
                            description=f"Invalid depth level format for {side}[{i}]",
                            severity="low",
                            field=f"depth.{side}"
                        ))
                        continue
                    
                    # Validate price and quantity
                    if 'price' not in level or level['price'] <= 0:
                        issues.append(QualityIssue(
                            issue_type=IssueType.INVALID_PRICE,
                            instrument_token=tick_data.get('instrument_token', 0),
                            timestamp=datetime.utcnow(),
                            description=f"Invalid depth price for {side}[{i}]: {level.get('price')}",
                            severity="low",
                            field=f"depth.{side}.price"
                        ))
                    
                    if 'quantity' not in level or level['quantity'] <= 0:
                        issues.append(QualityIssue(
                            issue_type=IssueType.INVALID_VOLUME,
                            instrument_token=tick_data.get('instrument_token', 0),
                            timestamp=datetime.utcnow(),
                            description=f"Invalid depth quantity for {side}[{i}]: {level.get('quantity')}",
                            severity="low",
                            field=f"depth.{side}.quantity"
                        ))
        
        return issues
    
    def _check_duplicate_data(self, tick_data: Dict[str, Any]) -> List[QualityIssue]:
        """Check for duplicate data (simplified implementation)."""
        issues = []
        # This is a simplified duplicate check
        # In a real implementation, you might maintain a cache of recent ticks
        # and check for exact duplicates within a time window
        return issues
    
    async def _check_critical_issues(self, issues: List[QualityIssue]) -> None:
        """Check for critical issues and send alerts."""
        critical_issues = [issue for issue in issues if issue.severity == "critical"]
        
        for issue in critical_issues:
            alert_key = f"{issue.issue_type}:{issue.instrument_token}"
            
            if alert_key not in self.critical_alerts:
                # Send alert
                await self._send_quality_alert(issue)
                self.critical_alerts.add(alert_key)
    
    async def _send_quality_alert(self, issue: QualityIssue) -> None:
        """Send quality alert event."""
        try:
            event = EventFactory.create_system_event(
                component="data_quality_monitor",
                severity="ERROR",
                message=f"Critical data quality issue: {issue.description}",
                event_type=EventType.SYSTEM_ERROR,
                details={
                    "issue_type": issue.issue_type.value,
                    "instrument_token": issue.instrument_token,
                    "field": issue.field,
                    "value": str(issue.value) if issue.value is not None else None,
                },
                source="data_quality_monitor"
            )
            
            # TODO: Update to use new event system
            if self.event_publisher:
                await self.event_publisher.publish("system.quality.alert", event, ignore_failures=True)
            
        except Exception as e:
            self.logger.error(f"Failed to send quality alert: {e}")
    
    def _update_system_metrics(self) -> None:
        """Update system-wide quality metrics."""
        self.system_metrics.total_instruments = len(self.instrument_metrics)
        self.system_metrics.total_ticks_processed = sum(
            m.total_ticks for m in self.instrument_metrics.values()
        )
        self.system_metrics.total_valid_ticks = sum(
            m.valid_ticks for m in self.instrument_metrics.values()
        )
        self.system_metrics.total_issues = len(self.recent_issues)
        
        # Calculate overall quality score
        if self.system_metrics.total_ticks_processed > 0:
            self.system_metrics.overall_quality_score = (
                self.system_metrics.total_valid_ticks / 
                self.system_metrics.total_ticks_processed * 100
            )
        
        # Update quality distribution
        self.system_metrics.quality_distribution = defaultdict(int)
        for metrics in self.instrument_metrics.values():
            self.system_metrics.quality_distribution[metrics.quality_level] += 1
        
        # Update issue distribution
        self.system_metrics.issue_distribution = defaultdict(int)
        for issue in self.recent_issues:
            self.system_metrics.issue_distribution[issue.issue_type] += 1
        
        self.system_metrics.last_update = datetime.utcnow()
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        self.logger.info("Started data quality monitoring loop")
        
        try:
            while self.is_running:
                # Update system metrics
                self._update_system_metrics()
                
                # Clear old critical alerts
                self._cleanup_alerts()
                
                # Publish quality metrics
                await self._publish_quality_metrics()
                
                # Sleep
                await asyncio.sleep(30)  # Update every 30 seconds
                
        except asyncio.CancelledError:
            self.logger.info("Quality monitoring loop cancelled")
        except Exception as e:
            self.logger.error(f"Error in quality monitoring loop: {e}")
    
    def _cleanup_alerts(self) -> None:
        """Clean up old critical alerts."""
        # This is a simplified cleanup - in practice you might want to
        # clear alerts based on time or resolution status
        if len(self.critical_alerts) > 100:
            # Keep only the most recent 50 alerts
            self.critical_alerts = set(list(self.critical_alerts)[-50:])
    
    async def _publish_quality_metrics(self) -> None:
        """Publish quality metrics as events."""
        try:
            metrics_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'system_metrics': {
                    'total_instruments': self.system_metrics.total_instruments,
                    'total_ticks_processed': self.system_metrics.total_ticks_processed,
                    'overall_quality_score': self.system_metrics.overall_quality_score,
                    'total_issues': self.system_metrics.total_issues,
                },
                'validation_performance': {
                    'avg_validation_time_ms': (
                        sum(self.validation_times) / len(self.validation_times)
                        if self.validation_times else 0
                    ),
                }
            }
            
            # Create proper SystemEvent object for the new event system
            metrics_event = SystemEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.HEALTH_CHECK,
                timestamp=datetime.now(timezone.utc),
                source="data_quality_monitor",
                component="storage",
                severity="INFO",
                message="Data quality metrics report",
                details=metrics_data
            )
            
            if self.event_publisher:
                # Use ignore_failures during shutdown to prevent hanging
                await self.event_publisher.publish("system.quality.metrics", metrics_event, ignore_failures=True)
            
        except Exception as e:
            self.logger.error(f"Failed to publish quality metrics: {e}")
    
    def get_quality_report(self) -> Dict[str, Any]:
        """Get comprehensive quality report.
        
        Returns:
            Quality report dictionary
        """
        # Top issues by type
        recent_issues_by_type = defaultdict(int)
        for issue in list(self.recent_issues)[-100:]:  # Last 100 issues
            recent_issues_by_type[issue.issue_type.value] += 1
        
        # Instrument quality summary
        quality_summary = {}
        for token, metrics in self.instrument_metrics.items():
            if metrics.total_ticks > 0:
                quality_summary[token] = {
                    'quality_score': metrics.quality_score,
                    'quality_level': metrics.quality_level.value,
                    'total_ticks': metrics.total_ticks,
                    'issue_count': len(metrics.issues),
                }
        
        return {
            'system_overview': {
                'total_instruments': self.system_metrics.total_instruments,
                'total_ticks_processed': self.system_metrics.total_ticks_processed,
                'overall_quality_score': self.system_metrics.overall_quality_score,
                'total_issues': self.system_metrics.total_issues,
                'last_update': self.system_metrics.last_update.isoformat() if self.system_metrics.last_update else None,
            },
            'quality_distribution': dict(self.system_metrics.quality_distribution),
            'recent_issues_by_type': dict(recent_issues_by_type),
            'top_problematic_instruments': self._get_top_problematic_instruments(5),
            'performance_metrics': {
                'avg_validation_time_ms': (
                    sum(self.validation_times) / len(self.validation_times)
                    if self.validation_times else 0
                ),
                'critical_alerts_count': len(self.critical_alerts),
            },
            'instrument_quality_summary': quality_summary,
        }
    
    def _get_top_problematic_instruments(self, count: int) -> List[Dict[str, Any]]:
        """Get top problematic instruments by issue count."""
        instruments = []
        
        for token, metrics in self.instrument_metrics.items():
            if metrics.total_ticks > 0:
                instruments.append({
                    'instrument_token': token,
                    'quality_score': metrics.quality_score,
                    'issue_count': len(metrics.issues),
                    'total_ticks': metrics.total_ticks,
                })
        
        # Sort by issue count descending, then by quality score ascending
        instruments.sort(key=lambda x: (-x['issue_count'], x['quality_score']))
        
        return instruments[:count]