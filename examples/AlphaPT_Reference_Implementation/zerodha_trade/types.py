"""Zerodha trading type definitions."""

from enum import Enum
from typing import Union
from decimal import Decimal


class ZerodhaOrderType(str, Enum):
    """Zerodha order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"  # Stop Loss
    SL_M = "SL-M"  # Stop Loss Market


class ZerodhaOrderStatus(str, Enum):
    """Zerodha order status."""
    OPEN = "OPEN"
    COMPLETE = "COMPLETE"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    TRIGGER_PENDING = "TRIGGER PENDING"
    MODIFY_PENDING = "MODIFY PENDING"
    CANCEL_PENDING = "CANCEL PENDING"


class ZerodhaProductType(str, Enum):
    """Zerodha product types."""
    CNC = "CNC"  # Cash and Carry
    MIS = "MIS"  # Margin Intraday Squareoff
    NRML = "NRML"  # Normal (Margin)


class ZerodhaValidityType(str, Enum):
    """Zerodha order validity."""
    DAY = "DAY"
    IOC = "IOC"  # Immediate or Cancel
    TTL = "TTL"  # Time Till Logout


class ZerodhaVarietyType(str, Enum):
    """Zerodha order variety."""
    REGULAR = "regular"
    AMO = "amo"  # After Market Order
    BO = "bo"  # Bracket Order
    CO = "co"  # Cover Order
    ICEBERG = "iceberg"


class ZerodhaTransactionType(str, Enum):
    """Zerodha transaction types."""
    BUY = "BUY"
    SELL = "SELL"


class ZerodhaExchange(str, Enum):
    """Zerodha exchanges."""
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    CDS = "CDS"
    MCX = "MCX"


class ZerodhaInstrumentType(str, Enum):
    """Zerodha instrument types."""
    EQ = "EQ"  # Equity
    FUT = "FUT"  # Futures
    CE = "CE"  # Call Option
    PE = "PE"  # Put Option


# Type aliases for better readability
ZerodhaPrice = Union[int, float, Decimal]
ZerodhaQuantity = Union[int, float]
ZerodhaAmount = Union[int, float, Decimal]