"""
Mock Zerodha API for Testing
Simulates Zerodha KiteConnect API responses for testing without actual broker connections.
CRITICAL: This is for testing only - never part of main application.
"""

import json
import random
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Callable
from unittest.mock import Mock
import websockets
from dataclasses import dataclass, asdict

from .realistic_data_generator import RealisticMarketDataGenerator


@dataclass
class MockOrder:
    """Mock order structure matching Zerodha order format"""
    order_id: str
    parent_order_id: Optional[str]
    exchange_order_id: Optional[str]
    placed_by: str
    variety: str
    status: str
    tradingsymbol: str
    exchange: str
    instrument_token: int
    product: str
    order_type: str
    transaction_type: str
    quantity: int
    filled_quantity: int
    pending_quantity: int
    price: float
    trigger_price: float
    average_price: float
    order_timestamp: str
    exchange_timestamp: Optional[str]
    status_message: Optional[str]
    tag: Optional[str]


@dataclass
class MockPosition:
    """Mock position structure matching Zerodha position format"""
    tradingsymbol: str
    exchange: str
    instrument_token: int
    product: str
    quantity: int
    overnight_quantity: int
    multiplier: float
    average_price: float
    close_price: float
    last_price: float
    value: float
    pnl: float
    m2m: float
    unrealised: float
    realised: float
    buy_quantity: int
    buy_price: float
    buy_value: float
    sell_quantity: int
    sell_price: float
    sell_value: float
    day_buy_quantity: int
    day_buy_price: float
    day_buy_value: float
    day_sell_quantity: int
    day_sell_price: float
    day_sell_value: float


