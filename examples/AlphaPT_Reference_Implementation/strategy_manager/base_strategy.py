"""Base strategy class for AlphaPT strategy framework."""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging

from .signal_types import TradingSignal, SignalType, SignalStrength
from core.logging.logger import get_logger


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies in AlphaPT.
    
    This class provides the foundational framework for strategy development,
    including lifecycle management, instrument handling, position tracking,
    and integration with the broader AlphaPT ecosystem.
    
    Key Features:
    - Event-driven market data processing
    - Integrated position and portfolio tracking
    - Risk-aware signal generation
    - Performance monitoring and analytics
    - Configuration-driven setup
    - Error handling and recovery
    """
    
    def __init__(self, strategy_name: str, config: Dict[str, Any]):
        """Initialize base strategy.
        
        Args:
            strategy_name: Unique identifier for this strategy instance
            config: Strategy configuration dictionary
        """
        self.strategy_name = strategy_name
        self.config = config
        self.logger = get_logger(f"strategy.{strategy_name}", "strategy")
        
        # Strategy state
        self.is_active = False
        self.is_initialized = False
        self.last_error = None
        self.error_count = 0
        
        # Instruments and market data
        self.instruments: Set[int] = set()
        self.instrument_info: Dict[int, Dict[str, Any]] = {}
        self.latest_ticks: Dict[int, Dict[str, Any]] = {}
        
        # Position and portfolio tracking
        self.positions: Dict[int, Decimal] = {}  # instrument_token -> quantity
        self.entry_prices: Dict[int, Decimal] = {}  # instrument_token -> avg_price
        self.unrealized_pnl: Dict[int, Decimal] = {}  # instrument_token -> pnl
        self.realized_pnl: Decimal = Decimal('0')
        
        # Signal tracking
        self.signals_generated = 0
        self.signals_executed = 0
        self.last_signal_time: Optional[datetime] = None
        
        # Performance metrics
        self.start_time = datetime.now(timezone.utc)
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.max_drawdown = Decimal('0')
        self.peak_portfolio_value = Decimal('0')
        
        # Strategy-specific parameters
        self.trading_params = config.get('parameters', {})
        self.risk_params = config.get('risk', {})
        self.routing_config = config.get('routing', {})
        
        # Load instruments from config
        self._load_instruments()
        
        self.logger.info(f"Strategy {strategy_name} initialized with {len(self.instruments)} instruments")
    
    def _load_instruments(self):
        """Load instruments from configuration."""
        instrument_configs = self.config.get('instruments', [])
        
        for instrument_config in instrument_configs:
            if isinstance(instrument_config, dict):
                token = instrument_config.get('instrument_token')
                if token:
                    self.instruments.add(token)
                    self.instrument_info[token] = instrument_config
            elif isinstance(instrument_config, (int, str)):
                token = int(instrument_config)
                self.instruments.add(token)
                self.instrument_info[token] = {'instrument_token': token}
        
        # Initialize positions for all instruments
        for token in self.instruments:
            self.positions[token] = Decimal('0')
            self.unrealized_pnl[token] = Decimal('0')
    
    async def start(self) -> bool:
        """Start the strategy.
        
        Returns:
            bool: True if strategy started successfully, False otherwise
        """
        try:
            self.logger.info(f"Starting strategy {self.strategy_name}...")
            
            # Validate configuration
            if not self._validate_config():
                self.logger.error("Strategy configuration validation failed")
                return False
            
            # Initialize strategy-specific components
            await self.initialize()
            
            self.is_active = True
            self.is_initialized = True
            
            self.logger.info(f"Strategy {self.strategy_name} started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start strategy {self.strategy_name}: {e}")
            self.last_error = str(e)
            self.error_count += 1
            return False
    
    async def stop(self):
        """Stop the strategy."""
        try:
            self.logger.info(f"Stopping strategy {self.strategy_name}...")
            
            self.is_active = False
            
            # Cleanup strategy-specific resources
            await self.cleanup()
            
            self.logger.info(f"Strategy {self.strategy_name} stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping strategy {self.strategy_name}: {e}")
            self.last_error = str(e)
            self.error_count += 1
    
    def _validate_config(self) -> bool:
        """Validate strategy configuration.
        
        Returns:
            bool: True if configuration is valid
        """
        # Check required fields
        if not self.instruments:
            self.logger.error("No instruments configured for strategy")
            return False
        
        # Validate routing configuration
        routing = self.routing_config
        if not routing.get('paper_trade', False) and not routing.get('live_trade', False):
            self.logger.error("No trading routes configured (paper_trade or live_trade)")
            return False
        
        return True
    
    def should_process_instrument(self, instrument_token: int) -> bool:
        """Check if strategy should process data for given instrument.
        
        Args:
            instrument_token: Instrument token to check
            
        Returns:
            bool: True if strategy trades this instrument
        """
        return instrument_token in self.instruments
    
    async def process_market_data(self, tick_data: Dict[str, Any]) -> Optional[TradingSignal]:
        """Process incoming market data and generate trading signals.
        
        This is the main entry point for market data processing. It updates
        internal state and calls the strategy-specific logic.
        
        Args:
            tick_data: Market tick data dictionary
            
        Returns:
            Optional[TradingSignal]: Trading signal if generated, None otherwise
        """
        try:
            if not self.is_active:
                return None
            
            instrument_token = tick_data.get('instrument_token')
            if not instrument_token or not self.should_process_instrument(instrument_token):
                return None
            
            # Update latest tick data
            self.latest_ticks[instrument_token] = tick_data
            
            # Update unrealized P&L
            self._update_unrealized_pnl(instrument_token, tick_data)
            
            # Call strategy-specific processing
            signal = await self.on_market_data(tick_data)
            
            # Post-process signal if generated
            if signal:
                signal = self._post_process_signal(signal)
                self.signals_generated += 1
                self.last_signal_time = datetime.now(timezone.utc)
                
                self.logger.info(f"Signal generated: {signal}")
            
            return signal
            
        except Exception as e:
            self.logger.error(f"Error processing market data: {e}")
            self.last_error = str(e)
            self.error_count += 1
            return None
    
    def _update_unrealized_pnl(self, instrument_token: int, tick_data: Dict[str, Any]):
        """Update unrealized P&L for instrument."""
        current_price = tick_data.get('last_price')
        if not current_price or instrument_token not in self.positions:
            return
        
        position = self.positions[instrument_token]
        if position == 0:
            self.unrealized_pnl[instrument_token] = Decimal('0')
            return
        
        entry_price = self.entry_prices.get(instrument_token, Decimal('0'))
        if entry_price == 0:
            return
        
        current_price = Decimal(str(current_price))
        price_diff = current_price - entry_price
        pnl = price_diff * position
        
        self.unrealized_pnl[instrument_token] = pnl
    
    def _post_process_signal(self, signal: TradingSignal) -> TradingSignal:
        """Post-process generated signal with strategy configuration."""
        # NOTE: Routing is now handled at the strategy manager level:
        # - Paper trading receives ALL signals by default (if enabled)
        # - Zerodha trading only receives signals from strategies with zerodha_trade=true
        
        # Apply risk parameters
        if 'max_position_size' in self.risk_params:
            max_size = self.risk_params['max_position_size']
            if signal.quantity > max_size:
                signal.quantity = max_size
                signal.add_tag('size_limited', True)
        
        # Set strategy metadata
        signal.strategy_version = self.config.get('version', '1.0')
        signal.add_tag('strategy_type', self.__class__.__name__)
        
        # Add routing configuration for debugging/monitoring
        signal.add_tag('routing_config', self.routing_config)
        
        return signal
    
    def update_position(self, instrument_token: int, quantity_change: Decimal, price: Decimal):
        """Update position for instrument.
        
        Args:
            instrument_token: Instrument to update
            quantity_change: Change in quantity (positive for buy, negative for sell)
            price: Execution price
        """
        current_position = self.positions.get(instrument_token, Decimal('0'))
        new_position = current_position + quantity_change
        
        # Update position
        self.positions[instrument_token] = new_position
        
        # Update entry price (weighted average)
        if new_position != 0:
            current_entry = self.entry_prices.get(instrument_token, Decimal('0'))
            current_value = current_position * current_entry
            new_value = quantity_change * price
            total_value = current_value + new_value
            
            if new_position != 0:
                self.entry_prices[instrument_token] = total_value / new_position
        else:
            # Position closed
            self.entry_prices[instrument_token] = Decimal('0')
            
            # Realize P&L
            realized = self.unrealized_pnl.get(instrument_token, Decimal('0'))
            self.realized_pnl += realized
            self.unrealized_pnl[instrument_token] = Decimal('0')
            
            # Update trade statistics
            self.total_trades += 1
            if realized > 0:
                self.winning_trades += 1
            elif realized < 0:
                self.losing_trades += 1
        
        self.logger.debug(f"Position updated: {instrument_token} -> {new_position} @ {price}")
    
    def get_position(self, instrument_token: int) -> Decimal:
        """Get current position for instrument."""
        return self.positions.get(instrument_token, Decimal('0'))
    
    def get_total_portfolio_value(self) -> Decimal:
        """Calculate total portfolio value including unrealized P&L."""
        total = self.realized_pnl
        for pnl in self.unrealized_pnl.values():
            total += pnl
        return total
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        portfolio_value = self.get_total_portfolio_value()
        
        # Update peak and drawdown
        if portfolio_value > self.peak_portfolio_value:
            self.peak_portfolio_value = portfolio_value
        
        current_drawdown = Decimal('0')
        if self.peak_portfolio_value > 0:
            current_drawdown = (self.peak_portfolio_value - portfolio_value) / self.peak_portfolio_value
            if current_drawdown > self.max_drawdown:
                self.max_drawdown = current_drawdown
        
        # Calculate win rate
        win_rate = 0.0
        if self.total_trades > 0:
            win_rate = self.winning_trades / self.total_trades
        
        # Calculate uptime
        uptime = datetime.now(timezone.utc) - self.start_time
        
        return {
            'strategy_name': self.strategy_name,
            'is_active': self.is_active,
            'uptime_seconds': uptime.total_seconds(),
            'total_portfolio_value': float(portfolio_value),
            'realized_pnl': float(self.realized_pnl),
            'unrealized_pnl': float(sum(self.unrealized_pnl.values())),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'max_drawdown': float(self.max_drawdown),
            'signals_generated': self.signals_generated,
            'signals_executed': self.signals_executed,
            'error_count': self.error_count,
            'last_signal_time': self.last_signal_time.isoformat() if self.last_signal_time else None,
            'instruments_count': len(self.instruments),
            'active_positions': len([p for p in self.positions.values() if p != 0])
        }
    
    def get_instruments(self) -> List[int]:
        """Get list of instruments traded by this strategy."""
        return list(self.instruments)
    
    def get_routing_config(self) -> Dict[str, Any]:
        """Get routing configuration for this strategy."""
        return self.routing_config.copy()
    
    def get_latest_tick(self, instrument_token: int) -> Optional[Dict[str, Any]]:
        """Get latest tick data for instrument."""
        return self.latest_ticks.get(instrument_token)
    
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours.
        
        This is a basic implementation. Override for more sophisticated
        market hours checking.
        """
        now = datetime.now(timezone.utc)
        # Basic check for weekdays only
        return now.weekday() < 5
    
    # Abstract methods that must be implemented by concrete strategies
    
    @abstractmethod
    async def initialize(self):
        """Initialize strategy-specific components.
        
        This method is called during strategy startup and should handle
        any strategy-specific initialization like loading historical data,
        setting up indicators, etc.
        """
        pass
    
    @abstractmethod
    async def on_market_data(self, tick_data: Dict[str, Any]) -> Optional[TradingSignal]:
        """Process market data and generate trading signals.
        
        This is the core strategy logic that processes incoming market data
        and decides whether to generate trading signals.
        
        Args:
            tick_data: Market tick data dictionary
            
        Returns:
            Optional[TradingSignal]: Trading signal if conditions are met
        """
        pass
    
    @abstractmethod
    async def cleanup(self):
        """Cleanup strategy-specific resources.
        
        This method is called during strategy shutdown and should handle
        cleanup of any strategy-specific resources.
        """
        pass
    
    # Optional methods that can be overridden by strategies
    
    async def on_signal_executed(self, signal: TradingSignal, execution_result: Dict[str, Any]):
        """Called when a signal is executed.
        
        Args:
            signal: The executed signal
            execution_result: Execution details
        """
        self.signals_executed += 1
        
        # Update position if execution was successful
        if execution_result.get('status') == 'executed':
            quantity = Decimal(str(execution_result.get('quantity', 0)))
            price = Decimal(str(execution_result.get('average_price', 0)))
            
            if signal.is_buy_signal():
                self.update_position(signal.instrument_token, quantity, price)
            elif signal.is_sell_signal():
                self.update_position(signal.instrument_token, -quantity, price)
    
    async def on_error(self, error: Exception, context: str = ""):
        """Called when an error occurs.
        
        Args:
            error: The error that occurred
            context: Additional context about the error
        """
        self.logger.error(f"Strategy error in {context}: {error}")
        self.last_error = str(error)
        self.error_count += 1
    
    async def on_position_update(self, instrument_token: int, new_position: Decimal):
        """Called when position is updated externally.
        
        Args:
            instrument_token: Instrument token
            new_position: New position quantity
        """
        old_position = self.positions.get(instrument_token, Decimal('0'))
        self.positions[instrument_token] = new_position
        
        self.logger.info(f"Position updated externally: {instrument_token} "
                        f"{old_position} -> {new_position}")
    
    def __str__(self) -> str:
        """String representation of the strategy."""
        return f"{self.__class__.__name__}({self.strategy_name})"
    
    def __repr__(self) -> str:
        """Detailed representation of the strategy."""
        return (f"{self.__class__.__name__}(name={self.strategy_name}, "
                f"instruments={len(self.instruments)}, active={self.is_active})")


