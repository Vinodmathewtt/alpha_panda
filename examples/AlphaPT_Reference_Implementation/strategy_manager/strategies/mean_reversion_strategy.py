"""Mean reversion strategy implementation."""

from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timezone
import statistics

from strategy_manager.base_strategy import BaseStrategy, TechnicalIndicatorMixin
from strategy_manager.signal_types import TradingSignal, SignalType, SignalStrength, create_buy_signal, create_sell_signal


class MeanReversionStrategy(BaseStrategy, TechnicalIndicatorMixin):
    """Mean reversion strategy based on price deviations from moving averages.
    
    This strategy identifies when prices deviate significantly from their
    moving average and generates signals expecting the price to revert to the mean.
    
    Strategy Logic:
    - Buy when price is significantly below the moving average (oversold)
    - Sell when price is significantly above the moving average (overbought)
    - Use Bollinger Band-like logic with standard deviation bands
    - Exit when price returns close to the moving average
    """
    
    def __init__(self, strategy_name: str, config: Dict[str, Any]):
        super().__init__(strategy_name, config)
        
        # Initialize price history if not already done by TechnicalIndicatorMixin
        if not hasattr(self, 'price_history'):
            self.price_history: Dict[int, List[Decimal]] = {}
        if not hasattr(self, 'volume_history'):
            self.volume_history: Dict[int, List[int]] = {}
        
        # Strategy parameters
        params = self.trading_params
        self.sma_period = params.get('sma_period', 50)
        self.deviation_threshold = params.get('deviation_threshold', 2.0)  # Standard deviations
        self.min_deviation_pct = params.get('min_deviation_pct', 0.01)  # 1%
        self.exit_threshold = params.get('exit_threshold', 0.5)  # Half the entry threshold
        
        # Volume filter
        self.min_volume_threshold = params.get('min_volume_threshold', 1000)
        
        # Position management
        self.default_quantity = params.get('default_quantity', 10)
        self.max_position_per_instrument = params.get('max_position_per_instrument', 50)
        
        # Signal management
        self.signal_cooldown_seconds = params.get('signal_cooldown_seconds', 600)  # 10 minutes
        self.last_signals: Dict[int, Dict[str, Any]] = {}
        
        # Additional state
        self.entry_prices: Dict[int, Decimal] = {}
        self.entry_sma: Dict[int, Decimal] = {}
        
        self.logger.info(f"Mean reversion strategy initialized: sma_period={self.sma_period}, "
                        f"deviation_threshold={self.deviation_threshold}")
    
    async def initialize(self):
        """Initialize strategy-specific components."""
        self.logger.info("Initializing mean reversion strategy...")
        
        # Initialize state for all instruments
        for instrument_token in self.instruments:
            self.price_history[instrument_token] = []
            self.last_signals[instrument_token] = {}
            self.entry_prices[instrument_token] = Decimal('0')
            self.entry_sma[instrument_token] = Decimal('0')
        
        self.logger.info("Mean reversion strategy initialization completed")
    
    async def cleanup(self):
        """Cleanup strategy resources."""
        self.logger.info("Cleaning up mean reversion strategy...")
        self.price_history.clear()
        self.last_signals.clear()
        self.entry_prices.clear()
        self.entry_sma.clear()
    
    async def on_market_data(self, tick_data: Dict[str, Any]) -> Optional[TradingSignal]:
        """Process market data and generate mean reversion signals."""
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')
        volume = tick_data.get('volume_traded', 0)
        
        if not last_price or not instrument_token:
            return None
        
        # Convert price to Decimal for precision
        current_price = Decimal(str(last_price))
        
        # Update price history
        self.update_price_history(instrument_token, current_price)
        
        # Check if we have enough data for analysis
        if len(self.price_history[instrument_token]) < self.sma_period:
            return None
        
        # Check minimum volume requirement
        if volume < self.min_volume_threshold:
            return None
        
        # Calculate moving average and standard deviation
        sma = self.get_sma(instrument_token, self.sma_period)
        if not sma:
            return None
        
        std_dev = self._calculate_standard_deviation(instrument_token)
        if not std_dev:
            return None
        
        # Calculate price deviation from mean
        price_deviation = current_price - sma
        deviation_in_std = price_deviation / std_dev if std_dev > 0 else Decimal('0')
        deviation_pct = abs(price_deviation) / sma
        
        # Check minimum deviation requirement
        if deviation_pct < Decimal(str(self.min_deviation_pct)):
            return None
        
        # Check signal cooldown
        if not self._can_generate_signal(instrument_token):
            return None
        
        # Generate signals based on mean reversion logic
        signal = self._evaluate_mean_reversion_signals(
            instrument_token,
            current_price,
            sma,
            deviation_in_std,
            deviation_pct,
            tick_data
        )
        
        if signal:
            # Record signal for cooldown and position tracking
            self.last_signals[instrument_token] = {
                'timestamp': datetime.now(timezone.utc),
                'signal_type': signal.signal_type,
                'price': current_price,
                'sma': sma,
                'deviation': deviation_in_std
            }
            
            # Record entry details for exit logic
            if signal.signal_type in [SignalType.BUY, SignalType.SELL]:
                self.entry_prices[instrument_token] = current_price
                self.entry_sma[instrument_token] = sma
        
        return signal
    
    def _calculate_standard_deviation(self, instrument_token: int) -> Optional[Decimal]:
        """Calculate standard deviation of recent prices."""
        prices = self.price_history[instrument_token]
        
        if len(prices) < self.sma_period:
            return None
        
        recent_prices = prices[-self.sma_period:]
        price_floats = [float(p) for p in recent_prices]
        
        try:
            std_dev = statistics.stdev(price_floats)
            return Decimal(str(std_dev))
        except Exception:
            return None
    
    def _can_generate_signal(self, instrument_token: int) -> bool:
        """Check if enough time has passed since last signal."""
        last_signal = self.last_signals.get(instrument_token, {})
        
        if not last_signal:
            return True
        
        last_time = last_signal.get('timestamp')
        if not last_time:
            return True
        
        time_diff = (datetime.now(timezone.utc) - last_time).total_seconds()
        return time_diff >= self.signal_cooldown_seconds
    
    def _evaluate_mean_reversion_signals(
        self,
        instrument_token: int,
        current_price: Decimal,
        sma: Decimal,
        deviation_in_std: Decimal,
        deviation_pct: Decimal,
        tick_data: Dict[str, Any]
    ) -> Optional[TradingSignal]:
        """Evaluate mean reversion signal conditions."""
        
        current_position = self.get_position(instrument_token)
        
        # Get instrument info
        instrument_info = self.instrument_info.get(instrument_token, {})
        tradingsymbol = instrument_info.get('tradingsymbol', str(instrument_token))
        exchange = instrument_info.get('exchange', 'NSE')
        
        # Determine signal strength based on deviation magnitude
        abs_deviation = abs(deviation_in_std)
        if abs_deviation >= self.deviation_threshold * 2:
            strength = SignalStrength.VERY_STRONG
        elif abs_deviation >= self.deviation_threshold * 1.5:
            strength = SignalStrength.STRONG
        elif abs_deviation >= self.deviation_threshold:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK
        
        # Mean reversion entry conditions
        oversold_condition = (
            deviation_in_std <= -self.deviation_threshold and  # Price significantly below SMA
            current_position >= -self.max_position_per_instrument  # Position limit
        )
        
        overbought_condition = (
            deviation_in_std >= self.deviation_threshold and   # Price significantly above SMA
            current_position <= self.max_position_per_instrument   # Position limit
        )
        
        # Exit conditions - price has reverted towards mean
        exit_long_condition = (
            current_position > 0 and
            deviation_in_std >= -self.exit_threshold  # Price back near or above SMA
        )
        
        exit_short_condition = (
            current_position < 0 and
            deviation_in_std <= self.exit_threshold   # Price back near or below SMA
        )
        
        # Stop loss conditions - price moved further away from mean
        stop_loss_long = (
            current_position > 0 and
            deviation_in_std <= -(self.deviation_threshold * 3)  # Price moved much further below
        )
        
        stop_loss_short = (
            current_position < 0 and
            deviation_in_std >= (self.deviation_threshold * 3)   # Price moved much further above
        )
        
        # Generate appropriate signal
        if exit_long_condition or exit_short_condition or stop_loss_long or stop_loss_short:
            # Exit existing position
            quantity = abs(int(current_position))
            if quantity > 0:
                exit_reason = "mean_reversion" if (exit_long_condition or exit_short_condition) else "stop_loss"
                return TradingSignal(
                    strategy_name=self.strategy_name,
                    instrument_token=instrument_token,
                    tradingsymbol=tradingsymbol,
                    exchange=exchange,
                    signal_type=SignalType.EXIT,
                    quantity=quantity,
                    price=current_price,
                    strength=strength,
                    confidence=0.8 if exit_reason == "mean_reversion" else 0.9,
                    reason=f"Exit ({exit_reason}): deviation={deviation_in_std:.2f}σ, "
                           f"price reverted towards SMA={sma}"
                )
        
        elif oversold_condition:
            # Buy signal - price oversold, expect reversion up
            confidence = min(0.95, 0.5 + (abs_deviation - self.deviation_threshold) * 0.2)
            return create_buy_signal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                quantity=self.default_quantity,
                price=current_price,
                strength=strength,
                confidence=confidence,
                reason=f"Oversold reversion buy: {deviation_in_std:.2f}σ below SMA, "
                       f"expecting reversion to {sma}"
            )
        
        elif overbought_condition:
            # Sell signal - price overbought, expect reversion down
            confidence = min(0.95, 0.5 + (abs_deviation - self.deviation_threshold) * 0.2)
            return create_sell_signal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                quantity=self.default_quantity,
                price=current_price,
                strength=strength,
                confidence=confidence,
                reason=f"Overbought reversion sell: {deviation_in_std:.2f}σ above SMA, "
                       f"expecting reversion to {sma}"
            )
        
        return None
    
    def get_bollinger_bands(self, instrument_token: int) -> Optional[Dict[str, Decimal]]:
        """Calculate Bollinger Band-like levels."""
        sma = self.get_sma(instrument_token, self.sma_period)
        std_dev = self._calculate_standard_deviation(instrument_token)
        
        if not sma or not std_dev:
            return None
        
        band_width = std_dev * Decimal(str(self.deviation_threshold))
        
        return {
            'upper_band': sma + band_width,
            'middle_band': sma,
            'lower_band': sma - band_width,
            'band_width': band_width * 2,
            'std_dev': std_dev
        }
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get strategy-specific information."""
        return {
            'strategy_type': 'Mean Reversion',
            'description': 'Mean reversion strategy using SMA and standard deviation bands',
            'parameters': {
                'sma_period': self.sma_period,
                'deviation_threshold': self.deviation_threshold,
                'min_deviation_pct': self.min_deviation_pct,
                'exit_threshold': self.exit_threshold,
                'default_quantity': self.default_quantity,
                'signal_cooldown_seconds': self.signal_cooldown_seconds
            },
            'indicators_used': ['SMA', 'Standard Deviation', 'Bollinger Band Logic'],
            'signal_types': ['BUY', 'SELL', 'EXIT'],
            'timeframe': 'Tick-based with SMA smoothing',
            'risk_management': ['Position limits', 'Stop loss at 3σ', 'Exit at mean reversion']
        }
    
    def get_debug_info(self, instrument_token: int) -> Dict[str, Any]:
        """Get debug information for a specific instrument."""
        if instrument_token not in self.price_history:
            return {}
        
        current_price = None
        sma = None
        std_dev = None
        bands = None
        deviation_in_std = None
        
        if self.price_history[instrument_token]:
            current_price = self.price_history[instrument_token][-1]
            sma = self.get_sma(instrument_token, self.sma_period)
            std_dev = self._calculate_standard_deviation(instrument_token)
            bands = self.get_bollinger_bands(instrument_token)
            
            if sma and std_dev:
                price_deviation = current_price - sma
                deviation_in_std = price_deviation / std_dev if std_dev > 0 else Decimal('0')
        
        return {
            'instrument_token': instrument_token,
            'current_price': float(current_price) if current_price else None,
            'sma': float(sma) if sma else None,
            'std_dev': float(std_dev) if std_dev else None,
            'deviation_in_std': float(deviation_in_std) if deviation_in_std else None,
            'bollinger_bands': {k: float(v) for k, v in bands.items()} if bands else None,
            'position': float(self.get_position(instrument_token)),
            'entry_price': float(self.entry_prices[instrument_token]),
            'entry_sma': float(self.entry_sma[instrument_token]),
            'price_history_length': len(self.price_history[instrument_token]),
            'last_signal': self.last_signals.get(instrument_token, {}),
            'can_generate_signal': self._can_generate_signal(instrument_token),
            'thresholds': {
                'entry_threshold': self.deviation_threshold,
                'exit_threshold': self.exit_threshold,
                'min_deviation_pct': self.min_deviation_pct
            }
        }
    
    async def on_signal_executed(self, signal: TradingSignal, execution_result: Dict[str, Any]):
        """Handle signal execution feedback."""
        await super().on_signal_executed(signal, execution_result)
        
        # Log execution with mean reversion context
        instrument_token = signal.instrument_token
        bands = self.get_bollinger_bands(instrument_token)
        
        self.logger.info(f"Mean reversion signal executed: {signal.signal_type.value} "
                        f"{execution_result.get('quantity', 0)} {signal.tradingsymbol} "
                        f"@ {execution_result.get('average_price', 0)} "
                        f"(bands: {bands['lower_band']:.2f}-{bands['upper_band']:.2f})" 
                        if bands else "")