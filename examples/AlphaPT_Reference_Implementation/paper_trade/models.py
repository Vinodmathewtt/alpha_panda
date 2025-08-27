"""Paper trading data models."""

from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from decimal import Decimal
import uuid

from .types import (
    OrderType,
    OrderStatus,
    OrderSide,
    TimeInForce,
    FillType,
    ProductType,
    ExchangeType,
    Price,
    Quantity,
    Amount
)


@dataclass
class OrderFill:
    """Represents an order fill (execution)."""
    fill_id: str
    order_id: str
    fill_type: FillType
    quantity: Quantity
    price: Price
    value: Amount
    commission: Amount = Decimal("0")
    timestamp: datetime = field(default_factory=datetime.utcnow)
    market_price: Optional[Price] = None
    slippage: Optional[Price] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PaperOrder:
    """Paper trading order model."""
    order_id: str
    strategy_name: str
    instrument_token: int
    tradingsymbol: str
    exchange: ExchangeType
    side: OrderSide
    order_type: OrderType
    product: ProductType
    quantity: Quantity
    price: Optional[Price] = None
    trigger_price: Optional[Price] = None
    disclosed_quantity: Optional[Quantity] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    tag: Optional[str] = None
    
    # Order state
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Quantity = 0
    pending_quantity: Optional[Quantity] = None
    average_price: Optional[Price] = None
    
    # Timestamps
    placed_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    
    # Order fills
    fills: List[OrderFill] = field(default_factory=list)
    
    # Metadata
    parent_order_id: Optional[str] = None
    notes: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization processing."""
        if self.pending_quantity is None:
            self.pending_quantity = self.quantity
    
    @property
    def is_buy(self) -> bool:
        """Check if this is a buy order."""
        return self.side == OrderSide.BUY
    
    @property
    def is_sell(self) -> bool:
        """Check if this is a sell order."""
        return self.side == OrderSide.SELL
    
    @property
    def is_market_order(self) -> bool:
        """Check if this is a market order."""
        return self.order_type == OrderType.MARKET
    
    @property
    def is_limit_order(self) -> bool:
        """Check if this is a limit order."""
        return self.order_type == OrderType.LIMIT
    
    @property
    def is_stop_order(self) -> bool:
        """Check if this is a stop order."""
        return self.order_type in [OrderType.STOP_LOSS, OrderType.STOP_LOSS_MARKET]
    
    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED
    
    @property
    def is_active(self) -> bool:
        """Check if order is active (can be filled)."""
        return self.status in [OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED]
    
    @property
    def total_value(self) -> Amount:
        """Get total value of filled quantity."""
        return sum(fill.value for fill in self.fills)
    
    @property
    def total_commission(self) -> Amount:
        """Get total commission paid."""
        return sum(fill.commission for fill in self.fills)
    
    def add_fill(self, fill: OrderFill) -> None:
        """Add a fill to this order."""
        self.fills.append(fill)
        self.filled_quantity += fill.quantity
        self.pending_quantity = self.quantity - self.filled_quantity
        
        # Update average price
        if self.fills:
            total_value = sum(f.value for f in self.fills)
            self.average_price = total_value / self.filled_quantity
        
        # Update status
        if self.filled_quantity >= self.quantity:
            self.status = OrderStatus.FILLED
            self.filled_at = fill.timestamp
        elif self.filled_quantity > 0:
            self.status = OrderStatus.PARTIALLY_FILLED
        
        self.updated_at = fill.timestamp
    
    def cancel(self) -> None:
        """Cancel this order."""
        if self.is_active:
            self.status = OrderStatus.CANCELLED
            self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "order_id": self.order_id,
            "strategy_name": self.strategy_name,
            "instrument_token": self.instrument_token,
            "tradingsymbol": self.tradingsymbol,
            "exchange": self.exchange.value,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "product": self.product.value,
            "quantity": float(self.quantity),
            "price": float(self.price) if self.price else None,
            "trigger_price": float(self.trigger_price) if self.trigger_price else None,
            "status": self.status.value,
            "filled_quantity": float(self.filled_quantity),
            "pending_quantity": float(self.pending_quantity) if self.pending_quantity else None,
            "average_price": float(self.average_price) if self.average_price else None,
            "placed_at": self.placed_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "total_value": float(self.total_value),
            "total_commission": float(self.total_commission),
            "fills_count": len(self.fills)
        }


@dataclass
class PaperPosition:
    """Paper trading position model."""
    strategy_name: str
    instrument_token: int
    tradingsymbol: str
    exchange: ExchangeType
    product: ProductType
    
    # Position details
    quantity: Quantity = 0
    average_price: Price = Decimal("0")
    last_price: Price = Decimal("0")
    
    # P&L calculations
    unrealized_pnl: Amount = Decimal("0")
    realized_pnl: Amount = Decimal("0")
    total_pnl: Amount = Decimal("0")
    
    # Day trading details
    day_buy_quantity: Quantity = 0
    day_buy_value: Amount = Decimal("0")
    day_sell_quantity: Quantity = 0
    day_sell_value: Amount = Decimal("0")
    
    # Overnight details
    overnight_quantity: Quantity = 0
    overnight_value: Amount = Decimal("0")
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
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
        """Check if position is flat (no quantity)."""
        return self.quantity == 0
    
    @property
    def market_value(self) -> Amount:
        """Get current market value of position."""
        return Decimal(str(self.quantity)) * Decimal(str(self.last_price))
    
    @property
    def cost_value(self) -> Amount:
        """Get cost value of position."""
        return Decimal(str(self.quantity)) * Decimal(str(self.average_price))
    
    def update_from_trade(
        self,
        side: OrderSide,
        quantity: Quantity,
        price: Price,
        is_day_trade: bool = True
    ) -> None:
        """Update position from a trade."""
        trade_value = Decimal(str(quantity)) * Decimal(str(price))
        
        if side == OrderSide.BUY:
            # Update day trading stats
            if is_day_trade:
                self.day_buy_quantity += quantity
                self.day_buy_value += trade_value
            
            if self.quantity >= 0:
                # Adding to long position or creating long from flat
                total_cost = self.cost_value + trade_value
                self.quantity += quantity
                self.average_price = total_cost / Decimal(str(self.quantity)) if self.quantity != 0 else Decimal("0")
            else:
                # Reducing short position
                if quantity >= abs(self.quantity):
                    # Closing short and potentially going long
                    realized_pnl_from_short = (Decimal(str(self.average_price)) - Decimal(str(price))) * abs(self.quantity)
                    self.realized_pnl += realized_pnl_from_short
                    
                    remaining_qty = quantity - abs(self.quantity)
                    self.quantity = remaining_qty
                    self.average_price = Decimal(str(price)) if remaining_qty > 0 else Decimal("0")
                else:
                    # Partially closing short
                    realized_pnl_from_partial = (Decimal(str(self.average_price)) - Decimal(str(price))) * quantity
                    self.realized_pnl += realized_pnl_from_partial
                    self.quantity += quantity  # quantity is negative for short
        
        else:  # SELL
            # Update day trading stats
            if is_day_trade:
                self.day_sell_quantity += quantity
                self.day_sell_value += trade_value
            
            if self.quantity <= 0:
                # Adding to short position or creating short from flat
                total_cost = abs(self.cost_value) + trade_value
                self.quantity -= quantity
                self.average_price = total_cost / abs(self.quantity) if self.quantity != 0 else Decimal("0")
            else:
                # Reducing long position
                if quantity >= self.quantity:
                    # Closing long and potentially going short
                    realized_pnl_from_long = (Decimal(str(price)) - Decimal(str(self.average_price))) * self.quantity
                    self.realized_pnl += realized_pnl_from_long
                    
                    remaining_qty = quantity - self.quantity
                    self.quantity = -remaining_qty
                    self.average_price = Decimal(str(price)) if remaining_qty > 0 else Decimal("0")
                else:
                    # Partially closing long
                    realized_pnl_from_partial = (Decimal(str(price)) - Decimal(str(self.average_price))) * quantity
                    self.realized_pnl += realized_pnl_from_partial
                    self.quantity -= quantity
        
        self.updated_at = datetime.utcnow()
    
    def update_market_price(self, price: Price) -> None:
        """Update last market price and unrealized P&L."""
        self.last_price = Decimal(str(price))
        
        if self.quantity != 0:
            if self.quantity > 0:
                # Long position
                self.unrealized_pnl = (self.last_price - Decimal(str(self.average_price))) * Decimal(str(self.quantity))
            else:
                # Short position
                self.unrealized_pnl = (Decimal(str(self.average_price)) - self.last_price) * abs(Decimal(str(self.quantity)))
        else:
            self.unrealized_pnl = Decimal("0")
        
        self.total_pnl = self.realized_pnl + self.unrealized_pnl
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "instrument_token": self.instrument_token,
            "tradingsymbol": self.tradingsymbol,
            "exchange": self.exchange.value,
            "product": self.product.value,
            "quantity": float(self.quantity),
            "average_price": float(self.average_price),
            "last_price": float(self.last_price),
            "market_value": float(self.market_value),
            "cost_value": float(self.cost_value),
            "unrealized_pnl": float(self.unrealized_pnl),
            "realized_pnl": float(self.realized_pnl),
            "total_pnl": float(self.total_pnl),
            "day_buy_quantity": float(self.day_buy_quantity),
            "day_buy_value": float(self.day_buy_value),
            "day_sell_quantity": float(self.day_sell_quantity),
            "day_sell_value": float(self.day_sell_value),
            "updated_at": self.updated_at.isoformat()
        }


@dataclass
class PaperTrade:
    """Represents a completed trade (matched buy/sell)."""
    trade_id: str
    strategy_name: str
    instrument_token: int
    tradingsymbol: str
    buy_order_id: str
    sell_order_id: str
    quantity: Quantity
    buy_price: Price
    sell_price: Price
    pnl: Amount
    commission: Amount = Decimal("0")
    trade_date: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def profit(self) -> Amount:
        """Get profit after commission."""
        return self.pnl - self.commission
    
    @property
    def return_pct(self) -> float:
        """Get return percentage."""
        cost = Decimal(str(self.quantity)) * Decimal(str(self.buy_price))
        if cost != 0:
            return float((self.profit / cost) * 100)
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "trade_id": self.trade_id,
            "strategy_name": self.strategy_name,
            "instrument_token": self.instrument_token,
            "tradingsymbol": self.tradingsymbol,
            "buy_order_id": self.buy_order_id,
            "sell_order_id": self.sell_order_id,
            "quantity": float(self.quantity),
            "buy_price": float(self.buy_price),
            "sell_price": float(self.sell_price),
            "pnl": float(self.pnl),
            "commission": float(self.commission),
            "profit": float(self.profit),
            "return_pct": self.return_pct,
            "trade_date": self.trade_date.isoformat()
        }


@dataclass
class PaperAccount:
    """Paper trading account model."""
    account_id: str
    strategy_name: str
    initial_capital: Amount
    current_capital: Amount
    available_margin: Amount
    used_margin: Amount = Decimal("0")
    unrealized_pnl: Amount = Decimal("0")
    realized_pnl: Amount = Decimal("0")
    total_pnl: Amount = Decimal("0")
    
    # Statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    max_profit: Amount = Decimal("0")
    max_loss: Amount = Decimal("0")
    max_drawdown: Amount = Decimal("0")
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def equity(self) -> Amount:
        """Get current equity (capital + unrealized P&L)."""
        return self.current_capital + self.unrealized_pnl
    
    @property
    def total_return(self) -> Amount:
        """Get total return."""
        return self.current_capital - self.initial_capital
    
    @property
    def total_return_pct(self) -> float:
        """Get total return percentage."""
        if self.initial_capital != 0:
            return float((self.total_return / self.initial_capital) * 100)
        return 0.0
    
    @property
    def win_rate(self) -> float:
        """Get win rate percentage."""
        if self.total_trades > 0:
            return (self.winning_trades / self.total_trades) * 100
        return 0.0
    
    @property
    def avg_profit(self) -> Amount:
        """Get average profit per trade."""
        if self.total_trades > 0:
            return self.total_pnl / self.total_trades
        return Decimal("0")
    
    def update_from_trade(self, trade: PaperTrade) -> None:
        """Update account from completed trade."""
        self.realized_pnl += trade.profit
        self.current_capital += trade.profit
        self.total_pnl = self.realized_pnl + self.unrealized_pnl
        
        # Update statistics
        self.total_trades += 1
        if trade.profit > 0:
            self.winning_trades += 1
            self.max_profit = max(self.max_profit, trade.profit)
        else:
            self.losing_trades += 1
            self.max_loss = min(self.max_loss, trade.profit)
        
        # Update drawdown
        peak_capital = max(self.current_capital, getattr(self, '_peak_capital', self.initial_capital))
        current_drawdown = peak_capital - self.current_capital
        self.max_drawdown = max(self.max_drawdown, current_drawdown)
        self._peak_capital = peak_capital
        
        self.updated_at = datetime.utcnow()
    
    def update_unrealized_pnl(self, unrealized_pnl: Amount) -> None:
        """Update unrealized P&L."""
        self.unrealized_pnl = unrealized_pnl
        self.total_pnl = self.realized_pnl + self.unrealized_pnl
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "account_id": self.account_id,
            "strategy_name": self.strategy_name,
            "initial_capital": float(self.initial_capital),
            "current_capital": float(self.current_capital),
            "equity": float(self.equity),
            "available_margin": float(self.available_margin),
            "used_margin": float(self.used_margin),
            "unrealized_pnl": float(self.unrealized_pnl),
            "realized_pnl": float(self.realized_pnl),
            "total_pnl": float(self.total_pnl),
            "total_return": float(self.total_return),
            "total_return_pct": self.total_return_pct,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "avg_profit": float(self.avg_profit),
            "max_profit": float(self.max_profit),
            "max_loss": float(self.max_loss),
            "max_drawdown": float(self.max_drawdown),
            "updated_at": self.updated_at.isoformat()
        }