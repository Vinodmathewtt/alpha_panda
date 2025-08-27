"""Volume spike strategy for testing signal generation."""

from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timezone
from collections import deque

from strategy_manager.base_strategy import BaseStrategy
from strategy_manager.signal_types import TradingSignal, SignalType, SignalStrength, create_buy_signal, create_sell_signal


class VolumeSpikeStrategy(BaseStrategy):
    """Strategy that triggers on volume spikes for easy testing.
    
    This strategy generates signals when volume spikes significantly above average.
    It's designed to trigger frequently for testing the strategy framework.
    
    Strategy Logic:
    - Track rolling average volume for each instrument
    - Buy when volume spike occurs with price increase
    - Sell when volume spike occurs with price decrease
    - Exit positions after holding period or reverse signal
    """
    
    def __init__(self, strategy_name: str, config: Dict[str, Any]):
        super().__init__(strategy_name, config)
        
        # Strategy parameters - designed to trigger easily
        params = self.trading_params
        self.volume_spike_multiplier = params.get('volume_spike_multiplier', 2.0)  # 2x average volume
        self.volume_window_size = params.get('volume_window_size', 20)  # Rolling window
        self.min_price_change_pct = params.get('min_price_change_pct', 0.002)  # 0.2% minimum price move
        
        # Volume and price tracking
        self.volume_history: Dict[int, deque] = {}
        self.price_history: Dict[int, deque] = {}
        self.last_tick_volumes: Dict[int, int] = {}
        self.last_tick_prices: Dict[int, Decimal] = {}
        
        # Position sizing
        self.default_quantity = params.get('default_quantity', 3)
        self.max_position_per_instrument = params.get('max_position_per_instrument', 15)
        
        # Signal generation control
        self.signal_cooldown_seconds = params.get('signal_cooldown_seconds', 60)  # 1 minute cooldown
        self.holding_period_seconds = params.get('holding_period_seconds', 300)  # 5 minute holding
        self.last_signals: Dict[int, Dict[str, Any]] = {}
        
        self.logger.info(f"Volume spike strategy initialized: spike_multiplier={self.volume_spike_multiplier}x, "
                        f"window={self.volume_window_size}, cooldown={self.signal_cooldown_seconds}s")
    
    async def initialize(self):
        """Initialize strategy-specific components."""
        self.logger.info("Initializing volume spike strategy...")
        
        # Initialize tracking for all instruments
        for instrument_token in self.instruments:
            self.volume_history[instrument_token] = deque(maxlen=self.volume_window_size)
            self.price_history[instrument_token] = deque(maxlen=self.volume_window_size)
            self.last_tick_volumes[instrument_token] = 0
            self.last_tick_prices[instrument_token] = Decimal('0')
            self.last_signals[instrument_token] = {}
        
        self.logger.info("Volume spike strategy initialization completed")
    
    async def cleanup(self):
        """Cleanup strategy resources."""
        self.logger.info("Cleaning up volume spike strategy...")
        self.volume_history.clear()
        self.price_history.clear()
        self.last_tick_volumes.clear()
        self.last_tick_prices.clear()
        self.last_signals.clear()
    
    async def on_market_data(self, tick_data: Dict[str, Any]) -> Optional[TradingSignal]:
        """Process market data and generate volume spike signals."""
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')
        volume_traded = tick_data.get('volume_traded', 0)
        
        if not last_price or not instrument_token:
            return None
        
        current_price = Decimal(str(last_price))
        current_volume = int(volume_traded)
        
        # Calculate volume delta (change since last tick)
        last_volume = self.last_tick_volumes[instrument_token]
        volume_delta = max(0, current_volume - last_volume)  # Only positive deltas
        
        # Update volume and price history
        if volume_delta > 0:  # Only track when there's actual volume
            self.volume_history[instrument_token].append(volume_delta)
            self.price_history[instrument_token].append(current_price)
        
        # Update last tick tracking
        self.last_tick_volumes[instrument_token] = current_volume
        self.last_tick_prices[instrument_token] = current_price
        
        # Need enough history for analysis
        if len(self.volume_history[instrument_token]) < self.volume_window_size // 2:
            return None
        
        # Check signal cooldown and holding period
        if not self._can_generate_signal(instrument_token):
            return None
        
        # Check for exit conditions first
        exit_signal = self._check_exit_conditions(instrument_token, current_price)
        if exit_signal:
            return exit_signal
        
        # Check for volume spike entry signals
        signal = self._evaluate_volume_spike_signals(
            instrument_token,
            current_price,
            volume_delta,
            tick_data
        )
        
        if signal:
            # Update last signal tracking
            self.last_signals[instrument_token] = {
                'timestamp': datetime.now(timezone.utc),
                'signal_type': signal.signal_type,
                'price': current_price,
                'volume_delta': volume_delta
            }
        
        return signal
    
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
    
    def _check_exit_conditions(self, instrument_token: int, current_price: Decimal) -> Optional[TradingSignal]:
        """Check if we should exit current position."""
        current_position = self.get_position(instrument_token)
        
        if current_position == 0:
            return None
        
        last_signal = self.last_signals.get(instrument_token, {})
        if not last_signal or 'timestamp' not in last_signal:
            return None
        
        # Check holding period
        time_since_entry = (datetime.now(timezone.utc) - last_signal['timestamp']).total_seconds()
        
        if time_since_entry >= self.holding_period_seconds:
            # Exit due to holding period
            quantity = abs(int(current_position))
            
            # Get instrument info
            instrument_info = self.instrument_info.get(instrument_token, {})
            tradingsymbol = instrument_info.get('tradingsymbol', str(instrument_token))
            exchange = instrument_info.get('exchange', 'NSE')
            
            return TradingSignal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                signal_type=SignalType.EXIT,
                quantity=quantity,
                price=current_price,
                strength=SignalStrength.MODERATE,
                confidence=0.7,
                reason=f"Holding period exit: held for {time_since_entry:.0f}s"
            )
        
        return None
    
    def _calculate_average_volume(self, instrument_token: int) -> Decimal:
        """Calculate average volume from history."""
        volumes = list(self.volume_history[instrument_token])
        if not volumes:
            return Decimal('0')
        
        return Decimal(str(sum(volumes) / len(volumes)))
    
    def _calculate_price_change(self, instrument_token: int) -> Optional[Decimal]:
        """Calculate recent price change percentage."""
        prices = list(self.price_history[instrument_token])
        if len(prices) < 2:
            return None
        
        old_price = prices[-2]  # Previous price
        new_price = prices[-1]  # Current price
        
        if old_price == 0:
            return None
        
        return (new_price - old_price) / old_price
    
    def _evaluate_volume_spike_signals(
        self,
        instrument_token: int,
        current_price: Decimal,
        volume_delta: int,
        tick_data: Dict[str, Any]
    ) -> Optional[TradingSignal]:
        """Evaluate volume spike signal conditions."""
        
        current_position = self.get_position(instrument_token)
        
        # Get instrument info
        instrument_info = self.instrument_info.get(instrument_token, {})
        tradingsymbol = instrument_info.get('tradingsymbol', str(instrument_token))
        exchange = instrument_info.get('exchange', 'NSE')
        
        # Calculate average volume
        avg_volume = self._calculate_average_volume(instrument_token)
        if avg_volume == 0:
            return None
        
        # Check for volume spike
        volume_ratio = Decimal(str(volume_delta)) / avg_volume
        
        if volume_ratio < Decimal(str(self.volume_spike_multiplier)):
            return None  # No significant volume spike
        
        # Calculate price change
        price_change_pct = self._calculate_price_change(instrument_token)
        if price_change_pct is None:
            return None
        
        # Check minimum price movement
        if abs(price_change_pct) < Decimal(str(self.min_price_change_pct)):
            return None
        
        # Determine signal strength based on volume spike magnitude
        if volume_ratio >= Decimal(str(self.volume_spike_multiplier * 3)):
            strength = SignalStrength.VERY_STRONG
            confidence = 0.9
        elif volume_ratio >= Decimal(str(self.volume_spike_multiplier * 2)):
            strength = SignalStrength.STRONG
            confidence = 0.8
        elif volume_ratio >= Decimal(str(self.volume_spike_multiplier * 1.5)):
            strength = SignalStrength.MODERATE
            confidence = 0.7
        else:
            strength = SignalStrength.WEAK
            confidence = 0.6
        
        # Entry signal conditions
        buy_condition = (
            price_change_pct > 0 and  # Price increasing
            current_position <= 0 and  # No long position
            current_position >= -self.max_position_per_instrument
        )
        
        sell_condition = (
            price_change_pct < 0 and  # Price decreasing
            current_position >= 0 and  # No short position
            current_position <= self.max_position_per_instrument
        )
        
        # Generate appropriate signal
        if buy_condition:
            return create_buy_signal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                quantity=self.default_quantity,
                price=current_price,
                strength=strength,
                confidence=confidence,
                reason=f"Volume spike buy: {volume_ratio:.1f}x avg volume, price up {price_change_pct:.3f}%"
            )
        
        elif sell_condition:
            return create_sell_signal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                quantity=self.default_quantity,
                price=current_price,
                strength=strength,
                confidence=confidence,
                reason=f"Volume spike sell: {volume_ratio:.1f}x avg volume, price down {price_change_pct:.3f}%"
            )
        
        return None
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get strategy-specific information."""
        return {
            'strategy_type': 'Volume Spike',
            'description': 'Generates signals on volume spikes with price movement',
            'parameters': {
                'volume_spike_multiplier': self.volume_spike_multiplier,
                'volume_window_size': self.volume_window_size,
                'min_price_change_pct': self.min_price_change_pct,
                'default_quantity': self.default_quantity,
                'signal_cooldown_seconds': self.signal_cooldown_seconds,
                'holding_period_seconds': self.holding_period_seconds
            },
            'indicators_used': ['Volume average', 'Price change'],
            'signal_types': ['BUY', 'SELL', 'EXIT'],
            'timeframe': 'Tick-based with volume spike detection',
            'testing_focused': True
        }
    
    def get_debug_info(self, instrument_token: int) -> Dict[str, Any]:
        """Get debug information for a specific instrument."""
        if instrument_token not in self.volume_history:
            return {}
        
        avg_volume = self._calculate_average_volume(instrument_token)
        price_change_pct = self._calculate_price_change(instrument_token)
        last_volume_delta = 0
        
        # Get last volume delta
        last_signal = self.last_signals.get(instrument_token, {})
        if last_signal:
            last_volume_delta = last_signal.get('volume_delta', 0)
        
        volume_ratio = None
        if avg_volume > 0 and last_volume_delta > 0:
            volume_ratio = float(Decimal(str(last_volume_delta)) / avg_volume)
        
        return {
            'instrument_token': instrument_token,
            'current_price': float(self.last_tick_prices[instrument_token]),
            'current_volume': self.last_tick_volumes[instrument_token],
            'avg_volume': float(avg_volume),
            'last_volume_delta': last_volume_delta,
            'volume_ratio': volume_ratio,
            'price_change_pct': float(price_change_pct * 100) if price_change_pct else None,
            'position': float(self.get_position(instrument_token)),
            'volume_history_length': len(self.volume_history[instrument_token]),
            'price_history_length': len(self.price_history[instrument_token]),
            'thresholds': {
                'volume_spike_multiplier': self.volume_spike_multiplier,
                'min_price_change_pct': self.min_price_change_pct * 100
            },
            'last_signal': last_signal,
            'can_generate_signal': self._can_generate_signal(instrument_token)
        }
    
    async def on_signal_executed(self, signal: TradingSignal, execution_result: Dict[str, Any]):
        """Handle signal execution feedback."""
        await super().on_signal_executed(signal, execution_result)
        
        # Log execution with volume context
        self.logger.info(f"Volume spike signal executed: {signal.signal_type.value} "
                        f"{execution_result.get('quantity', 0)} {signal.tradingsymbol} "
                        f"@ {execution_result.get('average_price', 0)} "
                        f"(reason: {signal.reason})")