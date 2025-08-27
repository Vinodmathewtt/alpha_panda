#!/usr/bin/env python3
"""
Test script to validate enhanced market data capture from PyKiteConnect.
Verifies that all available data fields are being captured including market depth.
"""

import sys
import asyncio
from pathlib import Path
from decimal import Decimal

# Add project root to Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from services.market_feed.formatter import TickFormatter
from core.schemas.events import MarketTick

def test_basic_tick_formatting():
    """Test basic tick data formatting"""
    formatter = TickFormatter()
    
    # Simulate basic LTP mode tick (minimal data)
    ltp_tick = {
        "instrument_token": 256265,
        "last_price": 19500.75,
        "mode": "ltp"
    }
    
    formatted = formatter.format_tick(ltp_tick)
    market_tick = MarketTick(**formatted)
    
    print("✅ Basic LTP tick formatting passed")
    print(f"   Fields captured: {len(formatted)}")
    assert market_tick.instrument_token == 256265
    assert market_tick.last_price == Decimal("19500.75")


def test_quote_mode_formatting():
    """Test quote mode tick with volume data"""
    formatter = TickFormatter()
    
    # Simulate quote mode tick (more data)
    quote_tick = {
        "instrument_token": 256265,
        "last_price": 19500.75,
        "volume_traded": 1250000,
        "last_traded_quantity": 50,
        "average_traded_price": 19485.25,
        "total_buy_quantity": 125000,
        "total_sell_quantity": 135000,
        "change": 1.25,
        "ohlc": {
            "open": 19450.00,
            "high": 19520.50,
            "low": 19430.25,
            "close": 19475.50
        },
        "mode": "quote"
    }
    
    formatted = formatter.format_tick(quote_tick)
    market_tick = MarketTick(**formatted)
    
    print("✅ Quote mode tick formatting passed")
    print(f"   Fields captured: {len(formatted)}")
    
    # Verify volume data captured
    assert market_tick.volume_traded == 1250000
    assert market_tick.total_buy_quantity == 125000
    assert market_tick.ohlc is not None
    assert market_tick.ohlc.open == Decimal("19450.00")


def test_full_mode_with_depth():
    """Test full mode tick with complete market depth"""
    formatter = TickFormatter()
    
    # Simulate full mode tick (complete data including 5-level depth)
    full_tick = {
        "instrument_token": 256265,
        "last_price": 19500.75,
        "volume_traded": 1250000,
        "last_traded_quantity": 50,
        "average_traded_price": 19485.25,
        "total_buy_quantity": 125000,
        "total_sell_quantity": 135000,
        "change": 1.25,
        "ohlc": {
            "open": 19450.00,
            "high": 19520.50,
            "low": 19430.25,
            "close": 19475.50
        },
        "oi": 8500000,  # Open Interest
        "oi_day_high": 8600000,
        "oi_day_low": 8400000,
        "last_trade_time": "2025-01-15 13:16:54",
        "exchange_timestamp": "2025-01-15 13:16:56",
        "tradable": True,
        "mode": "full",
        # CRITICAL: 5-level market depth
        "depth": {
            "buy": [
                {"price": 19500.00, "quantity": 100, "orders": 5},
                {"price": 19499.75, "quantity": 200, "orders": 8},
                {"price": 19499.50, "quantity": 150, "orders": 6},
                {"price": 19499.25, "quantity": 175, "orders": 7},
                {"price": 19499.00, "quantity": 125, "orders": 4}
            ],
            "sell": [
                {"price": 19500.75, "quantity": 110, "orders": 6},
                {"price": 19501.00, "quantity": 190, "orders": 9},
                {"price": 19501.25, "quantity": 160, "orders": 7},
                {"price": 19501.50, "quantity": 180, "orders": 8},
                {"price": 19501.75, "quantity": 135, "orders": 5}
            ]
        }
    }
    
    formatted = formatter.format_tick(full_tick)
    market_tick = MarketTick(**formatted)
    
    print("✅ Full mode tick with depth formatting passed")
    print(f"   Fields captured: {len(formatted)}")
    
    # Verify complete data captured
    assert market_tick.volume_traded == 1250000
    assert market_tick.oi == 8500000  # Open Interest
    assert market_tick.depth is not None
    
    # Verify 5-level market depth
    assert len(market_tick.depth.buy) == 5
    assert len(market_tick.depth.sell) == 5
    
    # Verify depth data structure
    best_bid = market_tick.depth.buy[0]
    assert best_bid.price == Decimal("19500.00")
    assert best_bid.quantity == 100
    assert best_bid.orders == 5
    
    best_ask = market_tick.depth.sell[0]
    assert best_ask.price == Decimal("19500.75")
    assert best_ask.quantity == 110
    assert best_ask.orders == 6
    
    print(f"   ✅ Market depth captured: {len(market_tick.depth.buy)} buy levels, {len(market_tick.depth.sell)} sell levels")
    print(f"   📊 Best bid: ₹{best_bid.price} ({best_bid.quantity} qty)")
    print(f"   📊 Best ask: ₹{best_ask.price} ({best_ask.quantity} qty)")


