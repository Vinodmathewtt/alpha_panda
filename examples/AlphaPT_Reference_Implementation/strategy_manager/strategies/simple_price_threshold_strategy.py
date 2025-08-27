"""Simple price threshold strategy for testing signal generation."""

from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timezone

from strategy_manager.base_strategy import BaseStrategy
from strategy_manager.signal_types import TradingSignal, SignalType, SignalStrength, create_buy_signal, create_sell_signal


class SimplePriceThresholdStrategy(BaseStrategy):
    """Simple strategy that triggers on price thresholds for easy testing.
    
    This strategy generates signals when price moves above or below configured thresholds.
    It's designed to trigger frequently for testing the strategy framework.
    
    Strategy Logic:
    - Buy when price moves above upper threshold
    - Sell when price moves below lower threshold
    - Exit positions when price returns to middle range
    - Uses percentage-based thresholds for easy configuration
    """
    
    def __init__(self, strategy_name: str, config: Dict[str, Any]):
        super().__init__(strategy_name, config)
        
        # Strategy parameters - designed to trigger easily
        params = self.trading_params
        self.upper_threshold_pct = params.get('upper_threshold_pct', 0.01)  # 1% above entry
        self.lower_threshold_pct = params.get('lower_threshold_pct', 0.01)  # 1% below entry
        self.exit_threshold_pct = params.get('exit_threshold_pct', 0.005)   # 0.5% for exits
        
        # Reference price tracking
        self.reference_prices: Dict[int, Decimal] = {}
        self.last_signal_prices: Dict[int, Decimal] = {}
        
        # Position sizing
        self.default_quantity = params.get('default_quantity', 5)
        self.max_position_per_instrument = params.get('max_position_per_instrument', 25)
        
        # Signal generation control
        self.signal_cooldown_seconds = params.get('signal_cooldown_seconds', 30)  # Short cooldown for testing
        self.last_signals: Dict[int, Dict[str, Any]] = {}
        
        # Minimum price movement to avoid noise
        self.min_price_movement = params.get('min_price_movement', 0.001)  # 0.1%
        
        self.logger.info(f"Price threshold strategy initialized: upper={self.upper_threshold_pct:.3f}%, "
                        f"lower={self.lower_threshold_pct:.3f}%, cooldown={self.signal_cooldown_seconds}s")
    
    async def initialize(self):
        """Initialize strategy-specific components."""
        self.logger.info("Initializing price threshold strategy...")
        
        # Initialize tracking for all instruments
        for instrument_token in self.instruments:
            self.reference_prices[instrument_token] = Decimal('0')
            self.last_signal_prices[instrument_token] = Decimal('0')
            self.last_signals[instrument_token] = {}
        
        self.logger.info("Price threshold strategy initialization completed")
    
    async def cleanup(self):
        """Cleanup strategy resources."""
        self.logger.info("Cleaning up price threshold strategy...")
        self.reference_prices.clear()
        self.last_signal_prices.clear()
        self.last_signals.clear()
    
    async def on_market_data(self, tick_data: Dict[str, Any]) -> Optional[TradingSignal]:
        """Process market data and generate threshold-based signals."""
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')
        
        if not last_price or not instrument_token:
            return None
        
        current_price = Decimal(str(last_price))
        
        # Initialize reference price if not set
        if self.reference_prices[instrument_token] == 0:
            self.reference_prices[instrument_token] = current_price
            self.logger.info(f"Set reference price for {instrument_token}: {current_price}")
            return None
        
        # Check signal cooldown
        if not self._can_generate_signal(instrument_token):
            return None
        
        # Generate signals based on price thresholds
        signal = self._evaluate_threshold_signals(
            instrument_token,
            current_price,
            tick_data
        )
        
        if signal:
            # Update last signal tracking
            self.last_signals[instrument_token] = {
                'timestamp': datetime.now(timezone.utc),
                'signal_type': signal.signal_type,
                'price': current_price
            }
            self.last_signal_prices[instrument_token] = current_price
            
            # Update reference price for next cycle
            if signal.signal_type in [SignalType.BUY, SignalType.SELL]:
                self.reference_prices[instrument_token] = current_price
                self.logger.info(f"Updated reference price for {instrument_token}: {current_price}")
        
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
    
    def _evaluate_threshold_signals(
        self,
        instrument_token: int,
        current_price: Decimal,
        tick_data: Dict[str, Any]
    ) -> Optional[TradingSignal]:
        """Evaluate threshold-based signal conditions."""
        
        reference_price = self.reference_prices[instrument_token]
        current_position = self.get_position(instrument_token)
        
        # Get instrument info
        instrument_info = self.instrument_info.get(instrument_token, {})
        tradingsymbol = instrument_info.get('tradingsymbol', str(instrument_token))
        exchange = instrument_info.get('exchange', 'NSE')
        
        # Calculate price change from reference
        price_change_pct = (current_price - reference_price) / reference_price
        
        # Check minimum movement threshold
        if abs(price_change_pct) < Decimal(str(self.min_price_movement)):
            return None
        
        # Calculate signal strength based on price movement magnitude
        abs_change = abs(price_change_pct)
        if abs_change >= Decimal(str(self.upper_threshold_pct * 2)):
            strength = SignalStrength.VERY_STRONG
            confidence = 0.9
        elif abs_change >= Decimal(str(self.upper_threshold_pct * 1.5)):
            strength = SignalStrength.STRONG
            confidence = 0.8
        elif abs_change >= Decimal(str(self.upper_threshold_pct)):
            strength = SignalStrength.MODERATE
            confidence = 0.7
        else:
            strength = SignalStrength.WEAK
            confidence = 0.6
        
        # Entry signal conditions
        buy_condition = (
            price_change_pct >= Decimal(str(self.upper_threshold_pct)) and
            current_position <= 0 and  # No long position or have short position
            current_position >= -self.max_position_per_instrument
        )
        
        sell_condition = (
            price_change_pct <= -Decimal(str(self.lower_threshold_pct)) and
            current_position >= 0 and  # No short position or have long position
            current_position <= self.max_position_per_instrument
        )
        
        # Exit conditions
        exit_long_condition = (
            current_position > 0 and
            price_change_pct <= -Decimal(str(self.exit_threshold_pct))
        )
        
        exit_short_condition = (
            current_position < 0 and
            price_change_pct >= Decimal(str(self.exit_threshold_pct))
        )
        
        # Generate appropriate signal
        if exit_long_condition or exit_short_condition:
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
                    confidence=confidence,
                    reason=f"Exit threshold: {price_change_pct:.3f}% from ref {reference_price}"
                )
        
        elif buy_condition:
            # Buy signal
            return create_buy_signal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                quantity=self.default_quantity,
                price=current_price,
                strength=strength,
                confidence=confidence,
                reason=f"Price up {price_change_pct:.3f}% from ref {reference_price}, above threshold {self.upper_threshold_pct:.3f}%"
            )
        
        elif sell_condition:
            # Sell signal
            return create_sell_signal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                quantity=self.default_quantity,
                price=current_price,
                strength=strength,
                confidence=confidence,
                reason=f"Price down {price_change_pct:.3f}% from ref {reference_price}, below threshold {self.lower_threshold_pct:.3f}%"
            )
        
        return None
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get strategy-specific information."""
        return {
            'strategy_type': 'Simple Price Threshold',
            'description': 'Generates signals on price threshold breaches for testing',
            'parameters': {
                'upper_threshold_pct': self.upper_threshold_pct,
                'lower_threshold_pct': self.lower_threshold_pct,
                'exit_threshold_pct': self.exit_threshold_pct,
                'default_quantity': self.default_quantity,
                'signal_cooldown_seconds': self.signal_cooldown_seconds,
                'min_price_movement': self.min_price_movement
            },
            'indicators_used': ['Price thresholds'],
            'signal_types': ['BUY', 'SELL', 'EXIT'],
            'timeframe': 'Tick-based with threshold monitoring',
            'testing_focused': True
        }
    
    def get_debug_info(self, instrument_token: int) -> Dict[str, Any]:
        """Get debug information for a specific instrument."""
        if instrument_token not in self.reference_prices:
            return {}
        
        reference_price = self.reference_prices[instrument_token]
        last_signal_price = self.last_signal_prices[instrument_token]
        
        # Get current price if available
        current_price = None
        latest_tick = self.get_latest_tick(instrument_token)
        if latest_tick:
            current_price = Decimal(str(latest_tick.get('last_price', 0)))
        
        price_change_pct = None
        if current_price and reference_price > 0:
            price_change_pct = float((current_price - reference_price) / reference_price * 100)
        
        return {
            'instrument_token': instrument_token,
            'current_price': float(current_price) if current_price else None,
            'reference_price': float(reference_price),
            'last_signal_price': float(last_signal_price),
            'price_change_pct': price_change_pct,
            'position': float(self.get_position(instrument_token)),
            'thresholds': {
                'upper_threshold_pct': self.upper_threshold_pct * 100,
                'lower_threshold_pct': self.lower_threshold_pct * 100,
                'exit_threshold_pct': self.exit_threshold_pct * 100
            },
            'last_signal': self.last_signals.get(instrument_token, {}),
            'can_generate_signal': self._can_generate_signal(instrument_token)
        }
    
    async def on_signal_executed(self, signal: TradingSignal, execution_result: Dict[str, Any]):
        """Handle signal execution feedback."""
        await super().on_signal_executed(signal, execution_result)
        
        # Log execution with threshold context
        self.logger.info(f"Threshold signal executed: {signal.signal_type.value} "
                        f"{execution_result.get('quantity', 0)} {signal.tradingsymbol} "
                        f"@ {execution_result.get('average_price', 0)} "
                        f"(reason: {signal.reason})")