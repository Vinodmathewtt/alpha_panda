"""SQLAlchemy models for PostgreSQL database."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import (
    JSON,
    UUID,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class OrderStatus(enum.Enum):
    """Order status enumeration."""

    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    TRIGGER_PENDING = "TRIGGER PENDING"


class OrderType(enum.Enum):
    """Order type enumeration."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class ProductType(enum.Enum):
    """Product type enumeration."""

    CNC = "CNC"
    MIS = "MIS"
    NRML = "NRML"


class TransactionType(enum.Enum):
    """Transaction type enumeration."""

    BUY = "BUY"
    SELL = "SELL"


class RiskBreachStatus(enum.Enum):
    """Risk breach status enumeration."""

    SAFE = "safe"
    WARNING = "warning"
    BREACHED = "breached"


class Order(Base):
    """Order tracking table."""

    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(String(50), unique=True, nullable=False, index=True)
    strategy_name = Column(String(100), nullable=False, index=True)
    instrument_token = Column(Integer, nullable=False)
    tradingsymbol = Column(String(50), nullable=False)
    exchange = Column(String(10), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    order_type = Column(Enum(OrderType), nullable=False)
    product = Column(Enum(ProductType), nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=True)
    trigger_price = Column(Numeric(10, 2), nullable=True)
    status = Column(Enum(OrderStatus), nullable=False, index=True)
    filled_quantity = Column(Integer, default=0)
    pending_quantity = Column(Integer, nullable=True)
    average_price = Column(Numeric(10, 2), nullable=True)
    disclosed_quantity = Column(Integer, nullable=True)
    validity = Column(String(10), nullable=False, default="DAY")
    variety = Column(String(20), nullable=False, default="regular")
    tag = Column(String(50), nullable=True)
    parent_order_id = Column(String(50), nullable=True)
    placed_by = Column(String(50), nullable=True)
    order_timestamp = Column(DateTime(timezone=True), nullable=False)
    exchange_timestamp = Column(DateTime(timezone=True), nullable=True)
    exchange_update_timestamp = Column(DateTime(timezone=True), nullable=True)
    status_message = Column(Text, nullable=True)
    cancelled_quantity = Column(Integer, default=0)
    market_protection = Column(Integer, default=0)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index("idx_orders_strategy_status", "strategy_name", "status"),
        Index("idx_orders_timestamp", "order_timestamp"),
        Index("idx_orders_instrument", "instrument_token"),
    )

    def __repr__(self) -> str:
        return (
            f"<Order(order_id='{self.order_id}', strategy='{self.strategy_name}', "
            f"symbol='{self.tradingsymbol}', status='{self.status.value}')>"
        )


class Position(Base):
    """Position tracking table."""

    __tablename__ = "positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_name = Column(String(100), nullable=False, index=True)
    tradingsymbol = Column(String(50), nullable=False)
    exchange = Column(String(10), nullable=False)
    instrument_token = Column(Integer, nullable=False)
    product = Column(Enum(ProductType), nullable=False)
    quantity = Column(Integer, nullable=False)
    overnight_quantity = Column(Integer, default=0)
    multiplier = Column(Integer, default=1)
    average_price = Column(Numeric(10, 2), nullable=False)
    close_price = Column(Numeric(10, 2), nullable=True)
    last_price = Column(Numeric(10, 2), nullable=True)
    value = Column(Numeric(12, 2), nullable=True)
    pnl = Column(Numeric(12, 2), nullable=True)
    m2m = Column(Numeric(12, 2), nullable=True)
    unrealised = Column(Numeric(12, 2), nullable=True)
    realised = Column(Numeric(12, 2), nullable=True)
    buy_quantity = Column(Integer, default=0)
    buy_price = Column(Numeric(10, 2), default=0)
    buy_value = Column(Numeric(12, 2), default=0)
    buy_m2m = Column(Numeric(12, 2), default=0)
    sell_quantity = Column(Integer, default=0)
    sell_price = Column(Numeric(10, 2), default=0)
    sell_value = Column(Numeric(12, 2), default=0)
    sell_m2m = Column(Numeric(12, 2), default=0)
    day_buy_quantity = Column(Integer, default=0)
    day_buy_price = Column(Numeric(10, 2), default=0)
    day_buy_value = Column(Numeric(12, 2), default=0)
    day_sell_quantity = Column(Integer, default=0)
    day_sell_price = Column(Numeric(10, 2), default=0)
    day_sell_value = Column(Numeric(12, 2), default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Unique constraint
    __table_args__ = (
        Index("idx_positions_strategy", "strategy_name"),
        Index("idx_positions_instrument", "instrument_token"),
        Index("unique_position", "strategy_name", "tradingsymbol", "exchange", "product", unique=True),
    )

    def __repr__(self) -> str:
        return (
            f"<Position(strategy='{self.strategy_name}', symbol='{self.tradingsymbol}', "
            f"quantity={self.quantity}, pnl={self.pnl})>"
        )


class RiskMetric(Base):
    """Risk metrics tracking table."""

    __tablename__ = "risk_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_name = Column(String(100), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False, index=True)
    metric_name = Column(String(100), nullable=False)
    current_value = Column(Numeric(12, 2), nullable=False)
    limit_value = Column(Numeric(12, 2), nullable=False)
    utilization_pct = Column(Numeric(5, 2), nullable=False)
    breach_status = Column(Enum(RiskBreachStatus), nullable=False)
    last_breach_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index("idx_risk_metrics_strategy", "strategy_name", "metric_type"),
        Index("idx_risk_metrics_breach", "breach_status"),
    )

    def __repr__(self) -> str:
        return (
            f"<RiskMetric(strategy='{self.strategy_name}', metric='{self.metric_name}', "
            f"status='{self.breach_status.value}')>"
        )


class InstrumentMaster(Base):
    """Instrument master data table."""

    __tablename__ = "instrument_master"

    instrument_token = Column(Integer, primary_key=True)
    exchange_token = Column(Integer, nullable=False)
    tradingsymbol = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=True)
    last_price = Column(Numeric(10, 2), nullable=True)
    expiry = Column(DateTime, nullable=True)
    strike = Column(Numeric(10, 2), nullable=True)
    tick_size = Column(Numeric(10, 4), nullable=True)
    lot_size = Column(Integer, nullable=True)
    instrument_type = Column(String(10), nullable=True)
    segment = Column(String(20), nullable=True)
    exchange = Column(String(10), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index("idx_instrument_symbol", "tradingsymbol"),
        Index("idx_instrument_exchange", "exchange"),
        Index("idx_instrument_type", "instrument_type"),
    )

    def __repr__(self) -> str:
        return (
            f"<InstrumentMaster(token={self.instrument_token}, "
            f"symbol='{self.tradingsymbol}', exchange='{self.exchange}')>"
        )


class StrategyMetadata(Base):
    """Strategy metadata and configuration table."""

    __tablename__ = "strategy_metadata"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_name = Column(String(100), unique=True, nullable=False, index=True)
    strategy_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    config = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    risk_limits = Column(JSON, nullable=True)
    instruments = Column(JSON, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<StrategyMetadata(name='{self.strategy_name}', " f"type='{self.strategy_type}', active={self.is_active})>"
        )


class TradingSession(Base):
    """Trading session tracking table."""

    __tablename__ = "trading_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(100), nullable=False)
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    session_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return (
            f"<TradingSession(session_id='{self.session_id}', " f"user_id='{self.user_id}', active={self.is_active})>"
        )
