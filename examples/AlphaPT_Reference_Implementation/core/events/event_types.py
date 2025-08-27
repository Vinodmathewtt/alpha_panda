"""Event type definitions and data models."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class EventType(str, Enum):
    """Event type enumeration."""

    # Market data events
    MARKET_TICK = "market.tick"
    MARKET_DEPTH = "market.depth"
    MARKET_STATUS_CHANGED = "market.status.changed"

    # Trading events
    TRADING_SIGNAL = "trading.signal"
    ORDER_PLACED = "trading.order.placed"
    ORDER_FILLED = "trading.order.filled"
    ORDER_CANCELLED = "trading.order.cancelled"
    ORDER_REJECTED = "trading.order.rejected"
    ORDER_MODIFIED = "trading.order.modified"
    POSITION_UPDATED = "trading.position.updated"

    # Risk events
    RISK_ALERT = "risk.alert"
    RISK_VIOLATION = "risk.violation"
    POSITION_LIMIT_BREACHED = "risk.position_limit_breached"
    LOSS_LIMIT_BREACHED = "risk.loss_limit_breached"

    # System events
    SYSTEM_STARTED = "system.started"
    SYSTEM_STOPPED = "system.stopped"
    SYSTEM_ERROR = "system.error"
    HEALTH_CHECK = "system.health.check"
    STRATEGY_STARTED = "system.strategy.started"
    STRATEGY_STOPPED = "system.strategy.stopped"
    STRATEGY_ERROR = "system.strategy.error"

    # Monitoring events
    MONITORING_METRIC = "system.monitoring.metric"
    MONITORING_ALERT = "system.monitoring.alert"


@dataclass
class BaseEvent:
    """Base event class."""

    event_id: str
    event_type: EventType
    timestamp: datetime
    source: str
    correlation_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["event_type"] = self.event_type.value
        return data

    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BaseEvent":
        """Create event from dictionary with validation."""
        try:
            # Validate required fields
            required_fields = ["event_id", "event_type", "timestamp", "source"]
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                from core.events.event_exceptions import EventValidationError
                raise EventValidationError(f"Missing required fields: {missing_fields}")
            
            # Parse timestamp
            if isinstance(data["timestamp"], str):
                data["timestamp"] = datetime.fromisoformat(data["timestamp"])
            
            # Parse event type
            if isinstance(data["event_type"], str):
                data["event_type"] = EventType(data["event_type"])
            
            return cls(**data)
        except ValueError as e:
            from core.events.event_exceptions import EventDeserializationError
            raise EventDeserializationError(f"Failed to parse event fields: {e}", field_errors={"parsing_error": str(e)})
        except TypeError as e:
            from core.events.event_exceptions import EventDeserializationError
            raise EventDeserializationError(f"Invalid event data structure: {e}", field_errors={"type_error": str(e)})

    @classmethod
    def from_json(cls, json_str: str) -> "BaseEvent":
        """Create event from JSON string with error handling."""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError as e:
            from core.events.event_exceptions import EventDeserializationError
            raise EventDeserializationError(f"Invalid JSON format: {e}", json_data=json_str[:200])
        except Exception as e:
            from core.events.event_exceptions import EventParsingError
            raise EventParsingError(f"Failed to parse event from JSON: {e}", event_data=json_str[:200], original_error=e)


@dataclass
class MarketDataEvent(BaseEvent):
    """Market data event."""

    instrument_token: Optional[int] = None
    exchange: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    last_price: Optional[float] = None
    last_quantity: Optional[int] = None
    volume: Optional[int] = None
    average_price: Optional[float] = None
    ohlc: Optional[Dict[str, float]] = None
    depth: Optional[Dict[str, List[Dict[str, Any]]]] = None


@dataclass
class TradingEvent(BaseEvent):
    """Trading event."""

    strategy_name: Optional[str] = None
    instrument_token: Optional[int] = None
    order_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    action: Optional[str] = None  # BUY, SELL, CANCEL
    quantity: Optional[int] = None
    price: Optional[Decimal] = None
    signal_strength: Optional[float] = None
    confidence: Optional[float] = None


@dataclass
class SystemEvent(BaseEvent):
    """System event."""

    component: Optional[str] = None
    severity: Optional[str] = None  # INFO, WARNING, ERROR, CRITICAL
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    status: Optional[str] = None  # healthy, degraded, unhealthy
    metrics: Optional[Dict[str, Any]] = None


@dataclass
class RiskEvent(BaseEvent):
    """Risk management event."""

    strategy_name: Optional[str] = None
    risk_type: Optional[str] = None  # position_limit, loss_limit, exposure_limit
    risk_metric: Optional[str] = None
    current_value: Optional[Decimal] = None
    limit_value: Optional[Decimal] = None
    utilization_pct: Optional[float] = None
    breach_level: Optional[str] = None  # warning, breach, recovery
    details: Optional[Dict[str, Any]] = None


class EventFactory:
    """Factory for creating events."""

    @staticmethod
    def create_market_tick_event(
        instrument_token: int,
        exchange: str,
        tick_data: Dict[str, Any],
        source: str = "market_feed",
        correlation_id: Optional[str] = None,
    ) -> MarketDataEvent:
        """Create market tick event."""
        import uuid

        return MarketDataEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.MARKET_TICK,
            timestamp=datetime.now(timezone.utc),
            source=source,
            correlation_id=correlation_id,
            instrument_token=instrument_token,
            exchange=exchange,
            data=tick_data,
            last_price=tick_data.get("last_price"),
            last_quantity=tick_data.get("last_quantity"),
            volume=tick_data.get("volume"),
            average_price=tick_data.get("average_price"),
            ohlc=tick_data.get("ohlc"),
            depth=tick_data.get("depth"),
        )

    @staticmethod
    def create_trading_signal_event(
        strategy_name: str,
        instrument_token: int,
        action: str,
        signal_strength: float,
        confidence: float,
        data: Optional[Dict[str, Any]] = None,
        source: str = "strategy_manager",
        correlation_id: Optional[str] = None,
    ) -> TradingEvent:
        """Create trading signal event."""
        import uuid

        return TradingEvent(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TRADING_SIGNAL,
            timestamp=datetime.now(timezone.utc),
            source=source,
            correlation_id=correlation_id,
            strategy_name=strategy_name,
            instrument_token=instrument_token,
            action=action,
            signal_strength=signal_strength,
            confidence=confidence,
            data=data or {},
        )

    @staticmethod
    def create_order_event(
        event_type: EventType,
        strategy_name: str,
        order_id: str,
        instrument_token: int,
        action: str,
        quantity: int,
        price: Optional[Decimal] = None,
        data: Optional[Dict[str, Any]] = None,
        source: str = "trading_engine",
        correlation_id: Optional[str] = None,
    ) -> TradingEvent:
        """Create order event."""
        import uuid

        return TradingEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            source=source,
            correlation_id=correlation_id,
            strategy_name=strategy_name,
            order_id=order_id,
            instrument_token=instrument_token,
            action=action,
            quantity=quantity,
            price=price,
            data=data or {},
        )

    @staticmethod
    def create_system_event(
        component: str,
        severity: str,
        message: str,
        event_type: EventType = EventType.SYSTEM_ERROR,
        status: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
        source: str = "system",
        correlation_id: Optional[str] = None,
    ) -> SystemEvent:
        """Create system event."""
        import uuid

        return SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            source=source,
            correlation_id=correlation_id,
            component=component,
            severity=severity,
            message=message,
            status=status,
            metrics=metrics,
            details=details,
        )

    @staticmethod
    def create_risk_event(
        strategy_name: str,
        risk_type: str,
        risk_metric: str,
        current_value: Decimal,
        limit_value: Decimal,
        utilization_pct: float,
        breach_level: str,
        details: Optional[Dict[str, Any]] = None,
        source: str = "risk_manager",
        correlation_id: Optional[str] = None,
    ) -> RiskEvent:
        """Create risk event."""
        import uuid

        # Determine event type based on breach level
        if breach_level == "breach":
            event_type = EventType.RISK_BREACH
        elif breach_level == "warning":
            event_type = EventType.RISK_WARNING
        else:
            event_type = EventType.RISK_RECOVERED

        return RiskEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            source=source,
            correlation_id=correlation_id,
            strategy_name=strategy_name,
            risk_type=risk_type,
            risk_metric=risk_metric,
            current_value=current_value,
            limit_value=limit_value,
            utilization_pct=utilization_pct,
            breach_level=breach_level,
            details=details or {},
        )
