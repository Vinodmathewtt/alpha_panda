"""Zerodha trading data models."""

from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from decimal import Decimal

from .types import (
    ZerodhaOrderType,
    ZerodhaOrderStatus,
    ZerodhaProductType,
    ZerodhaValidityType,
    ZerodhaVarietyType,
    ZerodhaTransactionType,
    ZerodhaExchange,
    ZerodhaInstrumentType,
    ZerodhaPrice,
    ZerodhaQuantity,
    ZerodhaAmount
)


@dataclass
class ZerodhaOrder:
    """Zerodha order model."""
    order_id: str
    strategy_name: str
    tradingsymbol: str
    exchange: ZerodhaExchange
    instrument_token: int
    transaction_type: ZerodhaTransactionType
    order_type: ZerodhaOrderType
    product: ZerodhaProductType
    variety: ZerodhaVarietyType
    quantity: ZerodhaQuantity
    price: Optional[ZerodhaPrice] = None
    trigger_price: Optional[ZerodhaPrice] = None
    validity: ZerodhaValidityType = ZerodhaValidityType.DAY
    disclosed_quantity: Optional[ZerodhaQuantity] = None
    tag: Optional[str] = None
    
    # Order state
    status: ZerodhaOrderStatus = ZerodhaOrderStatus.OPEN
    status_message: Optional[str] = None
    filled_quantity: ZerodhaQuantity = 0
    pending_quantity: Optional[ZerodhaQuantity] = None
    cancelled_quantity: ZerodhaQuantity = 0
    average_price: Optional[ZerodhaPrice] = None
    
    # Timestamps
    order_timestamp: datetime = field(default_factory=datetime.utcnow)
    exchange_timestamp: Optional[datetime] = None
    exchange_update_timestamp: Optional[datetime] = None
    
    # Additional Zerodha fields
    parent_order_id: Optional[str] = None
    placed_by: Optional[str] = None
    market_protection: int = 0
    guid: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization processing."""
        if self.pending_quantity is None:
            self.pending_quantity = self.quantity
    
    @property
    def is_buy(self) -> bool:
        """Check if this is a buy order."""
        return self.transaction_type == ZerodhaTransactionType.BUY
    
    @property
    def is_sell(self) -> bool:
        """Check if this is a sell order."""
        return self.transaction_type == ZerodhaTransactionType.SELL
    
    @property
    def is_complete(self) -> bool:
        """Check if order is completely filled."""
        return self.status == ZerodhaOrderStatus.COMPLETE
    
    @property
    def is_open(self) -> bool:
        """Check if order is open."""
        return self.status == ZerodhaOrderStatus.OPEN
    
    @property
    def is_cancelled(self) -> bool:
        """Check if order is cancelled."""
        return self.status == ZerodhaOrderStatus.CANCELLED
    
    @property
    def is_rejected(self) -> bool:
        """Check if order is rejected."""
        return self.status == ZerodhaOrderStatus.REJECTED
    
    @property
    def total_value(self) -> ZerodhaAmount:
        """Get total value of filled quantity."""
        if self.average_price and self.filled_quantity:
            return Decimal(str(self.filled_quantity)) * Decimal(str(self.average_price))
        return Decimal("0")
    
    def update_from_kite_order(self, kite_order: Dict[str, Any]) -> None:
        """Update order from Kite API response."""
        # Map Kite order fields to our model
        self.status = ZerodhaOrderStatus(kite_order.get("status", "OPEN"))
        self.status_message = kite_order.get("status_message")
        self.filled_quantity = kite_order.get("filled_quantity", 0)
        self.pending_quantity = kite_order.get("pending_quantity", self.quantity)
        self.cancelled_quantity = kite_order.get("cancelled_quantity", 0)
        self.average_price = kite_order.get("average_price")
        
        # Handle timestamps
        if kite_order.get("exchange_timestamp"):
            self.exchange_timestamp = datetime.fromisoformat(kite_order["exchange_timestamp"])
        if kite_order.get("exchange_update_timestamp"):
            self.exchange_update_timestamp = datetime.fromisoformat(kite_order["exchange_update_timestamp"])
        
        # Additional fields
        self.parent_order_id = kite_order.get("parent_order_id")
        self.placed_by = kite_order.get("placed_by")
        self.market_protection = kite_order.get("market_protection", 0)
        self.guid = kite_order.get("guid")
    
    def to_kite_params(self) -> Dict[str, Any]:
        """Convert to Kite API parameters."""
        params = {
            "tradingsymbol": self.tradingsymbol,
            "exchange": self.exchange.value,
            "transaction_type": self.transaction_type.value,
            "order_type": self.order_type.value,
            "product": self.product.value,
            "variety": self.variety.value,
            "quantity": int(self.quantity),
            "validity": self.validity.value
        }
        
        if self.price is not None:
            params["price"] = float(self.price)
        
        if self.trigger_price is not None:
            params["trigger_price"] = float(self.trigger_price)
        
        if self.disclosed_quantity is not None:
            params["disclosed_quantity"] = int(self.disclosed_quantity)
        
        if self.tag:
            params["tag"] = self.tag
        
        return params
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "order_id": self.order_id,
            "strategy_name": self.strategy_name,
            "tradingsymbol": self.tradingsymbol,
            "exchange": self.exchange.value,
            "instrument_token": self.instrument_token,
            "transaction_type": self.transaction_type.value,
            "order_type": self.order_type.value,
            "product": self.product.value,
            "variety": self.variety.value,
            "quantity": float(self.quantity),
            "price": float(self.price) if self.price else None,
            "trigger_price": float(self.trigger_price) if self.trigger_price else None,
            "validity": self.validity.value,
            "status": self.status.value,
            "status_message": self.status_message,
            "filled_quantity": float(self.filled_quantity),
            "pending_quantity": float(self.pending_quantity) if self.pending_quantity else None,
            "average_price": float(self.average_price) if self.average_price else None,
            "total_value": float(self.total_value),
            "order_timestamp": self.order_timestamp.isoformat(),
            "exchange_timestamp": self.exchange_timestamp.isoformat() if self.exchange_timestamp else None,
            "placed_by": self.placed_by,
            "tag": self.tag
        }


@dataclass
class ZerodhaPosition:
    """Zerodha position model."""
    strategy_name: str
    tradingsymbol: str
    exchange: ZerodhaExchange
    instrument_token: int
    product: ZerodhaProductType
    
    # Position details
    quantity: ZerodhaQuantity = 0
    overnight_quantity: ZerodhaQuantity = 0
    multiplier: int = 1
    average_price: ZerodhaPrice = Decimal("0")
    close_price: ZerodhaPrice = Decimal("0")
    last_price: ZerodhaPrice = Decimal("0")
    
    # P&L and values
    value: ZerodhaAmount = Decimal("0")
    pnl: ZerodhaAmount = Decimal("0")
    m2m: ZerodhaAmount = Decimal("0")  # Mark to market
    unrealised: ZerodhaAmount = Decimal("0")
    realised: ZerodhaAmount = Decimal("0")
    
    # Buy side
    buy_quantity: ZerodhaQuantity = 0
    buy_price: ZerodhaPrice = Decimal("0")
    buy_value: ZerodhaAmount = Decimal("0")
    buy_m2m: ZerodhaAmount = Decimal("0")
    
    # Sell side
    sell_quantity: ZerodhaQuantity = 0
    sell_price: ZerodhaPrice = Decimal("0")
    sell_value: ZerodhaAmount = Decimal("0")
    sell_m2m: ZerodhaAmount = Decimal("0")
    
    # Day trading
    day_buy_quantity: ZerodhaQuantity = 0
    day_buy_price: ZerodhaPrice = Decimal("0")
    day_buy_value: ZerodhaAmount = Decimal("0")
    day_sell_quantity: ZerodhaQuantity = 0
    day_sell_price: ZerodhaPrice = Decimal("0")
    day_sell_value: ZerodhaAmount = Decimal("0")
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0
    
    @property
    def is_flat(self) -> bool:
        """Check if position is flat."""
        return self.quantity == 0
    
    @property
    def net_quantity(self) -> ZerodhaQuantity:
        """Get net quantity (buy - sell)."""
        return self.buy_quantity - self.sell_quantity
    
    def update_from_kite_position(self, kite_position: Dict[str, Any]) -> None:
        """Update position from Kite API response."""
        self.quantity = kite_position.get("quantity", 0)
        self.overnight_quantity = kite_position.get("overnight_quantity", 0)
        self.multiplier = kite_position.get("multiplier", 1)
        self.average_price = Decimal(str(kite_position.get("average_price", 0)))
        self.close_price = Decimal(str(kite_position.get("close_price", 0)))
        self.last_price = Decimal(str(kite_position.get("last_price", 0)))
        
        # P&L values
        self.value = Decimal(str(kite_position.get("value", 0)))
        self.pnl = Decimal(str(kite_position.get("pnl", 0)))
        self.m2m = Decimal(str(kite_position.get("m2m", 0)))
        self.unrealised = Decimal(str(kite_position.get("unrealised", 0)))
        self.realised = Decimal(str(kite_position.get("realised", 0)))
        
        # Buy side
        self.buy_quantity = kite_position.get("buy_quantity", 0)
        self.buy_price = Decimal(str(kite_position.get("buy_price", 0)))
        self.buy_value = Decimal(str(kite_position.get("buy_value", 0)))
        self.buy_m2m = Decimal(str(kite_position.get("buy_m2m", 0)))
        
        # Sell side
        self.sell_quantity = kite_position.get("sell_quantity", 0)
        self.sell_price = Decimal(str(kite_position.get("sell_price", 0)))
        self.sell_value = Decimal(str(kite_position.get("sell_value", 0)))
        self.sell_m2m = Decimal(str(kite_position.get("sell_m2m", 0)))
        
        # Day trading
        self.day_buy_quantity = kite_position.get("day_buy_quantity", 0)
        self.day_buy_price = Decimal(str(kite_position.get("day_buy_price", 0)))
        self.day_buy_value = Decimal(str(kite_position.get("day_buy_value", 0)))
        self.day_sell_quantity = kite_position.get("day_sell_quantity", 0)
        self.day_sell_price = Decimal(str(kite_position.get("day_sell_price", 0)))
        self.day_sell_value = Decimal(str(kite_position.get("day_sell_value", 0)))
        
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "tradingsymbol": self.tradingsymbol,
            "exchange": self.exchange.value,
            "instrument_token": self.instrument_token,
            "product": self.product.value,
            "quantity": float(self.quantity),
            "overnight_quantity": float(self.overnight_quantity),
            "average_price": float(self.average_price),
            "close_price": float(self.close_price),
            "last_price": float(self.last_price),
            "value": float(self.value),
            "pnl": float(self.pnl),
            "m2m": float(self.m2m),
            "unrealised": float(self.unrealised),
            "realised": float(self.realised),
            "buy_quantity": float(self.buy_quantity),
            "buy_price": float(self.buy_price),
            "buy_value": float(self.buy_value),
            "sell_quantity": float(self.sell_quantity),
            "sell_price": float(self.sell_price),
            "sell_value": float(self.sell_value),
            "day_buy_quantity": float(self.day_buy_quantity),
            "day_sell_quantity": float(self.day_sell_quantity),
            "net_quantity": float(self.net_quantity),
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class ZerodhaAccount:
    """Zerodha account model."""
    strategy_name: str
    user_id: str
    
    # Margins
    equity_enabled: bool = True
    equity_net: ZerodhaAmount = Decimal("0")
    equity_available_cash: ZerodhaAmount = Decimal("0")
    equity_utilised_debits: ZerodhaAmount = Decimal("0")
    equity_utilised_exposure: ZerodhaAmount = Decimal("0")
    
    commodity_enabled: bool = False
    commodity_net: ZerodhaAmount = Decimal("0")
    commodity_available_cash: ZerodhaAmount = Decimal("0")
    commodity_utilised_debits: ZerodhaAmount = Decimal("0")
    commodity_utilised_exposure: ZerodhaAmount = Decimal("0")
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def update_from_kite_margins(self, kite_margins: Dict[str, Any]) -> None:
        """Update account from Kite margins API response."""
        # Equity margins
        equity = kite_margins.get("equity", {})
        self.equity_enabled = equity.get("enabled", True)
        self.equity_net = Decimal(str(equity.get("net", 0)))
        self.equity_available_cash = Decimal(str(equity.get("available", {}).get("cash", 0)))
        self.equity_utilised_debits = Decimal(str(equity.get("utilised", {}).get("debits", 0)))
        self.equity_utilised_exposure = Decimal(str(equity.get("utilised", {}).get("exposure", 0)))
        
        # Commodity margins
        commodity = kite_margins.get("commodity", {})
        self.commodity_enabled = commodity.get("enabled", False)
        self.commodity_net = Decimal(str(commodity.get("net", 0)))
        self.commodity_available_cash = Decimal(str(commodity.get("available", {}).get("cash", 0)))
        self.commodity_utilised_debits = Decimal(str(commodity.get("utilised", {}).get("debits", 0)))
        self.commodity_utilised_exposure = Decimal(str(commodity.get("utilised", {}).get("exposure", 0)))
        
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "user_id": self.user_id,
            "equity": {
                "enabled": self.equity_enabled,
                "net": float(self.equity_net),
                "available_cash": float(self.equity_available_cash),
                "utilised_debits": float(self.equity_utilised_debits),
                "utilised_exposure": float(self.equity_utilised_exposure)
            },
            "commodity": {
                "enabled": self.commodity_enabled,
                "net": float(self.commodity_net),
                "available_cash": float(self.commodity_available_cash),
                "utilised_debits": float(self.commodity_utilised_debits),
                "utilised_exposure": float(self.commodity_utilised_exposure)
            },
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class ZerodhaTrade:
    """Zerodha trade model."""
    trade_id: str
    strategy_name: str
    order_id: str
    exchange_order_id: str
    tradingsymbol: str
    exchange: ZerodhaExchange
    instrument_token: int
    transaction_type: ZerodhaTransactionType
    product: ZerodhaProductType
    quantity: ZerodhaQuantity
    price: ZerodhaPrice
    value: ZerodhaAmount
    
    # Trade details
    fill_timestamp: datetime
    exchange_timestamp: Optional[datetime] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_from_kite_trade(self, kite_trade: Dict[str, Any]) -> None:
        """Update trade from Kite API response."""
        self.exchange_order_id = kite_trade.get("exchange_order_id", "")
        self.quantity = kite_trade.get("quantity", 0)
        self.price = Decimal(str(kite_trade.get("price", 0)))
        self.value = Decimal(str(kite_trade.get("value", 0)))
        
        # Handle timestamps
        if kite_trade.get("fill_timestamp"):
            self.fill_timestamp = datetime.fromisoformat(kite_trade["fill_timestamp"])
        if kite_trade.get("exchange_timestamp"):
            self.exchange_timestamp = datetime.fromisoformat(kite_trade["exchange_timestamp"])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trade_id": self.trade_id,
            "strategy_name": self.strategy_name,
            "order_id": self.order_id,
            "exchange_order_id": self.exchange_order_id,
            "tradingsymbol": self.tradingsymbol,
            "exchange": self.exchange.value,
            "instrument_token": self.instrument_token,
            "transaction_type": self.transaction_type.value,
            "product": self.product.value,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "value": float(self.value),
            "fill_timestamp": self.fill_timestamp.isoformat(),
            "exchange_timestamp": self.exchange_timestamp.isoformat() if self.exchange_timestamp else None
        }