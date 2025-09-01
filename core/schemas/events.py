# CRITICAL: Standardized event envelope and data models
# This is the foundation - ALL services must use these schemas

from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
from core.utils.ids import generate_event_id


def generate_uuid7():
    """Deprecated shim. Use core.utils.ids.generate_event_id()."""
    return generate_event_id()


class AlphaPandaBaseModel(BaseModel):
    """Base model for all Alpha Panda schemas with proper JSON encoding (Pydantic v2)."""

    # Pydantic v2 configuration for JSON serialization
    model_config = ConfigDict(
        json_encoders={
            Decimal: (lambda v: float(v) if v is not None else None),
            datetime: (lambda v: v.isoformat() if v is not None else None),
        }
    )


class EventType(str, Enum):
    MARKET_TICK = "market_tick"
    TRADING_SIGNAL = "trading_signal" 
    VALIDATED_SIGNAL = "validated_signal"
    REJECTED_SIGNAL = "rejected_signal"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_FAILED = "order_failed"
    PNL_SNAPSHOT = "pnl_snapshot"
    SYSTEM_ERROR = "system_error"


class EventEnvelope(AlphaPandaBaseModel):
    """MANDATORY standardized envelope for ALL events"""
    # CRITICAL: Add missing required fields
    id: str = Field(default_factory=generate_event_id, description="Globally unique event ID for deduplication")
    correlation_id: str = Field(..., description="Links related events across services for tracing") 
    causation_id: Optional[str] = Field(None, description="ID of event that caused this one")
    trace_id: str = Field(default_factory=generate_event_id, description="Trace ID for observability across service boundaries")
    parent_trace_id: Optional[str] = Field(None, description="Parent trace ID for hierarchical tracing")
    broker: str = Field(..., description="Broker namespace (paper|zerodha) - audit only, NOT for routing")
    
    # Existing fields
    type: EventType
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    key: str = Field(..., description="Partitioning key for ordering")
    source: str = Field(..., description="Service that generated this event")
    version: int = Field(default=1, description="Schema version for compatibility")
    data: Dict[str, Any] = Field(..., description="Actual event payload")
    
    def create_child_event(self, event_type: EventType, data: Any, source: str, key: str) -> 'EventEnvelope':
        """Create child event with trace inheritance"""
        return EventEnvelope(
            id=generate_event_id(),
            type=event_type,
            ts=datetime.now(timezone.utc),
            source=source,
            key=key,
            broker=self.broker,
            data=data,
            correlation_id=self.correlation_id,
            causation_id=self.id,
            trace_id=self.trace_id,  # Inherit trace
            parent_trace_id=self.id  # Link parent
        )


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class ExecutionMode(str, Enum):
    PAPER = "paper"
    ZERODHA = "zerodha"


class OrderStatus(str, Enum):
    """Order status enumeration"""
    PENDING = "PENDING"
    PLACED = "PLACED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class MarketDepthLevel(AlphaPandaBaseModel):
    """Single level of market depth"""
    price: Decimal
    quantity: int
    orders: int

class MarketDepth(AlphaPandaBaseModel):
    """5-level market depth data"""
    buy: List[MarketDepthLevel] = Field(default_factory=list, description="Buy orders (5 levels)")
    sell: List[MarketDepthLevel] = Field(default_factory=list, description="Sell orders (5 levels)")

class OHLCData(AlphaPandaBaseModel):
    """OHLC data structure"""
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

