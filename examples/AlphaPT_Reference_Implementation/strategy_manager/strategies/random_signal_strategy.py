"""Random signal strategy for testing signal generation and framework reliability."""

from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timezone
import random

from strategy_manager.base_strategy import BaseStrategy
from strategy_manager.signal_types import TradingSignal, SignalType, SignalStrength, create_buy_signal, create_sell_signal


class RandomSignalStrategy(BaseStrategy):
    """Random signal generation strategy for comprehensive testing.
    
    This strategy generates random signals based on configurable probability.
    It's designed specifically for testing the strategy framework, signal routing,
    and trading engine reliability.
    
    Strategy Logic:
    - Generate random BUY/SELL signals based on probability
    - Include random exits for position management
    - Configurable signal frequency and randomness
    - Useful for stress testing and framework validation
    """
    
    def __init__(self, strategy_name: str, config: Dict[str, Any]):
        super().__init__(strategy_name, config)
        
        # Strategy parameters - for testing
        params = self.trading_params
        self.signal_probability = params.get('signal_probability', 0.001)  # 0.1% chance per tick
        self.exit_probability = params.get('exit_probability', 0.01)  # 1% chance to exit per tick
        self.buy_sell_ratio = params.get('buy_sell_ratio', 0.5)  # 50% buy, 50% sell
        
        # Position sizing
        self.min_quantity = params.get('min_quantity', 1)
        self.max_quantity = params.get('max_quantity', 10)
        self.max_position_per_instrument = params.get('max_position_per_instrument', 50)
        
        # Signal generation control
        self.signal_cooldown_seconds = params.get('signal_cooldown_seconds', 10)  # Short cooldown
        self.last_signals: Dict[int, Dict[str, Any]] = {}
        
        # Randomness control
        self.random_seed = params.get('random_seed', None)
        if self.random_seed:
            random.seed(self.random_seed)
        
        # Statistics tracking
        self.signals_attempted = 0
        self.signals_generated = 0
        self.buy_signals_generated = 0
        self.sell_signals_generated = 0
        self.exit_signals_generated = 0
        
        self.logger.info(f"Random signal strategy initialized: signal_prob={self.signal_probability:.4f}, "
                        f"exit_prob={self.exit_probability:.4f}, buy_ratio={self.buy_sell_ratio}")
    
    async def initialize(self):
        """Initialize strategy-specific components."""
        self.logger.info("Initializing random signal strategy...")
        
        # Initialize tracking for all instruments
        for instrument_token in self.instruments:
            self.last_signals[instrument_token] = {}
        
        self.logger.info("Random signal strategy initialization completed")
    
    async def cleanup(self):
        """Cleanup strategy resources."""
        self.logger.info("Cleaning up random signal strategy...")
        self.last_signals.clear()
        
        # Log final statistics
        self.logger.info(f"Random strategy statistics - Attempted: {self.signals_attempted}, "
                        f"Generated: {self.signals_generated}, "
                        f"Buy: {self.buy_signals_generated}, "
                        f"Sell: {self.sell_signals_generated}, "
                        f"Exit: {self.exit_signals_generated}")
    
    async def on_market_data(self, tick_data: Dict[str, Any]) -> Optional[TradingSignal]:
        """Process market data and potentially generate random signals."""
        instrument_token = tick_data.get('instrument_token')
        last_price = tick_data.get('last_price')
        
        if not last_price or not instrument_token:
            return None
        
        current_price = Decimal(str(last_price))
        self.signals_attempted += 1
        
        # Check signal cooldown
        if not self._can_generate_signal(instrument_token):
            return None
        
        # Check for exit signal first (if we have a position)
        current_position = self.get_position(instrument_token)
        if current_position != 0:
            if random.random() < self.exit_probability:
                signal = self._generate_exit_signal(instrument_token, current_price, tick_data)
                if signal:
                    self._update_signal_tracking(instrument_token, signal)
                return signal
        
        # Check for entry signal
        if random.random() < self.signal_probability:
            signal = self._generate_entry_signal(instrument_token, current_price, tick_data)
            if signal:
                self._update_signal_tracking(instrument_token, signal)
            return signal
        
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
    
    def _generate_entry_signal(
        self,
        instrument_token: int,
        current_price: Decimal,
        tick_data: Dict[str, Any]
    ) -> Optional[TradingSignal]:
        """Generate random entry signal."""
        
        current_position = self.get_position(instrument_token)
        
        # Get instrument info
        instrument_info = self.instrument_info.get(instrument_token, {})
        tradingsymbol = instrument_info.get('tradingsymbol', str(instrument_token))
        exchange = instrument_info.get('exchange', 'NSE')
        
        # Random quantity
        quantity = random.randint(self.min_quantity, self.max_quantity)
        
        # Random signal strength and confidence
        strengths = list(SignalStrength)
        strength = random.choice(strengths)
        confidence = random.uniform(0.5, 0.95)
        
        # Decide buy or sell based on ratio and position limits
        is_buy = random.random() < self.buy_sell_ratio
        
        # Check position limits
        if is_buy and current_position >= self.max_position_per_instrument:
            return None  # Can't buy more
        
        if not is_buy and current_position <= -self.max_position_per_instrument:
            return None  # Can't sell more
        
        # Generate signal
        if is_buy:
            self.buy_signals_generated += 1
            self.signals_generated += 1
            return create_buy_signal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                quantity=quantity,
                price=current_price,
                strength=strength,
                confidence=confidence,
                reason=f"Random buy signal (prob: {self.signal_probability:.4f})"
            )
        else:
            self.sell_signals_generated += 1
            self.signals_generated += 1
            return create_sell_signal(
                strategy_name=self.strategy_name,
                instrument_token=instrument_token,
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                quantity=quantity,
                price=current_price,
                strength=strength,
                confidence=confidence,
                reason=f"Random sell signal (prob: {self.signal_probability:.4f})"
            )
    
    def _generate_exit_signal(
        self,
        instrument_token: int,
        current_price: Decimal,
        tick_data: Dict[str, Any]
    ) -> Optional[TradingSignal]:
        """Generate random exit signal."""
        
        current_position = self.get_position(instrument_token)
        
        if current_position == 0:
            return None
        
        # Get instrument info
        instrument_info = self.instrument_info.get(instrument_token, {})
        tradingsymbol = instrument_info.get('tradingsymbol', str(instrument_token))
        exchange = instrument_info.get('exchange', 'NSE')
        
        # Exit full position
        quantity = abs(int(current_position))
        
        # Random signal strength and confidence
        strengths = list(SignalStrength)
        strength = random.choice(strengths)
        confidence = random.uniform(0.6, 0.9)
        
        self.exit_signals_generated += 1
        self.signals_generated += 1
        
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
            reason=f"Random exit signal (prob: {self.exit_probability:.4f})"
        )
    
    def _update_signal_tracking(self, instrument_token: int, signal: TradingSignal):
        """Update signal tracking information."""
        self.last_signals[instrument_token] = {
            'timestamp': datetime.now(timezone.utc),
            'signal_type': signal.signal_type,
            'price': signal.price,
            'quantity': signal.quantity
        }
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get strategy-specific information."""
        return {
            'strategy_type': 'Random Signal',
            'description': 'Generates random signals for testing framework reliability',
            'parameters': {
                'signal_probability': self.signal_probability,
                'exit_probability': self.exit_probability,
                'buy_sell_ratio': self.buy_sell_ratio,
                'min_quantity': self.min_quantity,
                'max_quantity': self.max_quantity,
                'signal_cooldown_seconds': self.signal_cooldown_seconds,
                'random_seed': self.random_seed
            },
            'indicators_used': ['Random probability'],
            'signal_types': ['BUY', 'SELL', 'EXIT'],
            'timeframe': 'Tick-based with random generation',
            'testing_focused': True,
            'statistics': {
                'signals_attempted': self.signals_attempted,
                'signals_generated': self.signals_generated,
                'buy_signals': self.buy_signals_generated,
                'sell_signals': self.sell_signals_generated,
                'exit_signals': self.exit_signals_generated
            }
        }
    
    def get_debug_info(self, instrument_token: int) -> Dict[str, Any]:
        """Get debug information for a specific instrument."""
        if instrument_token not in self.last_signals:
            return {}
        
        current_position = self.get_position(instrument_token)
        
        # Calculate probabilities for next signal
        next_signal_prob = self.signal_probability
        next_exit_prob = self.exit_probability if current_position != 0 else 0
        
        return {
            'instrument_token': instrument_token,
            'position': float(current_position),
            'probabilities': {
                'signal_probability': self.signal_probability,
                'exit_probability': self.exit_probability,
                'next_signal_prob': next_signal_prob,
                'next_exit_prob': next_exit_prob
            },
            'statistics': {
                'signals_attempted': self.signals_attempted,
                'signals_generated': self.signals_generated,
                'generation_rate': self.signals_generated / max(self.signals_attempted, 1)
            },
            'last_signal': self.last_signals.get(instrument_token, {}),
            'can_generate_signal': self._can_generate_signal(instrument_token)
        }
    
    async def on_signal_executed(self, signal: TradingSignal, execution_result: Dict[str, Any]):
        """Handle signal execution feedback."""
        await super().on_signal_executed(signal, execution_result)
        
        # Log execution
        self.logger.info(f"Random signal executed: {signal.signal_type.value} "
                        f"{execution_result.get('quantity', 0)} {signal.tradingsymbol} "
                        f"@ {execution_result.get('average_price', 0)} "
                        f"(confidence: {signal.confidence:.2f})")