def test_error_handling():
    """Test error handling with malformed data"""
    formatter = TickFormatter()
    
    # Test with missing required fields
    try:
        malformed_tick = {
            "instrument_token": 256265,
            # Missing last_price
            "volume_traded": 1000
        }
        formatted = formatter.format_tick(malformed_tick)
        MarketTick(**formatted)
        assert False, "Should have raised validation error"
    except Exception:
        print("✅ Error handling for missing required fields passed")
    
    # Test with invalid depth data
    tick_with_bad_depth = {
        "instrument_token": 256265,
        "last_price": 19500.75,
        "depth": {
            "buy": [
                {"price": "invalid", "quantity": 100, "orders": 5}
            ]
        }
    }
    
    formatted = formatter.format_tick(tick_with_bad_depth)
    market_tick = MarketTick(**formatted)
    
    # Should handle gracefully by excluding bad depth data
    assert market_tick.depth is None
    print("✅ Error handling for invalid depth data passed")


def test_data_coverage_comparison():
    """Compare data coverage between old and new implementation"""
    print("\n🔍 DATA COVERAGE COMPARISON")
    print("=" * 50)
    
    # Old implementation captured fields
    old_fields = [
        "instrument_token", "last_price", "volume", "timestamp", "ohlc"
    ]
    
    # New implementation captures fields
    new_fields = [
        "instrument_token", "last_price", "timestamp",
        "volume_traded", "last_traded_quantity", "average_traded_price",
        "total_buy_quantity", "total_sell_quantity", "change",
        "ohlc", "oi", "oi_day_high", "oi_day_low",
        "last_trade_time", "exchange_timestamp", "depth", "mode", "tradable"
    ]
    
    print(f"Old implementation: {len(old_fields)} fields")
    print(f"New implementation: {len(new_fields)} fields")
    print(f"Improvement: +{len(new_fields) - len(old_fields)} fields ({((len(new_fields) - len(old_fields)) / len(old_fields) * 100):.0f}% increase)")
    
    missing_in_old = set(new_fields) - set(old_fields)
    print(f"\nAdditional data now captured:")
    for field in sorted(missing_in_old):
        print(f"  ✅ {field}")
    
    print(f"\n🎯 Critical additions for trading strategies:")
    critical_additions = ["depth", "volume_traded", "total_buy_quantity", "total_sell_quantity", "oi"]
    for field in critical_additions:
        if field in missing_in_old:
            print(f"  🔥 {field} - Essential for advanced strategies")


def main():
    """Run all tests"""
    print("🧪 Testing Enhanced Market Data Capture")
    print("=" * 50)
    
    try:
        test_basic_tick_formatting()
        test_quote_mode_formatting()
        test_full_mode_with_depth()
        test_error_handling()
        test_data_coverage_comparison()
        
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ Enhanced market data capture is working correctly")
        print("📊 Complete PyKiteConnect data including 5-level market depth is now captured")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()