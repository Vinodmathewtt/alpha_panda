"""Risk management configuration settings."""

from decimal import Decimal
from typing import Dict, List
from pydantic import BaseModel, Field


class PositionLimitConfig(BaseModel):
    """Position limit configuration."""
    
    strategy_name: str = Field(..., description="Strategy name")
    max_value: Decimal = Field(..., description="Maximum position value")
    max_percentage: float = Field(..., description="Maximum percentage of portfolio")


class LossLimitConfig(BaseModel):
    """Loss limit configuration."""
    
    strategy_name: str = Field(..., description="Strategy name")
    max_daily_loss: Decimal = Field(..., description="Maximum daily loss")
    max_drawdown_pct: float = Field(..., description="Maximum drawdown percentage")


class RiskProfileConfig(BaseModel):
    """Risk profile configuration."""
    
    strategy_name: str = Field(..., description="Strategy name")
    position_limits: List[PositionLimitConfig] = Field(default_factory=list, description="Position limits")
    loss_limits: List[LossLimitConfig] = Field(default_factory=list, description="Loss limits")


class RiskConfig(BaseModel):
    """Risk management configuration."""
    
    # Global risk settings
    monitoring_enabled: bool = Field(default=True, description="Enable risk monitoring")
    monitoring_interval_seconds: int = Field(default=30, description="Risk monitoring interval in seconds")
    
    # Emergency stop settings
    emergency_stop_enabled: bool = Field(default=True, description="Enable emergency stop functionality")
    max_total_daily_loss: Decimal = Field(default=Decimal("50000"), description="Maximum total daily loss across all strategies")
    max_total_drawdown_pct: float = Field(default=25.0, description="Maximum total portfolio drawdown percentage")
    
    # Default risk profiles
    default_profiles: List[RiskProfileConfig] = Field(
        default=[
            RiskProfileConfig(
                strategy_name="default",
                position_limits=[
                    PositionLimitConfig(
                        strategy_name="default",
                        max_value=Decimal("100000"),  # 1L max position
                        max_percentage=10.0  # 10% of portfolio
                    )
                ],
                loss_limits=[
                    LossLimitConfig(
                        strategy_name="default",
                        max_daily_loss=Decimal("10000"),  # 10k daily loss limit
                        max_drawdown_pct=20.0  # 20% max drawdown
                    )
                ]
            ),
            RiskProfileConfig(
                strategy_name="conservative",
                position_limits=[
                    PositionLimitConfig(
                        strategy_name="conservative",
                        max_value=Decimal("50000"),  # 50k max position
                        max_percentage=5.0  # 5% of portfolio
                    )
                ],
                loss_limits=[
                    LossLimitConfig(
                        strategy_name="conservative",
                        max_daily_loss=Decimal("5000"),  # 5k daily loss limit
                        max_drawdown_pct=10.0  # 10% max drawdown
                    )
                ]
            ),
            RiskProfileConfig(
                strategy_name="aggressive",
                position_limits=[
                    PositionLimitConfig(
                        strategy_name="aggressive",
                        max_value=Decimal("200000"),  # 2L max position
                        max_percentage=20.0  # 20% of portfolio
                    )
                ],
                loss_limits=[
                    LossLimitConfig(
                        strategy_name="aggressive",
                        max_daily_loss=Decimal("20000"),  # 20k daily loss limit
                        max_drawdown_pct=30.0  # 30% max drawdown
                    )
                ]
            )
        ],
        description="Default risk profiles for different strategy types"
    )
    
    # Instrument-specific risk settings
    max_instrument_concentration_pct: float = Field(
        default=15.0, 
        description="Maximum concentration percentage for any single instrument"
    )
    
    # Volatility-based risk settings
    volatility_threshold_multiplier: float = Field(
        default=2.0,
        description="Volatility threshold multiplier for position sizing"
    )