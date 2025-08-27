"""Market tick data models for mock market feed.

These models exactly replicate the zerodha market feed data structure
to ensure seamless compatibility during development and testing.
"""

import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


@dataclass
class DepthItem:
    """Market depth item (bid/ask level)."""
    price: float
    quantity: int
    orders: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "price": self.price,
            "quantity": self.quantity,
            "orders": self.orders
        }


@dataclass
class MarketDepth:
    """5-level market depth data."""
    buy: List[DepthItem] = field(default_factory=list)
    sell: List[DepthItem] = field(default_factory=list)
    
    def __post_init__(self):
        """Ensure we have 5 levels for each side."""
        # Pad with empty levels if needed
        while len(self.buy) < 5:
            self.buy.append(DepthItem(price=0.0, quantity=0, orders=0))
        while len(self.sell) < 5:
            self.sell.append(DepthItem(price=0.0, quantity=0, orders=0))
    
    def to_dict(self) -> Dict[str, List[Dict[str, Any]]]:
        """Convert to dictionary format."""
        return {
            "buy": [item.to_dict() for item in self.buy[:5]],
            "sell": [item.to_dict() for item in self.sell[:5]]
        }


@dataclass
class OHLCData:
    """OHLC price data."""
    open: float
    high: float
    low: float
    close: float
    
    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary format."""
        return {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close
        }


@dataclass
class MockTickData:
    """Mock market tick data that replicates Zerodha KiteConnect tick format."""
    
    # Core price data (mandatory fields)
    instrument_token: int
    last_price: float
    last_traded_quantity: int = 0
    average_traded_price: float = 0.0
    volume_traded: int = 0
    
    # Market sentiment indicators
    total_buy_quantity: int = 0
    total_sell_quantity: int = 0
    
    # OHLC data
    ohlc: Optional[OHLCData] = None
    
    # Full 5-level market depth
    depth: Optional[MarketDepth] = None
    
    # Open Interest (for F&O instruments)
    oi: int = 0
    oi_day_high: int = 0
    oi_day_low: int = 0
    
    # Price change indicators
    net_change: float = 0.0
    percentage_change: float = 0.0
    
    # Timestamp
    exchange_timestamp: Optional[datetime] = None
    
    # Exchange and trading status
    exchange: str = "NSE"
    tradable: bool = True
    mode: str = "full"  # full, ltp, quote
    
    # Additional metadata
    tradingsymbol: Optional[str] = None
    
    def __post_init__(self):
        """Initialize computed fields and defaults."""
        if self.exchange_timestamp is None:
            self.exchange_timestamp = datetime.now(timezone.utc)
        
        # Initialize OHLC with last_price if not provided
        if self.ohlc is None:
            self.ohlc = OHLCData(
                open=self.last_price,
                high=self.last_price,
                low=self.last_price,
                close=self.last_price
            )
        
        # Initialize empty market depth if not provided
        if self.depth is None:
            self.depth = MarketDepth()
            self._generate_realistic_depth()
    
    def _generate_realistic_depth(self):
        """Generate realistic market depth around last price."""
        if not self.depth or self.last_price <= 0:
            return
        
        # Generate bid side (buy orders below last price)
        tick_size = self._get_tick_size()
        base_price = self.last_price - tick_size
        
        for i in range(5):
            price = base_price - (i * tick_size)
            if price > 0:
                # Decreasing quantity as we go away from last price
                base_qty = max(100, int(self.last_traded_quantity * (1.2 - i * 0.2)))
                quantity = base_qty + (i * 50)  # Some randomness
                orders = max(1, quantity // 100)  # Realistic order count
                
                self.depth.buy[i] = DepthItem(price=price, quantity=quantity, orders=orders)
        
        # Generate ask side (sell orders above last price)
        base_price = self.last_price + tick_size
        
        for i in range(5):
            price = base_price + (i * tick_size)
            base_qty = max(100, int(self.last_traded_quantity * (1.2 - i * 0.2)))
            quantity = base_qty + (i * 50)
            orders = max(1, quantity // 100)
            
            self.depth.sell[i] = DepthItem(price=price, quantity=quantity, orders=orders)
    
    def _get_tick_size(self) -> float:
        """Get appropriate tick size based on price."""
        if self.last_price <= 0:
            return 0.05
        elif self.last_price < 100:
            return 0.05
        elif self.last_price < 1000:
            return 0.1
        elif self.last_price < 10000:
            return 0.5
        else:
            return 1.0
    
    def update_price(self, new_price: float, quantity: int = 0):
        """Update tick with new price and maintain OHLC consistency."""
        self.last_price = new_price
        self.last_traded_quantity = quantity or self.last_traded_quantity
        self.exchange_timestamp = datetime.now(timezone.utc)
        
        # Update OHLC
        if self.ohlc:
            self.ohlc.high = max(self.ohlc.high, new_price)
            self.ohlc.low = min(self.ohlc.low, new_price)
            self.ohlc.close = new_price
        
        # Update volume and average price
        if quantity > 0:
            old_value = self.average_traded_price * self.volume_traded
            self.volume_traded += quantity
            new_value = old_value + (new_price * quantity)
            self.average_traded_price = new_value / self.volume_traded if self.volume_traded > 0 else new_price
        
        # Update price change metrics
        if self.ohlc and self.ohlc.open > 0:
            self.net_change = new_price - self.ohlc.open
            self.percentage_change = (self.net_change / self.ohlc.open) * 100
        
        # Regenerate market depth around new price
        self._generate_realistic_depth()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format matching Zerodha KiteConnect tick format."""
        return {
            "instrument_token": self.instrument_token,
            "mode": self.mode,
            "tradable": self.tradable,
            "last_price": self.last_price,
            "last_quantity": self.last_traded_quantity,
            "average_price": self.average_traded_price,
            "volume": self.volume_traded,
            "buy_quantity": self.total_buy_quantity,
            "sell_quantity": self.total_sell_quantity,
            "ohlc": self.ohlc.to_dict() if self.ohlc else {},
            "net_change": self.net_change,
            "percentage_change": self.percentage_change,
            "oi": self.oi,
            "oi_day_high": self.oi_day_high,
            "oi_day_low": self.oi_day_low,
            "timestamp": self.exchange_timestamp.isoformat() if self.exchange_timestamp else None,
            "exchange": self.exchange,
            "depth": self.depth.to_dict() if self.depth else {"buy": [], "sell": []},
        }
    
    def to_zerodha_format(self) -> Dict[str, Any]:
        """Convert to exact Zerodha KiteConnect tick format."""
        # This ensures 100% compatibility with zerodha market feed
        return self.to_dict()
    
    @classmethod
    def from_base_instrument(
        cls, 
        instrument_token: int, 
        tradingsymbol: str,
        last_price: float,
        exchange: str = "NSE"
    ) -> "MockTickData":
        """Create mock tick from basic instrument information."""
        return cls(
            instrument_token=instrument_token,
            tradingsymbol=tradingsymbol,
            last_price=last_price,
            exchange=exchange,
            last_traded_quantity=100,  # Default realistic quantity
            volume_traded=1000,       # Default daily volume
        )


@dataclass
class InstrumentConfig:
    """Configuration for mock instrument behavior."""
    instrument_token: int
    tradingsymbol: str
    exchange: str = "NSE"
    base_price: float = 100.0
    volatility: float = 0.02  # 2% daily volatility
    trend: float = 0.0  # Trend bias (-1 to 1)
    liquidity: float = 1.0  # Liquidity multiplier
    tick_frequency: float = 1.0  # Ticks per second
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "instrument_token": self.instrument_token,
            "tradingsymbol": self.tradingsymbol,
            "exchange": self.exchange,
            "base_price": self.base_price,
            "volatility": self.volatility,
            "trend": self.trend,
            "liquidity": self.liquidity,
            "tick_frequency": self.tick_frequency,
        }