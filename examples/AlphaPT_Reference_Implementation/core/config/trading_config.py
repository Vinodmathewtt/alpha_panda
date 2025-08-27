"""Trading configuration settings."""

from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class TradingMode(str, Enum):
    """Trading mode types - DEPRECATED: Use individual engine flags instead."""

    PAPER = "paper"
    ZERODHA = "zerodha"  # Renamed from "live" to "zerodha"
    BACKTEST = "backtest"


class ProductType(str, Enum):
    """Product types for trading."""

    CNC = "CNC"  # Cash and Carry
    MIS = "MIS"  # Margin Intraday Squareoff
    NRML = "NRML"  # Normal


class OrderType(str, Enum):
    """Order types."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"
    SL_M = "SL-M"


class Exchange(str, Enum):
    """Supported exchanges."""

    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"
    BFO = "BFO"
    CDS = "CDS"
    MCX = "MCX"


class TradingConfig(BaseModel):
    """Trading configuration settings."""

    # Trading mode (DEPRECATED - use individual engine flags in main settings)
    mode: TradingMode = Field(default=TradingMode.PAPER, description="DEPRECATED: Use individual engine flags instead")

    # Zerodha/Kite settings
    kite_api_key: Optional[str] = Field(default=None, description="Kite API key")
    kite_api_secret: Optional[str] = Field(default=None, description="Kite API secret")
    kite_access_token: Optional[str] = Field(default=None, description="Kite access token")
    kite_request_token: Optional[str] = Field(default=None, description="Kite request token")
    kite_timeout: int = Field(default=7, description="Kite API timeout in seconds")
    kite_pool: bool = Field(default=True, description="Use connection pooling")
    kite_pool_block: bool = Field(default=False, description="Block connection pool")

    # WebSocket settings
    websocket_reconnect_attempts: int = Field(default=50, description="WebSocket reconnect attempts")
    websocket_reconnect_delay: float = Field(default=5.0, description="WebSocket reconnect delay")
    websocket_ping_interval: int = Field(default=30, description="WebSocket ping interval")
    websocket_ping_timeout: int = Field(default=5, description="WebSocket ping timeout")

    # Order management
    default_product: ProductType = Field(default=ProductType.MIS, description="Default product type")
    default_order_type: OrderType = Field(default=OrderType.MARKET, description="Default order type")
    default_validity: str = Field(default="DAY", description="Default order validity")
    default_variety: str = Field(default="regular", description="Default order variety")

    # Risk limits
    max_position_value: Decimal = Field(default=Decimal("100000"), description="Maximum position value")
    max_daily_loss: Decimal = Field(default=Decimal("10000"), description="Maximum daily loss")
    max_orders_per_minute: int = Field(default=10, description="Maximum orders per minute")
    max_orders_per_day: int = Field(default=1000, description="Maximum orders per day")

    # Position limits
    max_positions_per_strategy: int = Field(default=10, description="Maximum positions per strategy")
    max_exposure_per_instrument: Decimal = Field(
        default=Decimal("0.1"), description="Maximum exposure per instrument (as fraction)"
    )
    max_sector_exposure: Decimal = Field(default=Decimal("0.3"), description="Maximum sector exposure (as fraction)")

    # Supported exchanges
    supported_exchanges: List[Exchange] = Field(
        default=[Exchange.NSE, Exchange.BSE, Exchange.NFO], description="Supported exchanges"
    )

    # Strategy settings
    max_concurrent_strategies: int = Field(default=5, description="Maximum concurrent strategies")
    strategy_timeout: int = Field(default=60, description="Strategy execution timeout in seconds")
    strategy_health_check_interval: float = Field(default=30.0, description="Strategy health check interval")

    # Paper trading settings
    paper_initial_balance: Decimal = Field(default=Decimal("1000000"), description="Paper trading initial balance")
    paper_commission_per_order: Decimal = Field(default=Decimal("20"), description="Paper trading commission per order")
    paper_slippage_bps: int = Field(default=5, description="Paper trading slippage in basis points")
    paper_market_impact_bps: int = Field(default=2, description="Paper trading market impact in basis points")

    # Enhanced paper trading realism (new settings)
    paper_transaction_cost_percentage: Decimal = Field(
        default=Decimal("0.05"), description="Paper trading transaction cost percentage"
    )
    paper_slippage_percentage: Decimal = Field(default=Decimal("0.01"), description="Paper trading slippage percentage")
    paper_enable_stop_loss: bool = Field(default=True, description="Enable stop loss in paper trading")
    paper_default_stop_loss_percentage: Decimal = Field(
        default=Decimal("2.0"), description="Default stop loss percentage"
    )

    # Market data settings
    subscribe_to_all_instruments: bool = Field(default=False, description="Subscribe to all instruments")
    instrument_tokens: List[int] = Field(default_factory=list, description="List of instrument tokens to subscribe")
    market_data_modes: List[str] = Field(default=["ltp", "ohlc"], description="Market data modes")

    @field_validator("max_position_value", "max_daily_loss", mode="before")
    @classmethod
    def validate_decimal_fields(cls, v):
        """Validate decimal fields."""
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v

    @field_validator("instrument_tokens")
    @classmethod
    def validate_instrument_tokens(cls, v):
        """Validate instrument tokens."""
        if not isinstance(v, list):
            raise ValueError("instrument_tokens must be a list")
        return v

    def is_zerodha_trading(self) -> bool:
        """Check if Zerodha trading is enabled (renamed from live trading)."""
        return self.mode == TradingMode.ZERODHA

    def is_paper_trading(self) -> bool:
        """Check if paper trading is enabled."""
        return self.mode == TradingMode.PAPER

    def is_backtesting(self) -> bool:
        """Check if backtesting is enabled."""
        return self.mode == TradingMode.BACKTEST

    def get_kite_session_config(self) -> dict:
        """Get Kite session configuration."""
        return {
            "api_key": self.kite_api_key,
            "access_token": self.kite_access_token,
            "timeout": self.kite_timeout,
            "pool": self.kite_pool,
            "pool_block": self.kite_pool_block,
        }

    def get_websocket_config(self) -> dict:
        """Get WebSocket configuration."""
        return {
            "reconnect_attempts": self.websocket_reconnect_attempts,
            "reconnect_delay": self.websocket_reconnect_delay,
            "ping_interval": self.websocket_ping_interval,
            "ping_timeout": self.websocket_ping_timeout,
        }
