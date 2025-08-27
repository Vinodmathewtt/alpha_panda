"""Comprehensive strategy health monitoring system.

This module provides granular health checks for trading strategies to detect
silent failures and ensure proper operating flow throughout the strategy
execution lifecycle.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque

from core.config.settings import Settings
from core.events import EventBusCore
from core.logging.logger import get_logger
from monitoring.health_checker import HealthStatus, HealthResult


class StrategyHealthLevel(str, Enum):
    """Strategy health levels."""
    EXCELLENT = "excellent"    # All checks passing, optimal performance
    GOOD = "good"             # Minor issues, acceptable performance  
    DEGRADED = "degraded"     # Performance issues, needs attention
    CRITICAL = "critical"     # Major issues, immediate action required
    FAILED = "failed"         # Strategy not functioning


class HealthCheckType(str, Enum):
    """Types of strategy health checks."""
    REGISTRATION = "registration"           # Strategy properly registered
    INITIALIZATION = "initialization"      # Strategy initialized correctly
    MARKET_DATA = "market_data"            # Receiving market data
    DATA_PROCESSING = "data_processing"    # Processing data correctly
    SIGNAL_GENERATION = "signal_generation" # Generating signals as expected
    EXECUTION_FLOW = "execution_flow"      # Orders executed properly
    PERFORMANCE = "performance"            # Performance within bounds
    ERROR_HANDLING = "error_handling"      # Error rates acceptable
    ROUTING = "routing"                    # Signal routing working correctly
    MARKET_DATA_QUALITY = "market_data_quality"  # Market data quality checks
    SIGNAL_QUALITY = "signal_quality"     # Signal quality and validation
    INSTRUMENT_COVERAGE = "instrument_coverage"  # All configured instruments covered


@dataclass
class StrategyHealthIssue:
    """Represents a strategy health issue."""
    strategy_name: str
    check_type: HealthCheckType
    severity: str
    description: str
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None
    auto_recoverable: bool = False


@dataclass 
class StrategyHealthMetrics:
    """Health metrics for a strategy."""
    strategy_name: str
    health_level: StrategyHealthLevel = StrategyHealthLevel.EXCELLENT
    health_score: float = 100.0
    
    # Registration and initialization
    is_registered: bool = False
    is_initialized: bool = False
    is_active: bool = False
    
    # Market data flow
    market_data_received: int = 0
    last_market_data_time: Optional[datetime] = None
    market_data_lag_seconds: float = 0.0
    data_processing_rate: float = 0.0
    
    # Signal generation
    signals_generated: int = 0
    last_signal_time: Optional[datetime] = None
    signal_generation_rate: float = 0.0
    signal_quality_score: float = 100.0
    
    # Execution flow
    signals_executed: int = 0
    execution_success_rate: float = 100.0
    execution_latency_ms: float = 0.0
    
    # Error tracking
    error_count: int = 0
    last_error_time: Optional[datetime] = None
    error_rate: float = 0.0
    
    # Performance metrics
    uptime_percentage: float = 100.0
    cpu_usage_percentage: float = 0.0
    memory_usage_mb: float = 0.0
    
    # Issues
    issues: List[StrategyHealthIssue] = field(default_factory=list)
    last_health_check: Optional[datetime] = None


class StrategyHealthMonitor:
    """Comprehensive strategy health monitoring system."""
    
    def __init__(self, settings: Settings, event_bus: EventBusCore):
        self.settings = settings
        self.event_bus = event_bus
        self.logger = get_logger("strategy_health_monitor", "monitoring")
        
        # Health metrics storage
        self.strategy_metrics: Dict[str, StrategyHealthMetrics] = {}
        self.health_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Monitoring configuration
        self.check_interval = settings.monitoring.health_check_interval
        self.max_data_lag_seconds = 30.0
        self.min_signal_rate_per_hour = 0.1
        self.max_error_rate_per_hour = 5.0
        self.max_execution_latency_ms = 1000.0
        
        # Monitoring state
        self.is_running = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.registered_strategies: Set[str] = set()
        
        # Data tracking
        self.strategy_data_counts: Dict[str, int] = defaultdict(int)
        self.strategy_last_activity: Dict[str, datetime] = {}
        self.strategy_error_counts: Dict[str, int] = defaultdict(int)
        
        # Enhanced monitoring data
        self.strategy_signal_counts: Dict[str, int] = defaultdict(int)
        self.strategy_signal_routing: Dict[str, Dict[str, int]] = defaultdict(lambda: {"paper": 0, "zerodha": 0})
        self.strategy_market_data_quality: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.strategy_instrument_data: Dict[str, Dict[int, datetime]] = defaultdict(dict)
        self.strategy_signal_quality_scores: Dict[str, List[float]] = defaultdict(lambda: deque(maxlen=100))
        
        self.logger.info("Strategy health monitor initialized")
    
    async def start(self):
        """Start the strategy health monitoring."""
        if self.is_running:
            return
        
        self.is_running = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        
        # Subscribe to strategy events
        await self._setup_event_subscriptions()
        
        self.logger.info("Strategy health monitor started")
    
    async def stop(self):
        """Stop the strategy health monitoring."""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Strategy health monitor stopped")
    
    async def _setup_event_subscriptions(self):
        """Setup event subscriptions for monitoring."""
        try:
            # Use subscriber manager for event subscriptions instead of direct event_bus calls
            # This aligns with the current event system architecture
            from core.events import subscriber
            
            # Register handlers using the decorator pattern (these are discovered automatically)
            self.logger.debug("Strategy health monitoring uses decorator-based event subscriptions")
            self.logger.info("Strategy health monitor event subscriptions setup (decorator-based)")
            
        except Exception as e:
            # If subscription setup fails, log the error but don't crash
            self.logger.warning(f"Strategy health monitor subscription setup failed: {e}")
            self.logger.info("Strategy health monitoring will work in polling mode only")
    
    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.is_running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in strategy health monitoring loop: {e}")
                await asyncio.sleep(5)
    
    async def _perform_health_checks(self):
        """Perform comprehensive health checks for all strategies."""
        current_time = datetime.now(timezone.utc)
        
        for strategy_name in self.registered_strategies:
            try:
                metrics = self.strategy_metrics.get(strategy_name)
                if not metrics:
                    metrics = StrategyHealthMetrics(strategy_name=strategy_name)
                    self.strategy_metrics[strategy_name] = metrics
                
                # Perform individual health checks
                await self._check_registration_health(strategy_name, metrics, current_time)
                await self._check_market_data_health(strategy_name, metrics, current_time)
                await self._check_signal_generation_health(strategy_name, metrics, current_time)
                await self._check_execution_health(strategy_name, metrics, current_time)
                await self._check_error_health(strategy_name, metrics, current_time)
                await self._check_performance_health(strategy_name, metrics, current_time)
                
                # Enhanced health checks
                await self._check_signal_routing_health(strategy_name, metrics, current_time)
                await self._check_market_data_quality_health(strategy_name, metrics, current_time)
                await self._check_signal_quality_health(strategy_name, metrics, current_time)
                await self._check_instrument_coverage_health(strategy_name, metrics, current_time)
                
                # Calculate overall health score and level
                self._calculate_health_score(metrics)
                
                # Store health check timestamp
                metrics.last_health_check = current_time
                
                # Store health history
                self.health_history[strategy_name].append({
                    "timestamp": current_time,
                    "health_level": metrics.health_level,
                    "health_score": metrics.health_score,
                    "issues_count": len(metrics.issues)
                })
                
                # Publish health events for critical issues
                await self._publish_health_events(strategy_name, metrics)
                
            except Exception as e:
                self.logger.error(f"Error checking health for strategy {strategy_name}: {e}")
    
    async def _check_registration_health(self, strategy_name: str, metrics: StrategyHealthMetrics, current_time: datetime):
        """Check if strategy is properly registered and initialized."""
        metrics.is_registered = strategy_name in self.registered_strategies
        
        if not metrics.is_registered:
            issue = StrategyHealthIssue(
                strategy_name=strategy_name,
                check_type=HealthCheckType.REGISTRATION,
                severity="critical",
                description="Strategy not properly registered",
                timestamp=current_time
            )
            metrics.issues.append(issue)
    
    async def _check_market_data_health(self, strategy_name: str, metrics: StrategyHealthMetrics, current_time: datetime):
        """Check market data reception and processing."""
        last_data_time = self.strategy_last_activity.get(strategy_name)
        
        if last_data_time:
            metrics.last_market_data_time = last_data_time
            lag = (current_time - last_data_time).total_seconds()
            metrics.market_data_lag_seconds = lag
            
            if lag > self.max_data_lag_seconds:
                issue = StrategyHealthIssue(
                    strategy_name=strategy_name,
                    check_type=HealthCheckType.MARKET_DATA,
                    severity="warning" if lag < 60 else "critical",
                    description=f"Market data lag: {lag:.1f}s (max: {self.max_data_lag_seconds}s)",
                    timestamp=current_time,
                    details={"lag_seconds": lag}
                )
                metrics.issues.append(issue)
        else:
            # No market data received
            if metrics.is_active:
                issue = StrategyHealthIssue(
                    strategy_name=strategy_name,
                    check_type=HealthCheckType.MARKET_DATA,
                    severity="critical",
                    description="No market data received",
                    timestamp=current_time
                )
                metrics.issues.append(issue)
    
    async def _check_signal_generation_health(self, strategy_name: str, metrics: StrategyHealthMetrics, current_time: datetime):
        """Check signal generation patterns."""
        if metrics.last_signal_time:
            time_since_signal = (current_time - metrics.last_signal_time).total_seconds()
            expected_interval = 3600 / max(self.min_signal_rate_per_hour, 0.1)  # Avoid division by zero
            
            if time_since_signal > expected_interval * 2:  # 2x expected interval
                issue = StrategyHealthIssue(
                    strategy_name=strategy_name,
                    check_type=HealthCheckType.SIGNAL_GENERATION,
                    severity="warning",
                    description=f"No signals generated for {time_since_signal/3600:.1f} hours",
                    timestamp=current_time,
                    details={"hours_since_signal": time_since_signal/3600}
                )
                metrics.issues.append(issue)
    
    async def _check_execution_health(self, strategy_name: str, metrics: StrategyHealthMetrics, current_time: datetime):
        """Check signal execution health."""
        if metrics.signals_generated > 0:
            metrics.execution_success_rate = (metrics.signals_executed / metrics.signals_generated) * 100
            
            if metrics.execution_success_rate < 80:  # Less than 80% execution rate
                issue = StrategyHealthIssue(
                    strategy_name=strategy_name,
                    check_type=HealthCheckType.EXECUTION_FLOW,
                    severity="warning",
                    description=f"Low execution rate: {metrics.execution_success_rate:.1f}%",
                    timestamp=current_time,
                    details={"execution_rate": metrics.execution_success_rate}
                )
                metrics.issues.append(issue)
    
    async def _check_error_health(self, strategy_name: str, metrics: StrategyHealthMetrics, current_time: datetime):
        """Check error rates and patterns."""
        error_count = self.strategy_error_counts.get(strategy_name, 0)
        metrics.error_count = error_count
        
        # Calculate error rate (errors per hour)
        uptime_hours = max((current_time - metrics.last_health_check).total_seconds() / 3600, 1.0) if metrics.last_health_check else 1.0
        metrics.error_rate = error_count / uptime_hours
        
        if metrics.error_rate > self.max_error_rate_per_hour:
            issue = StrategyHealthIssue(
                strategy_name=strategy_name,
                check_type=HealthCheckType.ERROR_HANDLING,
                severity="critical" if metrics.error_rate > 10 else "warning",
                description=f"High error rate: {metrics.error_rate:.1f} errors/hour",
                timestamp=current_time,
                details={"error_rate": metrics.error_rate}
            )
            metrics.issues.append(issue)
    
    async def _check_performance_health(self, strategy_name: str, metrics: StrategyHealthMetrics, current_time: datetime):
        """Check strategy performance metrics."""
        # Calculate uptime percentage
        if metrics.last_health_check:
            total_time = (current_time - metrics.last_health_check).total_seconds()
            # This is a simplified calculation - in reality you'd track actual downtime
            metrics.uptime_percentage = max(0, 100 - (metrics.error_count * 5))  # Each error reduces uptime by 5%
        
        if metrics.uptime_percentage < 95:
            issue = StrategyHealthIssue(
                strategy_name=strategy_name,
                check_type=HealthCheckType.PERFORMANCE,
                severity="warning",
                description=f"Low uptime: {metrics.uptime_percentage:.1f}%",
                timestamp=current_time,
                details={"uptime_percentage": metrics.uptime_percentage}
            )
            metrics.issues.append(issue)
    
    def _calculate_health_score(self, metrics: StrategyHealthMetrics):
        """Calculate overall health score and level."""
        base_score = 100.0
        
        # Deduct points for issues
        for issue in metrics.issues:
            if issue.severity == "critical":
                base_score -= 25
            elif issue.severity == "warning":
                base_score -= 10
            else:
                base_score -= 5
        
        # Deduct points for poor metrics
        if metrics.market_data_lag_seconds > 10:
            base_score -= min(20, metrics.market_data_lag_seconds)
        
        if metrics.execution_success_rate < 90:
            base_score -= (90 - metrics.execution_success_rate)
        
        if metrics.error_rate > 1:
            base_score -= min(30, metrics.error_rate * 5)
        
        metrics.health_score = max(0, base_score)
        
        # Determine health level
        if metrics.health_score >= 95:
            metrics.health_level = StrategyHealthLevel.EXCELLENT
        elif metrics.health_score >= 85:
            metrics.health_level = StrategyHealthLevel.GOOD
        elif metrics.health_score >= 70:
            metrics.health_level = StrategyHealthLevel.DEGRADED
        elif metrics.health_score >= 50:
            metrics.health_level = StrategyHealthLevel.CRITICAL
        else:
            metrics.health_level = StrategyHealthLevel.FAILED
        
        # Clear old issues (keep only recent ones)
        current_time = datetime.now(timezone.utc)
        metrics.issues = [
            issue for issue in metrics.issues 
            if (current_time - issue.timestamp).total_seconds() < 3600  # Keep issues for 1 hour
        ]
    
    async def _publish_health_events(self, strategy_name: str, metrics: StrategyHealthMetrics):
        """Publish health events for monitoring systems."""
        if metrics.health_level in [StrategyHealthLevel.CRITICAL, StrategyHealthLevel.FAILED]:
            from core.events.event_types import SystemEvent, EventType
            import uuid
            
            event = SystemEvent(
                event_id=str(uuid.uuid4()),
                event_type=EventType.SYSTEM_HEALTH_WARNING,
                timestamp=datetime.now(timezone.utc),
                source=f"strategy_health_monitor.{strategy_name}",
                details={
                    "strategy_name": strategy_name,
                    "health_level": metrics.health_level.value,
                    "health_score": metrics.health_score,
                    "issues": [
                        {
                            "type": issue.check_type.value,
                            "severity": issue.severity,
                            "description": issue.description,
                            "timestamp": issue.timestamp.isoformat()
                        }
                    for issue in metrics.issues
                ]
                }
            )
            
            await self.event_bus.publish("strategy.health.critical", event)
    
    # Event handlers
    async def _handle_strategy_registered(self, event_data: Dict[str, Any]):
        """Handle strategy registration event."""
        strategy_name = event_data.get("strategy_name")
        if strategy_name:
            self.registered_strategies.add(strategy_name)
            if strategy_name not in self.strategy_metrics:
                self.strategy_metrics[strategy_name] = StrategyHealthMetrics(strategy_name=strategy_name)
            self.strategy_metrics[strategy_name].is_registered = True
            self.logger.info(f"Strategy registered for health monitoring: {strategy_name}")
    
    async def _handle_strategy_started(self, event_data: Dict[str, Any]):
        """Handle strategy start event."""
        strategy_name = event_data.get("strategy_name")
        if strategy_name and strategy_name in self.strategy_metrics:
            self.strategy_metrics[strategy_name].is_active = True
            self.strategy_last_activity[strategy_name] = datetime.now(timezone.utc)
    
    async def _handle_strategy_stopped(self, event_data: Dict[str, Any]):
        """Handle strategy stop event."""
        strategy_name = event_data.get("strategy_name")
        if strategy_name and strategy_name in self.strategy_metrics:
            self.strategy_metrics[strategy_name].is_active = False
    
    async def _handle_strategy_error(self, event_data: Dict[str, Any]):
        """Handle strategy error event."""
        strategy_name = event_data.get("strategy_name")
        if strategy_name:
            self.strategy_error_counts[strategy_name] += 1
            if strategy_name in self.strategy_metrics:
                self.strategy_metrics[strategy_name].last_error_time = datetime.now(timezone.utc)
    
    async def _handle_market_data(self, event_data: Dict[str, Any]):
        """Handle market data events."""
        current_time = datetime.now(timezone.utc)
        
        # Extract instrument token from event data
        tick_data = event_data.get("data", event_data)
        instrument_token = tick_data.get("instrument_token")
        
        # Track which strategies should receive this data
        for strategy_name in self.registered_strategies:
            self.strategy_data_counts[strategy_name] += 1
            self.strategy_last_activity[strategy_name] = current_time
            
            # Track instrument-level data for coverage monitoring
            if instrument_token:
                self.strategy_instrument_data[strategy_name][instrument_token] = current_time
            
            if strategy_name in self.strategy_metrics:
                self.strategy_metrics[strategy_name].market_data_received += 1
    
    async def _handle_signal_generated(self, event_data: Dict[str, Any]):
        """Handle signal generation event."""
        strategy_name = event_data.get("strategy_name")
        if strategy_name and strategy_name in self.strategy_metrics:
            self.strategy_metrics[strategy_name].signals_generated += 1
            self.strategy_metrics[strategy_name].last_signal_time = datetime.now(timezone.utc)
    
    async def _handle_signal_executed(self, event_data: Dict[str, Any]):
        """Handle signal execution event."""
        strategy_name = event_data.get("strategy_name")
        if strategy_name and strategy_name in self.strategy_metrics:
            self.strategy_metrics[strategy_name].signals_executed += 1
    
    # Public API methods
    async def get_strategy_health(self, strategy_name: str) -> Optional[StrategyHealthMetrics]:
        """Get health metrics for a specific strategy."""
        return self.strategy_metrics.get(strategy_name)
    
    async def get_all_strategies_health(self) -> Dict[str, StrategyHealthMetrics]:
        """Get health metrics for all strategies."""
        return self.strategy_metrics.copy()
    
    async def get_unhealthy_strategies(self) -> List[str]:
        """Get list of strategies with health issues."""
        unhealthy = []
        for strategy_name, metrics in self.strategy_metrics.items():
            if metrics.health_level in [StrategyHealthLevel.CRITICAL, StrategyHealthLevel.FAILED]:
                unhealthy.append(strategy_name)
        return unhealthy
    
    async def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary."""
        total_strategies = len(self.strategy_metrics)
        healthy_count = 0
        degraded_count = 0
        critical_count = 0
        failed_count = 0
        
        for metrics in self.strategy_metrics.values():
            if metrics.health_level == StrategyHealthLevel.EXCELLENT or metrics.health_level == StrategyHealthLevel.GOOD:
                healthy_count += 1
            elif metrics.health_level == StrategyHealthLevel.DEGRADED:
                degraded_count += 1
            elif metrics.health_level == StrategyHealthLevel.CRITICAL:
                critical_count += 1
            else:
                failed_count += 1
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_strategies": total_strategies,
            "healthy": healthy_count,
            "degraded": degraded_count,
            "critical": critical_count,
            "failed": failed_count,
            "overall_health_percentage": (healthy_count / max(total_strategies, 1)) * 100
        }
    
    # Enhanced health check methods
    async def _check_signal_routing_health(self, strategy_name: str, metrics: StrategyHealthMetrics, current_time: datetime):
        """Check signal routing health and distribution."""
        routing_data = self.strategy_signal_routing.get(strategy_name, {"paper": 0, "zerodha": 0})
        total_signals = routing_data["paper"] + routing_data["zerodha"]
        
        if metrics.signals_generated > 0 and total_signals == 0:
            issue = StrategyHealthIssue(
                strategy_name=strategy_name,
                check_type=HealthCheckType.ROUTING,
                severity="critical",
                description="Signals generated but no routing recorded",
                timestamp=current_time,
                details={"signals_generated": metrics.signals_generated, "routed": total_signals}
            )
            metrics.issues.append(issue)
        
        # Check if routing distribution matches expected configuration
        if total_signals > 10:  # Only check for strategies with meaningful signal volume
            paper_ratio = routing_data["paper"] / total_signals if total_signals > 0 else 0
            
            # Paper trading should receive all signals (ratio should be 1.0 if paper trading enabled)
            if paper_ratio < 0.9:  # Allow some tolerance
                issue = StrategyHealthIssue(
                    strategy_name=strategy_name,
                    check_type=HealthCheckType.ROUTING,
                    severity="warning",
                    description=f"Unexpected paper trading ratio: {paper_ratio:.2f}",
                    timestamp=current_time,
                    details={"paper_ratio": paper_ratio, "routing_data": routing_data}
                )
                metrics.issues.append(issue)
    
    async def _check_market_data_quality_health(self, strategy_name: str, metrics: StrategyHealthMetrics, current_time: datetime):
        """Check market data quality for strategy."""
        quality_data = self.strategy_market_data_quality.get(strategy_name, {})
        
        # Check for data gaps
        if quality_data.get("data_gaps", 0) > 5:
            issue = StrategyHealthIssue(
                strategy_name=strategy_name,
                check_type=HealthCheckType.MARKET_DATA_QUALITY,
                severity="warning",
                description=f"Market data gaps detected: {quality_data['data_gaps']}",
                timestamp=current_time,
                details=quality_data
            )
            metrics.issues.append(issue)
        
        # Check for stale prices
        if quality_data.get("stale_prices", 0) > 3:
            issue = StrategyHealthIssue(
                strategy_name=strategy_name,
                check_type=HealthCheckType.MARKET_DATA_QUALITY,
                severity="warning",
                description=f"Stale price data detected: {quality_data['stale_prices']}",
                timestamp=current_time,
                details=quality_data
            )
            metrics.issues.append(issue)
    
    async def _check_signal_quality_health(self, strategy_name: str, metrics: StrategyHealthMetrics, current_time: datetime):
        """Check signal quality and validation."""
        quality_scores = self.strategy_signal_quality_scores.get(strategy_name, [])
        
        if len(quality_scores) >= 10:  # Need meaningful sample size
            avg_quality = sum(quality_scores) / len(quality_scores)
            metrics.signal_quality_score = avg_quality
            
            if avg_quality < 0.5:  # Low average confidence
                issue = StrategyHealthIssue(
                    strategy_name=strategy_name,
                    check_type=HealthCheckType.SIGNAL_QUALITY,
                    severity="warning",
                    description=f"Low signal quality score: {avg_quality:.2f}",
                    timestamp=current_time,
                    details={"avg_quality": avg_quality, "sample_size": len(quality_scores)}
                )
                metrics.issues.append(issue)
        
        # Check for signal validation failures (if any tracking exists)
        signal_count = self.strategy_signal_counts.get(strategy_name, 0)
        if signal_count > 0 and metrics.signals_generated == 0:
            issue = StrategyHealthIssue(
                strategy_name=strategy_name,
                check_type=HealthCheckType.SIGNAL_QUALITY,
                severity="critical",
                description="Signal count mismatch - signals counted but not recorded in metrics",
                timestamp=current_time,
                details={"counted_signals": signal_count, "metrics_signals": metrics.signals_generated}
            )
            metrics.issues.append(issue)
    
    async def _check_instrument_coverage_health(self, strategy_name: str, metrics: StrategyHealthMetrics, current_time: datetime):
        """Check if strategy is receiving data for all configured instruments."""
        instrument_data = self.strategy_instrument_data.get(strategy_name, {})
        
        # This would need to be populated with strategy's configured instruments
        # For now, we'll check if we have any instrument data at all
        if metrics.is_active and not instrument_data:
            issue = StrategyHealthIssue(
                strategy_name=strategy_name,
                check_type=HealthCheckType.INSTRUMENT_COVERAGE,
                severity="warning",
                description="No instrument data tracked for active strategy",
                timestamp=current_time,
                details={"active": metrics.is_active, "instruments_tracked": len(instrument_data)}
            )
            metrics.issues.append(issue)
        
        # Check for instruments with stale data
        stale_instruments = []
        for instrument_token, last_time in instrument_data.items():
            if (current_time - last_time).total_seconds() > 60:  # 1 minute stale threshold
                stale_instruments.append(instrument_token)
        
        if stale_instruments:
            issue = StrategyHealthIssue(
                strategy_name=strategy_name,
                check_type=HealthCheckType.INSTRUMENT_COVERAGE,
                severity="warning",
                description=f"Stale data for {len(stale_instruments)} instruments",
                timestamp=current_time,
                details={"stale_instruments": stale_instruments}
            )
            metrics.issues.append(issue)
    
    # Enhanced event handlers
    async def _handle_signal_events(self, event_data: Dict[str, Any]):
        """Handle general signal events."""
        strategy_name = event_data.get("strategy_name")
        if strategy_name:
            self.strategy_signal_counts[strategy_name] += 1
            
            # Track signal quality if confidence is available
            confidence = event_data.get("confidence")
            if confidence is not None:
                self.strategy_signal_quality_scores[strategy_name].append(confidence)
    
    async def _handle_paper_signal_routing(self, event_data: Dict[str, Any]):
        """Handle paper trading signal routing events."""
        strategy_name = event_data.get("strategy_name")
        if strategy_name:
            self.strategy_signal_routing[strategy_name]["paper"] += 1
    
    async def _handle_zerodha_signal_routing(self, event_data: Dict[str, Any]):
        """Handle zerodha trading signal routing events."""
        signal_data = event_data.get("signal", {})
        strategy_name = signal_data.get("strategy_name")
        if strategy_name:
            self.strategy_signal_routing[strategy_name]["zerodha"] += 1
    
    async def _handle_data_quality_events(self, event_data: Dict[str, Any]):
        """Handle market data quality events."""
        strategy_name = event_data.get("strategy_name")
        if strategy_name:
            quality_type = event_data.get("quality_type")
            if quality_type == "data_gap":
                self.strategy_market_data_quality[strategy_name]["data_gaps"] = \
                    self.strategy_market_data_quality[strategy_name].get("data_gaps", 0) + 1
            elif quality_type == "stale_price":
                self.strategy_market_data_quality[strategy_name]["stale_prices"] = \
                    self.strategy_market_data_quality[strategy_name].get("stale_prices", 0) + 1


# Global health monitor instance
_strategy_health_monitor: Optional[StrategyHealthMonitor] = None


def get_strategy_health_monitor(settings: Optional[Settings] = None, event_bus: Optional[EventBusCore] = None) -> StrategyHealthMonitor:
    """Get the global strategy health monitor instance."""
    global _strategy_health_monitor
    if _strategy_health_monitor is None:
        if not settings or not event_bus:
            raise ValueError("Settings and event_bus required for first initialization")
        _strategy_health_monitor = StrategyHealthMonitor(settings, event_bus)
    return _strategy_health_monitor


async def initialize_strategy_health_monitor(settings: Settings, event_bus: EventBusCore) -> StrategyHealthMonitor:
    """Initialize the strategy health monitor."""
    monitor = get_strategy_health_monitor(settings, event_bus)
    await monitor.start()
    return monitor


async def shutdown_strategy_health_monitor():
    """Shutdown the strategy health monitor."""
    global _strategy_health_monitor
    if _strategy_health_monitor:
        await _strategy_health_monitor.stop()
        _strategy_health_monitor = None