# Mean Reversion Strategy
from typing import Generator, List
from decimal import Decimal
from statistics import mean, stdev
from .base import BaseStrategy, MarketData
from core.schemas.events import SignalType, TradingSignal


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion strategy based on standard deviation bands"""
    
    def __init__(self, strategy_id: str, parameters: dict, brokers: List[str] = None, 
                 instrument_tokens: List[int] = None):
        super().__init__(strategy_id, parameters, brokers, instrument_tokens)
        self.lookback_period = parameters.get("lookback_period", 20)
        self.std_dev_threshold = parameters.get("std_dev_threshold", 2.0)
        self.position_size = parameters.get("position_size", 100)
        
    def on_market_data(self, data: MarketData) -> Generator[TradingSignal, None, None]:
        """Generate mean reversion trading signals"""
        
        # Add to history
        self._add_market_data(data)
        
        # Need enough history for mean reversion calculation
        if len(self._market_data_history) < self.lookback_period:
            return
            
        # Get recent prices
        recent_prices = [float(tick.last_price) for tick in self._market_data_history[-self.lookback_period:]]
        
        if len(recent_prices) < 2:
            return
            
        # Calculate mean and standard deviation
        price_mean = mean(recent_prices)
        price_std = stdev(recent_prices)
        
        if price_std == 0:
            return
            
        current_price = float(data.last_price)
        
        # Calculate z-score (how many standard deviations from mean)
        z_score = (current_price - price_mean) / price_std
        
        # Generate signals based on z-score
        if z_score > self.std_dev_threshold:
            # Price is too high - expect reversion down - SELL signal
            yield TradingSignal(
                strategy_id=self.strategy_id,
                instrument_token=data.instrument_token,
                signal_type=SignalType.SELL,
                quantity=self.position_size,
                price=data.last_price,
                timestamp=data.timestamp,
                confidence=min(float(abs(z_score) / 4), 1.0),  # Cap confidence at 1.0
                metadata={
                    "z_score": z_score,
                    "price_mean": price_mean,
                    "price_std": price_std,
                    "lookback_period": self.lookback_period,
                    "current_price": current_price
                }
            )
            
        elif z_score < -self.std_dev_threshold:
            # Price is too low - expect reversion up - BUY signal
            yield TradingSignal(
                strategy_id=self.strategy_id,
                instrument_token=data.instrument_token,
                signal_type=SignalType.BUY,
                quantity=self.position_size,
                price=data.last_price,
                timestamp=data.timestamp,
                confidence=min(float(abs(z_score) / 4), 1.0),  # Cap confidence at 1.0
                metadata={
                    "z_score": z_score,
                    "price_mean": price_mean,
                    "price_std": price_std,
                    "lookback_period": self.lookback_period,
                    "current_price": current_price
                }
            )