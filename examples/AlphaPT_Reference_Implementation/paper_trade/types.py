"""Paper trading type definitions."""

from enum import Enum
from typing import Union
from decimal import Decimal


class OrderType(str, Enum):
    """Order types supported in paper trading."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "SL"
    STOP_LOSS_MARKET = "SL-M"
    TAKE_PROFIT = "TP"
    TAKE_PROFIT_MARKET = "TP-M"


class OrderStatus(str, Enum):
    """Order status states."""
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class OrderSide(str, Enum):
    """Order side (direction)."""
    BUY = "BUY"
    SELL = "SELL"


class TimeInForce(str, Enum):
    """Time in force options."""
    DAY = "DAY"
    IOC = "IOC"  # Immediate or Cancel
    GTD = "GTD"  # Good Till Date
    GTC = "GTC"  # Good Till Cancelled


class FillType(str, Enum):
    """Types of order fills."""
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"


class ProductType(str, Enum):
    """Product types for trading."""
    CNC = "CNC"  # Cash and Carry
    MIS = "MIS"  # Margin Intraday Squareoff
    NRML = "NRML"  # Normal (Margin)


class ExchangeType(str, Enum):
    """Exchange types."""
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    CDS = "CDS"
    MCX = "MCX"


# Type aliases
Price = Union[int, float, Decimal]
Quantity = Union[int, float]
Amount = Union[int, float, Decimal]