class MarketTick(AlphaPandaBaseModel):
    """Complete market tick data - captures full PyKiteConnect structure"""
    # Core fields
    instrument_token: int
    last_price: Decimal
    timestamp: datetime
    # Optional symbol/name for convenience (not always provided by source)
    symbol: Optional[str] = None
    
    # Volume and quantity data
    volume_traded: Optional[int] = Field(None, description="Total volume traded")
    last_traded_quantity: Optional[int] = Field(None, description="Last traded quantity")
    average_traded_price: Optional[Decimal] = Field(None, description="Average traded price")
    total_buy_quantity: Optional[int] = Field(None, description="Total buy quantity")
    total_sell_quantity: Optional[int] = Field(None, description="Total sell quantity")
    
    # Price movement data
    change: Optional[Decimal] = Field(None, description="Price change percentage")
    
    # OHLC data
    ohlc: Optional[OHLCData] = Field(None, description="OHLC data")
    
    # Open Interest data (for derivatives)
    oi: Optional[int] = Field(None, description="Open Interest")
    oi_day_high: Optional[int] = Field(None, description="Day's highest OI")
    oi_day_low: Optional[int] = Field(None, description="Day's lowest OI")
    
    # Timing data
    last_trade_time: Optional[datetime] = Field(None, description="Last trade timestamp")
    exchange_timestamp: Optional[datetime] = Field(None, description="Exchange timestamp")
    
    # Market depth (5-level order book)
    depth: Optional[MarketDepth] = Field(None, description="5-level market depth")
    
    # Metadata
    mode: Optional[str] = Field(None, description="Tick mode (ltp, quote, full)")
    tradable: Optional[bool] = Field(None, description="Is instrument tradable")


class TradingSignal(AlphaPandaBaseModel):
    """Trading signal generated by strategy"""
    strategy_id: str
    instrument_token: int
    signal_type: SignalType
    quantity: int
    price: Optional[Decimal] = None
    timestamp: datetime
    confidence: Optional[float] = None  # Strategy confidence score (0.0 to 1.0)
    metadata: Optional[Dict[str, Any]] = None


class ValidatedSignal(AlphaPandaBaseModel):
    """Risk-validated trading signal"""
    original_signal: TradingSignal
    validated_quantity: int
    validated_price: Optional[Decimal] = None
    risk_checks: Dict[str, bool]
    timestamp: datetime


class RejectedSignal(AlphaPandaBaseModel):
    """Risk-rejected trading signal"""
    original_signal: TradingSignal
    rejection_reason: str
    risk_checks: Dict[str, bool]
    timestamp: datetime


class OrderPlaced(AlphaPandaBaseModel):
    """Order placement event"""
    order_id: str
    instrument_token: int
    signal_type: SignalType
    quantity: int
    price: Optional[Decimal]
    timestamp: datetime
    broker: str
    status: OrderStatus
    strategy_id: Optional[str] = None
    execution_mode: Optional[ExecutionMode] = None


class OrderFilled(AlphaPandaBaseModel):
    """Order fill event - both paper and live"""
    order_id: str
    instrument_token: int
    quantity: int
    fill_price: Decimal
    timestamp: datetime
    broker: str
    # Clarify side using enum for type safety; JSON serialization keeps values (e.g., "BUY")
    side: SignalType = SignalType.BUY
    strategy_id: Optional[str] = None
    signal_type: Optional[SignalType] = None
    execution_mode: Optional[ExecutionMode] = None
    fees: Optional[Decimal] = None


class OrderFailed(AlphaPandaBaseModel):
    """Order failure event"""
    strategy_id: str
    instrument_token: int
    signal_type: SignalType
    quantity: int
    price: Optional[Decimal]
    order_id: str
    execution_mode: ExecutionMode
    error_message: str
    timestamp: datetime
    broker: str


class Position(AlphaPandaBaseModel):
    """Portfolio position model"""
    instrument_token: int
    quantity: int
    average_price: Decimal
    current_price: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    realized_pnl: Optional[Decimal] = None
    broker: str
    last_updated: datetime


class PortfolioSnapshot(AlphaPandaBaseModel):
    """Portfolio snapshot model"""
    broker: str
    cash_balance: Decimal
    total_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    positions: List[Position]
    timestamp: datetime


class PnlSnapshot(AlphaPandaBaseModel):
    """P&L snapshot model"""
    broker: str
    instrument_token: Optional[int] = None
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    timestamp: datetime