class MockZerodhaAPI:
    """
    Mock implementation of Zerodha KiteConnect API for testing.
    Provides realistic responses without actual broker connection.
    """
    
    def __init__(self, api_key: str = "mock_api_key", access_token: str = "mock_access_token"):
        self.api_key = api_key
        self.access_token = access_token
        self.is_authenticated = False
        
        # Mock data stores
        self.orders: Dict[str, MockOrder] = {}
        self.positions: Dict[str, MockPosition] = {}
        self.portfolio = {}
        
        # Market data generator
        self.data_generator = RealisticMarketDataGenerator(seed=42)
        
        # Connection state
        self.is_connected = False
        self.websocket_callbacks: List[Callable] = []
        
        # Trading state
        self.order_counter = 1000
        self.margin_available = 100000.0  # ₹1 lakh available margin
        
        # Market hours simulation
        self.market_open = True
        
    def set_access_token(self, access_token: str):
        """Set access token (simulates authentication)"""
        self.access_token = access_token
        self.is_authenticated = True
        
    def login_url(self) -> str:
        """Return mock login URL"""
        return f"https://kite.trade/connect/login?api_key={self.api_key}&v=3"
        
    def generate_session(self, request_token: str, api_secret: str) -> Dict[str, Any]:
        """Mock session generation"""
        if not request_token or not api_secret:
            raise Exception("Invalid request token or API secret")
            
        return {
            "user_type": "individual",
            "email": "test@example.com",
            "user_name": "Test User",
            "user_shortname": "Test",
            "broker": "ZERODHA",
            "exchanges": ["NSE", "BSE", "NFO"],
            "products": ["CNC", "MIS", "NRML"],
            "order_types": ["MARKET", "LIMIT", "SL", "SL-M"],
            "avatar_url": None,
            "user_id": "TEST123",
            "api_key": self.api_key,
            "access_token": "mock_access_token_xyz",
            "public_token": "mock_public_token_abc",
            "enctoken": "mock_enc_token_def"
        }
        
    def profile(self) -> Dict[str, Any]:
        """Get user profile"""
        if not self.is_authenticated:
            raise Exception("Not authenticated")
            
        return {
            "user_id": "TEST123",
            "user_name": "Test User",
            "user_shortname": "Test",
            "email": "test@example.com",
            "user_type": "individual",
            "broker": "ZERODHA",
            "exchanges": ["NSE", "BSE", "NFO"],
            "products": ["CNC", "MIS", "NRML"],
            "order_types": ["MARKET", "LIMIT", "SL", "SL-M"]
        }
        
    def margins(self) -> Dict[str, Any]:
        """Get margins (simplified)"""
        if not self.is_authenticated:
            raise Exception("Not authenticated")
            
        return {
            "equity": {
                "enabled": True,
                "net": self.margin_available,
                "available": {
                    "adhoc_margin": 0,
                    "cash": self.margin_available * 0.8,
                    "opening_balance": self.margin_available,
                    "live_balance": self.margin_available,
                    "collateral": 0,
                    "intraday_payin": 0
                },
                "utilised": {
                    "debits": 0,
                    "exposure": 0,
                    "m2m_realised": 0,
                    "m2m_unrealised": 0,
                    "option_premium": 0,
                    "payout": 0,
                    "span": 0,
                    "holding_sales": 0,
                    "turnover": 0,
                    "liquid_collateral": 0,
                    "stock_collateral": 0
                }
            }
        }
        
    def place_order(self, variety: str, exchange: str, tradingsymbol: str,
                   transaction_type: str, quantity: int, product: str,
                   order_type: str, price: Optional[float] = None,
                   trigger_price: Optional[float] = None,
                   tag: Optional[str] = None) -> Dict[str, str]:
        """Place a mock order"""
        if not self.is_authenticated:
            raise Exception("Not authenticated")
            
        if not self.market_open:
            raise Exception("Market is closed")
            
        # Generate order ID
        order_id = f"MOCK{self.order_counter}"
        self.order_counter += 1
        
        # Get instrument token (simplified mapping)
        instrument_token = self._get_instrument_token(tradingsymbol)
        
        # Create mock order
        order = MockOrder(
            order_id=order_id,
            parent_order_id=None,
            exchange_order_id=f"EXC{order_id}",
            placed_by="TEST123",
            variety=variety,
            status="OPEN" if order_type == "LIMIT" else "COMPLETE",
            tradingsymbol=tradingsymbol,
            exchange=exchange,
            instrument_token=instrument_token,
            product=product,
            order_type=order_type,
            transaction_type=transaction_type,
            quantity=quantity,
            filled_quantity=quantity if order_type == "MARKET" else 0,
            pending_quantity=0 if order_type == "MARKET" else quantity,
            price=price or 0.0,
            trigger_price=trigger_price or 0.0,
            average_price=price or self._get_current_price(instrument_token),
            order_timestamp=datetime.now(timezone.utc).isoformat(),
            exchange_timestamp=datetime.now(timezone.utc).isoformat(),
            status_message=None,
            tag=tag
        )
        
        self.orders[order_id] = order
        
        # Update positions for market orders
        if order_type == "MARKET":
            self._update_position(order)
            
        return {"order_id": order_id}
        
    def orders(self) -> List[Dict[str, Any]]:
        """Get all orders"""
        if not self.is_authenticated:
            raise Exception("Not authenticated")
            
        return [asdict(order) for order in self.orders.values()]
        
    def order_history(self, order_id: str) -> List[Dict[str, Any]]:
        """Get order history"""
        if not self.is_authenticated:
            raise Exception("Not authenticated")
            
        if order_id not in self.orders:
            raise Exception(f"Order {order_id} not found")
            
        order = self.orders[order_id]
        return [asdict(order)]
        
    def positions(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get positions"""
        if not self.is_authenticated:
            raise Exception("Not authenticated")
            
        net_positions = []
        day_positions = []
        
        for position in self.positions.values():
            pos_dict = asdict(position)
            if position.overnight_quantity != 0:
                net_positions.append(pos_dict)
            if position.quantity != position.overnight_quantity:
                day_positions.append(pos_dict)
                
        return {
            "net": net_positions,
            "day": day_positions
        }
        
    def holdings(self) -> List[Dict[str, Any]]:
        """Get holdings (simplified)"""
        if not self.is_authenticated:
            raise Exception("Not authenticated")
            
        # Return empty holdings for simplicity
        return []
        
    def quote(self, instruments: List[str]) -> Dict[str, Dict[str, Any]]:
        """Get market quotes"""
        if not self.is_authenticated:
            raise Exception("Not authenticated")
            
        quotes = {}
        for instrument in instruments:
            if ":" in instrument:
                exchange, symbol = instrument.split(":", 1)
            else:
                exchange = "NSE"
                symbol = instrument
                
            instrument_token = self._get_instrument_token(symbol)
            current_price = self._get_current_price(instrument_token)
            
            quotes[instrument] = {
                "instrument_token": instrument_token,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "last_price": current_price,
                "volume": random.randint(1000, 100000),
                "buy_quantity": random.randint(100, 1000),
                "sell_quantity": random.randint(100, 1000),
                "ohlc": {
                    "open": current_price * random.uniform(0.99, 1.01),
                    "high": current_price * random.uniform(1.00, 1.02),
                    "low": current_price * random.uniform(0.98, 1.00),
                    "close": current_price
                },
                "net_change": random.uniform(-50, 50),
                "average_price": current_price * random.uniform(0.995, 1.005)
            }
            
        return quotes
        
    def cancel_order(self, variety: str, order_id: str) -> Dict[str, str]:
        """Cancel an order"""
        if not self.is_authenticated:
            raise Exception("Not authenticated")
            
        if order_id not in self.orders:
            raise Exception(f"Order {order_id} not found")
            
        order = self.orders[order_id]
        if order.status in ["COMPLETE", "CANCELLED"]:
            raise Exception(f"Cannot cancel order in {order.status} status")
            
        order.status = "CANCELLED"
        order.status_message = "Cancelled by user"
        
        return {"order_id": order_id}
        
    def modify_order(self, variety: str, order_id: str, **kwargs) -> Dict[str, str]:
        """Modify an order"""
        if not self.is_authenticated:
            raise Exception("Not authenticated")
            
        if order_id not in self.orders:
            raise Exception(f"Order {order_id} not found")
            
        order = self.orders[order_id]
        if order.status not in ["OPEN", "TRIGGER PENDING"]:
            raise Exception(f"Cannot modify order in {order.status} status")
            
        # Update modifiable fields
        if "quantity" in kwargs:
            order.quantity = kwargs["quantity"]
            order.pending_quantity = kwargs["quantity"] - order.filled_quantity
        if "price" in kwargs:
            order.price = kwargs["price"]
        if "trigger_price" in kwargs:
            order.trigger_price = kwargs["trigger_price"]
            
        return {"order_id": order_id}
        
    # WebSocket simulation methods
    def connect_websocket(self, callback: Callable):
        """Connect to mock WebSocket"""
        self.is_connected = True
        self.websocket_callbacks.append(callback)
        
    def subscribe_ticks(self, instrument_tokens: List[int]):
        """Subscribe to tick data"""
        if not self.is_connected:
            raise Exception("WebSocket not connected")
            
        # Start generating ticks for subscribed instruments
        asyncio.create_task(self._generate_websocket_ticks(instrument_tokens))
        
    async def _generate_websocket_ticks(self, instrument_tokens: List[int]):
        """Generate WebSocket ticks"""
        while self.is_connected:
            for token in instrument_tokens:
                try:
                    tick = self.data_generator.generate_tick(token)
                    
                    # Convert to WebSocket tick format
                    ws_tick = {
                        "instrument_token": tick.instrument_token,
                        "mode": "full",
                        "tradable": True,
                        "last_price": float(tick.last_price),
                        "last_quantity": tick.last_traded_quantity,
                        "average_price": float(tick.last_price) * random.uniform(0.995, 1.005),
                        "volume": tick.volume_traded,
                        "buy_quantity": tick.total_buy_quantity or 0,
                        "sell_quantity": tick.total_sell_quantity or 0,
                        "ohlc": {
                            "open": float(tick.ohlc["open"]) if tick.ohlc else float(tick.last_price),
                            "high": float(tick.ohlc["high"]) if tick.ohlc else float(tick.last_price),
                            "low": float(tick.ohlc["low"]) if tick.ohlc else float(tick.last_price),
                            "close": float(tick.ohlc["close"]) if tick.ohlc else float(tick.last_price)
                        },
                        "change": float(tick.change) if tick.change else 0.0,
                        "last_trade_time": tick.last_trade_time.isoformat() if tick.last_trade_time else None,
                        "timestamp": tick.timestamp.isoformat(),
                        "exchange_timestamp": tick.exchange_timestamp.isoformat() if tick.exchange_timestamp else None
                    }
                    
                    # Send to callbacks
                    for callback in self.websocket_callbacks:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback([ws_tick])
                            else:
                                callback([ws_tick])
                        except Exception as e:
                            print(f"Error in WebSocket callback: {e}")
                            
                except Exception as e:
                    print(f"Error generating tick for {token}: {e}")
                    
            # Wait before next batch of ticks
            await asyncio.sleep(random.uniform(0.1, 1.0))
            
    def disconnect_websocket(self):
        """Disconnect WebSocket"""
        self.is_connected = False
        self.websocket_callbacks.clear()
        
    # Helper methods
    def _get_instrument_token(self, symbol: str) -> int:
        """Get instrument token for symbol (simplified mapping)"""
        symbol_map = {
            "NIFTY 50": 256265,
            "NIFTY": 256265,
            "BANKNIFTY": 260105,
            "RELIANCE": 738561
        }
        return symbol_map.get(symbol, random.randint(100000, 999999))
        
    def _get_current_price(self, instrument_token: int) -> float:
        """Get current price for instrument"""
        if instrument_token in self.data_generator.current_prices:
            return float(self.data_generator.current_prices[instrument_token])
        return random.uniform(100, 5000)  # Random price for unknown instruments
        
    def _update_position(self, order: MockOrder):
        """Update position based on order"""
        key = f"{order.tradingsymbol}_{order.product}"
        
        if key not in self.positions:
            self.positions[key] = MockPosition(
                tradingsymbol=order.tradingsymbol,
                exchange=order.exchange,
                instrument_token=order.instrument_token,
                product=order.product,
                quantity=0,
                overnight_quantity=0,
                multiplier=1.0,
                average_price=0.0,
                close_price=order.average_price,
                last_price=order.average_price,
                value=0.0,
                pnl=0.0,
                m2m=0.0,
                unrealised=0.0,
                realised=0.0,
                buy_quantity=0,
                buy_price=0.0,
                buy_value=0.0,
                sell_quantity=0,
                sell_price=0.0,
                sell_value=0.0,
                day_buy_quantity=0,
                day_buy_price=0.0,
                day_buy_value=0.0,
                day_sell_quantity=0,
                day_sell_price=0.0,
                day_sell_value=0.0
            )
            
        position = self.positions[key]
        
        # Update position based on transaction type
        if order.transaction_type == "BUY":
            position.quantity += order.filled_quantity
            position.day_buy_quantity += order.filled_quantity
            position.buy_quantity += order.filled_quantity
            position.day_buy_value += order.filled_quantity * order.average_price
            position.buy_value += order.filled_quantity * order.average_price
            
        else:  # SELL
            position.quantity -= order.filled_quantity
            position.day_sell_quantity += order.filled_quantity
            position.sell_quantity += order.filled_quantity
            position.day_sell_value += order.filled_quantity * order.average_price
            position.sell_value += order.filled_quantity * order.average_price
            
        # Update average prices and P&L
        if position.buy_quantity > 0:
            position.buy_price = position.buy_value / position.buy_quantity
        if position.sell_quantity > 0:
            position.sell_price = position.sell_value / position.sell_quantity
        if position.day_buy_quantity > 0:
            position.day_buy_price = position.day_buy_value / position.day_buy_quantity
        if position.day_sell_quantity > 0:
            position.day_sell_price = position.day_sell_value / position.day_sell_quantity
            
        # Calculate P&L (simplified)
        if position.quantity != 0:
            position.average_price = (position.buy_value - position.sell_value) / abs(position.quantity)
            current_value = position.quantity * position.last_price
            invested_value = position.quantity * position.average_price
            position.unrealised = current_value - invested_value
            position.pnl = position.unrealised + position.realised
            
    # Simulation control methods
    def set_market_state(self, is_open: bool):
        """Set market open/close state"""
        self.market_open = is_open
        
    def simulate_order_fill(self, order_id: str, fill_quantity: Optional[int] = None):
        """Simulate partial or full order fill"""
        if order_id not in self.orders:
            return
            
        order = self.orders[order_id]
        if order.status != "OPEN":
            return
            
        fill_qty = fill_quantity or order.pending_quantity
        fill_qty = min(fill_qty, order.pending_quantity)
        
        order.filled_quantity += fill_qty
        order.pending_quantity -= fill_qty
        
        if order.pending_quantity == 0:
            order.status = "COMPLETE"
            
        # Update position
        self._update_position(order)
        
    def add_instrument(self, symbol: str, instrument_token: int, base_price: float):
        """Add custom instrument for testing"""
        from .realistic_data_generator import InstrumentConfig
        from decimal import Decimal
        
        self.data_generator.instruments[instrument_token] = InstrumentConfig(
            instrument_token=instrument_token,
            symbol=symbol,
            base_price=Decimal(str(base_price)),
            volatility=0.02,
            volume_base=10000,
            tick_size=Decimal("0.05"),
            lot_size=1
        )
        
        self.data_generator.current_prices[instrument_token] = Decimal(str(base_price))
        self.data_generator.cumulative_volumes[instrument_token] = 0
        self.data_generator.last_tick_time[instrument_token] = datetime.now(timezone.utc)