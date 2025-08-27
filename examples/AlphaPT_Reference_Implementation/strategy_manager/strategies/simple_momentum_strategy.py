"""Simple momentum strategy implementation."""

from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime, timezone

from strategy_manager.base_strategy import BaseStrategy, TechnicalIndicatorMixin
from strategy_manager.signal_types import TradingSignal, SignalType, SignalStrength, create_buy_signal, create_sell_signal


class SimpleMomentumStrategy(BaseStrategy, TechnicalIndicatorMixin):
    """Simple momentum strategy based on price trends and moving averages.
    
    This strategy identifies momentum by comparing current price to moving averages
    and generates buy/sell signals based on momentum strength and direction.
    
    Strategy Logic:
    - Buy when price is above short-term MA and showing strong upward momentum
    - Sell when price is below short-term MA and showing strong downward momentum
    - Use RSI to avoid overbought/oversold conditions
    """
    
    def __init__(self, strategy_name: str, config: Dict[str, Any]):
        super().__init__(strategy_name, config)
        
        # Initialize TechnicalIndicatorMixin explicitly
        self.price_history: Dict[int, List[Decimal]] = {}
        self.volume_history: Dict[int, List[int]] = {}
        
        # Strategy parameters
        params = self.trading_params
        self.short_ma_period = params.get('short_ma_period', 10)
        self.long_ma_period = params.get('long_ma_period', 30)
        self.momentum_threshold = params.get('momentum_threshold', 0.02)  # 2%
        self.rsi_period = params.get('rsi_period', 14)
        self.rsi_oversold = params.get('rsi_oversold', 30)
        self.rsi_overbought = params.get('rsi_overbought', 70)
        self.min_volume_threshold = params.get('min_volume_threshold', 1000)
        
        # Position sizing
        self.default_quantity = params.get('default_quantity', 10)
        self.max_position_per_instrument = params.get('max_position_per_instrument', 100)
        
        # State tracking
        self.last_signals: Dict[int, Dict[str, Any]] = {}
        self.signal_cooldown_seconds = params.get('signal_cooldown_seconds', 300)  # 5 minutes
        
        self.logger.info(f"Momentum strategy initialized: short_ma={self.short_ma_period}, "
                        f"long_ma={self.long_ma_period}, threshold={self.momentum_threshold}")
    
    async def initialize(self):
        """Initialize strategy-specific components."""
        self.logger.info("Initializing momentum strategy...")
        
        # Initialize price history for all instruments
        for instrument_token in self.instruments:
            self.price_history[instrument_token] = []
            self.last_signals[instrument_token] = {}
        
        self.logger.info("Momentum strategy initialization completed")
    
    async def cleanup(self):
        """Cleanup strategy resources."""
        self.logger.info("Cleaning up momentum strategy...")
        self.price_history.clear()
        self.last_signals.clear()
    
    async def on_market_data(self, tick_data: Dict[str, Any]) -> Optional[TradingSignal]:
        """Process market data and generate momentum-based signals."""
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
        if len(self.price_history[instrument_token]) < self.long_ma_period:
            return None
        
        # Check minimum volume requirement
        if volume < self.min_volume_threshold:
            return None
        
        # Calculate technical indicators
        short_ma = self.get_sma(instrument_token, self.short_ma_period)
        long_ma = self.get_sma(instrument_token, self.long_ma_period)
        rsi = self.get_rsi(instrument_token, self.rsi_period)
        
        if not short_ma or not long_ma or not rsi:
            return None
        
        # Calculate momentum
        momentum = self._calculate_momentum(instrument_token, current_price)
        if momentum is None:
            return None
        
        # Check signal cooldown
        if not self._can_generate_signal(instrument_token):
            return None
        
        # Generate trading signals based on momentum and technical indicators
        signal = self._evaluate_signal_conditions(
            instrument_token, 
            current_price, 
            short_ma, 
            long_ma, 
            momentum, 
            rsi,
            tick_data
        )
        
        if signal:
            # Record signal time for cooldown
            self.last_signals[instrument_token] = {
                'timestamp': datetime.now(timezone.utc),
                'signal_type': signal.signal_type,
                'price': current_price
            }
        
        return signal
    
    def _calculate_momentum(self, instrument_token: int, current_price: Decimal) -> Optional[Decimal]:
        """Calculate price momentum over the lookback period."""
        prices = self.price_history[instrument_token]
        
        lookback_period = self.trading_params.get('lookback_period', 20)
        if len(prices) < lookback_period:
            return None
        
        old_price = prices[-lookback_period]
        momentum = (current_price - old_price) / old_price
        
        return momentum
    
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
    
    def _evaluate_signal_conditions(
        self, 
        instrument_token: int,
        current_price: Decimal,
        short_ma: Decimal,
        long_ma: Decimal,
        momentum: Decimal,
        rsi: Decimal,
        tick_data: Dict[str, Any]
    ) -> Optional[TradingSignal]:
        """Evaluate conditions for generating trading signals."""
        
        current_position = self.get_position(instrument_token)
        
        # Get instrument info
        instrument_info = self.instrument_info.get(instrument_token, {})
        tradingsymbol = instrument_info.get('tradingsymbol', str(instrument_token))
        exchange = instrument_info.get('exchange', 'NSE')
        
        # Determine signal strength based on momentum magnitude
        momentum_abs = abs(momentum)
        if momentum_abs >= self.momentum_threshold * 2:
            strength = SignalStrength.VERY_STRONG
        elif momentum_abs >= self.momentum_threshold * 1.5:
            strength = SignalStrength.STRONG
        elif momentum_abs >= self.momentum_threshold:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK
        
        # Buy signal conditions
        buy_conditions = (
            current_price > short_ma and  # Price above short MA
            short_ma > long_ma and       # Short MA above long MA (uptrend)
            momentum >= self.momentum_threshold and  # Strong positive momentum
            rsi < self.rsi_overbought and  # Not overbought
            current_position < self.max_position_per_instrument  # Position limit
        )
        
        # Sell signal conditions
        sell_conditions = (
            current_price < short_ma and  # Price below short MA
            short_ma < long_ma and       # Short MA below long MA (downtrend)
            momentum <= -self.momentum_threshold and  # Strong negative momentum
            rsi > self.rsi_oversold and  # Not oversold
            current_position > -self.max_position_per_instrument  # Position limit
        )
        
        # Exit conditions for existing positions
        exit_long_conditions = (
            current_position > 0 and
            (current_price < short_ma or momentum <= -self.momentum_threshold * 0.5)
        )
        
        exit_short_conditions = (
            current_position < 0 and
            (current_price > short_ma or momentum >= self.momentum_threshold * 0.5)
        )
        
        # Generate appropriate signal
        if exit_long_conditions or exit_short_conditions:
            # Exit existing position
            quantity = abs(int(current_position))
            if quantity > 0:
                return TradingSignal(
                    strategy_name=self.strategy_name,
                    instrument_token=instrument_token,
                    tradingsymbol=tradingsymbol,
                    exchange=exchange,
                    signal_type=SignalType.EXIT,
                    quantity=quantity,
                    price=current_price,
                    strength=strength,
                    confidence=0.8,
                    reason=f"Exit signal: momentum={momentum:.4f}, price vs MA trend reversal"
                )
        
        elif buy_conditions and current_position <= 0:
            # Buy signal
            return create_buy_signal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                quantity=self.default_quantity,
                price=current_price,
                strength=strength,
                confidence=min(0.95, 0.6 + momentum_abs * 10),  # Higher confidence for stronger momentum
                reason=f"Buy signal: momentum={momentum:.4f}, MA trend up, RSI={rsi:.1f}"
            )
        
        elif sell_conditions and current_position >= 0:
            # Sell signal
            return create_sell_signal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                quantity=self.default_quantity,
                price=current_price,
                strength=strength,
                confidence=min(0.95, 0.6 + momentum_abs * 10),  # Higher confidence for stronger momentum
                reason=f"Sell signal: momentum={momentum:.4f}, MA trend down, RSI={rsi:.1f}"
            )
        
        return None
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get strategy-specific information."""
        return {
            'strategy_type': 'Simple Momentum',
            'description': 'Momentum strategy using moving averages and RSI',
            'parameters': {
                'short_ma_period': self.short_ma_period,
                'long_ma_period': self.long_ma_period,
                'momentum_threshold': float(self.momentum_threshold),
                'rsi_period': self.rsi_period,
                'rsi_oversold': self.rsi_oversold,
                'rsi_overbought': self.rsi_overbought,
                'default_quantity': self.default_quantity,
                'signal_cooldown_seconds': self.signal_cooldown_seconds
            },
            'indicators_used': ['SMA', 'RSI', 'Momentum'],
            'signal_types': ['BUY', 'SELL', 'EXIT'],
            'timeframe': 'Tick-based with MA smoothing'
        }
    
    async def on_signal_executed(self, signal: TradingSignal, execution_result: Dict[str, Any]):
        """Handle signal execution feedback."""
        await super().on_signal_executed(signal, execution_result)
        
        # Log execution details
        self.logger.info(f"Signal executed: {signal.signal_type.value} "
                        f"{execution_result.get('quantity', 0)} {signal.tradingsymbol} "
                        f"@ {execution_result.get('average_price', 0)}")
    
    def get_debug_info(self, instrument_token: int) -> Dict[str, Any]:
        """Get debug information for a specific instrument."""
        if instrument_token not in self.price_history:
            return {}
        
        current_price = None
        short_ma = None
        long_ma = None
        rsi = None
        momentum = None
        
        if self.price_history[instrument_token]:
            current_price = self.price_history[instrument_token][-1]
            short_ma = self.get_sma(instrument_token, self.short_ma_period)
            long_ma = self.get_sma(instrument_token, self.long_ma_period)
            rsi = self.get_rsi(instrument_token, self.rsi_period)
            momentum = self._calculate_momentum(instrument_token, current_price)
        
        return {
            'instrument_token': instrument_token,
            'current_price': float(current_price) if current_price else None,
            'short_ma': float(short_ma) if short_ma else None,
            'long_ma': float(long_ma) if long_ma else None,
            'rsi': float(rsi) if rsi else None,
            'momentum': float(momentum) if momentum else None,
            'position': float(self.get_position(instrument_token)),
            'price_history_length': len(self.price_history[instrument_token]),
            'last_signal': self.last_signals.get(instrument_token, {}),
            'can_generate_signal': self._can_generate_signal(instrument_token)
        }