"""Advanced risk management system for AlphaPT."""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal
from collections import defaultdict

from core.utils.exceptions import RiskManagementError
from core.config.settings import Settings
from core.events import EventBusCore, get_event_publisher, subscriber
from core.events.event_types import TradingEvent, RiskEvent, MarketDataEvent
from core.events.event_types import EventFactory, EventType
from core.logging.logger import get_logger

from .models import (
    RiskProfile,
    RiskMetric,
    RiskViolation,
    RiskCheck,
    RiskAlert,
    PositionLimit,
    LossLimit,
    ExposureLimit
)
from .types import (
    RiskLimitType,
    RiskSeverity,
    RiskStatus,
    ViolationType,
    RiskAction,
    MoneyAmount,
    PercentageAmount,
    QuantityAmount
)


# Global risk manager instance for decorator handlers
_risk_manager_instance: Optional['RiskManager'] = None


@subscriber.on_event("trading.signal.*", durable_name="risk-manager-signals")
async def handle_trading_signal_risk(event: TradingEvent) -> None:
    """Handle trading signal events for risk validation.
    
    This decorator-based handler routes trading signals to the risk manager for validation.
    """
    global _risk_manager_instance
    if _risk_manager_instance:
        await _risk_manager_instance._handle_trading_signal_event(event)


@subscriber.on_event("market.tick.*", durable_name="risk-manager-market-data")
async def handle_market_data_risk(event: MarketDataEvent) -> None:
    """Handle market data events for risk monitoring."""
    global _risk_manager_instance
    if _risk_manager_instance:
        await _risk_manager_instance._handle_market_data_event(event)


