"""
Rule-based mean reversion strategy implementation
Uses RSI and Bollinger Bands for mean reversion signals
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal
import statistics
from core.schemas.events import MarketTick as MarketData
from strategies.core.protocols import StrategyProcessor, SignalResult
from core.logging import get_trading_logger_safe

logger = get_trading_logger_safe("mean_reversion_strategy")


class RulesMeanReversionProcessor:
    """
    Pure rule-based mean reversion strategy using technical indicators
    Combines RSI and Bollinger Bands for signal generation
    """
    
    def __init__(self, lookback_periods: int = 20, rsi_period: int = 14, 
                 rsi_oversold: float = 30, rsi_overbought: float = 70,
                 bollinger_std: float = 2.0, position_size: int = 100):
        """
        Initialize mean reversion strategy
        
        Args:
            lookback_periods: Periods for moving average and Bollinger Bands
            rsi_period: Period for RSI calculation
            rsi_oversold: RSI level indicating oversold condition (buy signal)
            rsi_overbought: RSI level indicating overbought condition (sell signal) 
            bollinger_std: Standard deviation multiplier for Bollinger Bands
            position_size: Base quantity for orders
        """
        self.lookback = lookback_periods
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_std = bollinger_std
        self.qty = position_size
        
        # Require longer history for RSI calculation
        self.min_history = max(self.lookback, self.rsi_period * 2)
        
        logger.info("Initialized rules-based mean reversion strategy",
                   lookback=self.lookback, rsi_period=self.rsi_period,
                   rsi_oversold=self.rsi_oversold, rsi_overbought=self.rsi_overbought,
                   position_size=self.qty)
    
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """
        Process market tick and generate mean reversion signals
        
        Strategy Logic:
        1. Calculate RSI over specified period
        2. Calculate Bollinger Bands (moving average ± standard deviations)
        3. Generate BUY when RSI < oversold AND price < lower Bollinger Band
        4. Generate SELL when RSI > overbought AND price > upper Bollinger Band
        """
        if len(history) < self.min_history:
            return None
            
        try:
            current_price = float(tick.last_price)
            prices = [float(h.last_price) for h in history[-self.lookback:]]
            
            # Calculate RSI
            rsi = self._calculate_rsi(history[-self.rsi_period-1:] + [tick])
            if rsi is None:
                return None
                
            # Calculate Bollinger Bands
            sma = statistics.mean(prices)
            std_dev = statistics.stdev(prices) if len(prices) > 1 else 0
            upper_band = sma + (self.bb_std * std_dev)
            lower_band = sma - (self.bb_std * std_dev)
            
            # Mean reversion signals
            if rsi < self.rsi_oversold and current_price < lower_band:
                # Oversold condition - BUY signal
                confidence = min(1.0, (self.rsi_oversold - rsi) / 20.0 + 
                               (lower_band - current_price) / lower_band)
                return SignalResult(
                    signal_type="BUY",
                    confidence=confidence,
                    quantity=self.qty,
                    price=Decimal(str(current_price)),
                    reasoning=f"Mean reversion BUY: RSI={rsi:.1f} (oversold), price below lower BB"
                )
            elif rsi > self.rsi_overbought and current_price > upper_band:
                # Overbought condition - SELL signal
                confidence = min(1.0, (rsi - self.rsi_overbought) / 20.0 + 
                               (current_price - upper_band) / upper_band)
                return SignalResult(
                    signal_type="SELL",
                    confidence=confidence,
                    quantity=self.qty,
                    price=Decimal(str(current_price)),
                    reasoning=f"Mean reversion SELL: RSI={rsi:.1f} (overbought), price above upper BB"
                )
            
            return None
            
        except (ValueError, IndexError, AttributeError, statistics.StatisticsError) as e:
            logger.warning("Error processing mean reversion signal", error=str(e))
            return None
    
    def _calculate_rsi(self, price_data: List[MarketData]) -> Optional[float]:
        """
        Calculate RSI (Relative Strength Index)
        
        RSI = 100 - (100 / (1 + RS))
        where RS = Average Gain / Average Loss
        """
        if len(price_data) < 2:
            return None
            
        try:
            prices = [float(d.last_price) for d in price_data]
            gains = []
            losses = []
            
            for i in range(1, len(prices)):
                change = prices[i] - prices[i-1]
                if change > 0:
                    gains.append(change)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(change))
            
            if len(gains) < self.rsi_period:
                return None
                
            # Calculate average gain and loss
            avg_gain = statistics.mean(gains[-self.rsi_period:])
            avg_loss = statistics.mean(losses[-self.rsi_period:])
            
            if avg_loss == 0:
                return 100.0  # No losses = maximum RSI
                
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except (ValueError, statistics.StatisticsError):
            return None
    
    def get_required_history_length(self) -> int:
        """Return required historical data length"""
        return self.min_history
    
    def supports_instrument(self, token: int) -> bool:
        """Mean reversion strategy supports all liquid instruments"""
        return True
    
    def get_strategy_name(self) -> str:
        """Return strategy identifier"""
        return "mean_reversion"


def create_mean_reversion_processor(config: Dict[str, Any]) -> RulesMeanReversionProcessor:
    """
    Factory function to create mean reversion strategy processor
    
    Configuration parameters:
    - lookback_periods: Moving average period (default: 20)
    - rsi_period: RSI calculation period (default: 14)
    - rsi_oversold: RSI oversold threshold (default: 30)
    - rsi_overbought: RSI overbought threshold (default: 70)
    - bollinger_std: Bollinger Band standard deviation (default: 2.0)
    - position_size: Order quantity (default: 100)
    """
    return RulesMeanReversionProcessor(
        lookback_periods=config.get("lookback_periods", 20),
        rsi_period=config.get("rsi_period", 14),
        rsi_oversold=config.get("rsi_oversold", 30),
        rsi_overbought=config.get("rsi_overbought", 70),
        bollinger_std=config.get("bollinger_std", 2.0),
        position_size=config.get("position_size", 100)
    )
