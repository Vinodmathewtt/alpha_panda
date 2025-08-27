# CRITICAL: Standardized event envelope and data models
# This is the foundation - ALL services must use these schemas

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List
from uuid import uuid4
import uuid_utils


def generate_uuid7():
    """Generate UUID v7 for time-ordered event IDs using uuid_utils library"""
    return str(uuid_utils.uuid7())


class EventType(str, Enum):
    MARKET_TICK = "market_tick"
    TRADING_SIGNAL = "trading_signal" 
    VALIDATED_SIGNAL = "validated_signal"
    REJECTED_SIGNAL = "rejected_signal"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_FAILED = "order_failed"
    PNL_SNAPSHOT = "pnl_snapshot"


class EventEnvelope(BaseModel):
    """MANDATORY standardized envelope for ALL events"""
    # CRITICAL: Add missing required fields
    id: str = Field(default_factory=generate_uuid7, description="Globally unique event ID for deduplication")
    correlation_id: str = Field(..., description="Links related events across services for tracing") 
    causation_id: Optional[str] = Field(None, description="ID of event that caused this one")
    trace_id: str = Field(default_factory=generate_uuid7, description="Trace ID for observability across service boundaries")
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
            id=generate_uuid7(),
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


class MarketDepthLevel(BaseModel):
    """Single level of market depth"""
    price: Decimal
    quantity: int
    orders: int

class MarketDepth(BaseModel):
    """5-level market depth data"""
    buy: List[MarketDepthLevel] = Field(default_factory=list, description="Buy orders (5 levels)")
    sell: List[MarketDepthLevel] = Field(default_factory=list, description="Sell orders (5 levels)")

class OHLCData(BaseModel):
    """OHLC data structure"""
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

class MarketTick(BaseModel):
    """Complete market tick data - captures full PyKiteConnect structure"""
    # Core fields
    instrument_token: int
    last_price: Decimal
    timestamp: datetime
    
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


class TradingSignal(BaseModel):
    """Trading signal generated by strategy"""
    strategy_id: str
    instrument_token: int
    signal_type: SignalType
    quantity: int
    price: Optional[Decimal] = None
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None


class ValidatedSignal(BaseModel):
    """Risk-validated trading signal"""
    original_signal: TradingSignal
    validated_quantity: int
    validated_price: Optional[Decimal] = None
    risk_checks: Dict[str, bool]
    timestamp: datetime


class RejectedSignal(BaseModel):
    """Risk-rejected trading signal"""
    original_signal: TradingSignal
    rejection_reason: str
    risk_checks: Dict[str, bool]
    timestamp: datetime


class OrderPlaced(BaseModel):
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


class OrderFilled(BaseModel):
    """Order fill event - both paper and live"""
    order_id: str
    instrument_token: int
    quantity: int
    fill_price: Decimal
    timestamp: datetime
    broker: str
    side: Optional[str] = "BUY"  # BUY or SELL
    strategy_id: Optional[str] = None
    signal_type: Optional[SignalType] = None
    execution_mode: Optional[ExecutionMode] = None
    fees: Optional[Decimal] = None


class OrderFailed(BaseModel):
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


class Position(BaseModel):
    """Portfolio position model"""
    instrument_token: int
    quantity: int
    average_price: Decimal
    current_price: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    realized_pnl: Optional[Decimal] = None
    broker: str
    last_updated: datetime


class PortfolioSnapshot(BaseModel):
    """Portfolio snapshot model"""
    broker: str
    cash_balance: Decimal
    total_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    positions: List[Position]
    timestamp: datetime


class PnlSnapshot(BaseModel):
    """P&L snapshot model"""
    broker: str
    instrument_token: Optional[int] = None
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    timestamp: datetime