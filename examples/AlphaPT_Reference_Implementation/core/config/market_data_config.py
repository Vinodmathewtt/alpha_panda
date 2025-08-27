"""Market data configuration settings."""

from typing import List
from pydantic import BaseModel, Field


class MarketDataConfig(BaseModel):
    """Market data configuration."""
    
    # Default instrument tokens for mock market feed
    default_instrument_tokens: List[int] = Field(
        default=[408065, 738561, 779521, 895745, 1270529],
        description="Default NSE instrument tokens for market data subscription"
    )
    
    # Mock market feed settings
    mock_tick_interval_ms: int = Field(
        default=1000,
        description="Mock market data tick interval in milliseconds"
    )
    
    # Market data quality settings
    max_price_change_percent: float = Field(
        default=10.0,
        description="Maximum allowed price change percentage for data quality validation"
    )
    
    min_volume_threshold: int = Field(
        default=100,
        description="Minimum volume threshold for data quality validation"
    )
    
    # Instrument mapping
    default_instrument_mapping: dict = Field(
        default={
            408065: {"symbol": "HDFCBANK", "exchange": "NSE", "lot_size": 550},
            738561: {"symbol": "RELIANCE", "exchange": "NSE", "lot_size": 505},
            779521: {"symbol": "TCS", "exchange": "NSE", "lot_size": 100},
            895745: {"symbol": "INFY", "exchange": "NSE", "lot_size": 300},
            1270529: {"symbol": "ICICIBANK", "exchange": "NSE", "lot_size": 1375}
        },
        description="Default instrument token to symbol mapping"
    )