class RiskManager:
    """Comprehensive risk management system."""
    
    def __init__(self, settings: Settings, event_bus: Optional[EventBusCore] = None):
        """Initialize risk manager."""
        self.logger = get_logger(__name__)
        self.settings = settings
        self.event_bus = event_bus
        
        # Risk profiles by strategy
        self.risk_profiles: Dict[str, RiskProfile] = {}
        
        # Current risk metrics
        self.current_metrics: Dict[str, Dict[str, RiskMetric]] = defaultdict(dict)
        
        # Active violations
        self.active_violations: Dict[str, List[RiskViolation]] = defaultdict(list)
        
        # Risk monitoring state
        self.monitoring_enabled = True
        self.last_check_time = datetime.utcnow()
        
        # Cache for performance
        self._position_cache: Dict[str, Dict[int, Dict]] = defaultdict(dict)
        self._pnl_cache: Dict[str, Dict] = defaultdict(dict)
        
        self.logger.info("RiskManager initialized")
    
    async def initialize(self) -> None:
        """Initialize risk manager with default profiles."""
        try:
            await self._load_risk_profiles()
            await self._initialize_monitoring()
            self.logger.info("Risk manager initialization completed")
        except Exception as e:
            self.logger.error(f"Risk manager initialization failed: {e}")
            raise RiskManagementError(f"Failed to initialize risk manager: {e}")
    
    async def _publish_event(self, subject: str, event):
        """Helper method to publish events using the new event publisher service."""
        from core.events import get_event_publisher
        try:
            event_publisher = get_event_publisher(self.settings)
            await event_publisher.publish(subject, event)
        except Exception as e:
            self.logger.error(f"Failed to publish event to {subject}: {e}")
            # Don't raise exception to avoid breaking main functionality
    
    async def start(self) -> None:
        """Start risk manager operations."""
        try:
            self.monitoring_enabled = True
            
            # Set global instance for decorator handlers
            global _risk_manager_instance
            _risk_manager_instance = self
            self.logger.info("✅ Risk manager registered for event subscriptions")
            
            self.logger.info("Risk manager started")
        except Exception as e:
            self.logger.error(f"Risk manager start failed: {e}")
            raise RiskManagementError(f"Failed to start risk manager: {e}")
    
    async def stop(self) -> None:
        """Stop risk manager operations."""
        try:
            self.monitoring_enabled = False
            
            # Clear global instance
            global _risk_manager_instance
            _risk_manager_instance = None
            self.logger.info("Risk manager unregistered from event subscriptions")
            
            self.logger.info("Risk manager stopped")
        except Exception as e:
            self.logger.error(f"Risk manager stop failed: {e}")
            raise RiskManagementError(f"Failed to stop risk manager: {e}")
    
    async def shutdown(self) -> None:
        """Graceful shutdown."""
        try:
            await self.stop()
            await self._save_risk_state()
            self.logger.info("Risk manager shutdown completed")
        except Exception as e:
            self.logger.error(f"Risk manager shutdown failed: {e}")
    
    # Risk Profile Management
    
    async def create_risk_profile(
        self,
        strategy_name: str,
        position_limits: Optional[List[PositionLimit]] = None,
        loss_limits: Optional[List[LossLimit]] = None,
        exposure_limits: Optional[List[ExposureLimit]] = None
    ) -> RiskProfile:
        """Create risk profile for strategy."""
        try:
            profile = RiskProfile(
                strategy_name=strategy_name,
                position_limits=position_limits or [],
                loss_limits=loss_limits or [],
                exposure_limits=exposure_limits or []
            )
            
            self.risk_profiles[strategy_name] = profile
            
            # Initialize metrics
            await self._initialize_strategy_metrics(strategy_name)
            
            self.logger.info(f"Created risk profile for strategy: {strategy_name}")
            return profile
            
        except Exception as e:
            self.logger.error(f"Failed to create risk profile for {strategy_name}: {e}")
            raise RiskManagementError(f"Failed to create risk profile: {e}")
    
    async def update_risk_profile(
        self,
        strategy_name: str,
        **updates
    ) -> RiskProfile:
        """Update existing risk profile."""
        try:
            if strategy_name not in self.risk_profiles:
                raise RiskManagementError(f"Risk profile not found for strategy: {strategy_name}")
            
            profile = self.risk_profiles[strategy_name]
            
            for key, value in updates.items():
                if hasattr(profile, key):
                    setattr(profile, key, value)
            
            profile.updated_at = datetime.utcnow()
            
            self.logger.info(f"Updated risk profile for strategy: {strategy_name}")
            return profile
            
        except Exception as e:
            self.logger.error(f"Failed to update risk profile for {strategy_name}: {e}")
            raise RiskManagementError(f"Failed to update risk profile: {e}")
    
    async def get_risk_profile(self, strategy_name: str) -> Optional[RiskProfile]:
        """Get risk profile for strategy."""
        return self.risk_profiles.get(strategy_name)
    
    # Pre-trade Risk Checks
    
    async def check_order_risk(
        self,
        strategy_name: str,
        instrument_token: int,
        action: str,
        quantity: QuantityAmount,
        price: MoneyAmount,
        order_value: Optional[MoneyAmount] = None
    ) -> RiskCheck:
        """Comprehensive pre-trade risk check."""
        try:
            check_id = str(uuid.uuid4())
            violations = []
            warnings = []
            
            if order_value is None:
                order_value = Decimal(str(quantity)) * Decimal(str(price))
            
            # Get risk profile
            profile = await self.get_risk_profile(strategy_name)
            if not profile or not profile.enabled:
                return RiskCheck(
                    check_id=check_id,
                    strategy_name=strategy_name,
                    instrument_token=instrument_token,
                    action=action,
                    quantity=quantity,
                    price=price,
                    passed=True,
                    warnings=["No risk profile found - trading without limits"]
                )
            
            # Check position limits
            position_violations = await self._check_position_limits(
                strategy_name, instrument_token, action, quantity, order_value
            )
            violations.extend(position_violations)
            
            # Check loss limits
            loss_violations = await self._check_loss_limits(
                strategy_name, order_value
            )
            violations.extend(loss_violations)
            
            # Check exposure limits
            exposure_violations = await self._check_exposure_limits(
                strategy_name, instrument_token, order_value
            )
            violations.extend(exposure_violations)
            
            # Determine if order should pass
            hard_violations = [v for v in violations if v.violation_type == ViolationType.HARD_LIMIT]
            passed = len(hard_violations) == 0
            
            # Create risk check result
            risk_check = RiskCheck(
                check_id=check_id,
                strategy_name=strategy_name,
                instrument_token=instrument_token,
                action=action,
                quantity=quantity,
                price=price,
                passed=passed,
                violations=violations,
                warnings=warnings
            )
            
            # Log result
            if not passed:
                self.logger.warning(
                    f"Risk check FAILED for {strategy_name}: "
                    f"{len(hard_violations)} hard violations"
                )
            
            # Publish risk check event
            if self.event_bus:
                await self._publish_risk_check_event(risk_check)
            
            return risk_check
            
        except Exception as e:
            self.logger.error(f"Risk check failed for {strategy_name}: {e}")
            raise RiskManagementError(f"Risk check failed: {e}")
    
    # Position and PnL Updates
    
    async def update_position(
        self,
        strategy_name: str,
        instrument_token: int,
        quantity: QuantityAmount,
        value: MoneyAmount,
        unrealized_pnl: MoneyAmount = 0,
        realized_pnl: MoneyAmount = 0
    ) -> None:
        """Update position information for risk calculations."""
        try:
            position_data = {
                "quantity": quantity,
                "value": value,
                "unrealized_pnl": unrealized_pnl,
                "realized_pnl": realized_pnl,
                "updated_at": datetime.utcnow()
            }
            
            self._position_cache[strategy_name][instrument_token] = position_data
            
            # Update risk metrics
            await self._update_risk_metrics(strategy_name)
            
        except Exception as e:
            self.logger.error(f"Failed to update position for {strategy_name}: {e}")
    
    async def update_strategy_pnl(
        self,
        strategy_name: str,
        daily_pnl: MoneyAmount,
        total_pnl: MoneyAmount,
        unrealized_pnl: MoneyAmount = 0
    ) -> None:
        """Update strategy P&L for risk monitoring."""
        try:
            pnl_data = {
                "daily_pnl": daily_pnl,
                "total_pnl": total_pnl,
                "unrealized_pnl": unrealized_pnl,
                "updated_at": datetime.utcnow()
            }
            
            self._pnl_cache[strategy_name] = pnl_data
            
            # Check loss limits
            await self._monitor_loss_limits(strategy_name)
            
        except Exception as e:
            self.logger.error(f"Failed to update P&L for {strategy_name}: {e}")
    
    # Risk Monitoring
    
    async def get_risk_status(self, strategy_name: str) -> Dict[str, Any]:
        """Get comprehensive risk status for strategy."""
        try:
            profile = await self.get_risk_profile(strategy_name)
            if not profile:
                return {"status": "no_profile", "message": "No risk profile found"}
            
            metrics = self.current_metrics.get(strategy_name, {})
            violations = self.active_violations.get(strategy_name, [])
            
            # Calculate overall risk status
            violation_count = len(violations)
            hard_violations = len([v for v in violations if v.violation_type == ViolationType.HARD_LIMIT])
            
            if hard_violations > 0:
                overall_status = RiskStatus.BREACHED
            elif violation_count > 0:
                overall_status = RiskStatus.WARNING
            else:
                overall_status = RiskStatus.SAFE
            
            return {
                "strategy_name": strategy_name,
                "overall_status": overall_status.value,
                "violation_count": violation_count,
                "hard_violations": hard_violations,
                "metrics": {
                    name: {
                        "current_value": float(metric.current_value),
                        "limit_value": float(metric.limit_value),
                        "utilization_pct": metric.utilization_pct,
                        "status": metric.status.value
                    }
                    for name, metric in metrics.items()
                },
                "violations": [
                    {
                        "type": v.risk_type.value,
                        "severity": v.severity.value,
                        "message": v.message,
                        "utilization_pct": v.utilization_pct
                    }
                    for v in violations
                ],
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get risk status for {strategy_name}: {e}")
            return {"status": "error", "message": str(e)}
    
    async def get_all_risk_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get risk metrics for all strategies."""
        try:
            all_metrics = {}
            
            for strategy_name in self.risk_profiles.keys():
                all_metrics[strategy_name] = await self.get_risk_status(strategy_name)
            
            return all_metrics
            
        except Exception as e:
            self.logger.error(f"Failed to get all risk metrics: {e}")
            return {}
    
    # Private Methods
    
    async def _load_risk_profiles(self) -> None:
        """Load risk profiles from configuration or database."""
        # Load from configuration
        for profile_config in self.settings.risk.default_profiles:
            # Convert position limit configs to PositionLimit objects
            position_limits = [
                PositionLimit(
                    strategy_name=pl.strategy_name,
                    max_value=pl.max_value,
                    max_percentage=pl.max_percentage
                )
                for pl in profile_config.position_limits
            ]
            
            # Convert loss limit configs to LossLimit objects
            loss_limits = [
                LossLimit(
                    strategy_name=ll.strategy_name,
                    max_daily_loss=ll.max_daily_loss,
                    max_drawdown_pct=ll.max_drawdown_pct
                )
                for ll in profile_config.loss_limits
            ]
            
            await self.create_risk_profile(
                strategy_name=profile_config.strategy_name,
                position_limits=position_limits,
                loss_limits=loss_limits
            )
        
        self.logger.info("Default risk profiles loaded")
    
    async def _initialize_monitoring(self) -> None:
        """Initialize risk monitoring tasks."""
        if self.monitoring_enabled:
            # Start background monitoring task
            asyncio.create_task(self._risk_monitoring_loop())
    
    async def _risk_monitoring_loop(self) -> None:
        """Background risk monitoring loop."""
        while self.monitoring_enabled:
            try:
                await self._update_all_risk_metrics()
                await asyncio.sleep(5)  # Check every 5 seconds
            except Exception as e:
                self.logger.error(f"Risk monitoring loop error: {e}")
                await asyncio.sleep(10)  # Wait longer on errors
    
    async def _check_position_limits(
        self,
        strategy_name: str,
        instrument_token: int,
        action: str,
        quantity: QuantityAmount,
        order_value: MoneyAmount
    ) -> List[RiskViolation]:
        """Check position limits."""
        violations = []
        profile = self.risk_profiles.get(strategy_name)
        
        if not profile:
            return violations
        
        for limit in profile.position_limits:
            # Check if limit applies to this instrument
            if limit.instrument_token and limit.instrument_token != instrument_token:
                continue
            
            # Get current position
            current_position = self._position_cache[strategy_name].get(instrument_token, {})
            current_value = current_position.get("value", 0)
            current_quantity = current_position.get("quantity", 0)
            
            # Calculate new position after order
            if action.upper() == "BUY":
                new_value = Decimal(str(current_value)) + Decimal(str(order_value))
                new_quantity = current_quantity + quantity
            else:  # SELL
                new_value = Decimal(str(current_value)) - Decimal(str(order_value))
                new_quantity = current_quantity - quantity
            
            # Check value limit
            if limit.max_value and new_value > Decimal(str(limit.max_value)):
                violation = RiskViolation(
                    violation_id=str(uuid.uuid4()),
                    strategy_name=strategy_name,
                    risk_type=RiskLimitType.POSITION_LIMIT,
                    violation_type=ViolationType.HARD_LIMIT,
                    severity=RiskSeverity.HIGH,
                    current_value=new_value,
                    limit_value=Decimal(str(limit.max_value)),
                    utilization_pct=float((new_value / Decimal(str(limit.max_value))) * 100),
                    message=f"Position value limit exceeded: {new_value} > {limit.max_value}"
                )
                violations.append(violation)
            
            # Check quantity limit
            if limit.max_quantity and abs(new_quantity) > limit.max_quantity:
                violation = RiskViolation(
                    violation_id=str(uuid.uuid4()),
                    strategy_name=strategy_name,
                    risk_type=RiskLimitType.POSITION_LIMIT,
                    violation_type=ViolationType.HARD_LIMIT,
                    severity=RiskSeverity.HIGH,
                    current_value=abs(new_quantity),
                    limit_value=limit.max_quantity,
                    utilization_pct=float((abs(new_quantity) / limit.max_quantity) * 100),
                    message=f"Position quantity limit exceeded: {abs(new_quantity)} > {limit.max_quantity}"
                )
                violations.append(violation)
        
        return violations
    
    async def _check_loss_limits(
        self,
        strategy_name: str,
        order_value: MoneyAmount
    ) -> List[RiskViolation]:
        """Check loss limits."""
        violations = []
        profile = self.risk_profiles.get(strategy_name)
        
        if not profile:
            return violations
        
        pnl_data = self._pnl_cache.get(strategy_name, {})
        daily_pnl = pnl_data.get("daily_pnl", 0)
        
        for limit in profile.loss_limits:
            # Check daily loss limit
            if limit.max_daily_loss and daily_pnl < -abs(Decimal(str(limit.max_daily_loss))):
                violation = RiskViolation(
                    violation_id=str(uuid.uuid4()),
                    strategy_name=strategy_name,
                    risk_type=RiskLimitType.LOSS_LIMIT,
                    violation_type=ViolationType.HARD_LIMIT,
                    severity=RiskSeverity.CRITICAL,
                    current_value=abs(daily_pnl),
                    limit_value=Decimal(str(limit.max_daily_loss)),
                    utilization_pct=float((abs(daily_pnl) / Decimal(str(limit.max_daily_loss))) * 100),
                    message=f"Daily loss limit exceeded: {daily_pnl} < -{limit.max_daily_loss}"
                )
                violations.append(violation)
        
        return violations
    
    async def _check_exposure_limits(
        self,
        strategy_name: str,
        instrument_token: int,
        order_value: MoneyAmount
    ) -> List[RiskViolation]:
        """Check exposure limits."""
        violations = []
        # Placeholder for exposure limit checks
        # Would require instrument metadata (sector, exchange, etc.)
        return violations
    
    async def _initialize_strategy_metrics(self, strategy_name: str) -> None:
        """Initialize risk metrics for strategy."""
        if strategy_name not in self.current_metrics:
            self.current_metrics[strategy_name] = {}
    
    async def _update_risk_metrics(self, strategy_name: str) -> None:
        """Update risk metrics for strategy."""
        try:
            profile = self.risk_profiles.get(strategy_name)
            if not profile:
                return
            
            # Update position-based metrics
            positions = self._position_cache.get(strategy_name, {})
            total_position_value = sum(
                pos.get("value", 0) for pos in positions.values()
            )
            
            # Create or update position value metric
            if profile.position_limits:
                max_position = max(
                    (limit.max_value or 0 for limit in profile.position_limits),
                    default=0
                )
                if max_position > 0:
                    utilization = (total_position_value / max_position) * 100
                    status = self._get_metric_status(utilization)
                    
                    metric = RiskMetric(
                        strategy_name=strategy_name,
                        metric_type=RiskLimitType.POSITION_LIMIT,
                        metric_name="total_position_value",
                        current_value=total_position_value,
                        limit_value=max_position,
                        utilization_pct=utilization,
                        status=status
                    )
                    
                    self.current_metrics[strategy_name]["total_position_value"] = metric
            
        except Exception as e:
            self.logger.error(f"Failed to update risk metrics for {strategy_name}: {e}")
    
    async def _update_all_risk_metrics(self) -> None:
        """Update risk metrics for all strategies."""
        for strategy_name in self.risk_profiles.keys():
            await self._update_risk_metrics(strategy_name)
    
    async def _monitor_loss_limits(self, strategy_name: str) -> None:
        """Monitor loss limits and generate alerts."""
        try:
            profile = self.risk_profiles.get(strategy_name)
            if not profile:
                return
            
            pnl_data = self._pnl_cache.get(strategy_name, {})
            daily_pnl = pnl_data.get("daily_pnl", 0)
            
            for limit in profile.loss_limits:
                if limit.max_daily_loss and daily_pnl < -abs(Decimal(str(limit.max_daily_loss))):
                    # Generate alert
                    alert = RiskAlert(
                        alert_id=str(uuid.uuid4()),
                        strategy_name=strategy_name,
                        alert_type="loss_limit_breach",
                        severity=RiskSeverity.CRITICAL,
                        message=f"Daily loss limit breached: {daily_pnl}",
                        action_required=RiskAction.BLOCK_NEW_ORDERS
                    )
                    
                    await self._process_risk_alert(alert)
        
        except Exception as e:
            self.logger.error(f"Failed to monitor loss limits for {strategy_name}: {e}")
    
    def _get_metric_status(self, utilization_pct: float) -> RiskStatus:
        """Get risk status based on utilization percentage."""
        if utilization_pct >= 100:
            return RiskStatus.BREACHED
        elif utilization_pct >= 80:
            return RiskStatus.WARNING
        else:
            return RiskStatus.SAFE
    
    async def _publish_risk_check_event(self, risk_check: RiskCheck) -> None:
        """Publish risk check event."""
        try:
            if self.event_bus:
                event = EventFactory.create_system_event(
                    component="risk_manager",
                    severity="INFO" if risk_check.passed else "WARNING",
                    message=f"Risk check {'passed' if risk_check.passed else 'failed'} for {risk_check.strategy_name}",
                    event_type=EventType.RISK_BREACH if not risk_check.passed else EventType.HEALTH_CHECK,
                    details={"risk_check": risk_check.check_id, "violations": len(risk_check.violations)}
                )
                await self._publish_event("system.risk.check", event)
        except Exception as e:
            self.logger.error(f"Failed to publish risk check event: {e}")
    
    async def _process_risk_alert(self, alert: RiskAlert) -> None:
        """Process risk alert."""
        try:
            self.logger.warning(f"RISK ALERT: {alert.message}")
            
            # Publish alert event
            if self.event_bus:
                event = EventFactory.create_system_event(
                    component="risk_manager",
                    severity=alert.severity.value.upper(),
                    message=alert.message,
                    event_type=EventType.RISK_BREACH,
                    details={"alert_id": alert.alert_id, "action_required": alert.action_required.value}
                )
                await self._publish_event("system.risk.alert", event)
        
        except Exception as e:
            self.logger.error(f"Failed to process risk alert: {e}")
    
    async def _save_risk_state(self) -> None:
        """Save current risk state (placeholder)."""
        # In production, this would save to database
        pass
    
    async def _handle_trading_signal_event(self, event: TradingEvent) -> None:
        """Handle trading signal events for risk validation.
        
        Args:
            event: Trading signal event from new event system
        """
        try:
            self.logger.info(f"Received trading signal for risk validation: {event.source}")
            
            # Extract signal data from event
            if hasattr(event, 'data') and event.data:
                signal_data = event.data
                
                # Perform risk validation - this would typically involve:
                # 1. Position limit checks
                # 2. Loss limit validation
                # 3. Exposure limit verification
                # 4. Portfolio concentration checks
                
                self.logger.info(f"Performing risk validation for signal: {signal_data}")
                
                # Example: Check if trading is allowed
                if not self.monitoring_enabled:
                    self.logger.warning("Risk monitoring disabled - signal validation skipped")
                    return
                
                # Here you would call actual risk validation methods
                # await self.validate_signal(signal_data)
                
        except Exception as e:
            self.logger.error(f"Error handling trading signal for risk validation: {e}")
    
    async def _handle_market_data_event(self, event: MarketDataEvent) -> None:
        """Handle market data events for risk monitoring.
        
        Args:
            event: Market data event from new event system
        """
        try:
            # Extract market data
            instrument_token = event.instrument_token
            last_price = float(event.last_price) if event.last_price else None
            
            if last_price is None:
                return
            
            # Update risk monitoring with latest market data
            # This could involve:
            # 1. Mark-to-market calculations
            # 2. VaR updates
            # 3. Exposure recalculation
            # 4. Alert triggering based on price movements
            
            self.logger.debug(f"Updated risk monitoring for {instrument_token}: {last_price}")
            
        except Exception as e:
            self.logger.error(f"Error handling market data for risk monitoring: {e}")