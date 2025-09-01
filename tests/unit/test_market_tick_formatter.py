from datetime import datetime
from decimal import Decimal
from services.market_feed.formatter import TickFormatter


def test_tick_formatter_full_fields():
    fmt = TickFormatter()
    raw = {
        "instrument_token": 12345,
        "last_price": 125.5,
        "volume_traded": 1000,
        "last_traded_quantity": 50,
        "average_traded_price": 120.25,
        "total_buy_quantity": 5000,
        "total_sell_quantity": 4000,
        "change": 0.5,
        "ohlc": {"open": 120.0, "high": 130.0, "low": 119.0, "close": 124.0},
        "oi": 100,
        "oi_day_high": 120,
        "oi_day_low": 80,
        "last_trade_time": datetime.now(),
        "exchange_timestamp": datetime.now(),
        "mode": "full",
        "tradable": True,
        "depth": {
            "buy": [{"price": 125.0, "quantity": 100, "orders": 2}],
            "sell": [{"price": 126.0, "quantity": 90, "orders": 3}],
        },
    }
    out = fmt.format_tick(raw)
    assert out["instrument_token"] == 12345
    assert isinstance(out["last_price"], Decimal)
    assert out["volume_traded"] == 1000
    assert out["ohlc"]["open"] == Decimal("120.0")
    assert out["depth"]["buy"][0]["quantity"] == 100

