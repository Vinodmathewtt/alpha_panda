# Complete tick formatting utilities for PyKiteConnect data capture
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from decimal import Decimal
import decimal


class TickFormatter:
    """Formats raw PyKiteConnect market data into complete standardized tick format"""
    
    def format_tick(self, raw_tick: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format complete raw tick data from PyKiteConnect into enhanced MarketTick format.
        Captures ALL available fields including market depth, volume, timing, and OI data.
        """
        
        # Core required fields
        formatted_tick = {
            "instrument_token": int(raw_tick["instrument_token"]),
            "last_price": Decimal(str(raw_tick["last_price"])),
            "timestamp": self._format_timestamp(raw_tick)
        }
        
        # Volume and quantity data (available in quote/full mode)
        if "volume_traded" in raw_tick:
            formatted_tick["volume_traded"] = int(raw_tick["volume_traded"])
        if "last_traded_quantity" in raw_tick:
            formatted_tick["last_traded_quantity"] = int(raw_tick["last_traded_quantity"])
        if "average_traded_price" in raw_tick:
            formatted_tick["average_traded_price"] = Decimal(str(raw_tick["average_traded_price"]))
        if "total_buy_quantity" in raw_tick:
            formatted_tick["total_buy_quantity"] = int(raw_tick["total_buy_quantity"])
        if "total_sell_quantity" in raw_tick:
            formatted_tick["total_sell_quantity"] = int(raw_tick["total_sell_quantity"])
        
        # Price movement data
        if "change" in raw_tick:
            formatted_tick["change"] = Decimal(str(raw_tick["change"]))
        
        # OHLC data (structured format)
        ohlc_data = self._format_ohlc(raw_tick.get("ohlc"))
        if ohlc_data:
            formatted_tick["ohlc"] = ohlc_data
        
        # Open Interest data (derivatives)
        if "oi" in raw_tick:
            formatted_tick["oi"] = int(raw_tick["oi"])
        if "oi_day_high" in raw_tick:
            formatted_tick["oi_day_high"] = int(raw_tick["oi_day_high"])
        if "oi_day_low" in raw_tick:
            formatted_tick["oi_day_low"] = int(raw_tick["oi_day_low"])
        
        # Timing data
        if "last_trade_time" in raw_tick:
            formatted_tick["last_trade_time"] = self._format_datetime(raw_tick["last_trade_time"])
        if "exchange_timestamp" in raw_tick:
            formatted_tick["exchange_timestamp"] = self._format_datetime(raw_tick["exchange_timestamp"])
        
        # Market depth (5-level order book) - CRITICAL for advanced strategies
        depth_data = self._format_market_depth(raw_tick.get("depth"))
        if depth_data:
            formatted_tick["depth"] = depth_data
        
        # Metadata
        if "mode" in raw_tick:
            formatted_tick["mode"] = str(raw_tick["mode"])
        if "tradable" in raw_tick:
            formatted_tick["tradable"] = bool(raw_tick["tradable"])
            
        return formatted_tick
    
    def _format_timestamp(self, raw_tick: Dict[str, Any]) -> datetime:
        """Format timestamp with UTC normalization and proper fallback hierarchy"""
        # Priority: exchange_timestamp > last_trade_time > current time
        timestamp = raw_tick.get("exchange_timestamp") or raw_tick.get("last_trade_time")
        
        if timestamp is None:
            # Always return timezone-aware UTC datetime
            return datetime.now(timezone.utc)
        
        return self._normalize_to_utc(timestamp)
    
    def _normalize_to_utc(self, dt_value: Any) -> datetime:
        """Normalize any datetime value to UTC."""
        if dt_value is None:
            return datetime.now(timezone.utc)
        
        if isinstance(dt_value, datetime):
            # If naive, assume UTC
            if dt_value.tzinfo is None:
                return dt_value.replace(tzinfo=timezone.utc)
            # If timezone-aware, convert to UTC
            return dt_value.astimezone(timezone.utc)
        
        elif isinstance(dt_value, str):
            try:
                parsed = datetime.fromisoformat(dt_value)
                return self._normalize_to_utc(parsed)
            except ValueError:
                try:
                    parsed = datetime.strptime(dt_value, "%Y-%m-%d %H:%M:%S")
                    return parsed.replace(tzinfo=timezone.utc)
                except ValueError:
                    return datetime.now(timezone.utc)
        
        return datetime.now(timezone.utc)

    def _format_datetime(self, dt_value: Any) -> Optional[datetime]:
        """Format datetime from various input formats with UTC normalization"""
        if dt_value is None:
            return None
        
        return self._normalize_to_utc(dt_value)
    
    def _format_ohlc(self, ohlc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Format OHLC data into structured format"""
        if not ohlc:
            return None
            
        try:
            return {
                "open": Decimal(str(ohlc["open"])),
                "high": Decimal(str(ohlc["high"])),
                "low": Decimal(str(ohlc["low"])),
                "close": Decimal(str(ohlc["close"]))
            }
        except (KeyError, ValueError, TypeError) as e:
            # Log error but don't fail the entire tick processing
            return None
    
    def _format_market_depth(self, depth: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Format complete 5-level market depth data.
        This is CRITICAL for advanced trading strategies that need order book visibility.
        """
        if not depth:
            return None
        
        try:
            formatted_depth = {
                "buy": [],
                "sell": []
            }
            
            # Format buy orders (bids) - up to 5 levels
            buy_orders = depth.get("buy", [])
            for order in buy_orders[:5]:  # Limit to 5 levels
                if self._is_valid_depth_order(order):
                    try:
                        formatted_depth["buy"].append({
                            "price": Decimal(str(order["price"])),
                            "quantity": int(order["quantity"]),
                            "orders": int(order["orders"])
                        })
                    except (ValueError, TypeError, decimal.InvalidOperation):
                        # Skip invalid depth level
                        continue
            
            # Format sell orders (asks) - up to 5 levels
            sell_orders = depth.get("sell", [])
            for order in sell_orders[:5]:  # Limit to 5 levels
                if self._is_valid_depth_order(order):
                    try:
                        formatted_depth["sell"].append({
                            "price": Decimal(str(order["price"])),
                            "quantity": int(order["quantity"]),
                            "orders": int(order["orders"])
                        })
                    except (ValueError, TypeError, decimal.InvalidOperation):
                        # Skip invalid depth level
                        continue
            
            # Return None if no valid depth data
            if not formatted_depth["buy"] and not formatted_depth["sell"]:
                return None
            
            return formatted_depth
            
        except (KeyError, ValueError, TypeError) as e:
            # Log error but don't fail the entire tick processing
            return None
    
    def _is_valid_depth_order(self, order: Dict[str, Any]) -> bool:
        """Validate that a depth order has required fields"""
        try:
            required_fields = ["price", "quantity", "orders"]
            return all(field in order and order[field] is not None for field in required_fields)
        except:
            return False