class TechnicalIndicatorMixin:
    """Mixin class providing common technical indicators for strategies."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.price_history: Dict[int, List[Decimal]] = {}
        self.volume_history: Dict[int, List[int]] = {}
    
    def update_price_history(self, instrument_token: int, price: Decimal, max_length: int = 200):
        """Update price history for technical analysis."""
        if instrument_token not in self.price_history:
            self.price_history[instrument_token] = []
        
        self.price_history[instrument_token].append(price)
        
        # Keep only recent history
        if len(self.price_history[instrument_token]) > max_length:
            self.price_history[instrument_token] = self.price_history[instrument_token][-max_length:]
    
    def get_sma(self, instrument_token: int, period: int) -> Optional[Decimal]:
        """Calculate Simple Moving Average."""
        prices = self.price_history.get(instrument_token, [])
        if len(prices) < period:
            return None
        
        recent_prices = prices[-period:]
        return sum(recent_prices) / Decimal(period)
    
    def get_ema(self, instrument_token: int, period: int) -> Optional[Decimal]:
        """Calculate Exponential Moving Average."""
        prices = self.price_history.get(instrument_token, [])
        if len(prices) < period:
            return None
        
        multiplier = Decimal(2) / (Decimal(period) + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return ema
    
    def get_rsi(self, instrument_token: int, period: int = 14) -> Optional[Decimal]:
        """Calculate Relative Strength Index."""
        prices = self.price_history.get(instrument_token, [])
        if len(prices) < period + 1:
            return None
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(Decimal('0'))
            else:
                gains.append(Decimal('0'))
                losses.append(abs(change))
        
        if len(gains) < period:
            return None
        
        avg_gain = sum(gains[-period:]) / Decimal(period)
        avg_loss = sum(losses[-period:]) / Decimal(period)
        
        if avg_loss == 0:
            return Decimal('100')
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi