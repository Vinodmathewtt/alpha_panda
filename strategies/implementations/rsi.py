"""
Simple RSI-based strategy implementation
Pure RSI signals without additional indicators
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal
import statistics
from core.schemas.events import MarketTick as MarketData
from strategies.core.protocols import StrategyProcessor, SignalResult
from core.logging import get_trading_logger_safe

logger = get_trading_logger_safe("rsi_strategy")


class RulesRSIProcessor:
    """
    Simple RSI-based strategy for pure momentum trading
    Generates signals based solely on RSI overbought/oversold levels
    """
    
    def __init__(self, rsi_period: int = 14, rsi_oversold: float = 30, 
                 rsi_overbought: float = 70, position_size: int = 100):
        """
        Initialize RSI strategy
        
        Args:
            rsi_period: Period for RSI calculation (default: 14)
            rsi_oversold: RSI level for buy signals (default: 30)
            rsi_overbought: RSI level for sell signals (default: 70)
            position_size: Base quantity for orders
        """
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.qty = position_size
        
        # Need extra data for reliable RSI calculation
        self.min_history = self.rsi_period * 2
        
        logger.info("Initialized RSI strategy",
                   rsi_period=self.rsi_period,
                   oversold=self.rsi_oversold,
                   overbought=self.rsi_overbought,
                   position_size=self.qty)
    
    def process_tick(self, tick: MarketData, history: List[MarketData]) -> Optional[SignalResult]:
        """
        Process market tick and generate RSI-based signals
        
        Strategy Logic:
        1. Calculate RSI over specified period
        2. Generate BUY when RSI < oversold threshold
        3. Generate SELL when RSI > overbought threshold
        """
        if len(history) < self.min_history:
            return None
            
        try:
            # Calculate RSI using recent history + current tick
            rsi = self._calculate_rsi(history[-self.rsi_period-1:] + [tick])
            if rsi is None:
                return None
            
            current_price = float(tick.last_price)
            
            # Generate signals based on RSI thresholds
            if rsi < self.rsi_oversold:
                # Oversold - BUY signal
                confidence = min(1.0, (self.rsi_oversold - rsi) / self.rsi_oversold)
                return SignalResult(
                    signal_type="BUY",
                    confidence=confidence,
                    quantity=self.qty,
                    price=Decimal(str(current_price)),
                    reasoning=f"RSI oversold: {rsi:.1f} < {self.rsi_oversold}"
                )
            elif rsi > self.rsi_overbought:
                # Overbought - SELL signal  
                confidence = min(1.0, (rsi - self.rsi_overbought) / (100 - self.rsi_overbought))
                return SignalResult(
                    signal_type="SELL",
                    confidence=confidence,
                    quantity=self.qty,
                    price=Decimal(str(current_price)),
                    reasoning=f"RSI overbought: {rsi:.1f} > {self.rsi_overbought}"
                )
            
            return None
            
        except (ValueError, IndexError, AttributeError) as e:
            logger.warning("Error processing RSI signal", error=str(e))
            return None
    
    def _calculate_rsi(self, price_data: List[MarketData]) -> Optional[float]:
        """
        Calculate RSI (Relative Strength Index)
        Uses exponential moving average for smoothing
        """
        if len(price_data) < 2:
            return None
            
        try:
            prices = [float(d.last_price) for d in price_data]
            gains = []
            losses = []
            
            # Calculate price changes
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
                
            # Use simple moving average for RSI calculation
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
        """RSI strategy supports all liquid instruments"""
        return True
    
    def get_strategy_name(self) -> str:
        """Return strategy identifier"""
        return "rsi"


def create_rsi_processor(config: Dict[str, Any]) -> RulesRSIProcessor:
    """
    Factory function to create RSI strategy processor
    
    Configuration parameters:
    - rsi_period: RSI calculation period (default: 14)
    - rsi_oversold: RSI oversold threshold (default: 30)
    - rsi_overbought: RSI overbought threshold (default: 70)
    - position_size: Order quantity (default: 100)
    """
    return RulesRSIProcessor(
        rsi_period=config.get("rsi_period", 14),
        rsi_oversold=config.get("rsi_oversold", 30),
        rsi_overbought=config.get("rsi_overbought", 70),
        position_size=config.get("position_size", 100)
    )
